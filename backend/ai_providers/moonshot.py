"""
月之暗面 (Moonshot AI / Kimi) Provider
使用 OpenAI 兼容接口
"""

from typing import List, AsyncGenerator

from .base import BaseProvider, ProviderConfig, Message, ChatResponse, DEFAULT_PROVIDER_TIMEOUT


class MoonshotProvider(BaseProvider):
    """月之暗面 Kimi Provider"""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None
    
    def _get_client(self):
        """延迟初始化 LangChain 客户端"""
        if self._client is None:
            try:
                from langchain_openai import ChatOpenAI
                self._client = ChatOpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url or 'https://api.moonshot.cn/v1',
                    model=self.config.model or 'moonshot-v1-8k',
                    temperature=0.7,
                    max_tokens=2048,
                    request_timeout=DEFAULT_PROVIDER_TIMEOUT,
                )
            except ImportError:
                raise ImportError("langchain_openai is required for MoonshotProvider")
        return self._client
    
    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        """非流式对话"""
        client = self._get_client()
        
        lc_messages = [
            ("system" if m.role == "system" else 
             "human" if m.role == "user" else "ai", m.content)
            for m in messages
        ]
        
        response = await client.ainvoke(lc_messages)
        
        return ChatResponse(
            content=response.content,
            provider=self.name,
            model=self.model or 'moonshot-v1-8k',
            usage=getattr(response, 'usage', None),
            raw_response=response
        )
    
    async def chat_stream(self, messages: List[Message], **kwargs) -> AsyncGenerator[str, None]:
        """流式对话"""
        client = self._get_client()
        
        lc_messages = [
            ("system" if m.role == "system" else 
             "human" if m.role == "user" else "ai", m.content)
            for m in messages
        ]
        
        async for chunk in client.astream(lc_messages):
            if chunk.content:
                yield chunk.content


# 别名
KimiProvider = MoonshotProvider
