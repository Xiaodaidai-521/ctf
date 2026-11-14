# 全量检查：部署与环境专项（2026-11-13，Asia/Shanghai）

本专项已完成配置、依赖与隔离代理检查，并修复明确问题。当前电脑不能验收完整 Docker 部署：Docker CLI 存在，但 Linux Engine 管道不存在，`docker version` 无 Server，`HypervisorPresent=False`；业务 `.env` 未提供 `TLS_CERT_DIR`、`FRPS_CONFIG_FILE`。没有启动 Docker、改宿主虚拟化设置、部署服务或修改真实数据库。

## 已修复

| 问题与影响 | 最终改动 |
| --- | --- |
| Nginx 允许直接读取反馈附件，绕过 Django 鉴权 | `frontend/nginx.conf:63` 明确对 `/media/feedback_evidence/` 返回 404；原资源公开入口继续拒绝 |
| 静态扩展名正则抢先处理媒体、Django 静态和靶场 JS/CSS，导致别名或代理失效 | `/api/`、`/media/`、`/static/`、`/challenge/` 使用 `^~` 前缀 |
| Nginx 默认 1 MiB 限制阻断允许的资源上传；代理可能把私有内容缓冲到临时文件 | 总请求上限 56 MiB，对应默认 50 MiB 文件、5 MiB 封面及 multipart 开销；API 使用 HTTP/1.1 并关闭请求/响应代理缓冲。Django 继续执行逐文件校验；若部署调整应用上限，需同时调整代理上限 |
| Compose 后端健康检查访问不存在的 `/api/`，且没有处理正式 HTTPS/Host 策略 | 新 `backend/healthcheck.py` 从可信 loopback 请求真实 `/proxy/health/`，使用允许的 Host、Gunicorn 认可的 HTTPS scheme，并要求 200 + 精确响应 |
| Windows 工作树 `start.sh` 为 CRLF，Linux shebang 会失败 | 当前脚本规范化为 LF；Dockerfile 构建时再去除 CR，防止打包差异 |
| Docker build 隐藏静态收集错误，启动也吞掉静态收集失败 | 构建期不再要求运行时密钥；启动获取配置、迁移后收集静态，失败会停止启动 |
| requirements 使用旧 `docx`，缺少 ImageField/PIL 显式依赖和 Windows 原生 ACL 显式依赖 | 使用 `python-docx==1.2.0`、`Pillow==11.3.0`，加 `pywin32==312; sys_platform == 'win32'`；Linux 镜像补 `libmagic1` |
| Docker context 没有排除现有数据库、媒体、日志和本机依赖环境 | 新增 backend/frontend `.dockerignore`；保留应用源码和公开知识语料 |
| 前端镜像使用最新 pnpm 并允许改锁文件，难以复现 | 固定项目声明的 pnpm 10.29.3，使用 frozen lockfile；隔离目录校验现有锁文件成功 |
| 模块七旧交接文档把默认关闭写成接口未实现 | 修正文档状态，区分已实现、默认禁用与尚待真实联调 |

## 实际验证

1. 下载 nginx 官方 Windows 1.28.0 到专用临时目录，使用生成的一小时 TLS 证书、随机 loopback 端口、独立静态目录和 HTTP fixture。16 项检查全部通过，包括配置语法、TLS/HSTS、SPA 深链、媒体/静态别名、私有路径 404、靶场 JS 代理、2 MiB 上传、57 MiB 拒绝、未产生请求/代理临时文件、健康探针成功/失败。结束后 nginx 与 fixture 已停止，临时 TLS 私钥已删除。
2. `.state/full-audit-20261113/venv` 是本轮新建环境；安装项目 requirements 与测试 requirements 成功，`pip check` 通过。版本为 Python 3.12.8、Django 6.0.3、python-docx 1.2.0、Pillow 11.3.0、pywin32 312。旧 `.venv-local` 的 `pyvenv.cfg` 指向搬迁前 `D:\python` 和旧项目路径，不适合复用；没有改旧环境。主检查初始全局环境为 Django 6.0.5，最终测试应注明使用的解释器。
3. 真实 Windows 原生 DACL 回归 5/5 通过；没有放宽权限校验。
4. 真实 `.env` 下 `docker compose config --quiet` 因缺外部 TLS 路径失败。只在独立进程中用临时占位路径校验 Compose 结构，退出 0；这不表示正式 TLS/FRPS 文件存在或可部署。
5. requirements 的干净环境依赖解析退出 0，前端 frozen-lockfile 一致性退出 0；健康探针 Python 编译通过，启动脚本实测 CRLF 数为 0。未执行生产启动脚本或 Linux Docker image build。

专项证据位于 `artifacts/full-audit-20261113/runtime-*`。nginx/ACL 专项结果可能与主检查测试集合重叠，不应直接叠加为全量独立测试数。

## 无法在当前状态完成的前提与待决事项

| 项目 | 明确证据 | 后续需要 |
| --- | --- | --- |
| Docker/WSL2 运行 | Engine 管道不存在，Windows Hypervisor 未运行 | 用户选择在本机恢复 Docker 模式并重启，或在 Linux 测试服务器继续；现有切换说明见 `docs/virtualbox-docker-switching.md` |
| 正式 TLS/FRPS | `.env` 未配置所需外部目录/文件；`frp/frps.ini` 明示为不可直接部署模板 | 提供正式外部文件、域名、网络方案；FRPS 模板 loopback 监听不能直接用于跨容器连接，需按部署拓扑渲染 |
| 安全测试夹具的权限和路径 | phase3 夹具使用 `/tmp` + chmod600。当前 `/tmp` 存在，但实际新建 fixture 的目录、key、manifest 均不满足 Windows native DACL；phase4 固定旧 Linux 恢复证明文件不存在 | 迁移夹具到真实平台权限方式、重新生成可验证的备份/恢复证明。不能造证明或绕过权限让测试通过；相关 direct importers 记录在前置 JSON 中，不等同于失败测试数 |
| Windows libmagic | 干净 requirements 安装后仍缺系统 DLL | 本轮隔离测试用 PyPI `python-magic-standalone==0.4.29` 的 unofficial ABI wheel 中真实 libmagic 5.48 DLL，保留原 python-magic 0.4.27 wrapper。目录、文件哈希记录于 `runtime-native-magic.json`，只用于本轮测试；正式 Windows 分发方案仍须选定，Linux 用已补的 libmagic1 |
| 旧 standalone Nginx helper | `backend/start_nginx.sh:16` 使用旧 `ctf-bridge`、硬编码旧绝对挂载路径，未挂 TLS；`backend/nginx.conf:26` 指向与 Compose 不同的 `frps-server` 名称 | 明确保留/移除该旧入口或按最终拓扑重做。它未被当前 Compose 引用，现阶段不能当可部署入口 |
| 外部模型真实质量 | 2026-11-12 独立报告记录 embedding/DeepSeek 401、火山 429；本专项未重新请求供应商 | 有效凭据、模型权限和供应商额度就绪后，运行真实语义召回、回答引用及并发评测；不能以词法回归代替 |
| 模块四课程开放 | teacher-signoff 无教师签收，行业目录未选、阈值 draft | 两位教师审校与负责人确定目录、依据和开放范围 |
| 模块五课程语义与生产准入 | course-signoff 8.1 明列修复提示/解析引用、解释不评分、外部材料摘要与真实运行依赖 | 决定是否要求解释合格才能通过，确认提示/许可/课程版本，完成真实生产资源和清理验收 |
| 模块七第三阶段正式启用 | 服务与路由已实现，两个写入/发布开关默认 false | 按当前业务评测和审批制度完成模块六/八联调，再决定正式开启；旧文档的“未实现”不能作为现状结论 |

## 需要用户联调的独立清单

- Linux Docker + Nginx + Gunicorn + PostgreSQL 全链路：实际证书、Host/CSRF/Session Cookie、数据库传输、跨容器 FRP 可达性、健康状态和深链刷新。
- 双学生真实靶场：创建、隔离、JS/CSS/WebSocket、不同实验主机名访问、停止/到期/失败回收，以及 CPU/内存/PID 限额和服务器并发。
- 模块四/五课程：真实教师身份、审校与冻结版本、提示/受控解析、验证结果与帮助记录、延迟复测和教学保持观察。
- 模块六/七/八：真实候选和持久化评测报告、独立审批者、后续任务激活、观察、回退和事件对账；已有尝试保留原版本。
- 远程模型/向量服务：有效凭据下真实嵌入、检索、引用与失败处理；既往 401/429 的供应商问题不能由本地代码修复。

这些项目没有报告为通过，也没有因此省略本轮可独立完成的修复和测试。
