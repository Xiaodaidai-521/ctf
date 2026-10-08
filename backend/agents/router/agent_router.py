"""Backward-compatible import path for the canonical tutoring router."""

from .tutor_router import TutorAgentRouter

AgentRouter = TutorAgentRouter

__all__ = ["AgentRouter"]
