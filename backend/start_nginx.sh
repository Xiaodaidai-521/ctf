#!/bin/bash
# 启动Nginx代理容器

echo "启动Nginx代理容器..."

# 检查Nginx容器是否已存在
if docker ps -a --filter "name=ctf-nginx" --format "{{.Names}}" | grep -q "ctf-nginx"; then
    echo "停止并删除旧的Nginx容器..."
    docker stop ctf-nginx 2>/dev/null || true
    docker rm ctf-nginx 2>/dev/null || true
fi

# 启动Nginx容器
docker run -d \
  --name ctf-nginx \
  --network ctf-bridge \
  -p 80:80 \
  -v /workspace/projects/ctf-platform/backend/nginx.conf:/etc/nginx/conf.d/default.conf \
  nginx:latest

if [ $? -eq 0 ]; then
    echo "✅ Nginx代理容器启动成功"
    echo "   访问地址: http://ctf.local:80"
    echo "   健康检查: http://ctf.local:80/health"
else
    echo "❌ Nginx代理容器启动失败"
    exit 1
fi

# 等待Nginx启动
sleep 2

# 检查Nginx健康状态
if curl -s http://ctf.local:80/health | grep -q "healthy"; then
    echo "✅ Nginx健康检查通过"
else
    echo "⚠️ Nginx健康检查失败"
fi
