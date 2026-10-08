"""
AI Provider 统一接口与注册中心
支持多厂商：火山引擎、月之暗面、文心一言、通义千问、讯飞星火
"""

import os
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, AsyncGenerator, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod


def _ensure_env_loaded():
    """确保根目录 .env 已加载（不依赖 settings.py 的导入顺序）"""
    if os.environ.get('_DOTENV_LOADED'):
        return
    _root_dotenv = Path(__file__).resolve().parent.parent.parent / '.env'
    if _root_dotenv.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(_root_dotenv)
            os.environ['_DOTENV_LOADED'] = '1'
        except ImportError:
            pass


def _ensure_env_loaded(force: bool = False):
    """Load project .env files without depending on Django import order."""
    if os.environ.get('_DOTENV_LOADED') and not force:
        return

    try:
        from dotenv import dotenv_values, load_dotenv
    except ImportError:
        dotenv_values = None
        load_dotenv = None

    def read_dotenv(dotenv_path: Path) -> Dict[str, str]:
        if dotenv_values:
            return {k: v for k, v in dotenv_values(dotenv_path).items() if v is not None}

        values = {}
        for raw_line in dotenv_path.read_text(encoding='utf-8-sig').splitlines():
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                values[key] = value
        return values

    backend_dir = Path(__file__).resolve().parent.parent
    project_dir = backend_dir.parent
    candidates = [
        project_dir / '.env',
        backend_dir / '.env',
        Path.cwd() / '.env',
    ]

    loaded_paths = []
    for dotenv_path in dict.fromkeys(candidates):
        if not dotenv_path.exists():
            continue

        for key, value in read_dotenv(dotenv_path).items():
            if value is not None and (force or os.environ.get(key, '') == ''):
                os.environ[key] = value

        if load_dotenv:
            load_dotenv(dotenv_path, override=force)
        loaded_paths.append(str(dotenv_path))

    if loaded_paths:
        os.environ['_DOTENV_LOADED'] = '1'
        os.environ['_DOTENV_LOADED_PATHS'] = os.pathsep.join(loaded_paths)


def reload_env():
    """Reload .env values, filling variables that are currently empty."""
    _ensure_env_loaded(force=True)


def _normalize_volcano_model(model: str) -> str:
    """Convert Ark console display names to API model IDs."""
    model = (model or '').strip().replace(' ', '-')
    lowered = model.lower()
    if lowered.startswith('doubao-seed-2.0-'):
        return lowered.replace('doubao-seed-2.0-', 'doubao-seed-2-0-', 1)
    return model


_ensure_env_loaded()


@dataclass
class ProviderConfig:
    """厂商配置"""
    name: str
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    enabled: bool = True


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


class BaseProvider(ABC):
    """AI Provider 抽象基类"""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.name = config.name
    
    @abstractmethod
    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        """非流式对话"""
        pass
    
    @abstractmethod
    async def chat_stream(self, messages: List[Message], **kwargs) -> AsyncGenerator[str, None]:
        """流式对话"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """检查是否可用（有API Key且启用）"""
        pass


class ProviderRegistry:
    """Provider 注册中心"""
    
    _providers: Dict[str, BaseProvider] = {}
    _configs: Dict[str, ProviderConfig] = {}
    
    # 智能体到厂商的映射；未配置的智能体默认使用 DeepSeek。
    AGENT_PROVIDER_MAP = {
        # CTF 解题智能体
        'xiaohei':   'volcano',
        'analyst':   'deepseek',
        'architect': 'wenxin',
        'developer': 'volcano',
        'security':  'qwen',
        'tester':    'spark',
        # 学习辅助智能体
        'tutor':        'volcano',
        'curriculum':   'volcano',
        'content_gen':  'volcano',
        'code_mentor':  'volcano',
        'assessor':     'volcano',
        # Legal compliance agent
        'compliance_officer': 'qwen',
        'legal_reviewer': 'deepseek',
    }
    
    @classmethod
    def register(cls, name: str, provider_class: type):
        """注册 Provider 类"""
        cls._providers[name] = provider_class
    
    @classmethod
    def create_provider(cls, name: str, config: ProviderConfig) -> Optional[BaseProvider]:
        """创建 Provider 实例"""
        if name not in cls._providers:
            return None
        return cls._providers[name](config)
    
    @classmethod
    def get_provider_for_agent(cls, agent_id: str) -> str:
        """获取智能体对应的默认厂商"""
        return cls.AGENT_PROVIDER_MAP.get(agent_id, 'deepseek')
    
    @classmethod
    def set_agent_provider_map(cls, mapping: Dict[str, str]):
        """设置智能体-厂商映射"""
        cls.AGENT_PROVIDER_MAP.update(mapping)


class MultiProviderManager:
    """多厂商管理器 - 处理联合调用"""
    
    def __init__(self):
        self._instances: Dict[str, BaseProvider] = {}
        self._init_providers()
    
    def _init_providers(self):
        """从环境变量初始化所有厂商"""
        configs = {
            'volcano': ProviderConfig(
                name='volcano',
                api_key=os.getenv('ARK_API_KEY', ''),
                base_url=os.getenv('ARK_BASE_URL', 'https://ark.cn-beijing.volces.com/api/v3'),
                model=_normalize_volcano_model(os.getenv('ARK_MODEL', 'doubao-seed-2-0-lite-260428')),
                enabled=bool(os.getenv('ARK_API_KEY'))
            ),
            'deepseek': ProviderConfig(
                name='deepseek',
                api_key=os.getenv('DEEPSEEK_API_KEY', ''),
                base_url=os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
                model=os.getenv('DEEPSEEK_MODEL', 'deepseek-v4-pro'),
                enabled=bool(os.getenv('DEEPSEEK_API_KEY'))
            ),
            'moonshot': ProviderConfig(
                name='moonshot',
                api_key=os.getenv('MOONSHOT_API_KEY', ''),
                base_url=os.getenv('MOONSHOT_BASE_URL', 'https://api.moonshot.cn/v1'),
                model=os.getenv('MOONSHOT_MODEL', 'moonshot-v1-8k'),
                enabled=bool(os.getenv('MOONSHOT_API_KEY'))
            ),
            'wenxin': ProviderConfig(
                name='wenxin',
                api_key=os.getenv('WENXIN_API_KEY', ''),
                base_url=os.getenv('WENXIN_BASE_URL', 'https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat'),
                model=os.getenv('WENXIN_MODEL', 'ernie-bot-4'),
                enabled=bool(os.getenv('WENXIN_API_KEY'))
            ),
            'qwen': ProviderConfig(
                name='qwen',
                api_key=os.getenv('QWEN_API_KEY', ''),
                base_url=os.getenv('QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
                model=os.getenv('QWEN_MODEL', 'qwen-max'),
                enabled=bool(os.getenv('QWEN_API_KEY'))
            ),
            'spark': ProviderConfig(
                name='spark',
                api_key=os.getenv('SPARK_API_KEY', ''),
                base_url=os.getenv('SPARK_BASE_URL', 'wss://spark-api.xf-yun.com/v3.5/chat'),
                model=os.getenv('SPARK_MODEL', 'generalv3.5'),
                enabled=bool(os.getenv('SPARK_API_KEY'))
            ),
        }
        
        for name, config in configs.items():
            ProviderRegistry._configs[name] = config
            if config.enabled:
                provider = ProviderRegistry.create_provider(name, config)
                if provider:
                    self._instances[name] = provider
    
    def refresh(self):
        """重新初始化 providers"""
        _ensure_env_loaded(force=True)
        self._instances.clear()
        self._init_providers()
    
    def get_provider(self, name: str) -> Optional[BaseProvider]:
        """获取指定厂商实例"""
        return self._instances.get(name)
    
    def get_provider_for_agent(self, agent_id: str) -> Optional[BaseProvider]:
        """获取智能体对应的厂商实例"""
        provider_name = ProviderRegistry.get_provider_for_agent(agent_id)
        return self._instances.get(provider_name)
    
    async def chat_single(
        self, 
        agent_id: str, 
        messages: List[Message], 
        **kwargs
    ) -> Optional[ChatResponse]:
        """单智能体对话"""
        provider = self.get_provider_for_agent(agent_id)
        if not provider:
            return None
        return await provider.chat(messages, **kwargs)
    
    async def chat_collaborative(
        self,
        agent_ids: List[str],
        messages: List[Message],
        **kwargs
    ) -> List[ChatResponse]:
        """协作模式：多个智能体同时回答"""
        tasks = []
        for agent_id in agent_ids:
            provider = self.get_provider_for_agent(agent_id)
            if provider:
                tasks.append(self._chat_with_fallback(provider, messages, agent_id, **kwargs))
        
        if not tasks:
            return []
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, ChatResponse)]
    
    async def chat_sequential(
        self,
        agent_ids: List[str],
        initial_messages: List[Message],
        **kwargs
    ) -> List[ChatResponse]:
        """串行模式：智能体按顺序接力"""
        responses = []
        messages = list(initial_messages)
        
        for agent_id in agent_ids:
            provider = self.get_provider_for_agent(agent_id)
            if not provider:
                continue
            
            try:
                response = await provider.chat(messages, **kwargs)
                responses.append(response)
                
                # 将当前回答加入上下文，传给下一个智能体
                messages.append(Message(role='assistant', content=response.content))
                messages.append(Message(
                    role='system', 
                    content=f'以上是{agent_id}的回答，请在此基础上继续。'
                ))
            except Exception as e:
                print(f"Sequential chat error for {agent_id}: {e}")
                continue
        
        return responses
    
    async def chat_competitive(
        self,
        agent_ids: List[str],
        messages: List[Message],
        **kwargs
    ) -> ChatResponse:
        """竞争模式：多个方案选最优"""
        responses = await self.chat_collaborative(agent_ids, messages, **kwargs)
        
        if not responses:
            raise Exception("No provider available for competitive mode")
        
        if len(responses) == 1:
            return responses[0]
        
        # 简单的选择策略：选最长的回答（通常更详细）
        # 实际可以用另一个AI来评判
        best = max(responses, key=lambda r: len(r.content))
        return best
    
    async def _chat_with_fallback(
        self,
        provider: BaseProvider,
        messages: List[Message],
        agent_id: str,
        **kwargs
    ) -> Optional[ChatResponse]:
        """带错误处理的单厂商调用"""
        try:
            return await provider.chat(messages, **kwargs)
        except Exception as e:
            print(f"Provider {provider.name} error for agent {agent_id}: {e}")
            return None


# 延迟导入具体实现，避免循环依赖
def _load_providers():
    from . import volcano, deepseek, moonshot, wenxin, qwen, spark
    
    ProviderRegistry.register('volcano', volcano.VolcanoProvider)
    ProviderRegistry.register('deepseek', deepseek.DeepSeekProvider)
    ProviderRegistry.register('moonshot', moonshot.MoonshotProvider)
    ProviderRegistry.register('wenxin', wenxin.WenxinProvider)
    ProviderRegistry.register('qwen', qwen.QwenProvider)
    ProviderRegistry.register('spark', spark.SparkProvider)


# 全局管理器实例
_manager: Optional[MultiProviderManager] = None


def get_manager() -> MultiProviderManager:
    """获取全局多厂商管理器"""
    global _manager
    if _manager is None:
        _load_providers()
        _manager = MultiProviderManager()
    return _manager


def reset_manager():
    """重置管理器（用于测试）"""
    global _manager
    _manager = None
