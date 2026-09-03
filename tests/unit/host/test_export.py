"""Executable contracts for the offline evidence exporter.

The package exists so a hero journey can be reconstructed WITHOUT the
production VM and without rerunning anything. Two properties carry that
promise and every test below defends one of them:

- nothing is dropped: an operation whose body the state directory no
  longer holds is REPORTED as missing, an operation whose turn appended
  no session transcript is REPORTED with the reason it appended none,
  and a body no operation claims is still exported; the reverse (a
  quietly shorter package) would look identical to a clean run;
- nothing is invented and nothing is written back: canonical History
  travels byte-for-byte, raw webhook delivery records travel
  byte-for-byte, boards come from the production renderer, and the
  source state directory is never modified;
- nothing travels unclaimed: a raw delivery record this PR's inbox never
  admitted is counted and named, never copied.

Fixture stores are built from the real schemas — `pi_a2_bodies`,
`pi_operations`, `inbox`, `agent_routes`, `v5_review_requests` — and
real schema-5 History record shapes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from hamsterdan.host.export import EvidenceExportError, agent_operation_id, export_package, main

INSTALLATION, REPOSITORY_ID, PULL_REQUEST = 44, 31, 7
REPOSITORY = "hbnetwork/demo-pr-readiness"
INSTANCE = f"github:{INSTALLATION}:{REPOSITORY_ID}:pr:{PULL_REQUEST}"

REVIEW_OPERATION = f"review:{INSTANCE}:h1:i1"
MUTATION_OPERATION = f"mutation:{REPOSITORY}:pr:{PULL_REQUEST}:push:comment:9001:h1:i1"

# GitHub delivery guids: the exporter reads a raw record's delivery id
# out of its file name, so the fixture uses the real guid shape.
ADMITTED_DELIVERY = "0ad296b0-a66f-11f1-8280-881304021cbb"
SECOND_DELIVERY = "1be2f540-a66f-11f1-87d6-f8c096b92398"
OTHER_PR_DELIVERY = "2cf30a10-a66f-11f1-9a12-85ad4b6c2d00"

CONVERSATION_OPERATION = f"conversation:{REPOSITORY}:pr:{PULL_REQUEST}:delivery:{ADMITTED_DELIVERY}"

BOARD_ENTRIES = [
    "state:{'base': 'b1', 'base_current': True, 'head': 'h1', 'mergeable': True, 'phase': 'running', 'policy': 'p1'}",
    "checks:{'status': 'success'}",
]


def _record(kind: str, **fields: object) -> dict[str, object]:
    return {"record": kind, "schema": 5, **fields}


def _history() -> list[dict[str, object]]:
    return [
        _record("InstanceCreated", instance=INSTANCE, name="pr_v5", instant=0),
        _record(
            "ExternalEventDelivered",
            source="on_head",
            identity=f"v5:{ADMITTED_DELIVERY}",
            occurrence=1,
            instant=1,
            scope="/life",
            tokens=[{"color": "HeadSeen", "data": {"head": "h1"}}],
        ),
        _record(
            "ActivityRequested",
            transition="review.agent",
            activity="review_agent",
            occurrence=2,
            instant=2,
            scope="/review",
            correlation=REVIEW_OPERATION,
            idempotency=REVIEW_OPERATION,
            policy={"attempts": 1},
            input={"work": {"operation": REVIEW_OPERATION, "head": "h1", "attempt": 1}},
        ),
        _record(
            "ActivityCompleted",
            transition="review.agent",
            occurrence=2,
            instant=3,
            result={"$variant": "AgentReview", "head": "h1"},
        ),
        _record(
            "ActivityRequested",
            transition="review.agent",
            activity="review_agent",
            occurrence=3,
            instant=4,
            scope="/review",
            correlation=REVIEW_OPERATION,
            idempotency=REVIEW_OPERATION,
            policy={"attempts": 1},
            input={"work": {"operation": REVIEW_OPERATION, "head": "h1", "attempt": 2}},
        ),
        _record(
            "ActivityCompleted",
            transition="review.agent",
            occurrence=3,
            instant=5,
            result={"$variant": "RoundDeferred", "head": "h1"},
        ),
        _record(
            "ActivityRequested",
            transition="mut.git_gate",
            activity="git_gate",
            occurrence=4,
            instant=5,
            scope="/mut",
            correlation="push:comment:9001:h1:i1",
            idempotency="push:comment:9001:h1:i1",
            policy={"attempts": 1},
            input={"work": {"op": "change", "op_key": "push:comment:9001:h1:i1", "head": "h1", "attempt": 0}},
        ),
        _record(
            "ActivityCompleted",
            transition="dash.publish",
            occurrence=5,
            instant=6,
            result={"$variant": "DashLanded", "entries": BOARD_ENTRIES, "digest": "d1"},
        ),
        _record(
            "ActivityCompleted",
            transition="dash.publish",
            occurrence=6,
            instant=7,
            result={"$variant": "DashLanded", "entries": BOARD_ENTRIES[:1], "digest": "d2"},
        ),
        _record(
            "ActivityCompleted",
            transition="dash.publish",
            occurrence=7,
            instant=8,
            result={"$variant": "DashDeferred", "entries": BOARD_ENTRIES, "digest": "d3"},
        ),
    ]


def _database(path: Path, schema: str, statement: str, rows: list[tuple[object, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(schema)
        connection.executemany(statement, rows)
        connection.commit()
    finally:
        connection.close()


def _body_row(operation_id: str, *, session: bytes | None = b'{"role":"user"}\n') -> tuple[object, ...]:
    return (operation_id, "out-ref", "output text", None, "session-1", None, session, b"archive", "wd1", 1)


def _pi_operation_row(operation_id: str, *, cancelled: bool) -> tuple[object, ...]:
    """A settled Pi operation; a cancelled turn appended no transcript."""
    outcome = "cancelled" if cancelled else "completed"
    return (
        operation_id,
        "fp",
        "ep",
        "turn",
        "settled",
        outcome,
        0 if cancelled else 1,
        outcome if cancelled else "turn-completed",
        None if cancelled else "out-ref",
        None,
        "clean",
        "clean",
        1,
    )


def deliveries(tmp_path: Path, records: dict[str, object], *, name: str = "deliveries") -> Path:
    """A directory of raw GitHub delivery records, keyed by file name."""
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    for file_name, payload in records.items():
        (directory / file_name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return directory


def raw_delivery(delivery_id: str, event: str, action: str) -> dict[str, object]:
    """The shape GitHub's delivery API returns: payload plus metadata."""
    return {
        "guid": delivery_id,
        "event": event,
        "action": action,
        "status_code": 202,
        "request": {"headers": {"X-GitHub-Delivery": delivery_id}, "payload": {"action": action, "number": 7}},
        "response": {"headers": {"content-type": "application/json"}, "payload": "accepted"},
    }


def state_dir(
    tmp_path: Path,
    *,
    history: list[dict[str, object]] | None = None,
    bodies: tuple[str, ...] = (
        agent_operation_id(REVIEW_OPERATION, 1),
        agent_operation_id(MUTATION_OPERATION, 1),
        agent_operation_id(CONVERSATION_OPERATION, 1),
    ),
    routes: tuple[str, ...] = (REVIEW_OPERATION, MUTATION_OPERATION, CONVERSATION_OPERATION),
    sessionless: frozenset[str] = frozenset(),
    omit: frozenset[str] = frozenset(),
) -> Path:
    """One state directory shaped exactly like /var/lib/hamsterdan."""
    root = tmp_path / "state"
    instance = root / "applications" / str(INSTALLATION) / str(REPOSITORY_ID) / str(PULL_REQUEST)
    instance.mkdir(parents=True)
    (instance / "binding.json").write_text(
        json.dumps(
            {
                "instance_id": INSTANCE,
                "pull_request": PULL_REQUEST,
                "repository": REPOSITORY,
                "topology": "v5",
            }
        ),
        encoding="utf-8",
    )
    records = _history() if history is None else history
    (instance / "history.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    if "review-requests" not in omit:
        _database(
            instance / "review-requests.sqlite3",
            """CREATE TABLE v5_review_requests (
                operation TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt >= 1),
                request_json TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(operation, attempt))""",
            "INSERT INTO v5_review_requests VALUES (?,?,?,?)",
            [(REVIEW_OPERATION, 1, json.dumps({"repository": REPOSITORY, "head": "h1"}), "rq1")],
        )
    if "webhooks" not in omit:
        _database(
            root / "webhooks.sqlite3",
            """CREATE TABLE inbox (
                delivery_id TEXT PRIMARY KEY, event TEXT NOT NULL, observation TEXT NOT NULL,
                status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                reason TEXT, error_class TEXT, next_attempt_at REAL NOT NULL DEFAULT 0)""",
            "INSERT INTO inbox(delivery_id,event,observation,status,attempts) VALUES (?,?,?,?,?)",
            [
                (
                    ADMITTED_DELIVERY,
                    "pull_request",
                    json.dumps({"delivery_id": ADMITTED_DELIVERY, "action": "opened"}),
                    "terminal",
                    1,
                ),
                (
                    SECOND_DELIVERY,
                    "issue_comment",
                    json.dumps({"delivery_id": SECOND_DELIVERY, "action": "created"}),
                    "terminal",
                    1,
                ),
            ],
        )
    if "agent-routes" not in omit:
        _database(
            root / "agent-routes.sqlite3",
            """CREATE TABLE agent_routes (
                operation TEXT PRIMARY KEY, profile TEXT NOT NULL, snapshot TEXT NOT NULL,
                resolved INTEGER NOT NULL CHECK (resolved IN (0, 1)))""",
            "INSERT INTO agent_routes VALUES (?,?,?,?)",
            [(operation, "pi-native-a2-local", "{}", 1) for operation in routes],
        )
    if "bodies" not in omit:
        _database(
            root / "pi-a2" / "runtime-host" / "bodies.sqlite3",
            """CREATE TABLE pi_a2_bodies (
                operation_id TEXT PRIMARY KEY,
                output_reference TEXT, output_text TEXT,
                continuation_reference TEXT, session_id TEXT,
                working_binding TEXT, session_jsonl BLOB,
                workspace_archive BLOB NOT NULL, workspace_digest TEXT NOT NULL,
                aggregate_verified INTEGER NOT NULL CHECK (aggregate_verified IN (0, 1)))""",
            "INSERT INTO pi_a2_bodies VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                _body_row(operation_id, session=None if operation_id in sessionless else b'{"role":"user"}\n')
                for operation_id in bodies
            ],
        )
        _database(
            root / "pi-a2" / "runtime-host" / "operations.sqlite3",
            """CREATE TABLE pi_operations (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL,
                episode_id TEXT NOT NULL, turn_id TEXT NOT NULL, phase TEXT NOT NULL,
                outcome TEXT, accepted_appends INTEGER, termination_code TEXT,
                output_reference TEXT, continuation_reference TEXT,
                cleanup TEXT NOT NULL, cleanup_code TEXT NOT NULL,
                acknowledged INTEGER NOT NULL CHECK (acknowledged IN (0, 1)))""",
            """INSERT INTO pi_operations(operation_id,fingerprint,episode_id,turn_id,phase,outcome,
                accepted_appends,termination_code,output_reference,continuation_reference,
                cleanup,cleanup_code,acknowledged) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [_pi_operation_row(operation_id, cancelled=operation_id in sessionless) for operation_id in bodies],
        )
    return root


def build(tmp_path: Path, *, webhook_deliveries: tuple[Path, ...] = (), **changes) -> tuple[Path, object]:
    source = state_dir(tmp_path, **changes)
    out = tmp_path / "package"
    report = export_package(
        state_dir=source,
        out=out,
        repository=REPOSITORY,
        pull_request=PULL_REQUEST,
        webhook_deliveries=webhook_deliveries,
    )
    return out, report


def transcript(out: Path, operation: str, attempt: int) -> dict:
    stem = agent_operation_id(operation, attempt).replace(":", "-")
    return json.loads((out / "transcripts" / f"{stem}.json").read_text(encoding="utf-8"))


class TestHistoryTravelsAsTheAuthority:
    """The raw file is the authority; the index only navigates it."""

    def test_canonical_history_is_copied_byte_for_byte(self, tmp_path: Path) -> None:
        source = state_dir(tmp_path)
        out = tmp_path / "package"
        export_package(state_dir=source, out=out, repository=REPOSITORY, pull_request=PULL_REQUEST)
        original = (
            source / "applications" / str(INSTALLATION) / str(REPOSITORY_ID) / str(PULL_REQUEST) / "history.jsonl"
        ).read_bytes()
        assert (out / "history" / "history.jsonl").read_bytes() == original
        manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
        assert manifest["history"]["records"] == len(_history())
        assert manifest["history"]["sha256"] == hashlib.sha256(original).hexdigest()

    def test_the_index_names_every_record_once_in_file_order(self, tmp_path: Path) -> None:
        out, _ = build(tmp_path)
        lines = [
            line
            for line in (out / "history" / "index.md").read_text(encoding="utf-8").splitlines()
            if line[:5].strip().isdigit()
        ]
        assert len(lines) == len(_history())
        assert [line.split()[0] for line in lines] == [str(seq) for seq in range(1, len(_history()) + 1)]
        assert "ActivityRequested" in lines[2] and "review_agent" in lines[2]

    def test_a_record_kind_the_index_cannot_name_is_reported_not_hidden(self, tmp_path: Path) -> None:
        # a future Petrus record kind must surface as a gap: an index
        # that silently degrades would look like a complete index
        history = [*_history(), _record("SomethingNewer", occurrence=9, instant=9, detail="x")]
        _, report = build(tmp_path, history=history)
        assert any("SomethingNewer" in gap for gap in report.gaps)
        assert "detail=x" in (tmp_path / "package" / "history" / "index.md").read_text(encoding="utf-8")


class TestBoardHistory:
    """Every board the PR page showed, and only the ones it showed."""

    def test_each_landed_dashboard_publication_becomes_one_numbered_board(self, tmp_path: Path) -> None:
        out, report = build(tmp_path)
        boards = sorted(path.name for path in (out / "boards").glob("[0-9]*.md"))
        assert boards == ["0001.md", "0002.md"]
        assert report.numbers["boards"]["dash_landed"] == 2

    def test_a_board_is_the_production_render_of_its_entry_log(self, tmp_path: Path) -> None:
        out, _ = build(tmp_path)
        board = (out / "boards" / "0001.md").read_text(encoding="utf-8")
        assert board.startswith("## Hamsterdan summary — ")
        assert "✅ success" in board and "head h1 on base b1" in board

    def test_a_publication_that_never_landed_produces_no_board(self, tmp_path: Path) -> None:
        # DashDeferred is a board the reader never saw; rendering it
        # would put a state on the timeline that GitHub never showed
        out, _ = build(tmp_path)
        assert "d3" not in (out / "boards" / "index.md").read_text(encoding="utf-8")


class TestTranscriptJoin:
    """History and the agent bodies meet only at the pi: operation id."""

    def test_the_join_key_is_the_digest_the_agent_runner_writes(self) -> None:
        # PiNativeRunner._run writes exactly this key; a drift here
        # silently empties every transcript in the package
        expected = "pi:" + hashlib.sha256((REVIEW_OPERATION + chr(0) + "2").encode()).hexdigest()
        assert agent_operation_id(REVIEW_OPERATION, 2) == expected

    def test_a_review_attempt_carries_its_request_and_its_response(self, tmp_path: Path) -> None:
        out, _ = build(tmp_path)
        document = transcript(out, REVIEW_OPERATION, 1)
        assert document["kind"] == "review" and document["history_occurrences"] == [2]
        assert document["request"]["history_activity_inputs"][0]["work"]["attempt"] == 1
        assert document["request"]["review_request"] == {"repository": REPOSITORY, "head": "h1"}
        assert document["response"]["body_present"] is True
        assert document["response"]["output_text"] == "output text"
        assert document["pi_operation"]["outcome"] == "completed"
        session = out / "transcripts" / document["response"]["session_jsonl"]
        assert session.read_bytes() == b'{"role":"user"}\n'

    def test_an_operation_with_no_body_is_reported_as_missing_not_dropped(self, tmp_path: Path) -> None:
        # attempt 2 was requested in History but its body did not
        # survive; the package must still show the attempt happened
        out, report = build(tmp_path)
        document = transcript(out, REVIEW_OPERATION, 2)
        assert document["response"]["body_present"] is False
        assert document["history_occurrences"] == [3]
        assert report.numbers["transcripts"]["bodies_missing"] == 1
        assert any(f"{REVIEW_OPERATION} attempt 2" in gap for gap in report.gaps)
        assert f"{REVIEW_OPERATION} attempt 2" in (out / "README.md").read_text(encoding="utf-8")

    def test_a_mutation_operation_joins_through_its_binding_scoped_name(self, tmp_path: Path) -> None:
        # History records only the op_key; the agent id is scoped by the
        # repository and PR from binding.json, so the join needs both
        out, _ = build(tmp_path)
        document = transcript(out, MUTATION_OPERATION, 1)
        assert document["kind"] == "mutation" and document["attempt"] == 1
        assert document["response"]["body_present"] is True

    def test_two_requests_for_one_agent_turn_collapse_to_one_transcript(self, tmp_path: Path) -> None:
        # a mutation gate that reconciles lookup-first is requested
        # again under the same op_key and reuses the SAME agent turn;
        # counting it twice would inflate the join-coverage number
        repeated = [record for record in _history() if record.get("activity") == "git_gate"]
        repeated[0] = {**repeated[0], "occurrence": 8, "instant": 9}
        out, report = build(tmp_path, history=[*_history(), *repeated])
        document = transcript(out, MUTATION_OPERATION, 1)
        assert document["history_occurrences"] == [4, 8]
        assert len(document["request"]["history_activity_inputs"]) == 2
        assert report.numbers["transcripts"]["operations"] == 4

    def test_a_conversation_operation_absent_from_history_is_still_exported(self, tmp_path: Path) -> None:
        # comment classification runs before the ingress manifest, so
        # only agent-routes.sqlite3 proves the operation was dispatched
        out, _ = build(tmp_path)
        document = transcript(out, CONVERSATION_OPERATION, 1)
        assert document["origin"] == "agent-routes" and document["history_occurrences"] == []
        assert document["kind"] == "conversation" and document["response"]["body_present"] is True

    def test_a_body_no_operation_claims_is_exported_as_unattributed(self, tmp_path: Path) -> None:
        orphan = "pi:" + "a" * 64
        out, report = build(tmp_path, bodies=(agent_operation_id(REVIEW_OPERATION, 1), orphan))
        document = json.loads((out / "transcripts" / f"{orphan.replace(':', '-')}.json").read_text(encoding="utf-8"))
        assert document["kind"] == "unattributed" and document["response"]["body_present"] is True
        assert any(orphan in gap for gap in report.gaps)

    def test_the_index_lists_every_operation_with_its_join_outcome(self, tmp_path: Path) -> None:
        out, _ = build(tmp_path)
        index = json.loads((out / "transcripts" / "index.json").read_text(encoding="utf-8"))
        assert {entry["logical_operation"] for entry in index} == {
            REVIEW_OPERATION,
            MUTATION_OPERATION,
            CONVERSATION_OPERATION,
        }
        assert sum(entry["body_present"] for entry in index) == 3


class TestWebhookInbox:
    """Every admitted delivery row travels, whatever its disposition."""

    def test_every_inbox_row_travels_with_its_parsed_observation(self, tmp_path: Path) -> None:
        out, report = build(tmp_path)
        rows = [
            json.loads(line) for line in (out / "webhooks" / "inbox.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert [row["delivery_id"] for row in rows] == [ADMITTED_DELIVERY, SECOND_DELIVERY]
        assert rows[0]["observation"]["action"] == "opened"
        assert report.numbers["webhooks"] == {"rows": 2, "by_event": {"issue_comment": 1, "pull_request": 1}}

    def test_the_readme_says_the_inbox_holds_no_raw_request_body(self, tmp_path: Path) -> None:
        # the inbox persists the derived observation; a reader who
        # assumed these were raw payloads would misreport the evidence
        out, report = build(tmp_path)
        assert any("raw request body" in gap for gap in report.gaps)
        assert "raw request body" in (out / "README.md").read_text(encoding="utf-8")


class TestRawWebhookDeliveries:
    """The inbox decides which raw delivery records this PR may hold.

    The raw records come from outside the state directory, so the inbox
    is the only authority on which of them belong to this pull request.
    Copying one it never admitted would attribute another PR's traffic to
    this journey; dropping one it did admit would hide a delivery.
    """

    def test_a_raw_record_the_inbox_admitted_is_copied_byte_identically(self, tmp_path: Path) -> None:
        source = deliveries(
            tmp_path,
            {f"{ADMITTED_DELIVERY}-pull_request.json": raw_delivery(ADMITTED_DELIVERY, "pull_request", "opened")},
        )
        out, report = build(tmp_path, webhook_deliveries=(source,))
        original = (source / f"{ADMITTED_DELIVERY}-pull_request.json").read_bytes()
        copied = out / "webhooks" / "deliveries" / f"{ADMITTED_DELIVERY}-pull_request.json"
        assert copied.read_bytes() == original
        entry = next(
            item
            for item in json.loads((out / "webhooks" / "deliveries" / "index.json").read_text(encoding="utf-8"))
            if item["delivery_id"] == ADMITTED_DELIVERY
        )
        assert entry["sha256"] == hashlib.sha256(original).hexdigest()
        assert entry["bytes"] == len(original)
        assert report.numbers["raw_deliveries"]["copied"] == 1

    def test_an_inbox_row_with_no_raw_record_is_reported_as_a_gap(self, tmp_path: Path) -> None:
        # a delivery the service admitted but whose payload was never
        # salvaged is missing evidence; staying quiet would read as a
        # package that simply had fewer deliveries
        source = deliveries(
            tmp_path,
            {f"{ADMITTED_DELIVERY}-pull_request.json": raw_delivery(ADMITTED_DELIVERY, "pull_request", "opened")},
        )
        out, report = build(tmp_path, webhook_deliveries=(source,))
        assert report.numbers["raw_deliveries"]["inbox_rows_without_raw"] == [SECOND_DELIVERY]
        assert any(SECOND_DELIVERY in gap and "issue_comment" in gap for gap in report.gaps)
        assert SECOND_DELIVERY in (out / "README.md").read_text(encoding="utf-8")

    def test_a_raw_record_for_another_pull_request_is_counted_never_copied(self, tmp_path: Path) -> None:
        source = deliveries(
            tmp_path,
            {
                f"{ADMITTED_DELIVERY}-pull_request.json": raw_delivery(ADMITTED_DELIVERY, "pull_request", "opened"),
                f"{OTHER_PR_DELIVERY}-workflow_run.json": raw_delivery(OTHER_PR_DELIVERY, "workflow_run", "completed"),
            },
        )
        out, report = build(tmp_path, webhook_deliveries=(source,))
        assert report.numbers["raw_deliveries"]["out_of_scope_files"] == 1
        assert report.numbers["raw_deliveries"]["files_seen"] == 2
        assert not (out / "webhooks" / "deliveries" / f"{OTHER_PR_DELIVERY}-workflow_run.json").exists()
        listing = json.loads((out / "webhooks" / "out-of-scope-deliveries.json").read_text(encoding="utf-8"))
        assert [entry["delivery_id"] for entry in listing["files"]] == [OTHER_PR_DELIVERY]
        assert OTHER_PR_DELIVERY.encode() not in (out / "webhooks" / "deliveries" / "index.json").read_bytes()

    def test_a_redelivered_guid_travels_as_both_of_its_records(self, tmp_path: Path) -> None:
        # GitHub keeps the failed original and its redelivery under one
        # guid; exporting only one would erase the failure
        source = deliveries(
            tmp_path,
            {
                f"{ADMITTED_DELIVERY}-pull_request.json": raw_delivery(ADMITTED_DELIVERY, "pull_request", "opened"),
                f"{ADMITTED_DELIVERY}-pull_request-original-99.json": raw_delivery(
                    ADMITTED_DELIVERY, "pull_request", "opened"
                ),
            },
        )
        out, report = build(tmp_path, webhook_deliveries=(source,))
        assert report.numbers["raw_deliveries"]["copied"] == 2
        assert report.numbers["raw_deliveries"]["matched_deliveries"] == 1
        assert (out / "webhooks" / "deliveries" / f"{ADMITTED_DELIVERY}-pull_request-original-99.json").exists()

    def test_a_file_that_is_not_a_delivery_record_is_named_not_guessed_at(self, tmp_path: Path) -> None:
        source = deliveries(
            tmp_path,
            {
                f"{ADMITTED_DELIVERY}-pull_request.json": raw_delivery(ADMITTED_DELIVERY, "pull_request", "opened"),
                "_deliveries-index.json": [{"guid": ADMITTED_DELIVERY}],
            },
        )
        _, report = build(tmp_path, webhook_deliveries=(source,))
        assert report.numbers["raw_deliveries"]["unrecognized_files"] == [str(source / "_deliveries-index.json")]
        assert any("_deliveries-index.json" in gap for gap in report.gaps)

    def test_omitting_the_flag_is_stated_in_the_manifest_and_the_readme(self, tmp_path: Path) -> None:
        # a package built without raw records must not read like one
        # whose raw records simply did not exist
        out, report = build(tmp_path)
        manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
        assert manifest["raw_deliveries"] == {"supplied": False, "directories": [], "copied": 0}
        assert not (out / "webhooks" / "deliveries").exists()
        assert "no raw GitHub delivery record" in (out / "README.md").read_text(encoding="utf-8")
        assert any("no --webhook-deliveries directory was supplied" in gap for gap in report.gaps)

    def test_a_missing_delivery_directory_refuses_instead_of_reporting_zero(self, tmp_path: Path) -> None:
        # a typo in the path would otherwise produce a package that
        # truthfully reports 0 copied and 0 gaps about it
        source = state_dir(tmp_path)
        with pytest.raises(EvidenceExportError, match="does not exist"):
            export_package(
                state_dir=source,
                out=tmp_path / "package",
                repository=REPOSITORY,
                pull_request=PULL_REQUEST,
                webhook_deliveries=(tmp_path / "absent",),
            )


class TestSessionTranscriptCoverage:
    """Every operation says whether its session transcript survived.

    A session transcript exists only in the `session_jsonl` column of
    `pi_a2_bodies`. An operation with a body and no transcript is
    therefore a turn that appended none, and the package must say which
    turn and why — an unclassified absence reads as data loss.
    """

    def test_a_completed_turn_exports_its_full_session_transcript(self, tmp_path: Path) -> None:
        out, report = build(tmp_path)
        document = transcript(out, REVIEW_OPERATION, 1)
        assert document["coverage"] == "session_exported"
        session = out / "transcripts" / document["response"]["session_jsonl"]
        assert session.read_bytes() == b'{"role":"user"}\n'
        assert document["response"]["session_jsonl_bytes"] == len(session.read_bytes())
        assert report.numbers["transcripts"]["session_jsonl_bytes"] == 3 * len(b'{"role":"user"}\n')

    def test_a_body_without_a_session_is_reported_with_the_reason_not_dropped(self, tmp_path: Path) -> None:
        # the review gate deferred the round, so the agent turn was
        # cancelled before it appended a single transcript line
        cancelled = agent_operation_id(REVIEW_OPERATION, 1)
        out, report = build(tmp_path, sessionless=frozenset({cancelled}))
        document = transcript(out, REVIEW_OPERATION, 1)
        assert document["response"]["body_present"] is True
        assert document["response"]["session_present"] is False
        assert document["coverage"] == "body_without_session"
        assert "cancelled before any transcript line was appended" in document["coverage_reason"]
        assert report.numbers["transcripts"]["coverage"]["body_without_session"] == 1
        assert any("has a body but no session transcript" in gap and cancelled in gap for gap in report.gaps)
        assert cancelled in (out / "README.md").read_text(encoding="utf-8")

    def test_a_deferred_round_with_neither_names_the_deferral_as_its_reason(self, tmp_path: Path) -> None:
        # RoundDeferred is a settled outcome, not lost evidence; the
        # package must distinguish it from an unexplained absence
        out, report = build(tmp_path)
        document = transcript(out, REVIEW_OPERATION, 2)
        assert document["coverage"] == "no_body_no_session"
        assert document["history_terminals"] == ["RoundDeferred"]
        assert "deferred before the agent runtime stored a body" in document["coverage_reason"]
        assert any("RoundDeferred" in gap for gap in report.gaps)

    def test_an_absence_history_cannot_explain_says_so_rather_than_inventing_one(self, tmp_path: Path) -> None:
        history = [record for record in _history() if record.get("result", {}).get("$variant") != "RoundDeferred"]
        out, _ = build(tmp_path, history=history)
        document = transcript(out, REVIEW_OPERATION, 2)
        assert document["coverage"] == "no_body_no_session"
        assert "History does not say why" in document["coverage_reason"]

    def test_the_coverage_classes_account_for_every_operation_exactly_once(self, tmp_path: Path) -> None:
        out, report = build(tmp_path, sessionless=frozenset({agent_operation_id(MUTATION_OPERATION, 1)}))
        coverage = report.numbers["transcripts"]["coverage"]
        assert coverage == {"session_exported": 2, "body_without_session": 1, "no_body_no_session": 1}
        assert sum(coverage.values()) == report.numbers["transcripts"]["operations"]
        index = json.loads((out / "transcripts" / "index.json").read_text(encoding="utf-8"))
        assert sum(entry["session_present"] for entry in index) == coverage["session_exported"]


class TestMissingPiecesAreNamed:
    """A state directory missing a store yields a package that says so."""

    @pytest.mark.parametrize(
        ("store", "phrase"),
        [
            ("bodies", "bodies.sqlite3"),
            ("webhooks", "webhooks.sqlite3"),
            ("agent-routes", "agent-routes.sqlite3"),
            ("review-requests", "review-requests.sqlite3"),
        ],
    )
    def test_an_absent_store_is_named_in_the_readme(self, tmp_path: Path, store: str, phrase: str) -> None:
        out, report = build(tmp_path, omit=frozenset({store}))
        assert any(phrase in gap for gap in report.gaps)
        assert phrase in (out / "README.md").read_text(encoding="utf-8")
        assert (out / "history" / "history.jsonl").exists()

    def test_an_absent_bodies_store_still_lists_every_history_operation(self, tmp_path: Path) -> None:
        out, report = build(tmp_path, omit=frozenset({"bodies"}))
        assert report.numbers["transcripts"]["bodies_joined"] == 0
        assert transcript(out, REVIEW_OPERATION, 1)["response"]["body_present"] is False

    def test_the_absent_run_identity_is_reported_against_the_done_condition(self, tmp_path: Path) -> None:
        # the image sha and petrus pin were never state-directory files;
        # a package that stayed quiet would look complete
        _, report = build(tmp_path)
        assert any("run-identity" in gap for gap in report.gaps)
        assert report.numbers["identity"]["files"] == ["binding.json"]

    def test_a_supplied_identity_file_travels_and_clears_the_gap(self, tmp_path: Path) -> None:
        pins = tmp_path / "pins.md"
        pins.write_text("petrus @ 4e5c2500\nimage sha-7df44260\n", encoding="utf-8")
        source = state_dir(tmp_path)
        out = tmp_path / "package"
        report = export_package(
            state_dir=source,
            out=out,
            repository=REPOSITORY,
            pull_request=PULL_REQUEST,
            identity=(pins,),
        )
        assert (out / "identity" / "pins.md").read_text(encoding="utf-8").startswith("petrus @")
        assert not any("run-identity" in gap for gap in report.gaps)


class TestPackageBoundaries:
    """The exporter never widens custody: no writes, no credentials."""

    def test_a_credential_named_file_is_excluded_and_listed(self, tmp_path: Path) -> None:
        source = state_dir(tmp_path)
        (source / "webhook-secret").write_text("never-copied", encoding="utf-8")
        secret = tmp_path / "hamsterdan.env"
        secret.write_text("HAMSTERDAN_PI_API_KEY=never-copied", encoding="utf-8")
        out = tmp_path / "package"
        report = export_package(
            state_dir=source,
            out=out,
            repository=REPOSITORY,
            pull_request=PULL_REQUEST,
            identity=(secret,),
        )
        assert not (out / "identity" / "hamsterdan.env").exists()
        assert "webhook-secret" in report.numbers["identity"]["excluded_by_name"]
        assert "never-copied" not in (out / "README.md").read_text(encoding="utf-8")
        copied = b"".join(path.read_bytes() for path in out.rglob("*") if path.is_file())
        assert b"never-copied" not in copied

    def test_the_source_state_directory_is_never_written_to(self, tmp_path: Path) -> None:
        # WAL-mode stores roll forward on open; the archive is the only
        # copy of this evidence, so the exporter queries copies
        source = state_dir(tmp_path)
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(source.rglob("*")) if path.is_file()
        }
        export_package(state_dir=source, out=tmp_path / "package", repository=REPOSITORY, pull_request=PULL_REQUEST)
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(source.rglob("*")) if path.is_file()
        }
        assert after == before

    def test_an_unknown_pull_request_refuses_instead_of_writing_an_empty_package(self, tmp_path: Path) -> None:
        source = state_dir(tmp_path)
        out = tmp_path / "package"
        with pytest.raises(EvidenceExportError, match="expected exactly one"):
            export_package(state_dir=source, out=out, repository=REPOSITORY, pull_request=999)
        assert not out.exists()

    def test_a_populated_output_directory_is_refused(self, tmp_path: Path) -> None:
        source = state_dir(tmp_path)
        out = tmp_path / "package"
        out.mkdir()
        (out / "README.md").write_text("earlier package", encoding="utf-8")
        with pytest.raises(EvidenceExportError, match="not empty"):
            export_package(state_dir=source, out=out, repository=REPOSITORY, pull_request=PULL_REQUEST)
        assert (out / "README.md").read_text(encoding="utf-8") == "earlier package"


class TestCommandLine:
    """The CLI reports gaps on stderr; a refusal is not a package."""

    def test_a_successful_run_prints_every_gap_and_the_package_path(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        source = state_dir(tmp_path)
        out = tmp_path / "package"
        code = main(
            [
                "--state-dir",
                str(source),
                "--out",
                str(out),
                "--repository",
                REPOSITORY,
                "--pull-request",
                str(PULL_REQUEST),
            ]
        )
        captured = capsys.readouterr()
        assert code == 0
        assert captured.err.count("GAP: ") == json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))["gaps"]
        assert f"package written to {out}" in captured.out

    def test_a_refused_export_exits_nonzero_with_the_reason(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(
            [
                "--state-dir",
                str(tmp_path / "absent"),
                "--out",
                str(tmp_path / "package"),
                "--repository",
                REPOSITORY,
                "--pull-request",
                str(PULL_REQUEST),
            ]
        )
        assert code == 2
        assert "export failed:" in capsys.readouterr().err
