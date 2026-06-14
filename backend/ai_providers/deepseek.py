"""
DeepSeek Provider
Uses the OpenAI-compatible chat API.
"""

from typing import List, AsyncGenerator

from .base import BaseProvider, ProviderConfig, Message, ChatResponse, DEFAULT_PROVIDER_TIMEOUT


class DeepSeekProvider(BaseProvider):
    """DeepSeek OpenAI-compatible provider."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from langchain_openai import ChatOpenAI
                self._client = ChatOpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url or 'https://api.deepseek.com',
                    model=self.config.model or 'deepseek-v4-pro',
                    temperature=0.7,
                    max_tokens=2048,
                    request_timeout=DEFAULT_PROVIDER_TIMEOUT,
                )
            except ImportError:
                raise ImportError("langchain_openai is required for DeepSeekProvider")
        return self._client

    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        client = self._get_client()
        lc_messages = [
            (
                "system" if message.role == "system"
                else "human" if message.role == "user"
                else "ai",
                message.content,
            )
            for message in messages
        ]
        response = await client.ainvoke(lc_messages)

        return ChatResponse(
            content=response.content,
            provider=self.name,
            model=self.config.model or 'deepseek-v4-pro',
            usage=getattr(response, 'usage', None),
            raw_response=response,
        )

    async def chat_stream(self, messages: List[Message], **kwargs) -> AsyncGenerator[str, None]:
        client = self._get_client()
        lc_messages = [
            (
                "system" if message.role == "system"
                else "human" if message.role == "user"
                else "ai",
                message.content,
            )
            for message in messages
        ]

        async for chunk in client.astream(lc_messages):
            if chunk.content:
                yield chunk.content
