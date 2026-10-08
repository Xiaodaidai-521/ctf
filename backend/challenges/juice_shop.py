"""Pinned Juice Shop runtime, with a separate network and writable layer per learner."""

import logging
import random
import time
import uuid
from datetime import timedelta
from ipaddress import ip_address
from urllib.parse import urlsplit

import docker
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .container_audit import record_container_audit
from .models import ChallengeContainer

logger = logging.getLogger(__name__)
PROFILE = 'juice-shop'
LABEL = 'ctf.juice-shop.instance'


def is_juice_shop(challenge):
    return challenge.docker_image == settings.JUICE_SHOP_IMAGE


class JuiceShopRuntime:
    def __init__(self, client):
        self.client = client

    def audit(self, action, record, error=''):
        try:
            record_container_audit(
                action=action, result='failed' if error else 'success', container=record,
                network=record.runtime_metadata.get('network', ''), error_message=error,
            )
        except Exception:
            logger.exception('Could not record Juice Shop lifecycle audit')

    def start(self, user, challenge):
        record = None
        try:
            host = settings.JUICE_SHOP_PUBLIC_HOST
            parsed = urlsplit(f'http://{host}')
            if (not parsed.hostname or parsed.netloc != host or parsed.port is not None
                    or parsed.username or parsed.password or any(c.isspace() for c in host)):
                raise ValueError('JUICE_SHOP_PUBLIC_HOST 必须为不含协议、端口或路径的主机名/IP')
            ip_address(settings.JUICE_SHOP_BIND_IP)
            first, last = settings.JUICE_SHOP_PORT_MIN, settings.JUICE_SHOP_PORT_MAX
            if not 1024 <= first <= last <= 65535:
                raise ValueError('Juice Shop 端口范围必须位于 1024–65535')
            self.client.ping()
            self.client.images.get(settings.JUICE_SHOP_IMAGE)

            # Serialize reservations across backend workers; Docker owns port allocation.
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=user.pk)
                existing = ChallengeContainer.objects.filter(
                    user=user, challenge=challenge, status__in=['pending', 'running'],
                ).first()
                if existing:
                    return False, '已有运行中或待启动的环境，请先停止或等待到期回收', existing
                instance = uuid.uuid4().hex[:16]
                record = ChallengeContainer.objects.create(
                    user=user, challenge=challenge, container_id=instance,
                    docker_container_name=f'ctf-js-{instance}', status='pending',
                    expires_at=timezone.now() + timedelta(minutes=5),
                    runtime_metadata={'profile': PROFILE, 'network': f'ctf-js-{instance}'},
                )
            self.audit('start_requested', record)
            self.client.networks.create(
                record.runtime_metadata['network'], driver='bridge',
                labels={LABEL: instance},
            )
            container = self._create(record, first, last)
            deadline = time.monotonic() + settings.JUICE_SHOP_START_TIMEOUT
            while time.monotonic() < deadline:
                container.reload()
                state = container.attrs['State']
                if state.get('Status') in ('exited', 'dead'):
                    raise RuntimeError('Juice Shop 在启动过程中退出，请查看容器日志')
                if state.get('Health', {}).get('Status') == 'healthy':
                    break
                time.sleep(1)
            else:
                raise RuntimeError('Juice Shop 健康检查超时')
            record.status = 'running'
            record.started_at = timezone.now()
            record.expires_at = timezone.now() + timedelta(seconds=settings.CONTAINER_LIFETIME)
            record.access_url = f'http://{host}:{record.port}/'
            record.save()
            self.audit('start_succeeded', record)
            return True, 'Juice Shop 已就绪；停止后再次启动将重置练习数据', record
        except Exception as exc:
            logger.exception('Juice Shop startup failed')
            if record:
                record.status = 'error'
                record.runtime_metadata['error'] = str(exc)
                record.save()
                self.audit('start_failed', record, str(exc))
                self.stop(record, final_status='error')
            return False, f'Juice Shop 启动失败：{exc}', None

    def _create(self, record, first, last):
        ports = list(range(first, last + 1))
        random.SystemRandom().shuffle(ports)
        for port in ports:
            container = self.client.containers.create(
                image=settings.JUICE_SHOP_IMAGE,
                name=record.docker_container_name,
                network=record.runtime_metadata['network'],
                ports={'3000/tcp': (settings.JUICE_SHOP_BIND_IP, port)},
                labels={LABEL: record.container_id},
                user='65532', read_only=False, mem_limit='768m', nano_cpus=1000000000,
                pids_limit=256, cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
                tmpfs={'/tmp': 'rw,noexec,nosuid,size=64m'},
                healthcheck={
                    'test': ['CMD', '/nodejs/bin/node', '-e',
                             "require('http').get('http://127.0.0.1:3000/rest/products/search?q=',"
                             "r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"],
                    'interval': 2000000000, 'timeout': 2000000000,
                    'start_period': 10000000000, 'retries': 30,
                },
            )
            try:
                container.start()
            except docker.errors.APIError as exc:
                container.remove(force=True, v=True)
                if any(text in str(exc).lower() for text in ('port is already allocated', 'address already in use')):
                    continue
                raise
            record.port = port
            record.save(update_fields=['port'])
            return container
        raise RuntimeError('Juice Shop 端口范围已被占满')

    def stop(self, record, final_status='stopped'):
        self.audit('stop_requested', record)
        try:
            try:
                container = self.client.containers.get(record.docker_container_name)
                if container.labels.get(LABEL) != record.container_id:
                    raise RuntimeError('容器资源归属不匹配，拒绝删除')
                container.remove(force=True, v=True)
            except docker.errors.NotFound:
                pass
            try:
                network = self.client.networks.get(record.runtime_metadata['network'])
                if network.attrs.get('Labels', {}).get(LABEL) != record.container_id:
                    raise RuntimeError('网络资源归属不匹配，拒绝删除')
                network.remove()
            except docker.errors.NotFound:
                pass
            record.status = final_status
            record.destroyed_at = timezone.now()
            record.access_url = ''
            record.save()
            self.audit('stop_succeeded', record)
            return True
        except Exception as exc:
            # Keep the record eligible for cleanup when the daemon becomes available again.
            record.status = 'error'
            record.runtime_metadata['error'] = str(exc)
            record.save()
            self.audit('stop_failed', record, str(exc))
            logger.exception('Juice Shop cleanup failed')
            return False

    def refresh(self, record):
        if record.is_expired and record.status in ('pending', 'running', 'error'):
            self.stop(record)
        elif record.status == 'running':
            try:
                container = self.client.containers.get(record.docker_container_name)
                if container.status != 'running':
                    self.stop(record, final_status='error')
            except docker.errors.NotFound:
                self.stop(record, final_status='destroyed')
        return record
