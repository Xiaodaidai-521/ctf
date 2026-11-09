"""
FRP 客户端管理模块
为每个题目容器创建对应的 FRP 客户端容器（sidecar 模式）
"""

import docker
import logging
from django.conf import settings
from .models import ChallengeContainer


logger = logging.getLogger(__name__)


class FRPClientManager:
    """FRP 客户端管理器"""

    def __init__(self):
        self.docker_client = docker.from_env()

        # FRP 服务器配置
        self.frps_server = getattr(settings, 'FRP_SERVER', 'frps-server')
        self.frps_port = getattr(settings, 'FRP_SERVER_PORT', 7000)
        # Legacy sidecar secret delivery has not been migrated; keep it closed.
        self.frps_vhost_port = getattr(settings, 'FRP_HTTP_PORT', 9123)

        # Docker 网络配置
        self.network_name = getattr(settings, 'DOCKER_NETWORK', 'ctf-network')

        # FRP 客户端镜像
        self.frpc_image = 'snowdreamtech/frpc:0.52.3'

    def _ensure_image(self):
        logger.error('FRP_SIDECAR_DISABLED')
        return False

    def start_frpc_sidecar(self, container: ChallengeContainer) -> bool:
        logger.warning('FRP_SIDECAR_DISABLED')
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

            logger.info('FRP_SIDECAR_STOPPED')
            return True

        except docker.errors.NotFound:
            return True
        except Exception:
            logger.error('FRP_SIDECAR_STOP_FAILED')
            return False

    def _generate_frpc_config(self, container: ChallengeContainer) -> str:
        raise RuntimeError('FRP_SIDECAR_DISABLED')

    def restart_frpc_sidecar(self, container: ChallengeContainer) -> bool:
        logger.warning('FRP_SIDECAR_DISABLED')
        return False


# 单例模式
_frpc_manager_instance = None


def get_frpc_manager() -> FRPClientManager:
    """获取 FRP 客户端管理器单例"""
    global _frpc_manager_instance
    if _frpc_manager_instance is None:
        _frpc_manager_instance = FRPClientManager()
    return _frpc_manager_instance
