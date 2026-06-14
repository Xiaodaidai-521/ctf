"""
讯飞星火 (iFlytek Spark) Provider
使用讯飞星火认知大模型 API（WebSocket）
"""

import json
from typing import List, AsyncGenerator

from .base import BaseProvider, ProviderConfig, Message, ChatResponse, DEFAULT_PROVIDER_TIMEOUT


class SparkProvider(BaseProvider):
    """讯飞星火 Provider"""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
    
    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        """
        非流式对话
        
        讯飞星火使用 WebSocket 协议，这里用非流式方式收集完整响应。
        """
        import asyncio
        import websockets
        
        # 解析 API Key（格式：APPID|APIKey|APISecret）
        api_key = self.config.api_key
        if '|' in api_key:
            parts = api_key.split('|')
            app_id = parts[0]
            api_key = parts[1] if len(parts) > 1 else ''
            api_secret = parts[2] if len(parts) > 2 else ''
        else:
            import os
            app_id = os.getenv('SPARK_APP_ID', '')
            api_key = os.getenv('SPARK_API_KEY', api_key)
            api_secret = os.getenv('SPARK_SECRET', '')
        
        if not all([app_id, api_key, api_secret]):
            raise Exception("Spark provider requires APPID, APIKey and APISecret")
        
        # 生成鉴权 URL
        auth_url = self._create_auth_url(
            host='spark-api.xf-yun.com',
            path=f'/v{self.model or "3.5"}/chat',
            api_key=api_key,
            api_secret=api_secret,
        )
        
        # 构建请求参数
        payload = {
            "header": {
                "app_id": app_id,
                "uid": f"ctf_{id(self)}"
            },
            "parameter": {
                "chat": {
                    "domain": self.model or 'generalv3.5',
                    "temperature": kwargs.get('temperature', 0.7),
                    "max_tokens": kwargs.get('max_tokens', 2048),
                }
            },
            "payload": {
                "message": {
                    "text": [
                        {"role": m.role, "content": m.content} for m in messages
                    ]
                }
            }
        }
        
        full_content = []
        
        async with websockets.connect(
            auth_url,
            open_timeout=DEFAULT_PROVIDER_TIMEOUT,
            ping_timeout=DEFAULT_PROVIDER_TIMEOUT,
            close_timeout=DEFAULT_PROVIDER_TIMEOUT,
        ) as ws:
            await ws.send(json.dumps(payload))
            
            while True:
                response = await asyncio.wait_for(ws.recv(), timeout=DEFAULT_PROVIDER_TIMEOUT)
                
                if isinstance(response, bytes):
                    response = response.decode('utf-8')
                
                data = json.loads(response)
                
                header = data.get('header', {})
                code = header.get('code', -1)
                
                if code != 0:
                    raise Exception(f"Spark API error: {data}")
                
                payload_data = data.get('payload', {})
                choices = payload_data.get('choices', {})
                text = choices.get('text', [])
                
                for item in text:
                    content = item.get('content', '')
                    if content:
                        full_content.append(content)
                
                status = choices.get('status', -1)
                if status == 2:  # 最后一条消息
                    break
        
        return ChatResponse(
            content=''.join(full_content),
            provider=self.name,
            model=self.model or 'generalv3.5',
            raw_response={'full_content': full_content}
        )
    
    async def chat_stream(self, messages: List[Message], **kwargs) -> AsyncGenerator[str, None]:
        """流式对话"""
        import asyncio
        import websockets
        
        api_key = self.config.api_key
        if '|' in api_key:
            parts = api_key.split('|')
            app_id = parts[0]
            api_key = parts[1] if len(parts) > 1 else ''
            api_secret = parts[2] if len(parts) > 2 else ''
        else:
            import os
            app_id = os.getenv('SPARK_APP_ID', '')
            api_key = os.getenv('SPARK_API_KEY', api_key)
            api_secret = os.getenv('SPARK_SECRET', '')
        
        auth_url = self._create_auth_url(
            host='spark-api.xf-yun.com',
            path=f'/v{self.model or "3.5"}/chat',
            api_key=api_key,
            api_secret=api_secret,
        )
        
        payload = {
            "header": {"app_id": app_id, "uid": f"ctf_{id(self)}"},
            "parameter": {
                "chat": {
                    "domain": self.model or 'generalv3.5',
                    "temperature": kwargs.get('temperature', 0.7),
                    "max_tokens": kwargs.get('max_tokens', 2048),
                }
            },
            "payload": {
                "message": {
                    "text": [{"role": m.role, "content": m.content} for m in messages]
                }
            }
        }
        
        async with websockets.connect(
            auth_url,
            open_timeout=DEFAULT_PROVIDER_TIMEOUT,
            ping_timeout=DEFAULT_PROVIDER_TIMEOUT,
            close_timeout=DEFAULT_PROVIDER_TIMEOUT,
        ) as ws:
            await ws.send(json.dumps(payload))
            
            while True:
                response = await asyncio.wait_for(ws.recv(), timeout=DEFAULT_PROVIDER_TIMEOUT)
                if isinstance(response, bytes):
                    response = response.decode('utf-8')
                
                data = json.loads(response)
                header = data.get('header', {})
                if header.get('code', -1) != 0:
                    raise Exception(f"Spark API error: {data}")
                
                choices = data.get('payload', {}).get('choices', {})
                text = choices.get('text', [])
                for item in text:
                    content = item.get('content', '')
                    if content:
                        yield content
                
                if choices.get('status', -1) == 2:
                    break
    
    @staticmethod
    def _create_auth_url(host: str, path: str, api_key: str, api_secret: str) -> str:
        """生成讯飞 WebSocket 鉴权 URL"""
        import hmac
        hashlib_module = __import__('hashlib')
        base64_module = __import__('base64')
        urllib_parse = __import__('urllib.parse')
        
        now = int(__import__('time').time())
        signature_origin = f"host: {host}\ndate: {__import__('datetime').datetime.utcfromtimestamp(now).strftime('%a, %d %b %Y %H:%M:%S GMT')}\n{path}\nHTTP/1.1"
        
        signature_sha = hmac.new(
            api_secret.encode('utf-8'),
            signature_origin.encode('utf-8'),
            digestmod=hashlib_module.sha256
        ).digest()
        signature = base64_module.b64encode(signature_sha).decode(encoding='utf-8')
        
        authorization_origin = (
            f'api_key="{api_key}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature}"'
        )
        authorization = base64_module.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
        
        url = f"wss://{host}{path}?authorization={authorization}&date={now}&host={host}"
        return url


# 别名
IFlytekProvider = SparkProvider
