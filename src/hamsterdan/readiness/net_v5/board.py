"""Render the dashboard entries as a human decision board.

The dashboard loop's entry log is the projection identity (digest,
self-heal, close-frozen history) and stays untouched; this module is
the PRESENTATION of that log at the publication seam. The board answers
exactly three reader questions, in order: can this merge, who acts
next, and which head does the answer refer to. Latest fact per concern
wins — transient states (queued, in_progress) are folded away, and the
readiness ANNOUNCEMENT stays with the advisory comment: an all-clear
board points at it, never announces.

An entry this renderer cannot parse is shown verbatim in the attention
list instead of faulting the upsert: a render fault would wedge the
board behind the manual recovery door, which is a worse outcome for a
display-only surface than one ugly row.
"""

from __future__ import annotations

from ast import literal_eval
from collections.abc import Mapping, Sequence

_CHECKS_CELL = {
    "pending": "⏳ not started",
    "queued": "⏳ queued",
    "in_progress": "⏳ in progress",
    "success": "✅ success",
    "failure": "❌ failing",
}

_REVIEW_CELL = {
    "pending": "⏳ reviewing",
    "clear": "✅ clear",
    "blocking": "❌ blocking",
    "unable": "⚠️ unable",
}


def _parsed(entry: str) -> tuple[str, Mapping] | None:
    kind, separator, raw = entry.partition(":")
    if not separator:
        return None
    try:
        body = literal_eval(raw)
    except ValueError, SyntaxError:
        return None
    if not isinstance(body, Mapping):
        return None
    return kind, body


def _short(sha: object) -> str:
    return str(sha)[:7]


class _Facts:
    """The latest fact per concern, plus the paired open/closed sets."""

    def __init__(self, entries: Sequence[str]) -> None:
        self.latest: dict[str, Mapping] = {}
        self.faults: dict[tuple[str, str], Mapping] = {}
        self.mutations: dict[str, Mapping] = {}
        self.human_needed: Mapping | None = None
        self.unparsed: list[str] = []
        for entry in entries:
            parsed = _parsed(entry)
            if parsed is None:
                self.unparsed.append(entry)
                continue
            kind, body = parsed
            self.latest[kind] = body
            if kind == "fault":
                key = (str(body.get("where", "")), str(body.get("op", "")))
                if body.get("status") in ("resolved", "cancelled"):
                    self.faults.pop(key, None)
                else:
                    self.faults[key] = body
            elif kind == "mutation_pending":
                self.mutations[str(body.get("op_key", ""))] = body
            elif kind == "mutation_settled":
                self.mutations.pop(str(body.get("op_key", "")), None)
            elif kind == "human_needed":
                self.human_needed = body
            elif kind == "checks":
                # fresh CI evidence obsoletes the exhausted-ladder escalation
                self.human_needed = None


def _verdict(facts: _Facts) -> str:
    state = facts.latest.get("state", {})
    checks = str(facts.latest.get("checks", {}).get("status", "pending"))
    review = facts.latest.get("review", {})
    findings = facts.latest.get("findings", {})
    human = facts.latest.get("human", {})
    head = _short(state.get("head", ""))
    if state.get("phase") == "terminal":
        return "closed — this board is frozen."
    if state.get("phase") == "quiescent":
        return "paused — draft PR. I resume when it leaves draft."
    if facts.faults:
        (_, op), body = next(iter(facts.faults.items()))
        reason = str(body.get("reason", ""))
        return f"⚠️ needs attention — operation `{op}` faulted: {reason}. Ask me to recover it."
    if facts.human_needed is not None:
        return f"❌ CI keeps failing on `{head}` — automated reruns are exhausted. **A human needs to look.**"
    if facts.mutations:
        return f"🔧 working — I'm pushing an update to `{head}`."
    if checks == "failure":
        return f"❌ CI failed for `{head}`. **Author:** fix and push; I re-evaluate the new head."
    if int(findings.get("blocking", 0) or 0) > 0:
        blocking, count = findings["blocking"], findings.get("count", findings["blocking"])
        return f"❌ {blocking} blocking finding(s) of {count} on `{head}`. **Author:** see the review findings."
    if review.get("status") == "unable":
        return (
            f"⚠️ I could not review `{head}` ({review.get('category', 'unable')}). Push a new head or ask me to retry."
        )
    if human.get("changes_requested"):
        return f"waiting on author — a reviewer requested changes on `{head}`."
    if int(human.get("unresolved", 0) or 0) > 0:
        return f"waiting on humans — {human['unresolved']} unresolved review thread(s) on `{head}`."
    if not state.get("base_current", False):
        return f"⚠️ base is stale — the target branch moved past `{_short(state.get('base', ''))}`. **Author:** update the branch."
    if not state.get("mergeable", True):
        return f"❌ merge conflict on `{head}`. **Author:** resolve and push."
    if checks in ("pending", "queued", "in_progress"):
        return f"⏳ waiting on CI for `{head}`. Nothing for you to do."
    if review.get("status") != "clear":
        return f"⏳ reviewing `{head}`. Nothing for you to do."
    if not human.get("approval", False):
        return f"waiting on human approval for `{head}` — everything on my side is clear."
    return f"✅ all gates clear for `{head}` — see the readiness advisory. Merging stays yours."


def _review_cell(facts: _Facts) -> str:
    review = facts.latest.get("review", {})
    findings = facts.latest.get("findings", {})
    status = str(review.get("status", "pending"))
    cell = _REVIEW_CELL.get(status, f"⚠️ {status}")
    if status == "unable":
        category = str(review.get("category", ""))
        return cell if category in ("", "unable") else f"{cell} · {category}"
    if "count" in findings:
        count = int(findings["count"] or 0)
        if count == 0:
            return f"{cell} · 0 findings"
        return f"{cell} · {findings.get('blocking', 0)} blocking of {count} finding(s)"
    return cell


def _human_cell(facts: _Facts) -> str:
    human = facts.latest.get("human", {})
    if not human:
        return "⏳ no review yet"
    approval = "✅ approved" if human.get("approval") else "⏳ not approved"
    if human.get("changes_requested"):
        approval = "❌ changes requested"
    return f"{approval} · {human.get('unresolved', 0)} unresolved thread(s)"


def _rows(facts: _Facts) -> list[tuple[str, str]]:
    state = facts.latest.get("state", {})
    checks = str(facts.latest.get("checks", {}).get("status", "pending"))
    base = _short(state.get("base", ""))
    return [
        ("CI checks", _CHECKS_CELL.get(checks, f"⚠️ {checks}")),
        ("Dan's review", _review_cell(facts)),
        ("Human review", _human_cell(facts)),
        ("Base", f"✅ current with `{base}`" if state.get("base_current") else f"⚠️ behind `{base}`"),
        ("Conflicts", "✅ none" if state.get("mergeable", True) else "❌ merge conflict"),
    ]


def _attention(facts: _Facts) -> list[str]:
    lines = []
    for (where, op), body in facts.faults.items():
        reason = str(body.get("reason", ""))
        lines.append(f"- ⚠️ {where} operation `{op}` faulted: {reason} — ask me to recover it.")
    for body in facts.mutations.values():
        lines.append(f"- 🔧 push in flight: `{body.get('op', '')}`.")
    if facts.human_needed is not None:
        fingerprint = _short(facts.human_needed.get("fingerprint", ""))
        lines.append(f"- ❌ CI failure `{fingerprint}` exhausted automated reruns — a human needs to look.")
    lines.extend(f"- ⚠️ unrecognized: `{entry}`" for entry in facts.unparsed)
    return lines


def render_board(entries: Sequence[str]) -> str:
    facts = _Facts(entries)
    table = "\n".join(f"| {gate} | {cell} |" for gate, cell in _rows(facts))
    sections = [
        f"## Hamsterdan summary — {_verdict(facts)}",
        f"| Gate | State |\n|------|-------|\n{table}",
    ]
    attention = _attention(facts)
    if attention:
        sections.append("\n".join(attention))
    state = facts.latest.get("state", {})
    if state.get("head"):
        # full shas, not shorts: the reader's trust anchor, and GitHub
        # auto-links full commit shas in prose
        sections.append(f"<sub>head {state['head']} on base {state.get('base', '')}</sub>")
    return "\n\n".join(sections)
