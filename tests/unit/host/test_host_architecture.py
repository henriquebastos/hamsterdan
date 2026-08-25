"""Assert credential isolation at the host-agent contract."""

from dataclasses import fields

from hamsterdan.agents import CodingRequest, ConversationRequest, ReviewRequest


def test_agent_requests_are_credential_free() -> None:
    request_fields = {
        field.name.casefold() for kind in (ReviewRequest, ConversationRequest, CodingRequest) for field in fields(kind)
    }
    for forbidden in ("github_token", "installation_token", "private_key", "credential"):
        assert forbidden not in request_fields
