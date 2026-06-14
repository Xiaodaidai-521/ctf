# 后端 Dockerfile
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 设置时区和环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai

# 安装系统依赖（Docker CLI + 时区 + curl）
RUN apt-get update && apt-get install -y \
    docker.io \
    curl \
    tzdata \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建必要的目录
RUN mkdir -p logs media staticfiles

# 复制启动脚本
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# 收集静态文件
RUN python manage.py collectstatic --noinput 2>/dev/null || true

# 暴露端口
EXPOSE 8000

# 启动命令（使用 start.sh 处理迁移和启动）
CMD ["/app/start.sh"]
