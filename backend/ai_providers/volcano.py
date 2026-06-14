"""
火山引擎 (Volcano Engine / Ark) Provider
使用 OpenAI 兼容接口
"""

import os
from typing import List, Optional, AsyncGenerator

from .base import BaseProvider, ProviderConfig, Message, ChatResponse, DEFAULT_PROVIDER_TIMEOUT


class VolcanoProvider(BaseProvider):
    """火山引擎 Ark Provider"""
    
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
                    base_url=self.config.base_url,
                    model=self.config.model or 'doubao-seed-2-0-lite-260428',
                    temperature=0.7,
                    max_tokens=1024,
                    request_timeout=DEFAULT_PROVIDER_TIMEOUT,
                )
            except ImportError:
                raise ImportError("langchain_openai is required for VolcanoProvider")
        return self._client
    
    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        """非流式对话"""
        client = self._get_client()
        
        # 转换消息格式
        lc_messages = [
            ("system" if m.role == "system" else 
             "human" if m.role == "user" else "ai", m.content)
            for m in messages
        ]
        
        # 调用API
        response = await client.ainvoke(lc_messages)
        
        return ChatResponse(
            content=response.content,
            provider=self.name,
            model=self.model or 'doubao-seed-2-0-mini-260215',
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
    
    def is_available(self) -> bool:
        """检查是否可用"""
        return super().is_available() and bool(self.config.base_url)


# 兼容旧代码的别名
ArkProvider = VolcanoProvider
