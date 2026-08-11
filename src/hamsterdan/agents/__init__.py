"""Credential-free typed agent protocol and Amp execution adapter."""

from .amp import AmpExecuteRunner
from .pi import PiNativeRunner, UnavailablePiRunner, encode_prompt
from .protocol import (
    AgentCleanupCategory,
    AgentProtocolError,
    AgentResultCategory,
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
    "AgentCleanupCategory",
    "AgentProtocolError",
    "AgentResultCategory",
    "AgentRunner",
    "AmpExecuteRunner",
    "ChangeRequest",
    "ChangeResult",
    "CodingRequest",
    "CodingResult",
    "ConversationRequest",
    "ConversationResult",
    "PiNativeRunner",
    "RepairRequest",
    "RepairResult",
    "ReviewRequest",
    "ReviewResult",
    "UnavailablePiRunner",
    "encode_prompt",
]
