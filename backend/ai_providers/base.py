"""
AI Provider 抽象基类
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, AsyncGenerator
from dataclasses import dataclass

DEFAULT_PROVIDER_TIMEOUT = 120


def ensure_langchain_compat():
    """Patch LangChain 1.x globals expected by older integration packages."""
    try:
        import langchain
    except ImportError:
        return

    defaults = {
        'verbose': False,
        'debug': False,
        'llm_cache': None,
    }
    for name, value in defaults.items():
        if not hasattr(langchain, name):
            setattr(langchain, name, value)


ensure_langchain_compat()


@dataclass
class Message:
    """标准消息格式"""
    role: str  # system/user/assistant
    content: str


@dataclass
class ChatResponse:
    """标准响应格式"""
    content: str
    provider: str
    model: str
    usage: Optional[Dict] = None
    raw_response: Optional[Any] = None


@dataclass
class ProviderConfig:
    """厂商配置"""
    name: str
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    enabled: bool = True


class BaseProvider(ABC):
    """AI Provider 抽象基类"""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.name = config.name
        self.model = config.model
    
    @abstractmethod
    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        """
        非流式对话
        
        Args:
            messages: 消息列表
            **kwargs: 额外参数（temperature, max_tokens等）
        
        Returns:
            ChatResponse: 标准响应
        """
        pass
    
    @abstractmethod
    async def chat_stream(self, messages: List[Message], **kwargs) -> AsyncGenerator[str, None]:
        """
        流式对话
        
        Args:
            messages: 消息列表
            **kwargs: 额外参数
        
        Yields:
            str: 流式返回的文本片段
        """
        pass
    
    def is_available(self) -> bool:
        """检查是否可用（有API Key且启用）"""
        return self.config.enabled and bool(self.config.api_key)
    
    def _format_messages(self, messages: List[Message]) -> List[Dict]:
        """将标准消息格式转换为厂商特定格式"""
        return [{"role": m.role, "content": m.content} for m in messages]
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头（子类可覆盖）"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}"
        }
