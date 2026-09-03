"""Export one PR's durable state as a self-contained offline evidence package.

Reconstructing a hero journey without the production VM needs the
workflow authority (canonical History), the agent bodies and full
session transcripts that produced its effects, the webhook rows that
drove it together with the raw GitHub delivery records behind them, and
every board the PR page ever showed. This module copies exactly those
out of a local state-directory copy, joins the agent bodies on the
``pi:`` operation id, and NAMES every piece the state directory does not
hold instead of dropping it: a package that silently omits evidence is
worse than no package.

The state directory keeps only the DERIVED observation of a webhook, so
the raw delivery records arrive from outside it through
``--webhook-deliveries``; the exporter admits a raw record only when the
PR's own inbox claims its delivery id, and names every record it left
behind.

Nothing here reads credential material. Only the named durable stores
below are opened, and each is copied to a scratch directory before it is
queried so the source copy is never written to.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hamsterdan.readiness.net_v5.board import render_board

HISTORY_SCHEMA = 5
PACKAGE_SCHEMA = 1

# Names the exporter refuses to copy even if a caller points --identity
# at them. The package is shared; credential material never travels.
CREDENTIAL_NAMES = frozenset({".env", "env", "hamsterdan.env", "installations.json"})
CREDENTIAL_SUFFIXES = frozenset({".pem", ".key", ".crt", ".p12"})
CREDENTIAL_MARKERS = ("secret", "token", "credential", "private-key", "privatekey", "apikey", "api-key")

# The state directory has never held a run-identity artifact; the image
# sha, petrus pin, and runtime identity are captured beside it. Their
# absence is a reported gap, not a silent one.
IDENTITY_STATE_FILES = ("image.txt", "image-identity.txt", "runtime-identity.txt", "pins.md", "petrus-pin.txt")

_OPERATION_ID = re.compile(r"\A[A-Za-z0-9:._-]{1,256}\Z")

# GitHub names a saved delivery record after its delivery guid and the
# event that carried it. The label is kept whole so a redelivered guid
# (same delivery id, two files) travels as two records, not one.
_DELIVERY_FILE = re.compile(
    r"\A(?P<delivery>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})-(?P<label>.+)\.json\Z",
    re.IGNORECASE,
)

# Terminal record kinds that settle one Activity occurrence.
_TERMINAL_RECORDS = frozenset({"ActivityCompleted", "ActivityFailed", "ActivityTerminalQuarantined"})

# The review gate defers a round when the readiness preconditions are
# not met yet. The agent turn is cancelled at once, so a deferred round
# legitimately has no session transcript and often no body at all.
AGENT_DEFERRAL_VARIANTS = frozenset({"RoundDeferred"})

_INDEX_FIELDS: Mapping[str, tuple[str, ...]] = {
    "InstanceCreated": ("instance", "name"),
    "TokensInitialized": ("place",),
    "DeliveryRegistrationOpened": ("source", "key"),
    "ExternalEventDelivered": ("source", "identity"),
    "CandidateSelected": ("transition",),
    "FiringBegun": ("transition",),
    "FiringCompleted": ("transition",),
    "TokensConsumed": ("place",),
    "TokensProduced": ("place",),
    "ActivityRequested": ("transition", "activity", "correlation"),
    "ActivityCompleted": ("transition",),
    "ActivityFailed": ("transition", "reason"),
    "ActivityTerminalQuarantined": ("transition", "reason"),
}

_INBOX_COLUMNS = ("delivery_id", "event", "observation", "status", "attempts", "reason", "error_class")
_BODY_COLUMNS = (
    "operation_id",
    "output_reference",
    "output_text",
    "continuation_reference",
    "session_id",
    "working_binding",
    "workspace_digest",
    "aggregate_verified",
)
_PI_OPERATION_COLUMNS = (
    "operation_id",
    "fingerprint",
    "episode_id",
    "turn_id",
    "phase",
    "outcome",
    "accepted_appends",
    "termination_code",
    "output_reference",
    "continuation_reference",
    "cleanup",
    "cleanup_code",
    "acknowledged",
)


class EvidenceExportError(RuntimeError):
    """The evidence package cannot be built from the given state directory."""


def agent_operation_id(operation: str, attempt: int) -> str:
    """The bodies.sqlite3 key for one logical agent operation attempt.

    This is the ONLY join between canonical History and the agent
    session bodies, and it is duplicated from
    ``hamsterdan.agents.pi.PiNativeRunner`` on purpose: the exporter
    must reproduce the key from archived data without composing a
    runner.
    """
    return f"pi:{hashlib.sha256(f'{operation}\0{attempt}'.encode()).hexdigest()}"


@dataclass
class Report:
    """What the package holds, and what the state directory did not."""

    numbers: dict[str, Any] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)

    def gap(self, message: str) -> None:
        self.gaps.append(message)


@dataclass(frozen=True)
class Instance:
    """One PR's durable Instance directory and its binding identity."""

    directory: Path
    installation_id: int
    repository_id: int
    pull_request: int
    instance_id: str
    repository: str
    topology: str


@dataclass(frozen=True)
class Operation:
    """One agent operation attempt, before its body is looked up.

    One attempt can be requested by MORE than one History record — a
    mutation gate that reconciles lookup-first is requested again under
    the same op_key and reuses the same agent turn — so the occurrences
    and their inputs are plural while the body key stays singular.
    """

    operation_id: str
    logical_operation: str
    attempt: int
    kind: str
    origin: str
    history_occurrences: tuple[int, ...]
    history_inputs: tuple[object, ...]


@dataclass(frozen=True)
class RawDelivery:
    """One saved GitHub webhook delivery record, keyed by its delivery id."""

    path: Path
    delivery_id: str
    label: str


def _connect(path: Path, scratch: Path) -> sqlite3.Connection:
    """Query a copy so a WAL rollforward can never touch the source."""
    target = scratch / path.name
    shutil.copyfile(path, target)
    for sidecar in ("-wal", "-shm"):
        companion = path.with_name(path.name + sidecar)
        if companion.exists():
            shutil.copyfile(companion, target.with_name(target.name + sidecar))
    return sqlite3.connect(target)


def _rows(connection: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    cursor = connection.execute(query)
    names = tuple(column[0] for column in cursor.description)
    return [dict(zip(names, values, strict=True)) for values in cursor.fetchall()]


def find_instance(state_dir: Path, repository: str, pull_request: int) -> Instance:
    """Select the one Instance directory whose binding matches the PR."""
    matches: list[Instance] = []
    for binding_path in sorted(state_dir.glob(f"applications/*/*/{pull_request}/binding.json")):
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        if binding.get("repository", "").lower() != repository.lower():
            continue
        if binding.get("pull_request") != pull_request:
            raise EvidenceExportError(f"binding {binding_path} disagrees with its own path")
        directory = binding_path.parent
        matches.append(
            Instance(
                directory=directory,
                installation_id=int(directory.parts[-3]),
                repository_id=int(directory.parts[-2]),
                pull_request=pull_request,
                instance_id=str(binding["instance_id"]),
                repository=str(binding["repository"]),
                topology=str(binding.get("topology", "")),
            )
        )
    if len(matches) != 1:
        raise EvidenceExportError(
            f"state directory holds {len(matches)} Instances for {repository} PR {pull_request}; expected exactly one"
        )
    return matches[0]


def read_history(path: Path) -> list[dict[str, Any]]:
    """Canonical History in file order; the line number is the record seq."""
    records: list[dict[str, Any]] = []
    for seq, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            raise EvidenceExportError(f"History record {seq} is not JSON") from None
        if not isinstance(record, dict) or "record" not in record:
            raise EvidenceExportError(f"History record {seq} has no record kind")
        records.append(record)
    return records


def _index_line(seq: int, record: Mapping[str, Any], report: Report) -> str:
    kind = str(record["record"])
    fields = _INDEX_FIELDS.get(kind)
    if fields is None:
        report.gap(f"history index has no field vocabulary for record kind {kind!r} (record {seq})")
        fields = tuple(sorted(set(record) - {"record", "schema", "instant", "occurrence"}))
    parts = [f"occurrence={record['occurrence']}"] if "occurrence" in record else []
    parts.extend(f"{name}={record[name]!s}" for name in fields if record.get(name) is not None)
    tokens = record.get("tokens")
    if isinstance(tokens, list):
        parts.append("tokens=" + ",".join(str(token.get("color")) for token in tokens if isinstance(token, dict)))
    result = record.get("result")
    if isinstance(result, dict) and "$variant" in result:
        parts.append(f"result={result['$variant']}")
    return f"{seq:>5}  {kind:<30} {' '.join(parts)}"


def history_index(records: Sequence[Mapping[str, Any]], report: Report) -> str:
    header = (
        "# History index\n\n"
        "One line per record of `history.jsonl`, in file order. `seq` is the\n"
        "1-based line number in that file — open the raw line to see the full\n"
        "record. `occurrence` correlates an Activity request with its terminal\n"
        "and with the firing that produced it.\n\n"
        "```\n  seq  kind                           fields\n"
    )
    lines = (_index_line(seq, record, report) for seq, record in enumerate(records, start=1))
    return header + "\n".join(lines) + "\n```\n"


def board_documents(records: Sequence[Mapping[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    """Every landed dashboard publication, paired with its History seq."""
    landed = []
    for seq, record in enumerate(records, start=1):
        result = record.get("result")
        if (
            record["record"] == "ActivityCompleted"
            and isinstance(result, dict)
            and result.get("$variant") == "DashLanded"
        ):
            landed.append((seq, result))
    return landed


def history_terminals(records: Sequence[Mapping[str, Any]]) -> dict[int, tuple[str, ...]]:
    """Every Activity terminal variant, keyed by the occurrence it settles.

    An operation with no session transcript is only half-explained by the
    agent runtime. History says WHY the turn ended: a deferred round is a
    settled outcome, an unnamed one is a gap.
    """
    terminals: dict[int, tuple[str, ...]] = {}
    for record in records:
        if record["record"] not in _TERMINAL_RECORDS or "occurrence" not in record:
            continue
        result = record.get("result")
        variant = result.get("$variant") if isinstance(result, dict) else None
        name = str(variant or record.get("reason") or record["record"])
        occurrence = int(record["occurrence"])
        terminals[occurrence] = (*terminals.get(occurrence, ()), name)
    return terminals


def history_operations(records: Sequence[Mapping[str, Any]], instance: Instance) -> list[Operation]:
    """Every agent operation attempt canonical History itself requests."""
    operations: dict[str, Operation] = {}
    for record in records:
        if record["record"] != "ActivityRequested":
            continue
        payload = record.get("input")
        work = payload.get("work") if isinstance(payload, dict) else None
        if not isinstance(work, dict):
            continue
        if record.get("activity") == "review_agent":
            logical, attempt, kind = str(work["operation"]), int(work["attempt"]), "review"
        elif record.get("activity") == "git_gate":
            # The mutation agent runs once per op_key; the net's own
            # `attempt` counts fenced pushes, not agent turns.
            logical = f"mutation:{instance.repository}:pr:{instance.pull_request}:{work['op_key']}"
            attempt, kind = 1, "mutation"
        else:
            continue
        operation_id = agent_operation_id(logical, attempt)
        seen = operations.get(operation_id)
        occurrence = int(record["occurrence"])
        operations[operation_id] = Operation(
            operation_id=operation_id,
            logical_operation=logical,
            attempt=attempt,
            kind=kind,
            origin="history",
            history_occurrences=(*(seen.history_occurrences if seen else ()), occurrence),
            history_inputs=(*(seen.history_inputs if seen else ()), payload),
        )
    return list(operations.values())


def routed_operations(routes: Sequence[Mapping[str, Any]], known: Sequence[Operation]) -> list[Operation]:
    """Agent operations routed outside the net, chiefly conversation.

    Comment classification runs BEFORE the ingress manifest stages, so
    its operations never reach canonical History. `agent-routes.sqlite3`
    is the only durable record that they were dispatched at all.
    """
    logical_known = {operation.logical_operation for operation in known}
    operations = []
    for row in routes:
        logical = str(row["operation"])
        if logical in logical_known:
            continue
        operations.append(
            Operation(
                operation_id=agent_operation_id(logical, 1),
                logical_operation=logical,
                attempt=1,
                kind=logical.partition(":")[0],
                origin="agent-routes",
                history_occurrences=(),
                history_inputs=(),
            )
        )
    return operations


def _transcript_stem(operation_id: str) -> str:
    if not _OPERATION_ID.fullmatch(operation_id):
        raise EvidenceExportError(f"agent operation id {operation_id!r} is malformed")
    return operation_id.replace(":", "-")


def session_coverage(
    operation: Operation,
    body: Mapping[str, Any] | None,
    session: bytes | None,
    pi_operation: Mapping[str, Any] | None,
    terminals: Mapping[int, tuple[str, ...]],
) -> tuple[str, str]:
    """How much of one operation survived, and why no more than that.

    The session transcript lives in the ``session_jsonl`` column of
    ``pi_a2_bodies`` and NOWHERE else, so a body without a session is a
    turn that produced no transcript rather than a transcript the
    exporter failed to find. Naming which of the two happened is the
    whole point: an unclassified absence reads like data loss.
    """
    variants = tuple(
        dict.fromkeys(name for occurrence in operation.history_occurrences for name in terminals.get(occurrence, ()))
    )
    settled = f"History terminal {'/'.join(variants)}" if variants else "no History terminal"
    if session:
        return "session_exported", ""
    if body is not None:
        outcome = str((pi_operation or {}).get("outcome") or "")
        if outcome != "cancelled":
            return "body_without_session", f"the agent runtime records outcome {outcome or 'unknown'} ({settled})"
        return "body_without_session", (
            "the agent turn was cancelled before any transcript line was appended"
            f" (termination {(pi_operation or {}).get('termination_code')},"
            f" accepted_appends {(pi_operation or {}).get('accepted_appends')}; {settled})"
        )
    if variants and set(variants) <= AGENT_DEFERRAL_VARIANTS:
        return "no_body_no_session", f"the round was deferred before the agent runtime stored a body ({settled})"
    return "no_body_no_session", f"the agent runtime stored nothing and History does not say why ({settled})"


def _write_transcripts(
    out: Path,
    operations: Sequence[Operation],
    bodies: Mapping[str, Mapping[str, Any]],
    sessions: Mapping[str, bytes | None],
    pi_operations: Mapping[str, Mapping[str, Any]],
    review_requests: Mapping[tuple[str, int], Mapping[str, Any]],
    terminals: Mapping[int, tuple[str, ...]],
    report: Report,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, Any]] = []
    joined = 0
    session_bytes = 0
    classes: dict[str, int] = {"session_exported": 0, "body_without_session": 0, "no_body_no_session": 0}
    for operation in operations:
        stem = _transcript_stem(operation.operation_id)
        body = bodies.get(operation.operation_id)
        session = sessions.get(operation.operation_id)
        pi_operation = pi_operations.get(operation.operation_id)
        coverage, reason = session_coverage(operation, body, session, pi_operation, terminals)
        classes[coverage] += 1
        session_name = None
        if session:
            session_name = f"{stem}.session.jsonl"
            (out / session_name).write_bytes(session)
            session_bytes += len(session)
        request = review_requests.get((operation.logical_operation, operation.attempt))
        document = {
            "operation_id": operation.operation_id,
            "logical_operation": operation.logical_operation,
            "attempt": operation.attempt,
            "kind": operation.kind,
            "origin": operation.origin,
            "history_occurrences": list(operation.history_occurrences),
            "history_terminals": [
                name for occurrence in operation.history_occurrences for name in terminals.get(occurrence, ())
            ],
            "coverage": coverage,
            "coverage_reason": reason,
            "request": {
                "history_activity_inputs": list(operation.history_inputs),
                "review_request": json.loads(request["request_json"]) if request else None,
                "review_request_digest": request["digest"] if request else None,
            },
            "response": {
                "body_present": body is not None,
                **({name: body[name] for name in _BODY_COLUMNS if name != "operation_id"} if body else {}),
                "session_present": session_name is not None,
                "session_jsonl": session_name,
                "session_jsonl_bytes": len(session) if session else 0,
            },
            "pi_operation": pi_operation,
        }
        (out / f"{stem}.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        index.append(
            {
                "operation_id": operation.operation_id,
                "logical_operation": operation.logical_operation,
                "attempt": operation.attempt,
                "kind": operation.kind,
                "origin": operation.origin,
                "history_occurrences": list(operation.history_occurrences),
                "file": f"{stem}.json",
                "body_present": body is not None,
                "session_present": session_name is not None,
                "session_jsonl": session_name,
                "coverage": coverage,
                "coverage_reason": reason,
            }
        )
        named = f"agent operation {operation.logical_operation} attempt {operation.attempt} ({operation.operation_id})"
        if coverage == "no_body_no_session":
            report.gap(f"{named} has no body in bodies.sqlite3 and no session transcript: {reason}")
        elif coverage == "body_without_session":
            joined += 1
            report.gap(f"{named} has a body but no session transcript: {reason}")
        else:
            joined += 1
    (out / "index.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report.numbers["transcripts"] = {
        "operations": len(operations),
        "bodies_joined": joined,
        "bodies_missing": len(operations) - joined,
        "sessions_exported": classes["session_exported"],
        "session_jsonl_bytes": session_bytes,
        "coverage": classes,
    }


def index_raw_deliveries(directories: Sequence[Path]) -> tuple[dict[str, list[RawDelivery]], list[str]]:
    """Every saved delivery record in the supplied directories, by delivery id."""
    by_delivery: dict[str, list[RawDelivery]] = {}
    unrecognized: list[str] = []
    for directory in directories:
        if not directory.is_dir():
            raise EvidenceExportError(f"webhook delivery directory {directory} does not exist")
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            match = _DELIVERY_FILE.fullmatch(path.name)
            if match is None:
                unrecognized.append(str(path))
                continue
            delivery_id = match["delivery"].lower()
            record = RawDelivery(path=path, delivery_id=delivery_id, label=match["label"])
            by_delivery.setdefault(delivery_id, []).append(record)
    return by_delivery, unrecognized


def _write_raw_deliveries(
    out: Path, directories: Sequence[Path], rows: Sequence[Mapping[str, Any]], report: Report
) -> None:
    """Copy the raw record behind every inbox row, and only those.

    The inbox is the admission decision for THIS pull request. A raw
    record it never claims belongs to another PR's journey, so copying it
    would put evidence in the package that this PR's authority cannot
    account for — it is excluded, counted and listed instead.
    """
    if not directories:
        report.numbers["raw_deliveries"] = {"supplied": False, "directories": [], "copied": 0}
        report.gap(
            "the webhook inbox stores the DERIVED observation, not the raw request body; "
            "the state directory retains no raw webhook payloads and no --webhook-deliveries "
            "directory was supplied, so this package holds no raw delivery record"
        )
        return
    by_delivery, unrecognized = index_raw_deliveries(directories)
    admitted = {str(row["delivery_id"]).lower(): row for row in rows}
    target = out / "deliveries"
    target.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    for delivery_id, row in admitted.items():
        records = by_delivery.get(delivery_id, [])
        if not records:
            report.gap(
                f"webhook inbox row {row['delivery_id']} ({row['event']}) has no raw delivery "
                f"record in the supplied directories; only its derived observation travels"
            )
            continue
        for record in records:
            destination = target / record.path.name
            if destination.exists():
                report.gap(f"two supplied directories hold a delivery record named {record.path.name}; kept the first")
                continue
            shutil.copyfile(record.path, destination)
            payload = destination.read_bytes()
            copied.append(
                {
                    "file": record.path.name,
                    "delivery_id": record.delivery_id,
                    "label": record.label,
                    "inbox_event": row["event"],
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "source": str(record.path),
                }
            )
    out_of_scope = [
        {"file": record.path.name, "delivery_id": record.delivery_id, "label": record.label, "source": str(record.path)}
        for delivery_id in sorted(by_delivery)
        if delivery_id not in admitted
        for record in by_delivery[delivery_id]
    ]
    (target / "index.json").write_text(json.dumps(copied, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "out-of-scope-deliveries.json").write_text(
        json.dumps(
            {
                "note": (
                    "delivery records found in the supplied directories whose delivery id this "
                    "pull request's webhook inbox never admitted; none of them were copied"
                ),
                "count": len(out_of_scope),
                "unrecognized_file_names": sorted(unrecognized),
                "files": out_of_scope,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    for name in sorted(unrecognized):
        report.gap(f"{name} is not named <delivery_id>-<event>.json; it was not classified as a delivery record")
    report.numbers["raw_deliveries"] = {
        "supplied": True,
        "directories": [str(directory) for directory in directories],
        "files_seen": sum(len(records) for records in by_delivery.values()),
        "matched_deliveries": len([delivery_id for delivery_id in admitted if delivery_id in by_delivery]),
        "copied": len(copied),
        "bytes": sum(int(entry["bytes"]) for entry in copied),
        "inbox_rows_without_raw": sorted(delivery_id for delivery_id in admitted if delivery_id not in by_delivery),
        "out_of_scope_files": len(out_of_scope),
        "out_of_scope_listing": "webhooks/out-of-scope-deliveries.json",
        "unrecognized_files": sorted(unrecognized),
    }


def _write_webhooks(out: Path, state_dir: Path, scratch: Path, deliveries: Sequence[Path], report: Report) -> None:
    path = state_dir / "webhooks.sqlite3"
    if not path.exists():
        report.gap("state directory has no webhooks.sqlite3; the webhook inbox is absent from this package")
        report.numbers["webhooks"] = {"rows": 0, "by_event": {}}
        # With no inbox there is no admission decision, so no raw record
        # can be claimed for this PR; every supplied one is out of scope.
        _write_raw_deliveries(out, deliveries, (), report)
        return
    out.mkdir(parents=True, exist_ok=True)
    connection = _connect(path, scratch)
    try:
        rows = _rows(connection, f"SELECT rowid, {', '.join(_INBOX_COLUMNS)} FROM inbox ORDER BY rowid")
    finally:
        connection.close()
    by_event: dict[str, int] = {}
    with (out / "inbox.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            row["observation"] = json.loads(row["observation"])
            by_event[str(row["event"])] = by_event.get(str(row["event"]), 0) + 1
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    report.numbers["webhooks"] = {"rows": len(rows), "by_event": dict(sorted(by_event.items()))}
    _write_raw_deliveries(out, deliveries, rows, report)


def _write_boards(out: Path, records: Sequence[Mapping[str, Any]], report: Report) -> None:
    landed = board_documents(records)
    out.mkdir(parents=True, exist_ok=True)
    index = ["# Board history", "", "Every board the PR page showed, in publication order.", ""]
    for ordinal, (seq, result) in enumerate(landed, start=1):
        name = f"{ordinal:04d}.md"
        entries = [str(entry) for entry in result["entries"]]
        (out / name).write_text(render_board(entries) + "\n", encoding="utf-8")
        index.append(f"- [{name}]({name}) — History seq {seq}, digest `{result.get('digest', '')}`")
    (out / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    report.numbers["boards"] = {"dash_landed": len(landed), "files": len(landed)}
    if not landed:
        report.gap("canonical History holds no landed dashboard publication; no board state is reproducible")


def _credential_named(path: Path) -> bool:
    name = path.name.lower()
    return (
        name in CREDENTIAL_NAMES
        or path.suffix.lower() in CREDENTIAL_SUFFIXES
        or any(marker in name for marker in CREDENTIAL_MARKERS)
    )


def _write_identity(out: Path, state_dir: Path, instance: Instance, extra: Sequence[Path], report: Report) -> None:
    out.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    excluded: list[str] = []
    shutil.copyfile(instance.directory / "binding.json", out / "binding.json")
    copied.append("binding.json")
    for name in IDENTITY_STATE_FILES:
        candidate = state_dir / name
        if candidate.is_file():
            shutil.copyfile(candidate, out / name)
            copied.append(name)
    for path in extra:
        if _credential_named(path):
            excluded.append(path.name)
            continue
        if not path.is_file():
            raise EvidenceExportError(f"identity file {path} does not exist")
        shutil.copyfile(path, out / path.name)
        copied.append(path.name)
    for path in sorted(state_dir.rglob("*")):
        if path.is_file() and _credential_named(path):
            excluded.append(str(path.relative_to(state_dir)))
    (out / "index.json").write_text(
        json.dumps({"files": sorted(copied), "excluded_by_name": sorted(set(excluded))}, indent=2) + "\n",
        encoding="utf-8",
    )
    report.numbers["identity"] = {"files": sorted(copied), "excluded_by_name": sorted(set(excluded))}
    if len(copied) == 1:
        report.gap(
            "the state directory holds no run-identity artifact (image sha, petrus pin, runtime identity); "
            "only binding.json is in identity/ — pass --identity for the captured ones"
        )


def _write_history(out: Path, source: Path, records: Sequence[Mapping[str, Any]], report: Report) -> None:
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, out / "history.jsonl")
    (out / "index.md").write_text(history_index(records, report), encoding="utf-8")
    schemas = {record.get("schema") for record in records}
    if schemas != {HISTORY_SCHEMA}:
        report.gap(f"canonical History carries schema versions {sorted(map(str, schemas))}, expected {HISTORY_SCHEMA}")
    report.numbers["history"] = {
        "records": len(records),
        "bytes": source.stat().st_size,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "schemas": sorted(str(value) for value in schemas),
    }


def _raw_delivery_prose(report: Report) -> str:
    numbers = report.numbers.get("raw_deliveries", {})
    if not numbers.get("supplied"):
        return (
            "No `--webhook-deliveries` directory was supplied to this build, so\n"
            "**this package holds no raw GitHub delivery record**. The webhook\n"
            "inbox persists the DERIVED observation only; the full request\n"
            "payload and the request/response metadata of each delivery are not\n"
            "in the state directory and were not supplied from outside it.\n"
        )
    return (
        f"`webhooks/deliveries/` holds {numbers['copied']} raw GitHub delivery record file(s),\n"
        f"covering {numbers['matched_deliveries']} of the {report.numbers['webhooks']['rows']} inbox rows"
        f" (a redelivered id has two files), copied\n"
        f"byte-for-byte from {', '.join(f'`{name}`' for name in numbers['directories'])} with a\n"
        f"sha256 per file in `webhooks/deliveries/index.json`. A record is copied only when\n"
        f"this pull request's own inbox admitted its delivery id; the other\n"
        f"{numbers['out_of_scope_files']} record(s) in those directories belong to deliveries this\n"
        f"PR never admitted and are named — not copied — in\n"
        f"`webhooks/out-of-scope-deliveries.json`. Inbox rows with no raw record:\n"
        f"{len(numbers['inbox_rows_without_raw'])}.\n"
    )


def _coverage_prose(report: Report) -> str:
    coverage = report.numbers.get("transcripts", {}).get("coverage", {})
    return (
        f"Of {report.numbers.get('transcripts', {}).get('operations', 0)} operations,\n"
        f"{coverage.get('session_exported', 0)} carry a full `.session.jsonl` transcript,\n"
        f"{coverage.get('body_without_session', 0)} have a response body but no transcript, and\n"
        f"{coverage.get('no_body_no_session', 0)} have neither. Every operation names its own class in\n"
        f"`transcripts/index.json` (`coverage`) together with the reason\n"
        f"(`coverage_reason`), and each of the last two classes is listed under\n"
        f"Gaps below. A session transcript exists only in the `session_jsonl`\n"
        f"column of `pi_a2_bodies`; there is no other store of one, so a body\n"
        f"without a transcript is a turn that appended none — chiefly a review\n"
        f"round the gate deferred, cancelling the agent turn at once.\n"
    )


def _readme(instance: Instance, report: Report) -> str:
    gaps = "\n".join(f"- {gap}" for gap in report.gaps) or "- none reported."
    raw_deliveries = _raw_delivery_prose(report)
    coverage = _coverage_prose(report)
    return f"""# Hamsterdan evidence package — {instance.repository} PR {instance.pull_request}

Built offline from a local copy of `/var/lib/hamsterdan` by
`python -m hamsterdan.host.export`. Everything here is a copy or a
derivation of that durable state; nothing was fetched and nothing was
rerun. `MANIFEST.json` carries the same numbers as this file, machine
readable.

Instance `{instance.instance_id}` (installation {instance.installation_id},
repository {instance.repository_id}, topology `{instance.topology}`).

## What each directory is

- `history/history.jsonl` — canonical History, copied verbatim. This is
  the workflow authority: every other artifact here is derived from it
  or joined to it. `history/index.md` is a navigation aid, one line per
  record, keyed by the 1-based line number (`seq`) of the raw file.
- `transcripts/` — one `.json` per agent operation attempt with its
  request and its response body, plus the full Pi session transcript as
  `<id>.session.jsonl` whenever the turn appended one.
  `transcripts/index.json` lists every operation, whether its body was
  found, whether its session travelled, and why not when it did not.
- `webhooks/inbox.jsonl` — every row of the durable webhook inbox, one
  JSON object per line, all columns.
- `webhooks/deliveries/` — the raw GitHub delivery record (full request
  payload plus request and response metadata) behind each of those rows,
  when one was supplied; `webhooks/out-of-scope-deliveries.json` names
  the supplied records this PR's inbox never admitted.
- `boards/` — every board the PR page ever showed, rendered from each
  landed dashboard publication in History with the production renderer
  (`hamsterdan.readiness.net_v5.board.render_board`), numbered in
  publication order. `boards/index.md` maps each file to its History
  `seq`.
- `identity/` — the Instance binding plus whatever run-identity
  artifacts were available (image sha, petrus pin, runtime identity).

## How records join

Canonical History records an agent Activity as `ActivityRequested` with
the logical operation and attempt inside `input.work`. The agent runner
derives the body key from exactly those two values:

    operation_id = "pi:" + sha256(f"{{operation}}\\0{{attempt}}").hexdigest()

That `operation_id` is the primary key of `pi_a2_bodies` in
`pi-a2/runtime-host/bodies.sqlite3` and of `pi_operations` in
`operations.sqlite3`. Each `transcripts/<id>.json` carries the logical
operation, the attempt, every History `occurrence` that requested it,
and the joined body — or `"body_present": false` when the state
directory did not retain one.

Three operation families use the key:

- `review:...` — attempt is the net's review attempt, taken from
  History; the composed request also survives in
  `review-requests.sqlite3` and is inlined as `request.review_request`.
- `mutation:...` — one agent turn per `op_key`, so attempt is 1. A gate
  that reconciles lookup-first is requested again under the same key, so
  one transcript can list several `history_occurrences`.
- `conversation:...` — comment classification runs BEFORE the ingress
  manifest stages, so these operations never enter History. They are
  recovered from `agent-routes.sqlite3` at attempt 1; their `origin` is
  `agent-routes` and their `history_occurrences` list is empty.

Webhook inbox rows join to History through the delivery id: the
observation's `delivery_id` appears in the conversation operation name
and in the ingress identities of `ExternalEventDelivered` records.

## Session transcript coverage

{coverage}
## Raw webhook deliveries

{raw_deliveries}
## How to replay the net from History

`history.jsonl` alone reconstructs the run. `Engine.load` binds every
declared handler before it replays, so the V5 gate implementations have
to be present — but replay never CALLS one, it only re-reads the
recorded terminals. Uninitialized gate instances are therefore enough,
and nothing in this recipe can touch GitHub, Pi, or the network:

```python
from pathlib import Path

from petrus.engine import Engine
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.petrinet import NetPath
from petrus.motus.activity import activity
from petrus.motus.dispatch import InlineDispatch

from hamsterdan.host.v5.gates import V5PublicationGates
from hamsterdan.host.v5.mutation import V5MutationGate
from hamsterdan.host.v5.rerun import V5RerunGate
from hamsterdan.host.v5.review import V5ReviewGate
from hamsterdan.readiness.net_v5 import build_net_v5
from hamsterdan.readiness.net_v5.gating import VariantPayloadConverter, wire_gates
from hamsterdan.readiness.net_v5.topology import DERIVED, GATES

publications = V5PublicationGates.__new__(V5PublicationGates)
mutation = V5MutationGate.__new__(V5MutationGate)
rerun = V5RerunGate.__new__(V5RerunGate)
review = V5ReviewGate.__new__(V5ReviewGate)
converter = VariantPayloadConverter()
definitions = {{
    name: activity(implementation, name=name, converter=converter)
    for name, implementation in {{
        "rerun_gate": rerun.rerun_gate,
        "review_agent": review.review_agent,
        "publish_gate": publications.publish_gate,
        "git_gate": mutation.git_gate,
        "reply_gate": publications.reply_gate,
        "dash_gate": publications.dash_gate,
        "reminder_gate": publications.reminder_gate,
        "announce_gate": publications.announce_gate,
    }}.items()
}}
built = build_net_v5()
engine = Engine.load(
    built.net,
    "{instance.instance_id}",
    history=JsonlHistoryStore(Path("history/history.jsonl")),
    dispatch=InlineDispatch(definitions),
    handlers=wire_gates(built, GATES, definitions, DERIVED),
    guards=built.guards,
    activities=tuple(item.declaration for item in definitions.values()),
)
print(len(tuple(engine.records)), "records")
print(tuple(engine.marking.place(NetPath("life.state"))))
```

Loading replays every record in order and rebuilds the exact final
marking. The board sequence in `boards/` is the same replay projected at
the publication seam: each landed dashboard result carries the entry log
the board renderer folds.

## Excluded by name

The exporter opens only the durable stores it names above, and it
refuses to copy any file whose name matches credential material
(`.env`, `*.pem`, `*.key`, or a name containing `secret`, `token`,
`credential`, `api-key`). `identity/index.json` lists every such path
seen under the state directory; none of them were copied. No
secret value is read, printed, or stored anywhere in this package.

## Gaps

{gaps}
"""


def export_package(
    *,
    state_dir: Path,
    out: Path,
    repository: str,
    pull_request: int,
    identity: Sequence[Path] = (),
    webhook_deliveries: Sequence[Path] = (),
) -> Report:
    """Write the evidence package and return what it holds and lacks."""
    if not state_dir.is_dir():
        raise EvidenceExportError(f"state directory {state_dir} does not exist")
    if out.exists() and any(out.iterdir()):
        raise EvidenceExportError(f"output directory {out} already exists and is not empty")
    instance = find_instance(state_dir, repository, pull_request)
    history_path = instance.directory / "history.jsonl"
    if not history_path.is_file():
        raise EvidenceExportError(f"Instance {instance.instance_id} has no canonical History at {history_path}")
    records = read_history(history_path)
    report = Report()
    report.numbers["instance"] = {
        "repository": instance.repository,
        "pull_request": instance.pull_request,
        "installation_id": instance.installation_id,
        "repository_id": instance.repository_id,
        "instance_id": instance.instance_id,
        "topology": instance.topology,
        "state_directory": str(state_dir),
    }
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hamsterdan-export-") as scratch_name:
        scratch = Path(scratch_name)
        operations = history_operations(records, instance)
        operations.extend(routed_operations(_agent_routes(state_dir, scratch, report), operations))
        bodies, sessions = _bodies(state_dir, scratch, report)
        _adopt_unattributed(operations, bodies, report)
        _write_history(out / "history", history_path, records, report)
        _write_boards(out / "boards", records, report)
        _write_transcripts(
            out / "transcripts",
            operations,
            bodies,
            sessions,
            _pi_operations(state_dir, scratch, report),
            _review_requests(instance, scratch, report),
            history_terminals(records),
            report,
        )
        _write_webhooks(out / "webhooks", state_dir, scratch, webhook_deliveries, report)
        _write_identity(out / "identity", state_dir, instance, identity, report)
    report.numbers["gaps"] = len(report.gaps)
    (out / "MANIFEST.json").write_text(
        json.dumps({"schema": PACKAGE_SCHEMA, **report.numbers, "gap_details": report.gaps}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    (out / "README.md").write_text(_readme(instance, report), encoding="utf-8")
    return report


def _agent_routes(state_dir: Path, scratch: Path, report: Report) -> list[dict[str, Any]]:
    path = state_dir / "agent-routes.sqlite3"
    if not path.exists():
        report.gap("state directory has no agent-routes.sqlite3; operations routed outside History cannot be recovered")
        return []
    connection = _connect(path, scratch)
    try:
        return _rows(connection, "SELECT operation, profile, resolved FROM agent_routes ORDER BY operation")
    finally:
        connection.close()


def _bodies(
    state_dir: Path, scratch: Path, report: Report
) -> tuple[dict[str, dict[str, Any]], dict[str, bytes | None]]:
    path = state_dir / "pi-a2" / "runtime-host" / "bodies.sqlite3"
    if not path.exists():
        report.gap(f"state directory has no {path.relative_to(state_dir)}; no agent session body is available")
        return {}, {}
    connection = _connect(path, scratch)
    try:
        rows = _rows(
            connection,
            f"SELECT {', '.join(_BODY_COLUMNS)}, length(workspace_archive) AS workspace_archive_bytes,"
            " session_jsonl FROM pi_a2_bodies",
        )
    finally:
        connection.close()
    bodies: dict[str, dict[str, Any]] = {}
    sessions: dict[str, bytes | None] = {}
    for row in rows:
        key = str(row["operation_id"])
        sessions[key] = row.pop("session_jsonl")
        bodies[key] = row
    return bodies, sessions


def _pi_operations(state_dir: Path, scratch: Path, report: Report) -> dict[str, dict[str, Any]]:
    path = state_dir / "pi-a2" / "runtime-host" / "operations.sqlite3"
    if not path.exists():
        report.gap(f"state directory has no {path.relative_to(state_dir)}; agent settlement outcomes are unavailable")
        return {}
    connection = _connect(path, scratch)
    try:
        rows = _rows(connection, f"SELECT {', '.join(_PI_OPERATION_COLUMNS)} FROM pi_operations ORDER BY sequence")
    finally:
        connection.close()
    return {str(row["operation_id"]): row for row in rows}


def _review_requests(instance: Instance, scratch: Path, report: Report) -> dict[tuple[str, int], dict[str, Any]]:
    path = instance.directory / "review-requests.sqlite3"
    if not path.exists():
        report.gap("Instance has no review-requests.sqlite3; composed review requests are unavailable")
        return {}
    connection = _connect(path, scratch)
    try:
        rows = _rows(connection, "SELECT operation, attempt, request_json, digest FROM v5_review_requests")
    finally:
        connection.close()
    return {(str(row["operation"]), int(row["attempt"])): row for row in rows}


def _adopt_unattributed(operations: list[Operation], bodies: Mapping[str, Mapping[str, Any]], report: Report) -> None:
    """Export a body no known operation claims rather than dropping it."""
    claimed = {operation.operation_id for operation in operations}
    for operation_id in sorted(set(bodies) - claimed):
        report.gap(f"agent body {operation_id} matches no known operation; exported as unattributed")
        operations.append(
            Operation(
                operation_id=operation_id,
                logical_operation="",
                attempt=0,
                kind="unattributed",
                origin="bodies",
                history_occurrences=(),
                history_inputs=(),
            )
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m hamsterdan.host.export",
        description="Export one PR's durable Hamsterdan state as an offline evidence package.",
    )
    parser.add_argument("--state-dir", type=Path, required=True, help="local copy of /var/lib/hamsterdan")
    parser.add_argument("--out", type=Path, required=True, help="package directory to create")
    parser.add_argument("--repository", required=True, help="owner/name of the monitored repository")
    parser.add_argument("--pull-request", type=int, required=True, help="pull request number")
    parser.add_argument(
        "--identity",
        type=Path,
        action="append",
        default=[],
        help="extra run-identity file to copy into identity/ (repeatable)",
    )
    parser.add_argument(
        "--webhook-deliveries",
        type=Path,
        action="append",
        default=[],
        dest="webhook_deliveries",
        help="directory of raw GitHub delivery records named <delivery_id>-<event>.json (repeatable)",
    )
    arguments = parser.parse_args(argv)
    try:
        report = export_package(
            state_dir=arguments.state_dir,
            out=arguments.out,
            repository=arguments.repository,
            pull_request=arguments.pull_request,
            identity=tuple(arguments.identity),
            webhook_deliveries=tuple(arguments.webhook_deliveries),
        )
    except EvidenceExportError as error:
        print(f"export failed: {error}", file=sys.stderr)
        return 2
    for gap in report.gaps:
        print(f"GAP: {gap}", file=sys.stderr)
    print(json.dumps(report.numbers, indent=2, sort_keys=True))
    print(f"package written to {arguments.out} (gaps: {len(report.gaps)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
