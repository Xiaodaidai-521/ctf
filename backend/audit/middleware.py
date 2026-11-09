# audit/middleware.py
# -*- coding: utf-8 -*-
"""
审计中间件
自动记录登录登出、异常请求
"""
import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class AuditMiddleware(MiddlewareMixin):
    """审计中间件：记录异常请求"""

    # 忽略的路径（静态文件、健康检查等）
    IGNORED_PATHS = ['/static/', '/media/', '/favicon', '/health']

    def process_response(self, request, response):
        # 记录 5xx 错误
        if response.status_code >= 500 and not self._is_ignored(request.path):
            try:
                from .models import AuditEvent
                AuditEvent.log(
                    category='exception',
                    summary='HTTP_SERVER_ERROR',
                    level='ERROR',
                    detail={'status_code': response.status_code},
                )
            except Exception:
                logger.error('AUDIT_UNAVAILABLE', extra={'reason_code': 'AUDIT_UNAVAILABLE'})
        return response

    def process_exception(self, request, exception):
        """记录未捕获的异常"""
        if not self._is_ignored(request.path):
            try:
                from .models import AuditEvent
                AuditEvent.log(
                    category='exception',
                    summary='REQUEST_EXCEPTION',
                    level='CRITICAL',
                )
            except Exception:
                logger.error('AUDIT_UNAVAILABLE', extra={'reason_code': 'AUDIT_UNAVAILABLE'})
        return None  # 不拦截异常，让 Django 正常处理

    @staticmethod
    def _is_ignored(path: str) -> bool:
        for p in AuditMiddleware.IGNORED_PATHS:
            if path.startswith(p):
                return True
        return False
