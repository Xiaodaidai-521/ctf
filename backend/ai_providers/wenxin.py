"""
百度文心一言 (Wenxin Yiyan / ERNIE Bot) Provider
使用百度千帆 API
"""

import json
from typing import List, AsyncGenerator

from .base import BaseProvider, ProviderConfig, Message, ChatResponse, DEFAULT_PROVIDER_TIMEOUT


class WenxinProvider(BaseProvider):
    """百度文心一言 Provider"""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.access_token = None
    
    def _get_access_token(self) -> str:
        """获取百度访问令牌（简化版，实际应该缓存）"""
        # 注意：实际生产环境应该缓存token，避免频繁请求
        import requests
        
        # 从 API Key 解析 AK/SK
        # 百度 API Key 格式通常是 AK|SK 或需要单独配置
        api_key = self.config.api_key
        if '|' in api_key:
            ak, sk = api_key.split('|', 1)
        else:
            # 从环境变量获取
            import os
            ak = os.getenv('WENXIN_AK', api_key)
            sk = os.getenv('WENXIN_SK', '')
        
        url = f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={ak}&client_secret={sk}"
        response = requests.post(url, timeout=DEFAULT_PROVIDER_TIMEOUT)
        result = response.json()
        return result.get('access_token', '')
    
    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        """非流式对话"""
        import aiohttp
        
        if not self.access_token:
            self.access_token = self._get_access_token()
        
        url = f"{self.config.base_url}/completions?access_token={self.access_token}"
        
        # 转换消息格式为百度格式
        # 百度格式：messages 数组，每个有 role/content
        payload = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get('temperature', 0.7),
            "max_output_tokens": kwargs.get('max_tokens', 2048),
        }
        
        timeout = aiohttp.ClientTimeout(total=DEFAULT_PROVIDER_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                result = await response.json()
                
                if 'error_code' in result:
                    raise Exception(f"Wenxin API error: {result}")
                
                return ChatResponse(
                    content=result.get('result', ''),
                    provider=self.name,
                    model=self.model or 'ernie-bot-4',
                    usage=result.get('usage'),
                    raw_response=result
                )
    
    async def chat_stream(self, messages: List[Message], **kwargs) -> AsyncGenerator[str, None]:
        """流式对话"""
        import aiohttp
        
        if not self.access_token:
            self.access_token = self._get_access_token()
        
        url = f"{self.config.base_url}/completions?access_token={self.access_token}"
        
        payload = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get('temperature', 0.7),
            "max_output_tokens": kwargs.get('max_tokens', 2048),
            "stream": True,
        }
        
        timeout = aiohttp.ClientTimeout(total=DEFAULT_PROVIDER_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data:'):
                        data = json.loads(line[5:])
                        if 'result' in data:
                            yield data['result']


# 别名
BaiduProvider = WenxinProvider
ErnieProvider = WenxinProvider
