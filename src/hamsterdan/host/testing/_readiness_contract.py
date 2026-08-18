"""Strict deterministic values shared by the readiness profile and provider."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal, cast

from petrus.testing.dst import Budget, CheckerIdentity, ProfileIdentity, digest_json
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
    "provider_calls": 512,
    "effects": 128,
    "host_followups": 512,
    "pending_custody": 64,
    "runnable": 64,
    "dispatch_entries": 256,
    "payload_bytes": 65_536,
    "history_bytes": 2_097_152,
    "observation_bytes": 2_097_152,
    "wall_watchdog_seconds": 60,
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

_PROFILE_DEFINITION = {
    "topology": "production",
    "limits": PROFILE_LIMITS,
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
    "faults": ["readiness.github.effect"],
}
PROFILE_IDENTITY = ProfileIdentity(
    name="hamsterdan.readiness.production-world",
    version=1,
    digest=digest_json(_PROFILE_DEFINITION),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="hamsterdan.readiness.independent-model",
    version=1,
    digest=digest_json(
        {
            "checks": [
                "expected readiness equals detached host verdict",
                "modeled custody action equals detached host disposition",
                "provider effect identity accepts at most once",
                "independent readiness safety violations remain empty",
            ]
        }
    ),
)
DEFAULT_BUDGET = Budget(
    actions=512,
    queued_commands=64,
    timer_advances=32,
    logical_instant=2_000_000,
    reloads=8,
    predicate_polls=256,
    artifact_bytes=4_194_304,
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
