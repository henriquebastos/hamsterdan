"""Strict deterministic values shared by the readiness profile and provider."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal, cast

from petrus.testing.dst import BudgetV4, CheckerIdentity, ProfileIdentity, digest_json
from pydantic import JsonValue, TypeAdapter

from hamsterdan.testing.readiness import AuthorityClaim

HEAD = "a" * 40
BASE = "b" * 40
SUBJECT = "github:44:31:pr:7"
WEBHOOK_SECRET = "readiness-world-webhook-secret"
BOT = "hamsterdan-test[bot]"

type ProfileDisposition = Literal["applied", "idempotent", "refused_expected", "quarantined"]

PROFILE_LIMITS = {
    "authority_generations": 16,
    "provider_truth_changes": 128,
    "webhook_emissions": 64,
    "delivery_attempts": 128,
    "checks": 64,
    "reviews": 64,
    "findings": 128,
    "comments": 128,
    "threads": 128,
    "agent_operations": 128,
    "git_publications": 64,
    "git_reconciliations": 128,
    "provider_calls": 512,
    "effects": 128,
    "host_followups": 512,
    "pending_custody": 64,
    "runnable": 64,
    "dispatch_entries": 256,
    "reloads": 8,
    "payload_bytes": 65_536,
    "history_bytes": 2_097_152,
    "observation_bytes": 2_097_152,
}

PROFILE_RESOURCE_LIMITS = {
    "retained.host.history_bytes": PROFILE_LIMITS["history_bytes"],
    "retained.host.history_records": 4_096,
    "retained.host.sqlite_bytes": 4_194_304,
    "retained.host.sqlite_rows": 4_096,
    "retained.profile.dropped_generations": PROFILE_LIMITS["reloads"],
    "retained.profile.followups": PROFILE_LIMITS["host_followups"],
    "retained.provider.admissions": PROFILE_LIMITS["webhook_emissions"],
    "retained.provider.agent_operations": PROFILE_LIMITS["agent_operations"],
    "retained.provider.authorities": PROFILE_LIMITS["authority_generations"],
    "retained.provider.bytes": 2_097_152,
    "retained.provider.calls": PROFILE_LIMITS["provider_calls"],
    "retained.provider.checks": PROFILE_LIMITS["checks"],
    "retained.provider.collisions": PROFILE_LIMITS["effects"],
    "retained.provider.comments": PROFILE_LIMITS["comments"],
    "retained.provider.custody_actions": PROFILE_LIMITS["delivery_attempts"],
    "retained.provider.delivery_attempts": PROFILE_LIMITS["delivery_attempts"],
    "retained.provider.effect_bindings": PROFILE_LIMITS["effects"],
    "retained.provider.effects": PROFILE_LIMITS["effects"],
    "retained.provider.findings": PROFILE_LIMITS["findings"],
    "retained.provider.git_publications": PROFILE_LIMITS["git_publications"],
    "retained.provider.git_reconciliations": PROFILE_LIMITS["git_reconciliations"],
    "retained.provider.reviews": PROFILE_LIMITS["reviews"],
    "retained.provider.threads": PROFILE_LIMITS["threads"],
    "retained.provider.truth_changes": PROFILE_LIMITS["provider_truth_changes"],
    "retained.provider.webhooks": PROFILE_LIMITS["webhook_emissions"],
    "pending.host.activities": PROFILE_LIMITS["dispatch_entries"],
    "pending.host.custody": PROFILE_LIMITS["pending_custody"],
    "pending.host.dispatch": PROFILE_LIMITS["dispatch_entries"],
    "pending.host.runnable": PROFILE_LIMITS["runnable"],
    "pending.host.timer_acks": PROFILE_LIMITS["dispatch_entries"],
    "pending.host.timer_maturities": PROFILE_LIMITS["dispatch_entries"],
    "pending.host.timers": PROFILE_LIMITS["dispatch_entries"],
    "pending.profile.proposals": PROFILE_LIMITS["runnable"],
}

_POLICY_CANONICAL = {
    "strict": True,
    "update_required": True,
    "required_checks": ["build"],
    "required_approvals": 0,
    "conversation_resolution": False,
    "source": "effective_rules",
}
READINESS_POLICY_DIGEST = hashlib.sha256(
    json.dumps(_POLICY_CANONICAL, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
REMINDER_DELAY = 86_400

_PROFILE_DEFINITION = {
    "dst_api": "petrus.testing.dst/v4",
    "topology": "v5",
    "reminder_delay": REMINDER_DELAY,
    "limits": PROFILE_LIMITS,
    "resource_limits": PROFILE_RESOURCE_LIMITS,
    "observation_semantics": [
        "effect provider authority is retained at acceptance",
        "readiness effect authorship is bound to the exact outstanding V5 Activity request",
        "semantic admission records provider authority when custody executes",
        "every distinct full admitted authority claim advances the model generation",
        "provider movement does not retroactively invalidate historical effects",
        "dashboard, conversation, and reminder effects are fixed incarnation-bound unfenced kinds",
        "current readiness is an authority-fenced V5 provider effect",
        (
            "reminder identity, incarnation, sequence, head, due, maturity, and status derive from "
            "admitted authority, logical time, and provider acceptance"
        ),
        "timer custody is detached from the durable V5 host boundary",
        "detached host state is the durable V5 authority grant, never a Petri marking",
        "authorized Git publication is derived from one admitted human comment and exact operation identity",
        "Git ref acceptance and lookup-first recovery live in independent modeled provider truth",
        "ambiguous Git recovery requires one admitted human grant naming the exact operation",
    ],
    "commands": [
        "readiness.agent.terminal",
        "readiness.github.ci.set",
        "readiness.github.effect.reveal",
        "readiness.github.human.comment",
        "readiness.github.human.resolve_thread",
        "readiness.github.human.review",
        "readiness.github.pr.set",
        "readiness.github.review.set",
        "readiness.github.webhook.deliver",
        "readiness.github.webhook.emit",
        "readiness.host.activity_one",
        "readiness.host.custody_one",
        "readiness.host.drive_one",
        "readiness.host.reconcile_one",
        "readiness.time.advance",
    ],
    "observations": ["readiness.state"],
    "faults": ["readiness.github.effect", "readiness.git.publish"],
}
PROFILE_IDENTITY = ProfileIdentity(
    name="hamsterdan.readiness.v5-world",
    version=2,
    digest=digest_json(_PROFILE_DEFINITION),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="hamsterdan.readiness.independent-model",
    version=4,
    digest=digest_json(
        {
            "checks": [
                "expected readiness equals the current authority-fenced V5 provider effect after disclosed work drains",
                "only disclosed eligible work permits transient readiness-publication lag",
                "durable V5 grant matches active or quiescent authority and terminal lifecycle",
                (
                    "independent reminder identity, authority, due/maturity instants, and status match "
                    "detached durable V5 timer custody after disclosed work drains"
                ),
                "modeled custody action equals detached host disposition",
                "provider effect identity accepts at most once",
                "authorized Git acceptance matches canonical V5 request and terminal recovery",
                "lookup-first Git recovery retains its exact admitted human grant",
                "independent readiness safety violations remain empty",
            ]
        }
    ),
)
DEFAULT_BUDGET = BudgetV4(
    actions=512,
    queued_commands=64,
    timer_advances=32,
    logical_instant=2_000_000,
    reloads=PROFILE_LIMITS["reloads"],
    predicate_polls=256,
    artifact_bytes=4_194_304,
    profile_resources=PROFILE_RESOURCE_LIMITS,
)

COMMAND_KEYS = {
    "readiness.github.pr.set": {"subject", "authority"},
    "readiness.github.ci.set": {"subject", "head", "required_checks", "checks"},
    "readiness.github.review.set": {"subject", "head", "status", "findings"},
    "readiness.github.human.review": {"subject", "review", "reviewer", "head", "state"},
    "readiness.github.human.comment": {"subject", "comment", "author", "fixture", "digest"},
    "readiness.github.human.resolve_thread": {"subject", "thread", "resolver", "resolved"},
    "readiness.github.webhook.emit": {"subject", "delivery", "event", "fixture", "digest"},
    "readiness.github.webhook.deliver": {"delivery"},
    "readiness.agent.terminal": {"subject", "operation", "attempt", "status", "fixture", "digest"},
    "readiness.github.effect.reveal": {"subject", "operation"},
    "readiness.host.custody_one": set(),
    "readiness.host.drive_one": set(),
    "readiness.host.activity_one": set(),
    "readiness.host.reconcile_one": set(),
    "readiness.time.advance": {"seconds"},
}
HOST_COMMANDS = frozenset(name for name in COMMAND_KEYS if name.startswith("readiness.host."))
SHA = re.compile(r"[0-9a-f]{40}")
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}")
OPERATION = re.compile(r"[A-Za-z][A-Za-z0-9_./:-]{0,255}")
EVENTS = frozenset(
    {
        "issue_comment",
        "pull_request",
        "pull_request_review",
        "pull_request_review_thread",
        "workflow_job",
        "workflow_run",
    }
)
EFFECT_KINDS = frozenset({"conversation", "dashboard", "finding", "readiness", "reminder"})


def strict_object(value: JsonValue, keys: set[str], label: str) -> dict[str, JsonValue]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{label} requires exact fields {sorted(keys)}")
    return cast(dict[str, JsonValue], value)


def parse_authority(value: object) -> AuthorityClaim:
    return TypeAdapter(AuthorityClaim).validate_json(json.dumps(value, sort_keys=True, separators=(",", ":")))


def strict_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def bounded_text(value: JsonValue, label: str, *, pattern: re.Pattern[str] | None = None) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > 20_000
        or (pattern is not None and pattern.fullmatch(value) is None)
    ):
        raise ValueError(f"{label} is outside its closed bounded vocabulary")
    return value


def bounded_json(value: object, limit: int, label: str) -> bytes:
    encoded = json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > limit:
        raise ValueError(f"{label} has {len(encoded)} bytes; limit is {limit}")
    return encoded
