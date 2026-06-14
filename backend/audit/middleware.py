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
                    summary=f'服务端错误 {response.status_code}: {request.method} {request.path}',
                    level='ERROR',
                    request=request,
                    detail={
                        'status_code': response.status_code,
                        'method': request.method,
                        'path': request.path,
                    }
                )
            except Exception as e:
                logger.error(f"审计中间件记录失败: {e}")
        return response

    def process_exception(self, request, exception):
        """记录未捕获的异常"""
        if not self._is_ignored(request.path):
            try:
                from .models import AuditEvent
                AuditEvent.log(
                    category='exception',
                    summary=f'未处理异常: {type(exception).__name__}: {str(exception)[:100]}',
                    level='CRITICAL',
                    request=request,
                    detail={
                        'exception_type': type(exception).__name__,
                        'exception_msg': str(exception)[:500],
                        'method': request.method,
                        'path': request.path,
                    }
                )
            except Exception as e:
                logger.error(f"审计中间件异常记录失败: {e}")
        return None  # 不拦截异常，让 Django 正常处理

    @staticmethod
    def _is_ignored(path: str) -> bool:
        for p in AuditMiddleware.IGNORED_PATHS:
            if path.startswith(p):
                return True
        return False
