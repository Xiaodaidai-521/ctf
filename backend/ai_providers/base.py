"""AI provider abstractions."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, AsyncGenerator
from dataclasses import dataclass

DEFAULT_PROVIDER_TIMEOUT = 120


def ensure_langchain_compat():
    try:
        import langchain
    except ImportError:
        return
    for name, value in {"verbose": False, "debug": False, "llm_cache": None}.items():
        if not hasattr(langchain, name):
            setattr(langchain, name, value)


ensure_langchain_compat()


def extract_usage(response):
    """Normalize LangChain/OpenAI usage without estimating missing values."""
    usage = getattr(response, "usage_metadata", None) or getattr(response, "usage", None)
    if not usage:
        metadata = getattr(response, "response_metadata", None) or {}
        usage = metadata.get("token_usage") or metadata.get("usage")
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
    completion = usage.get("completion_tokens", usage.get("output_tokens"))
    total = usage.get("total_tokens")
    normalized = {
        "prompt_tokens": int(prompt) if isinstance(prompt, int) else None,
        "completion_tokens": int(completion) if isinstance(completion, int) else None,
        "total_tokens": int(total) if isinstance(total, int) else None,
    }
    return normalized if any(value is not None for value in normalized.values()) else None


@dataclass
class Message:
    role: str
    content: str


@dataclass
class ChatResponse:
    content: str
    provider: str
    model: str
    usage: Optional[Dict] = None
    raw_response: Optional[Any] = None


@dataclass
class ProviderConfig:
    name: str
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    enabled: bool = True


class BaseProvider(ABC):
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.name = config.name
        self.model = config.model

    @abstractmethod
    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        pass

    @abstractmethod
    async def chat_stream(self, messages: List[Message], **kwargs) -> AsyncGenerator[str, None]:
        pass

    def is_available(self) -> bool:
        return self.config.enabled and bool(self.config.api_key)

    def _format_messages(self, messages: List[Message]) -> List[Dict]:
        return [{"role": message.role, "content": message.content} for message in messages]

    def _get_headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.config.api_key}"}
