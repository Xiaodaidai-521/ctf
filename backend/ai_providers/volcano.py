"""Volcano Engine provider using the existing LangChain integration."""

import time
from typing import List, AsyncGenerator

from ai_assistant.performance import current_metrics
from .base import BaseProvider, ProviderConfig, Message, ChatResponse, DEFAULT_PROVIDER_TIMEOUT, extract_usage


class VolcanoProvider(BaseProvider):
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        if self._client is None:
            from langchain_openai import ChatOpenAI
            self._client = ChatOpenAI(
                api_key=self.config.api_key, base_url=self.config.base_url,
                model=self.config.model or "doubao-seed-2-0-lite-260428",
                temperature=0.7, max_tokens=1024, request_timeout=DEFAULT_PROVIDER_TIMEOUT,
            )
        return self._client

    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        started = time.monotonic()
        usage = None
        try:
            response = await self._get_client().ainvoke([
                ("system" if message.role == "system" else "human" if message.role == "user" else "ai", message.content)
                for message in messages
            ])
            usage = extract_usage(response)
            return ChatResponse(content=response.content, provider=self.name, model=self.model or "doubao-seed-2-0-mini-260215", usage=usage, raw_response=response)
        finally:
            metrics = current_metrics()
            if metrics:
                metrics.record_llm(duration_ms=(time.monotonic() - started) * 1000, usage=usage)

    async def chat_stream(self, messages: List[Message], **kwargs) -> AsyncGenerator[str, None]:
        async for chunk in self._get_client().astream([
            ("system" if message.role == "system" else "human" if message.role == "user" else "ai", message.content)
            for message in messages
        ]):
            if chunk.content:
                yield chunk.content

    def is_available(self):
        return super().is_available() and bool(self.config.base_url)


ArkProvider = VolcanoProvider
