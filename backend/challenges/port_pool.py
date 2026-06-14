"""
端口池管理器
为题目容器分配和管理内网端口
"""

from django.core.cache import cache
from typing import Optional


class PortPool:
    """端口池管理器"""

    def __init__(self):
        # 端口范围：8080-9000（920个端口）
        self.start_port = 8080
        self.end_port = 9000
        self.total_ports = self.end_port - self.start_port + 1
        self.cache_key_prefix = 'port_pool_'

    def allocate_port(self, user_id: int, challenge_id: int, container_uuid: str) -> Optional[int]:
        """
        分配端口

        Args:
            user_id: 用户ID
            challenge_id: 题目ID
            container_uuid: 容器UUID

        Returns:
            Optional[int]: 分配的端口号，失败返回None
        """
        # 使用容器UUID作为唯一标识
        cache_key = f"{self.cache_key_prefix}{container_uuid}"

        # 检查是否已经分配过
        existing_port = cache.get(cache_key)
        if existing_port:
            return existing_port

        # 使用简单的哈希算法分配端口
        # 使用user_id和challenge_id的组合来确保同一个用户+题目的容器使用相同端口
        hash_value = hash(f"{user_id}-{challenge_id}")
        port = self.start_port + (hash_value % self.total_ports)

        # 检查端口是否可用
        if self._is_port_available(port):
            # 标记端口为已使用
            cache.set(cache_key, port, timeout=86400)  # 24小时过期
            cache.set(f"{self.cache_key_prefix}port_{port}", container_uuid, timeout=86400)
            return port

        # 如果端口已被占用，尝试找到下一个可用端口
        for offset in range(1, self.total_ports):
            test_port = self.start_port + ((hash_value + offset) % self.total_ports)
            if self._is_port_available(test_port):
                cache.set(cache_key, test_port, timeout=86400)
                cache.set(f"{self.cache_key_prefix}port_{test_port}", container_uuid, timeout=86400)
                return test_port

        return None

    def release_port(self, container_uuid: str) -> bool:
        """
        释放端口

        Args:
            container_uuid: 容器UUID

        Returns:
            bool: 是否释放成功
        """
        cache_key = f"{self.cache_key_prefix}{container_uuid}"
        port = cache.get(cache_key)

        if port:
            cache.delete(cache_key)
            cache.delete(f"{self.cache_key_prefix}port_{port}")
            return True

        return False

    def get_port(self, container_uuid: str) -> Optional[int]:
        """
        获取容器的端口

        Args:
            container_uuid: 容器UUID

        Returns:
            Optional[int]: 端口号，不存在返回None
        """
        cache_key = f"{self.cache_key_prefix}{container_uuid}"
        return cache.get(cache_key)

    def _is_port_available(self, port: int) -> bool:
        """
        检查端口是否可用

        Args:
            port: 端口号

        Returns:
            bool: 是否可用
        """
        cache_key = f"{self.cache_key_prefix}port_{port}"
        return not cache.get(cache_key)

    def get_used_ports(self) -> list:
        """
        获取所有已使用的端口

        Returns:
            list: 已使用的端口列表
        """
        used_ports = []
        for port in range(self.start_port, self.end_port + 1):
            if not self._is_port_available(port):
                used_ports.append(port)
        return used_ports

    def get_available_port_count(self) -> int:
        """
        获取可用端口数量

        Returns:
            int: 可用端口数量
        """
        return self.total_ports - len(self.get_used_ports())


# 单例模式
_port_pool_instance = None


def get_port_pool() -> PortPool:
    """获取端口池单例"""
    global _port_pool_instance
    if _port_pool_instance is None:
        _port_pool_instance = PortPool()
    return _port_pool_instance
