"""Credential-free typed agent protocol and Amp execution adapter."""

from .amp import AmpExecuteRunner
from .protocol import (
    AgentProtocolError,
    AgentRunner,
    ChangeRequest,
    ChangeResult,
    CodingRequest,
    CodingResult,
    ConversationRequest,
    ConversationResult,
    RepairRequest,
    RepairResult,
    ReviewRequest,
    ReviewResult,
)

__all__ = [
    "AgentProtocolError",
    "AgentRunner",
    "AmpExecuteRunner",
    "ChangeRequest",
    "ChangeResult",
    "CodingRequest",
    "CodingResult",
    "ConversationRequest",
    "ConversationResult",
    "RepairRequest",
    "RepairResult",
    "ReviewRequest",
    "ReviewResult",
]
