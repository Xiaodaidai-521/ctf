"""
阿里通义千问 (Qwen / DashScope) Provider
使用阿里云 DashScope API
"""

import json
from typing import List, AsyncGenerator

from .base import BaseProvider, ProviderConfig, Message, ChatResponse, DEFAULT_PROVIDER_TIMEOUT


class QwenProvider(BaseProvider):
    """通义千问 Provider"""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None
    
    def _get_client(self):
        """延迟初始化 LangChain 客户端（OpenAI 兼容）"""
        if self._client is None:
            try:
                from langchain_openai import ChatOpenAI
                self._client = ChatOpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url or 'https://dashscope.aliyuncs.com/compatible-mode/v1',
                    model=self.config.model or 'qwen-max',
                    temperature=0.7,
                    max_tokens=2048,
                    request_timeout=DEFAULT_PROVIDER_TIMEOUT,
                )
            except ImportError:
                raise ImportError("langchain_openai is required for QwenProvider")
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
            model=self.config.model or 'qwen-max',
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
DashScopeProvider = QwenProvider
AlibabaProvider = QwenProvider
