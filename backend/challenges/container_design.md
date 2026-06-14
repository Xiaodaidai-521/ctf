# CTF题目容器代理功能架构设计

## 1. 总体架构

```
用户请求 → Django API → 容器管理器 → Docker API + FRP API
                                  ↓
                         FRP Server (frps)
                                  ↓
                         用户访问路径: http://domain:port/challenge/{user_id}-{uuid}/
                                  ↓
                         Docker容器 (通过Docker网络访问)
```

## 2. 核心组件

### 2.1 数据模型

#### ChallengeContainer模型
```python
class ChallengeContainer(models.Model):
    """用户题目容器记录"""
    STATUS_CHOICES = [
        ('pending', '待启动'),
        ('running', '运行中'),
        ('stopped', '已停止'),
        ('destroyed', '已销毁'),
        ('error', '错误'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, verbose_name='题目')
    container_id = models.CharField(max_length=100, unique=True, verbose_name='容器UUID')
    docker_container_name = models.CharField(max_length=255, verbose_name='Docker容器名称')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    port = models.IntegerField(default=0, verbose_name='映射端口')
    access_url = models.CharField(max_length=500, blank=True, verbose_name='访问URL')
    frp_config = models.TextField(blank=True, verbose_name='FRP配置')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='启动时间')
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name='过期时间')
    destroyed_at = models.DateTimeField(null=True, blank=True, verbose_name='销毁时间')
```

### 2.2 容器管理器（ContainerManager）

职责：
- 创建Docker容器
- 配置FRP代理
- 管理容器生命周期
- 自动清理过期容器

核心方法：
```python
class ContainerManager:
    def start_container(self, user, challenge):
        """启动题目容器"""
        pass

    def stop_container(self, user, challenge):
        """停止题目容器"""
        pass

    def destroy_container(self, container):
        """销毁容器"""
        pass

    def get_container_status(self, user, challenge):
        """获取容器状态"""
        pass

    def update_frp_config(self, containers):
        """更新FRP配置"""
        pass

    def cleanup_expired_containers(self):
        """清理过期容器"""
        pass
```

### 2.3 FRP配置生成器

基于路径路由模式生成FRP配置：

```python
# FRP配置模板（路径路由）
[http_{user_id}-{container_uuid}]
type = http
local_ip = {user_id}-{container_uuid}
local_port = {challenge.redirect_port}
locations = /challenge/{user_id}-{container_uuid}
use_compression = true
```

访问URL格式：
```
http://frp_domain:frp_port/challenge/{user_id}-{container_uuid}/
```

## 3. API接口设计

### 3.1 启动题目容器
```
POST /api/challenges/{id}/start/
请求: {}
响应: {
    "success": true,
    "container": {
        "container_id": "abc123",
        "status": "running",
        "access_url": "http://domain:9123/challenge/1-abc123/"
    }
}
```

### 3.2 停止题目容器
```
POST /api/challenges/{id}/stop/
请求: {}
响应: {
    "success": true,
    "message": "容器已停止"
}
```

### 3.3 获取容器状态
```
GET /api/challenges/{id}/container/
响应: {
    "container_id": "abc123",
    "status": "running",
    "access_url": "http://domain:9123/challenge/1-abc123/",
    "expires_at": "2025-01-25T12:00:00Z"
}
```

## 4. 技术实现细节

### 4.1 Docker网络配置
- 创建Docker网络：`ctf-network`
- 容器网络别名：`{user_id}-{container_uuid}`
- 容器间通信通过网络别名进行

### 4.2 FRP配置
- 使用FRP 0.37.0+版本（支持locations）
- FRP Server运行在独立容器或主机上
- 通过HTTP API动态更新配置

### 4.3 容器生命周期
1. 用户点击"启动题目"
2. 检查是否已有运行中的容器
3. 分配UUID，创建容器记录
4. 使用Docker SDK创建容器
5. 生成FRP配置
6. 调用FRP API更新配置
7. 返回访问URL给用户
8. 定时任务检查并清理过期容器

### 4.4 容器过期策略
- 默认容器生命周期：2小时
- 过期后自动停止并删除
- 用户可手动提前停止

## 5. 安全考虑

### 5.1 容器隔离
- 每个用户独立的容器实例
- 容器之间无法互相访问
- 限制容器资源（CPU、内存）

### 5.2 网络安全
- 使用Docker网络隔离
- FRP代理只暴露指定路径
- 容器无法访问宿主机网络

### 5.3 权限控制
- 只有管理员可启动所有题目
- 学生只能启动已启用且分类下有权限的题目
- 限制同时运行容器数量

## 6. 配置要求

### 6.1 环境变量
```bash
# FRP配置
FRP_API_URL=http://frps:7500
FRP_HTTP_DOMAIN=ctf.example.com
FRP_HTTP_PORT=9123

# Docker配置
DOCKER_NETWORK=ctf-network
CONTAINER_LIFETIME=7200  # 秒

# 资源限制
CONTAINER_CPU_LIMIT=0.5
CONTAINER_MEMORY_LIMIT=512M
```

### 6.2 依赖安装
```bash
pip install docker requests
```

## 7. 文件结构

```
backend/
├── challenges/
│   ├── models.py              # 添加ChallengeContainer模型
│   ├── container_manager.py   # 容器管理器
│   ├── frp_config.py          # FRP配置生成器
│   └── views.py               # 添加容器相关API视图
└── scripts/
    └── cleanup_containers.py  # 定时清理脚本
```
