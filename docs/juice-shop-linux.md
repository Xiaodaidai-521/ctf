# Juice Shop 接入与 Linux 部署

## 已实现的范围

平台题目列表中的 **OWASP Juice Shop · 数据安全综合靶场** 为自由练习入口。登录用户可启动自己的环境、打开根路径地址、停止环境；再次启动生成全新容器。镜像固定为：

```text
bkimminich/juice-shop:v20.2.0@sha256:8739101ade29358abb5469ee66ae78e582c97ed0a5543a4ad102e5fa5193526b
```

每个实例使用独立 Docker bridge 网络、容器可写层和宿主机端口，不加入平台控制网络，不挂载 Docker socket 或宿主机目录。默认限制 768 MiB 内存、1 CPU、256 个进程，使用镜像的非 root 用户。普通 bridge 网络允许出站访问；它不是阻断宿主机/公网访问的网络策略。教学服务器应放在独立实验网络，通过实验网或 VPN 访问。

平台在商品接口健康检查通过后才显示环境就绪；健康检查失败会回收本次资源。生命周期事件写入现有审计系统。停止和到期回收删除容器及其专属网络，因此练习数据不保留。

此阶段不提供统一 Flag、不计入平台积分，不自动同步 Juice Shop 挑战进度、评分或演练报告。AI、Web3 等依赖额外服务的挑战未配置。crAPI 暂缓接入，项目下现有 crAPI 源码和镜像保留。

## Linux 配置

以下命令在 Linux 服务器上的 `project-code` 目录执行，要求 Docker Engine 使用 Linux 容器、Compose v2+。服务器上的 Docker daemon 必须与后端配置的 daemon 相同。

原有平台 `.env` 中的数据库、SECRET_KEY、ALLOWED_HOSTS、FRP 等必填值应按原部署配置填写。新增参数示例：

```dotenv
# 宿主机实验网/VPN 网卡 IP；仅本机调试时保持 127.0.0.1
JUICE_SHOP_BIND_IP=10.20.0.10
# 学生可访问的实验域名或 IP，不含协议、端口、路径
JUICE_SHOP_PUBLIC_HOST=lab.example.test
JUICE_SHOP_PORT_MIN=18080
JUICE_SHOP_PORT_MAX=18179
# 环境寿命，秒；启动时写入实例的到期时间
CONTAINER_LIFETIME=7200
```

将 `lab.example.test` 解析至实验网 IP，允许学生网络访问 TCP 18080–18179。绑定 IP 必须是 Linux 宿主机实际拥有的地址。默认值为 `127.0.0.1`，远程学生无法通过它访问。

**靶场地址应使用与平台不同的主机名，且平台会话 Cookie 不应设置为覆盖靶场的父域。** 仅换端口不能隔离 Cookie。例如平台使用 `platform.example.test`，靶场使用 `lab.example.test`，平台维持 host-only Cookie。靶场端口直接进入 Juice Shop，不经过平台登录鉴权，故应限定在实验网/VPN 内；平台仍校验环境启停操作的用户身份。

## 安装和导入

```bash
docker pull bkimminich/juice-shop:v20.2.0@sha256:8739101ade29358abb5469ee66ae78e582c97ed0a5543a4ad102e5fa5193526b
docker compose config --quiet
docker compose up -d --build backend frontend container-cleanup
docker compose exec backend python manage.py migrate --noinput
docker compose exec backend python manage.py import_juice_shop
```

`import_juice_shop` 可重复执行，更新同一条靶场记录，不会重复创建。其默认描述与配置会被重新写入。后端启动脚本也会执行数据库迁移。此接入使用现有 Python Docker SDK，后端不需要额外运行 Compose 来启动学生环境。

Linux Compose 中的 `container-cleanup` 服务每 60 秒执行一次 `cleanup_containers`，回收过期运行环境，以及到期的未完成/失败实例。回收服务不运行时，用户查询其过期实例也会触发回收，但这不能替代定时服务。

```bash
docker compose ps
docker compose logs --tail 50 container-cleanup
docker compose exec backend python manage.py cleanup_containers --dry-run
```

宿主机原生运行 Django 时，使用同一虚拟环境执行 `migrate`、`import_juice_shop`，并用 cron 每分钟运行 `python manage.py cleanup_containers`。需要使用相同数据库及 Docker 配置。

## 平台操作

1. 登录平台，进入“题目矩阵”，在 Web 分类找到 Juice Shop。
2. 点击“启动容器”，等待后端健康检查通过。
3. 在新窗口打开给出的 `http://实验域名:分配端口/`，在 Juice Shop 内注册实验账号。平台账号与靶场账号独立。
4. 可打开 `/#/score-board` 查看靶场自身的挑战进度。
5. 点击“停止容器”，或等待平台显示的到期时间。再次启动会得到干净环境。

已有本地演示地址 `localhost:3000` 是独立演示实例，不等同于平台为用户新建的环境。服务器接入无需启动 `external-labs/compose.juice-shop.yml`。

## 验证

新增自动测试覆盖导入幂等性、自由练习提交限制、资源归属校验、失败回滚及回收 dry-run。真实 Docker 测试通过平台 API 验证双用户启动、页面和商品接口、独立网络及端口、停止、重建、到期回收：

```bash
cd backend
RUN_JUICE_DOCKER_TESTS=1 python manage.py test challenges.test_juice_shop --noinput
```

测试需预先拉取上述镜像；使用 Django 测试数据库，结束后清理测试容器和网络。实际 Linux 服务器地址尚未填写，因此远程学生访问仍需在部署时验证。
