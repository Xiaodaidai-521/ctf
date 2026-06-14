"""
容器管理器
负责Docker容器的创建、启动、停止和销毁
"""

import docker
import os
import uuid
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from typing import Optional, Tuple
from .models import ChallengeContainer, Challenge
from .frp_config import get_frp_manager
from .port_pool import get_port_pool


class ContainerManager:
    """容器管理器"""

    def __init__(self):
        # 初始化Docker客户端
        self.docker_client = docker.from_env()
        self.frp_manager = get_frp_manager()
        self.port_pool = get_port_pool()

        # 配置参数
        self.network_name = getattr(settings, 'DOCKER_NETWORK', 'ctf-network')
        self.container_lifetime = getattr(settings, 'CONTAINER_LIFETIME', 7200)  # 默认2小时
        self.cpu_limit = getattr(settings, 'CONTAINER_CPU_LIMIT', 0.5)
        self.memory_limit = getattr(settings, 'CONTAINER_MEMORY_LIMIT', '512m')

        # 确保Docker网络存在
        self._ensure_network()

    def _ensure_network(self):
        """确保Docker网络存在"""
        try:
            self.docker_client.networks.get(self.network_name)
        except docker.errors.NotFound:
            try:
                self.docker_client.networks.create(
                    self.network_name,
                    driver="bridge"
                )
                print(f"✅ Docker网络 '{self.network_name}' 创建成功")
            except Exception as e:
                print(f"❌ 创建Docker网络失败: {str(e)}")

    def start_container(self, user, challenge: Challenge) -> Tuple[bool, str, Optional[ChallengeContainer]]:
        """
        启动题目容器

        Args:
            user: 用户实例
            challenge: 题目实例

        Returns:
            Tuple[bool, str, Optional[ChallengeContainer]]:
                (是否成功, 消息, 容器实例)
        """
        # 检查题目是否有Docker镜像
        if not challenge.docker_image:
            return False, "该题目没有配置Docker镜像", None

        # 检查是否已有运行中的容器
        existing = ChallengeContainer.objects.filter(
            user=user,
            challenge=challenge,
            status='running'
        ).first()

        if existing and existing.is_running:
            return False, "已有运行中的容器", existing

        # 停止旧的容器
        if existing:
            self.stop_container(existing)

        try:
            # 生成容器UUID和名称
            container_uuid = str(uuid.uuid4())[:8]
            user_id = user.id
            network_alias = f"{user_id}-{container_uuid}"
            container_name = f"ctf-{user_id}-{challenge.id}-{container_uuid}"

            # 分配端口池
            pool_port = self.port_pool.allocate_port(user_id, challenge.id, container_uuid)
            if not pool_port:
                return False, "端口池已满，无法分配端口", None

            # 创建容器记录
            container_record = ChallengeContainer.objects.create(
                user=user,
                challenge=challenge,
                container_id=container_uuid,
                docker_container_name=container_name,
                status='pending',
                port=pool_port  # 保存分配的端口
            )

            # 配置网络别名
            networking_config = self.docker_client.api.create_networking_config({
                self.network_name: self.docker_client.api.create_endpoint_config(
                    aliases=[network_alias]
                )
            })

            # 创建Docker容器
            # 映射端口：主机端口(池端口) -> 容器内部端口
            container_port = challenge.redirect_port or 80
            port_mapping = {
                container_port: pool_port  # 主机端口:容器端口
            }

            docker_container = self.docker_client.containers.run(
                image=challenge.docker_image,
                name=container_name,
                detach=True,
                network=self.network_name,
                networking_config=networking_config,
                ports=port_mapping,
                mem_limit=self.memory_limit,
                cpu_quota=int(self.cpu_limit * 100000),
                cpu_period=100000,
                remove=False,
            )

            # 更新容器记录状态
            container_record.status = 'running'
            container_record.started_at = timezone.now()
            container_record.expires_at = timezone.now() + timedelta(seconds=self.container_lifetime)

            # 生成访问URL（使用Django代理，格式：http://localhost:8000/challenge/<user_id>-<uuid>/）
            access_url = f"http://localhost:8000/challenge/{user_id}-{container_uuid}/"
            container_record.access_url = access_url

            container_record.save()

            print(f"✅ 容器启动成功: {container_name}, 端口: {pool_port}, URL: {access_url}")
            return True, "容器启动成功", container_record

        except docker.errors.ImageNotFound:
            container_record.status = 'error'
            container_record.save()
            return False, f"Docker镜像 '{challenge.docker_image}' 不存在，请先拉取镜像", None
        except docker.errors.APIError as e:
            container_record.status = 'error'
            container_record.save()
            return False, f"Docker API错误: {str(e)}", None
        except Exception as e:
            if 'container_record' in locals():
                container_record.status = 'error'
                container_record.save()
            return False, f"容器启动失败: {str(e)}", None

    def stop_container(self, container: ChallengeContainer) -> bool:
        """
        停止容器

        Args:
            container: ChallengeContainer实例

        Returns:
            bool: 是否停止成功
        """
        try:
            # 停止Docker容器
            docker_container = self.docker_client.containers.get(
                container.docker_container_name
            )
            docker_container.stop()
            docker_container.remove()

            # 回收端口
            self.port_pool.release_port(container.container_id)

            # 更新容器记录状态
            container.status = 'stopped'
            container.destroyed_at = timezone.now()
            container.save()

            print(f"✅ 容器已停止: {container.docker_container_name}")
            return True

        except docker.errors.NotFound:
            # 容器不存在，只更新状态
            container.status = 'destroyed'
            container.destroyed_at = timezone.now()
            container.save()
            return True
        except docker.errors.APIError as e:
            print(f"❌ 停止容器失败: {str(e)}")
            return False
        except Exception as e:
            print(f"❌ 停止容器异常: {str(e)}")
            return False

    def get_container_status(self, user, challenge: Challenge) -> Optional[ChallengeContainer]:
        """
        获取容器状态

        Args:
            user: 用户实例
            challenge: 题目实例

        Returns:
            Optional[ChallengeContainer]: 容器实例
        """
        container = ChallengeContainer.objects.filter(
            user=user,
            challenge=challenge
        ).order_by('-created_at').first()

        if not container:
            return None

        # 如果容器已过期，标记为已停止
        if container.is_expired and container.status == 'running':
            self.stop_container(container)

        return container

    def _update_frp_for_all_containers(self):
        """更新所有运行中容器的FRP配置"""
        running_containers = ChallengeContainer.objects.filter(
            status='running'
        ).select_related('challenge', 'user')

        try:
            self.frp_manager.update_frp_config(running_containers)
        except Exception as e:
            # 如果FRP服务器不可用，只记录警告，不影响容器启动
            print(f"⚠️  FRP配置更新失败（FRP服务器可能未启动）: {str(e)}")
            # 注意：容器仍然可以启动，只是外部无法通过FRP URL访问

    def cleanup_expired_containers(self) -> int:
        """
        清理过期容器

        Returns:
            int: 清理的容器数量
        """
        expired_containers = ChallengeContainer.objects.filter(
            status='running'
        ).select_related('challenge', 'user')

        count = 0
        for container in expired_containers:
            if container.is_expired:
                if self.stop_container(container):
                    count += 1

        if count > 0:
            print(f"✅ 清理了 {count} 个过期容器")

        return count

    def destroy_all_user_containers(self, user) -> int:
        """
        销毁用户的所有容器

        Args:
            user: 用户实例

        Returns:
            int: 销毁的容器数量
        """
        containers = ChallengeContainer.objects.filter(
            user=user,
            status='running'
        )

        count = 0
        for container in containers:
            if self.stop_container(container):
                count += 1

        return count

    def get_docker_image_status(self, image_name: str) -> bool:
        """
        检查Docker镜像是否存在

        Args:
            image_name: 镜像名称

        Returns:
            bool: 镜像是否存在
        """
        try:
            self.docker_client.images.get(image_name)
            return True
        except docker.errors.ImageNotFound:
            return False
        except Exception:
            return False

    def pull_docker_image(self, image_name: str) -> bool:
        """
        拉取Docker镜像

        Args:
            image_name: 镜像名称

        Returns:
            bool: 是否拉取成功
        """
        try:
            print(f"⏳ 正在拉取镜像: {image_name}")
            self.docker_client.images.pull(image_name)
            print(f"✅ 镜像拉取成功: {image_name}")
            return True
        except Exception as e:
            print(f"❌ 镜像拉取失败: {str(e)}")
            return False

    def _start_frpc_sidecar(self, container: ChallengeContainer) -> bool:
        """
        启动 FRP 客户端容器（sidecar 模式）

        Args:
            container: ChallengeContainer 实例

        Returns:
            bool: 是否启动成功
        """
        try:
            # 确保 FRP 客户端镜像存在
            frpc_image = 'snowdreamtech/frpc:0.52.3'
            try:
                self.docker_client.images.get(frpc_image)
            except docker.errors.ImageNotFound:
                self.docker_client.images.pull(frpc_image)
                print(f"✅ FRP 客户端镜像拉取成功: {frpc_image}")

            # 获取容器网络信息
            container_info = self.docker_client.containers.get(
                container.docker_container_name
            ).attrs
            networks = container_info['NetworkSettings']['Networks']
            network = list(networks.keys())[0]
            container_ip = networks[network]['IPAddress']

            # 获取 FRP 服务器 IP
            frps_ip = None
            ctf_bridge = self.docker_client.networks.get('ctf-bridge')
            for c in ctf_bridge.containers:
                if c.name == 'frps-server':
                    c.reload()
                    frps_ip = c.attrs['NetworkSettings']['Networks']['ctf-bridge']['IPAddress']
                    break

            if not frps_ip:
                print("⚠️  FRP 服务器未启动，跳过 FRP 客户端启动")
                return False

            # 生成 FRP 客户端配置（使用路径路由模式）
            # 注意：Nginx处理路径重写，FRP直接转发
            frpc_config = f"""[common]
server_addr = {frps_ip}
server_port = 7000
token = ctf_platform_secret

[http_{container.user.id}-{container.container_id}]
type = http
local_ip = {container_ip}
local_port = {container.challenge.redirect_port or 80}
custom_domains = ctf.local
locations = /challenge/{container.user.id}-{container.container_id}/
use_compression = true
host_header_rewrite = ctf.local
"""

            # 保存配置文件
            config_path = f'/tmp/frpc_{container.container_id}.ini'
            with open(config_path, 'w') as f:
                f.write(frpc_config)

            # FRP 客户端容器名称
            frpc_container_name = f"frpc-{container.docker_container_name}"

            # 停止旧的 FRP 客户端容器
            try:
                old_frpc = self.docker_client.containers.get(frpc_container_name)
                old_frpc.stop()
                old_frpc.remove()
            except docker.errors.NotFound:
                pass

            # 创建并启动 FRP 客户端容器
            frpc_container = self.docker_client.containers.create(
                image=frpc_image,
                name=frpc_container_name,
                entrypoint='/usr/bin/frpc',
                command=['-c', '/frpc.ini'],
                volumes={config_path: {'bind': '/frpc.ini', 'mode': 'ro'}},
                restart_policy={'Name': 'unless-stopped'}
            )

            # 连接到两个网络
            self.docker_client.networks.get(network).connect(frpc_container)
            ctf_bridge.connect(frpc_container)

            # 启动容器
            frpc_container.start()

            print(f"✅ FRP 客户端容器启动成功: {frpc_container_name}")
            return True

        except Exception as e:
            print(f"⚠️  FRP 客户端容器启动失败（不影响题目容器使用）: {str(e)}")
            return False

    def _stop_frpc_sidecar(self, container: ChallengeContainer) -> bool:
        """
        停止 FRP 客户端容器

        Args:
            container: ChallengeContainer 实例

        Returns:
            bool: 是否停止成功
        """
        try:
            frpc_container_name = f"frpc-{container.docker_container_name}"
            frpc_container = self.docker_client.containers.get(frpc_container_name)
            frpc_container.stop()
            frpc_container.remove()
            print(f"✅ FRP 客户端容器已停止: {frpc_container_name}")
            return True
        except docker.errors.NotFound:
            return True
        except Exception as e:
            print(f"⚠️  停止 FRP 客户端容器失败: {str(e)}")
            return False


# 单例模式
_container_manager_instance = None


def get_container_manager() -> ContainerManager:
    """获取容器管理器单例"""
    global _container_manager_instance
    if _container_manager_instance is None:
        _container_manager_instance = ContainerManager()
    return _container_manager_instance
