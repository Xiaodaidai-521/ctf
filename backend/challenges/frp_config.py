"""
FRP配置生成与更新模块
支持基于路径路由的FRP代理配置
"""

import requests
from django.conf import settings
from typing import List, Optional


class FRPConfigManager:
    """FRP配置管理器"""

    def __init__(self):
        self.api_url = getattr(settings, 'FRP_API_URL', 'http://localhost:7500')
        self.http_domain = getattr(settings, 'FRP_HTTP_DOMAIN', 'localhost')
        self.http_port = getattr(settings, 'FRP_HTTP_PORT', '9123')
        self.timeout = 5

    def generate_container_config(self, container) -> str:
        """
        生成单个容器的FRP配置（路径路由模式）

        Args:
            container: ChallengeContainer实例

        Returns:
            str: FRP配置字符串
        """
        user_id = container.user.id
        container_uuid = container.container_id
        redirect_port = container.challenge.redirect_port or 80

        # 使用路径路由模式的FRP配置
        config = f"""[http_{user_id}-{container_uuid}]
type = http
local_ip = {user_id}-{container_uuid}
local_port = {redirect_port}
locations = /challenge/{user_id}-{container_uuid}
use_compression = true
"""
        return config

    def generate_access_url(self, container) -> str:
        """
        生成容器访问URL（使用路径路由模式 + Nginx代理）

        Args:
            container: ChallengeContainer实例

        Returns:
            str: 访问URL
        """
        user_id = container.user.id
        container_uuid = container.container_id

        # 使用Nginx代理（端口80），URL末尾带/
        url = f"http://{self.http_domain}/challenge/{user_id}-{container_uuid}/"

        return url

    def generate_batch_config(self, containers: List) -> str:
        """
        批量生成容器的FRP配置

        Args:
            containers: ChallengeContainer实例列表

        Returns:
            str: 合并后的FRP配置字符串
        """
        config = ""
        for container in containers:
            if container.status == 'running':
                config += self.generate_container_config(container)
        return config

    def get_common_config(self) -> str:
        """
        获取FRP的[common]配置段

        Returns:
            str: common配置
        """
        try:
            response = requests.get(
                f"{self.api_url}/api/config",
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.text
        except requests.RequestException:
            pass

        # 返回默认配置
        return """[common]
bind_addr = 0.0.0.0
bind_port = 7000
vhost_http_port = 9123
"""

    def update_frp_config(self, containers: List) -> bool:
        """
        更新FRP服务器配置

        Args:
            containers: 需要代理的容器列表

        Returns:
            bool: 是否更新成功
        """
        try:
            # 获取common配置
            common_config = self.get_common_config()

            # 生成容器配置
            containers_config = self.generate_batch_config(containers)

            # 合并配置
            full_config = common_config + containers_config

            # 更新配置到FRP服务器
            response = requests.put(
                f"{self.api_url}/api/config",
                data=full_config,
                timeout=self.timeout
            )

            if response.status_code != 200:
                return False

            # 重新加载FRP配置
            reload_response = requests.get(
                f"{self.api_url}/api/reload",
                timeout=self.timeout
            )

            return reload_response.status_code == 200

        except requests.RequestException as e:
            print(f"FRP配置更新失败: {str(e)}")
            return False

    def reload_frp(self) -> bool:
        """
        重新加载FRP配置

        Returns:
            bool: 是否重载成功
        """
        try:
            response = requests.get(
                f"{self.api_url}/api/reload",
                timeout=self.timeout
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def test_connection(self) -> bool:
        """
        测试FRP服务器连接

        Returns:
            bool: 是否连接成功
        """
        try:
            response = requests.get(
                f"{self.api_url}/api/serverinfo",
                timeout=self.timeout
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_server_status(self) -> Optional[dict]:
        """
        获取FRP服务器状态

        Returns:
            Optional[dict]: 服务器状态信息
        """
        try:
            response = requests.get(
                f"{self.api_url}/api/serverinfo",
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
        except requests.RequestException:
            pass
        return None


# 单例模式
_frp_manager_instance = None


def get_frp_manager() -> FRPConfigManager:
    """获取FRP管理器单例"""
    global _frp_manager_instance
    if _frp_manager_instance is None:
        _frp_manager_instance = FRPConfigManager()
    return _frp_manager_instance
