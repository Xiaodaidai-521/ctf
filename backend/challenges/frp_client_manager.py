"""
FRP 客户端管理模块
为每个题目容器创建对应的 FRP 客户端容器（sidecar 模式）
"""

import docker
from django.conf import settings
from .models import ChallengeContainer


class FRPClientManager:
    """FRP 客户端管理器"""

    def __init__(self):
        self.docker_client = docker.from_env()

        # FRP 服务器配置
        self.frps_server = getattr(settings, 'FRP_SERVER', 'frps-server')
        self.frps_port = getattr(settings, 'FRP_SERVER_PORT', 7000)
        self.frps_token = getattr(settings, 'FRP_TOKEN', 'ctf_platform_secret')
        self.frps_vhost_port = getattr(settings, 'FRP_HTTP_PORT', 9123)

        # Docker 网络配置
        self.network_name = getattr(settings, 'DOCKER_NETWORK', 'ctf-network')

        # FRP 客户端镜像
        self.frpc_image = 'snowdreamtech/frpc:0.52.3'

    def _ensure_image(self):
        """确保 FRP 客户端镜像存在"""
        try:
            self.docker_client.images.get(self.frpc_image)
        except docker.errors.ImageNotFound:
            try:
                self.docker_client.images.pull(self.frpc_image)
            except Exception as e:
                print(f"⚠️  拉取 FRP 客户端镜像失败: {str(e)}")

    def start_frpc_sidecar(self, container: ChallengeContainer) -> bool:
        """
        启动 FRP 客户端 sidecar 容器

        Args:
            container: ChallengeContainer 实例

        Returns:
            bool: 是否启动成功
        """
        try:
            # 确保 FRP 客户端镜像存在
            self._ensure_image()

            # 生成 FRP 客户端配置
            frpc_config = self._generate_frpc_config(container)

            # FRP 客户端容器名称
            frpc_container_name = f"frpc-{container.docker_container_name}"

            # 停止旧的 FRP 客户端容器
            try:
                old_frpc = self.docker_client.containers.get(frpc_container_name)
                old_frpc.stop()
                old_frpc.remove()
            except docker.errors.NotFound:
                pass

            # 启动 FRP 客户端容器
            self.docker_client.containers.run(
                image=self.frpc_image,
                name=frpc_container_name,
                network=self.network_name,
                command=f"frpc -c /frpc.ini",
                detach=True,
                auto_remove=False,
                volumes={
                    '/frpc.ini': {
                        'bind': frpc_config,
                        'mode': 'ro'
                    }
                },
                restart_policy={'Name': 'unless-stopped'}
            )

            # 保存 FRP 客户端容器名称
            container.frp_client_container = frpc_container_name
            container.save()

            print(f"✅ FRP 客户端容器启动成功: {frpc_container_name}")
            return True

        except Exception as e:
            print(f"❌ FRP 客户端容器启动失败: {str(e)}")
            return False

    def stop_frpc_sidecar(self, container: ChallengeContainer) -> bool:
        """
        停止 FRP 客户端 sidecar 容器

        Args:
            container: ChallengeContainer 实例

        Returns:
            bool: 是否停止成功
        """
        try:
            if not container.frp_client_container:
                return True

            frpc_container = self.docker_client.containers.get(
                container.frp_client_container
            )
            frpc_container.stop()
            frpc_container.remove()

            print(f"✅ FRP 客户端容器已停止: {container.frp_client_container}")
            return True

        except docker.errors.NotFound:
            return True
        except Exception as e:
            print(f"❌ 停止 FRP 客户端容器失败: {str(e)}")
            return False

    def _generate_frpc_config(self, container: ChallengeContainer) -> str:
        """
        生成 FRP 客户端配置

        Args:
            container: ChallengeContainer 实例

        Returns:
            str: FRP 客户端配置内容
        """
        user_id = container.user.id
        container_uuid = container.container_id
        challenge_port = container.challenge.redirect_port or 80

        # 题目容器网络别名（通过 Docker 网络访问）
        container_alias = f"{user_id}-{container_uuid}"

        config = f"""[common]
server_addr = {self.frps_server}
server_port = {self.frps_port}
token = {self.frps_token}

[http_{user_id}-{container_uuid}]
type = http
local_ip = {container_alias}
local_port = {challenge_port}
use_compression = true
use_encryption = false
"""
        return config

    def restart_frpc_sidecar(self, container: ChallengeContainer) -> bool:
        """
        重启 FRP 客户端 sidecar 容器

        Args:
            container: ChallengeContainer 实例

        Returns:
            bool: 是否重启成功
        """
        try:
            if container.frp_client_container:
                frpc_container = self.docker_client.containers.get(
                    container.frp_client_container
                )
                frpc_container.restart()
                print(f"✅ FRP 客户端容器重启成功: {container.frp_client_container}")
                return True
            else:
                return self.start_frpc_sidecar(container)
        except docker.errors.NotFound:
            return self.start_frpc_sidecar(container)
        except Exception as e:
            print(f"❌ 重启 FRP 客户端容器失败: {str(e)}")
            return False


# 单例模式
_frpc_manager_instance = None


def get_frpc_manager() -> FRPClientManager:
    """获取 FRP 客户端管理器单例"""
    global _frpc_manager_instance
    if _frpc_manager_instance is None:
        _frpc_manager_instance = FRPClientManager()
    return _frpc_manager_instance
