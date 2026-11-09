# 数据安全验收入口（第1／2期记录与第3期增量）

本文件冻结复验命令／集合和判定口径；最终候选 SHA、实际退出码、失败与独立亲验结论以 R 和 E1/E2 为准。**§1–5 保留第 1 期最初记录，含当时的阻断状态，不代表当前状态。**第 1 期已在 `2970a4cb` 独立亲验通过；第 2 期命令和范围见 §6，执行自检不代替独立验收。

## 1. 环境和命令约定

所有命令从 `/home/hatch/workspace/ctf-data-security` 执行，解释器 `.venv/bin/python`；不 cd 主区。每次用新的证据标签，`isolation.run` 拒绝覆盖。包装器在专用配置下执行命令，不接受继承部署凭据。精确的底层 command/cwd/head/exit_code/output_sha256 均落在 E1 同名 `.json`；`verify_phase1` 汇集它们，不把文档中的预期当实际结果。

```sh
.venv/bin/python -B -m tools.data_security.isolation pg-start
.venv/bin/python -B -m tools.data_security.isolation main-check --label accept-main-check
.venv/bin/python -B -m tools.data_security.isolation main-drift --label accept-main-drift
.venv/bin/python -B -m tools.data_security.isolation main-domain-tests --label accept-main-domain-tests
.venv/bin/python -B -m tools.data_security.isolation mainline-unit --label accept-mainline-unit
.venv/bin/python -B -m tools.data_security.isolation mainline-check --label accept-mainline-check
.venv/bin/python -B -m tools.data_security.isolation mainline-drift --label accept-mainline-drift
.venv/bin/python -B -m tools.data_security.isolation mainline-postgres --label accept-mainline-postgres
.venv/bin/python -B -m tools.data_security.isolation export-check --label accept-export-check
.venv/bin/python -B -m tools.data_security.isolation export-drift --label accept-export-drift
.venv/bin/python -B -m tools.data_security.isolation export-tests --label accept-export-tests
.venv/bin/python -B -m tools.data_security.isolation frontend-build --label accept-frontend-build
```

首次缺 node_modules 时才运行 `frontend-install --label <新标签>`，底层是 pnpm 10.29.3 `install --frozen-lockfile --store-dir <W>/.state/pnpm-store`；构建是 frontend 目录 `pnpm run build`。已经通过且输入未变的安装不重复。PostgreSQL 演练必须保持专用库身份，不能以 SQLite 代证锁。

### 1.1 原测试分组，不删测试

| 包装动作／cwd | 底层入口／集合 |
|---|---|
| main-domain-tests／backend | `manage.py test --noinput -v 2` 加 MAIN_TEST_LABELS：agent_runtime、agents、ai_assistant、audit、challenges、export_quota、export_risk、feedback_center、learning_analytics、learning_map、legal、legal_kb、rag_ingestion、resources、skill_review、student_profiles、test_auth、users。原首次 aggregate 记录中该部分共 476 项，不把这个历史数冒充新命令通过数 |
| main-tests／backend | 保留原 `manage.py test --noinput -v 2` 全目录发现入口用于累计诊断；首次实跑 633 项包含 mainline1 157 项。此单进程先加载 ai_providers，使 mainline 的“无 provider 导入”断言冲突；结果保留，不改旧断言 |
| mainline-unit／backend | 原 README 入口 `python -B -m unittest discover -s mainline1/tests -v`，独立无 Django 进程；实跑 157 项。不可并入先加载 provider 的 Django 进程替代 |
| mainline-postgres／backend | `python -B -m django test mainline1.tests.postgres_cases mainline1.tests.postgres_review_cases mainline1.tests.postgres_planning_cases mainline1.tests.postgres_operations_cases --noinput -v 2`，原 58 项 PostgreSQL 用例 |
| export-tests／tasks/controlled-export-execution | `manage.py test --noinput -v 2 controlled_export`，原 58 项；check 与 makemigrations --check --dry-run 同配置 |
| 新 M0／工具 | 下面的纯 unittest 入口，与 Django 套件分进程；不要求正式 app 注册 |

首次库存为 73 个已跟踪测试相关文件、715 个 AST 测试方法；这是库存而不是通过数。Docker 集成需要固定本地镜像及隔离资源，原 skip 保留为未验分支，不新增 skip、更不把它算成功。现有 Docx 可选库分支已补依赖并定向运行，不能继续靠缺库跳过。新增按域命令是明确分组，不宣称尚未运行的 476 项已经全过；G02 仍阻断。

### 1.2 新契约、边界与看护

```sh
.venv/bin/python -B - <<'PY'
import sys
from tools.data_security.isolation import ROOT, clean_env, run
env = clean_env()
env['PYTHONPATH'] = str(ROOT) + ':' + str(ROOT / 'backend')
raise SystemExit(run('accept-m0', [sys.executable, '-B', '-m', 'unittest',
    'discover', '-s', 'backend/data_security/tests', '-t', 'backend', '-v'], ROOT, env))
PY

.venv/bin/python -B -m tools.data_security.dependencies
.venv/bin/python -B -m tools.data_security.verify_phase1
.venv/bin/python -B tools/data_security/watchdog.py \
  --mapping /home/hatch/workspace/data-security-seven-phases/sessions/phase-01.json --next-phase
```

验收时也应经 `isolation.run` 给后两条检查保存新标签证据。下一期检查在未完成／未独立亲验时**预期退出 1**，不能为追求全 0 改成放行；实际第 2 期开工还须明确本期批准和前置有效性。

新测试包括：

- `test_contracts.py`：所有 DTO 的有效实例、wire/JSON roundtrip、SERVER_ONLY 拒绝客户端、缺字段／额外字段／类型／schema、深不可变、repr/敏感序列化、JSON null、未知值／NaN／重复键、Limits、坐标、哈希／批准绑定、key purpose、格式、UTC、quota unknown、报告复检、reveal 状态、所有 Protocol。
- `test_samples.py`：500 条内存合成集合、类别和 teaching 分组、唯一／确定性、保留地址空间、仅候选 checksum、从未激活凭据、零分母。候选生成／标签校验是夹具，不是 M1 检测器或地区识别。
- `test_dependencies.py`：11×11 导入边及 from/import 两种写法、反向 B、相对／别名、纯层环境／框架／I/O／随机源、动态代码、外层互相依赖／秘密配置、未知模块、本期不接线；真实生产源扫描兼容 Python BOM，不修改原文件。
- `test_import_isolation.py`：全新 `-I -B -S` 子进程、空环境且环境读主动抛错、禁 SDK/Django/DB import、禁 socket、只允许 Python 源／标准库读取、禁文件写入、无媒体目录；导入 39 DTO/19 ports 并 roundtrip Limits。Python 层护栏不冒充 OS 沙箱。
- `test_watchdog.py`：正常 0 退出无标记、异常只写 JSONL，均恢复同 SID 一次；并发锁、旧 PID 元数据、marker/候选/HEAD/脏树、完成与亲验分离、取消／拒绝粘性、控制哈希、防漏读／半行、OS EACCES 不当用户拒绝、blocked 保持存活。只使用隔离报告夹具。

### 1.3 回退／诊断入口

`tools.data_security.rollback_probe` 必须经 `environment()` 的隔离设置运行。它在新进程使 M0 import 不可用，再运行旧 Django check、1122 条根路由检查和原鉴权中间件／密码哈希检查；没有移动／删除文件或操作真实数据。它只证明第 1 期可断接，**不替代失败的完整回归**。

`mainline-migrate --label <新标签>` 与 `mainline-rollback --label <新标签>` 仅针对 ds_phase1_mainline 的 mainline1 migrations；已有 forward→zero 证据均退出 0。不是生产回填／备份恢复，不重复已通过数据迁移。

`tools.data_security.diagnose_baseline` 只对 6 个既有失败测试观测 SQLSTATE／HTTP status，保持断言和异常流；不记录 SQL、响应体、令牌或测试秘密。失败退出 1 是诊断事实，不是失败注入验收通过。

## 2. 已有基线结果与阻断登记

所有下表标签位于 E1；原失败保留。最终候选验证须记录实际 SHA，不把这些在起点且有新文件未提交时运行的结果冒称独立验收。

| 证据标签 | 亲跑结果／说明 |
|---|---|
| baseline-main-check / baseline-main-drift | 均退出 0 |
| baseline-frontend-install / baseline-frontend-build | 均退出 0，使用冻结锁文件／匹配 pnpm |
| baseline-mainline-unit | 首次 46 项、5 import errors，缺原测试 jsonschema；退出 1，保留 |
| baseline-mainline-unit-deps-fixed | 157 项通过；只补测试依赖 |
| baseline-mainline-check / baseline-mainline-drift | 均退出 0 |
| baseline-mainline-postgres | 58 项、1 failure，新测试角色与原子进程角色不一致；不是业务修复 |
| baseline-mainline-postgres-role-fixed | 原 58 项通过，20.464s；改新隔离配置及专用库 owner，未改旧测试 |
| baseline-mainline-migrate / baseline-mainline-rollback | 专用库正向／逆向均退出 0 |
| baseline-export-check / baseline-export-drift | 均退出 0 |
| baseline-export-tests | 58 项、19 errors、退出 1；B-BASELINE-01 |
| baseline-main-tests | 633 项、17 failures、8 errors、2 skipped，507.153s、退出 1；不是全绿 |
| baseline-rag-docx-env-corrected | 5 项通过：RAG 原 mock-provider 分支＋Docx 4 项；补 optional 依赖、保留原 LLM 默认值，新 Python 网络护栏不允许真实调用 |
| baseline-main-failure-diagnosis | 6 项、5 failures/1 error、退出 1；2 次 0A000、2 次 HTTP 503、3 次 HTTP 401。只证明这次定向请求，不外推所有 19 个 feedback 失败的唯一原因 |
| m0-contracts-first | 37 项通过，契约＋样本 |
| watchdog-fixtures-first | 13 项通过；后续 OS 误分类修复回归见下一行 |
| watchdog-os-error-regression | 14 项通过，真实拒绝仍阻止恢复 |
| m0-boundary-first | 11 项、1 failure；检查器把旧文件 BOM 当语法错误，原文件未改 |
| m0-boundary-encoding-fixed | 12 项通过；检查器按 Python 原始 bytes 解析并加 BOM 正／负回归 |
| phase1-disconnection-rollback | 退出 0；新包不可用时旧 check／路由／基本鉴权仍在，未称完整旧回归通过 |

### 2.1 需验收方处置的旧基线问题

- **B-BASELINE-01，独立执行器 PostgreSQL**：`controlled_export/services.py:378` 在 nullable 反向 OneToOne join 上无 OF 限定 FOR UPDATE，触发 0A000；58 项中 19 errors。另有 `baseline-export-outer-join-reproduction.json` 专用临时表复现。不得改 SQLite、删测试或在 M0 阶段顺手修旧业务。
- **B-BASELINE-02，反馈创建 PostgreSQL**：`backend/feedback_center/services/submission.py:258–261,284` 在创建前无 OF 限定锁 6 个 nullable 外键联查；`views.py:554–563` 会捕获 DatabaseError。主回归中 11 failures 发生在创建期望 201，8 KeyErrors 在读取成功响应字段，尚未到标题所指后续业务。定向 2 项实测 0A000 与 503，确认共用创建入口缺陷，不夸大为 19 个独立业务故障。
- **B-BASELINE-03，挑战代理入口**：`backend/challenges/access.py:17–19` 把签名访问值放 URL 查询参数，与 tests.py:121 不一致；`views.py:362–365` 清空认证器／csrf_exempt，不能满足 Token／Session owner 和 CSRF 断言。定向三次代理请求均 401；不抄签名值进证据，不越界修改路由／权限。
- **B-ENV-01，测试配置（已修正对应分支）**：此前新环境强制关闭 RAG LLM 分支导致 fake-provider 断言失败；移除错误覆盖，保留正式默认值并禁实际网络，定向通过。python-docx 从原 skip 改为具备依赖后实际跑通；两个安装失败及成功重试均保留。
- **B-HARNESS-01，聚合进程污染（已冻结分组，未伪造整套通过）**：mainline semantic 要求 ai_providers 不在 sys.modules；full Django discovery 先加载该旧模块。保留失败，复验按原纯 unittest 单独进程运行，不删该断言；新增 main-domain-tests 尚需验收方按候选实跑。
- **B-RESOURCE-01，Docker 生命周期**：原 pinned-image 分支跳过，未运行、未授权配置共享 daemon／镜像资源；不算通过。若属于必须验分支需提供符合 worktree 隔离要求的资源与授权，不能仅因缺环境豁免。

## 3. 合成数据和统计冻结

数据版本 `synthetic-2026-11-04.v1`，内存确定性生成：四类别各 50 正／50 负＝400，另 trusted-published 50／self-asserted-upload 50＝100，合计 500。每条有唯一 ID／类别／期望／来源版本；可信 teaching 是夹具标签，不是实际批准。哈希为字段长度前缀编码的 SHA-256，`verify_phase1` 只落指纹／计数，不导出样本全文。

邮箱用 `.invalid`，正例 IPv4 用文档网段，卡候选无账户关联且不推断地域；凭据为从未激活的派生夹具。第 1 期未实现检测／脱敏算法，不用 dataset 构建成功宣称召回或漏出达标。后续按既定类别扩充 Unicode、嵌套 JSON、跨块、完整私钥块、格式与异常覆盖，不提前写本期已测这些检测性能。

| 指标／版本 ds.metrics.v1 | 分子／分母及报告要求 | 本期数值 |
|---|---|---|
| 禁止原文漏出数 | 实际响应／最终业务载荷／日志／审计／指定持久化副本的完整禁止样本出现次数；支持验收集合目标 0；teaching 例外单列 | 检测／出口性能未运行，null；证据卫生扫描单列，不与保护性能混淆 |
| 正例召回 | 正确命中正例 / 标注正例，逐类别、逐出口，不以总平均掩盖缺口 | 未运行，null |
| 负例误报 | 被错误处理负例 / 标注负例，差异逐条复核 | 未运行，null |
| 教学误伤 | 非期望修改的已批准教学样本 / 同类样本 | 未运行，null；无正式已批准样本 |
| 启用出口覆盖 | 已通过集成验收启用出口 / 基线应保护启用出口；关闭／未知另列 | 新实现启用 0；旧部署分母未知，null，不填 100% |
| 处理覆盖 | processed/eligible；total=eligible+excluded，eligible=processed+failed+unknown+unscanned；Unit 分开 | 只验不变量和零分母，不编造处理量 |
| 依赖违规数 | M0–M9/B 静态扫描及违规夹具 | 当前检查实际值见 E1；不外推未实现适配器的运行时所有权 |

所有比率保留分子、分母、版本、零分母原因；0 分母必须 null，失败、排除、未知、未扫不可揉成成功。M0 的 Coverage/Metric 已覆盖此不变量；没有真实模型调用、生产 key_ref 或已批准策略版本可填，本期明确记未启用。

## 4. 门禁到可复验证据

| 门禁 | 检查入口／证据 | 判定边界 |
|---|---|---|
| G01 | verify_phase1 的 scope、git diff／HEAD／branch／主区只读比较；本地候选记录 | 必须基线为祖先、只改 M0/test/tools/docs/.gitignore、主区未动；未提交状态不冒充候选 |
| G02 | 新 unittest、原 mainline 两组、主域／执行器回归、前端 build，均有实际命令 | **被 B-BASELINE-01/02/03 与未验资源阻断**；环境／旧基线失败由验收方处置，无豁免 |
| G03 | test_samples、verify_phase1 dataset/metrics，contracts Limits/Coverage | 500 构造＋口径可验；本期无检测性能值 |
| G04 | dependencies＋test_dependencies＋import isolation；contracts 模块／唯一入口表 | 只 M0，无未来实现／bootstrap／正式替身，静态检查非万能沙箱 |
| G05 | 活跃映射／PID-start_ticks／heartbeat、test_watchdog、--next-phase | 演练与实际挂接分别验证；完整放行还缺完成及独立亲验，不能自签 |
| G06 | verify_phase1 的证据权限／合成值与凭据形状扫描；SafeResult；实际操作清单 | 不输出匹配原文；扫描有已知覆盖边界；真实 API／部署／轮换／真实迁移均未做 |
| G07 | disconnection-rollback、mainline forward/zero、原文件未变 | 断接新包不削旧能力；不替代失败回归或生产恢复演练 |
| 1-F01 | operations C01–C16 和 verify_phase1 ID 完整性 | 每项来源／调用方／所有者／子任务／期次／退出明确，迁移全未实施 |
| 1-B01 | 39 DTO 测试＋无 site/env/net/DB/media import 子进程 | 闭类型／有界／未知字段及 schema 拒绝；不声称 DTO 自身授予业务权限 |
| 1-B02 | contracts 两源映射、四组原 Protocol/DTO 保留清单；旧测试 | 不偷换坐标／摘要／批准，未复制整个原业务契约 |
| 1-F02 | operations 对象／出口／用途／厂商区域／原文／D1–D16 | 实测、静态默认与待批未知分开，后期未定能力不启用 |
| 1-B03 | 依赖违规夹具、Limits／Coverage、额度／旧链语义冻结 | unknown 保留，锁序、原摘要不删；待后期真实集成 |
| 1-F03 | watchdog-fixtures 和回归、新鲜候选状态夹具、实际 recovery 证据 | 同 SID 恢复、无重复、标记与亲验分离；真实 R 不由夹具写标记 |

## 5. 依赖／更新责任与复验责任

M0 仅 Python 标准库（PSF 许可），无新第三方运行时依赖。隔离测试新增 jsonschema 4.25.1 与 python-docx 1.2.0（均 MIT），后端契约／测试维护角色负责固定版本、安全更新和重验。原 Django/DRF、psycopg2、pgvector、openpyxl、cryptography 继续由原后端依赖责任者更新；本期读到的精确版本和许可元数据在 E1。Node/pnpm/npm 与前端锁由前端构建责任者维护；PostgreSQL／扩展由隔离资源／部署角色维护。本期未安装新密钥平台、消息总线或 age；未来 age 版本／来源校验与许可证由第 3 期补齐，未定不执行备份能力。

独立验收方必须在报告候选 SHA 上重新亲跑适用命令／构建，检查未运行分支及基线阻断处置、主区状态、回退和证据权限；仅看执行者摘要不能放行。没有全部门禁通过不写真实完成标记；没有同 SHA 的独立亲验通过不启动下一期。

## 6. 第 2 期：纯核心与薄兼容的复验

从 W 执行；每次使用唯一标签，E2=`/home/hatch/workspace/data-security-seven-phases/evidence/phase-02/`。验收者在 R 所列准确候选、干净工作树上重跑，不能把带未提交源码的历史命令算作候选证据：

```sh
.venv/bin/python -B -m tools.data_security.verify_phase2 all --label accept2-all
.venv/bin/python -B -m tools.data_security.verify_phase2 metrics --label accept2-metrics
.venv/bin/python -B -m tools.data_security.verify_phase2 dependencies --label accept2-dependencies
.venv/bin/python -B -m tools.data_security.verify_phase2 mainline-unit --label accept2-mainline-unit
.venv/bin/python -B -m tools.data_security.verify_phase2 main-check --label accept2-main-check
.venv/bin/python -B -m tools.data_security.verify_phase2 main-drift --label accept2-main-drift
.venv/bin/python -B -m tools.data_security.verify_phase2 mainline-check --label accept2-mainline-check
.venv/bin/python -B -m tools.data_security.verify_phase2 mainline-drift --label accept2-mainline-drift
.venv/bin/python -B -m tools.data_security.verify_phase2 export-check --label accept2-export-check
.venv/bin/python -B -m tools.data_security.verify_phase2 export-drift --label accept2-export-drift
.venv/bin/python -B -m tools.data_security.verify_phase2 mainline-postgres --label accept2-mainline-postgres
.venv/bin/python -B -m tools.data_security.verify_phase2 export-tests --label accept2-export-tests
.venv/bin/python -B -m tools.data_security.verify_phase2 main-domain-tests --label accept2-main-domain-default
.venv/bin/python -B -m tools.data_security.verify_phase2 main-domain-tests --bound --label accept2-main-domain-bound
.venv/bin/python -B -m tools.data_security.verify_phase2 frontend-build --label accept2-frontend
.venv/bin/python -B -m tools.data_security.verify_phase2 rollback --label accept2-rollback
.venv/bin/python -B -m tools.data_security.verify_phase2 audit --label accept2-audit
```

`all` 包含原63项 M0/依赖/看护测试和本期47项测试（共110项）；`core` 可单独定位纯算法。纯 mainline 与 Django 继续分进程，main18域继续采用已接受的 `baseline_fix_test_cleanup.CleanupRunner`，只清理测试 worker 自有连接，原断言不改、不 keepdb、不强终止连接。数据库动作均核对专用 PostgreSQL，3套 check/drift 不可用 SQLite 替代。

`main-domain-tests` 默认实际执行普通 `python -B manage.py test`，不调用测试绑定；同名JSON应包含manage.py、原18域及CleanupRunner。只有加 `--bound` 才改走 `phase2_test_entry django` 的显式测试装配。两次累计476项串行运行，不能共用正在使用的测试库，也不能用绑定结果代替默认结果。`phase2_test_entry all` 的兼容测试分别验证未绑定／显式绑定／绑定失败，并在每项后恢复全局绑定；正式启动文件不改。

2026-11-05打回证据 `verify2-main-domain-cleanup` 原文件位于E1目录（476项、3失败、1原Docker skip），原样保留；E2的b47e3d92预绑定绿灯不是默认兼容证明。修复后的默认golden直接在内存读取2970a4cb原实现，比较输出与告警、长输入、凭据后缀／块、大小写和法律备注截断边界，不持久化另一份基线算法。

| 门禁 | 可复验入口／测试 | 边界 |
|---|---|---|
| 2-B01 | test_phase2_offline 新 `-I -B` 空环境／空媒体目录进程；整个 core suite 在拒绝环境／I/O／框架 import 的守卫下运行 | 先加载结果脱敏工具，断言 M0–M3 未加载再上守卫；只允许源码／标准库／密码库只读导入。Python guard 不是内核沙箱 |
| 2-B02 | core/services 的固定参数、策略、上下文、时钟、随机材料重复结果 | exact binding 在处理后和审计后复核；不查 latest |
| 2-F01 | 三类300正反例、Unicode跨度／重叠／整字段冲突、JSON原下标和根跨度、表格映射／限额、算法/L3/假名截断负例 | 第四类不自动识别；完整凭据只在已有兼容命中后整体处理；无真实表格交付 |
| 2-F02 | NIST AES-256-GCM空值与零块向量、RFC5869 case1、RFC4231 case1；篡改／跨域／格式负例 | 未迁移历史 Fernet；无部分明文／空值 fallback |
| 2-F03 | 10000次 OS随机封装盐／nonce／密文去重、长度与往返；inspect 标准库 SystemRandom→urandom 路径；正式输入拒绝确定性函数／包装函数／假端口 | 去重不等于随机性证明；仅 B 输入门，实际正式装配留第3期 |
| 2-B03 | 基线 AST 在内存运行的500×3 candidates golden、默认OutputSanitizer／fact_redactor逐项golden、原18域默认476项与显式绑定476项、mainline既有回归 | 默认两旧入口与一期一致；显式绑定保留完整值保护；未绑定与绑定失败严格区分，规则单份，不追加批准差异 |
| 2-B04 | MemoryPolicy、FakeKeys、MemoryAudit 正／拒绝／异常／坏收据／撤销／到期；生产环境拒绝 | 测试替身仅 tests，不接正式设施；审计成功不代表交付成功 |
| G01/G04 | phase2_audit、phase2依赖扫描、原 phase1未来模块拒绝夹具 | M0/旧测试不变，其他业务不得直连，M5–M7/真实M8/M9不提前开放 |
| G02 | 上列全部测试和前端构建 | B-RESOURCE-01沿已接受处置保持“环境受限未验”，Docker skip不是通过；无新增skip |
| G03 | phase2_metrics | 每种出口枚举分别运行三类各50正50负与100教学来源用例，只测 M4 合成端口；真实出口指标 null，不能声称集成安全 |
| G05 | 活跃 phase-02映射/PID/checked_at、watchdog原测试及首进程身份新例 | 正常停且无标记仍续同SID；未独立验收必须阻止第3期 |
| G06 | phase2_audit 文件哈希／权限／已知夹具和凭据形状扫描，SafeResult输出 | 不导出样本/根密钥值；当前命令未封口的日志留下一次审计，非万能秘密扫描 |
| G07 | phase2_rollback 禁止核心和B导入后旧check/路由/基本鉴权、默认输出／法律基线兼容、mainline未绑定关闭、M0和已接受修复原样 | 三旧入口反向patch只check未实际回退；不接生产、不改数据／密钥版本、不释放unknown额度 |

G03数据指纹沿用 `synthetic-2026-11-04.v1`，500条不改。每个出口的适用核心样本400，total=400/eligible=350/processed=350/excluded=50；失败／未知／未扫另列，第四族100条明确不适用、不挪成成功数。每类召回/误报保留分子分母；教学批准为测试生成的精确哈希／字段／来源授权，不是实际业务批准。禁止原文指标检查纯返回值及元数据审计中的命中源值；真实响应／模型/日志/持久化未验，单列null。真实启用出口数0，部署分母未知，不填100%。

本期不新增第三方运行时依赖，使用已有 cryptography 44.0.0（Apache-2.0/BSD双许可）；后端维护角色负责安全更新及向量／负例复验。完整运行版本在 phase2_audit；原失败证据保留。R只有准确候选对应的执行完成信号有效，验收者另写同SHA亲验结论；第3期不能由执行者自签放行。

## 7. 第3期：正式适配／P0隔离复验

起点65ef487f，范围和六项隔离批准见R。所有命令从W执行，仍用原专用PostgreSQL，不用SQLite、不读真实厂商凭据、不发真实API。每次新标签；E3记录实际退出码／时间／HEAD／输出摘要，未提交工作树成绩不是准确候选成绩。以下动作均是必跑集合，不能只挑绿色条目。

```sh
.venv/bin/python -B -m tools.data_security.verify_phase3 unit --label accept3-unit
.venv/bin/python -B -m tools.data_security.verify_phase3 integration --label accept3-integration
.venv/bin/python -B -m tools.data_security.verify_phase3 all --label accept3-all
.venv/bin/python -B -m tools.data_security.verify_phase3 core --label accept3-core
.venv/bin/python -B -m tools.data_security.verify_phase3 metrics --label accept3-metrics
.venv/bin/python -B -m tools.data_security.verify_phase3 dependencies --label accept3-dependencies
.venv/bin/python -B -m tools.data_security.verify_phase3 mainline-unit --label accept3-mainline-unit
.venv/bin/python -B -m tools.data_security.verify_phase3 main-check --label accept3-main-check
.venv/bin/python -B -m tools.data_security.verify_phase3 main-drift --label accept3-main-drift
.venv/bin/python -B -m tools.data_security.verify_phase3 mainline-check --label accept3-mainline-check
.venv/bin/python -B -m tools.data_security.verify_phase3 mainline-drift --label accept3-mainline-drift
.venv/bin/python -B -m tools.data_security.verify_phase3 export-check --label accept3-export-check
.venv/bin/python -B -m tools.data_security.verify_phase3 export-drift --label accept3-export-drift
.venv/bin/python -B -m tools.data_security.verify_phase3 mainline-postgres --label accept3-mainline-postgres
.venv/bin/python -B -m tools.data_security.verify_phase3 export-tests --label accept3-export-tests
.venv/bin/python -B -m tools.data_security.verify_phase3 main-domain-tests --label accept3-default
.venv/bin/python -B -m tools.data_security.verify_phase3 main-domain-tests --bound --label accept3-bound
.venv/bin/python -B -m tools.data_security.verify_phase3 frontend-build --label accept3-frontend
.venv/bin/python -B -m tools.data_security.verify_phase3 rollback --label accept3-rollback
.venv/bin/python -B -m tools.data_security.verify_phase3 audit --label accept3-audit
.venv/bin/python -B -m tools.data_security.phase3_backup_verify --tools /home/hatch/workspace/data-security-seven-phases/isolated-tools/phase3-root
.venv/bin/python -B -m tools.data_security.phase3_transport_verify --tools /home/hatch/workspace/data-security-seven-phases/isolated-tools/phase3-root
```

数据库套件串行，包含备份和TLS内的PG探针；不得在旧测试库未释放时启动另一套。普通main-domain仍直接manage.py，不预绑定核心；bound仍独立phase入口。原476项全部保留，新增发现项使总数增长，以实际日志为准。原Docker受限skip保持未验，不加新skip。备份16项位于专用tools入口，不在纯测试中用环境skip冒充绿色。

| 门禁 | 复验覆盖和限制 |
|---|---|
| 3-F01／3-B01 | test_phase3_official：六厂商chat/stream、两embedding、完整PEM／跨块凭据；audit.test_phase3_bootstrap：真实B＋文件仓储／密钥＋PG审计＋单聊/接力/并发/重复请求，以及实际教学/Compliance/RAG、双向跨厂商503切换。仅patch最终HTTP/WS发送，业务结果无裸SDK字段 |
| 3-F02 | official缺钥／撤销／错用途／未批策略／超限／非官方／重定向／审计失败；B拒绝替身／固定随机／动态实现路径／密钥复用及正式启动。输入阶段拒绝发送0；重定向和响应超限只能在原请求后发现，断言无后续发送或部分输出，不能伪称原请求未发生 |
| 3-F03／3-B02 | audit_gateway、audit_persistence、content用例：message/args/exception/extra白名单，跨块保护，旧事件入口最小化，Sink失败不递归，event_id去重、durable与confirmed分开，relay不回流；HTTP/SSE固定异常码、embedding别名与未知厂商/缺handle失败关闭 |
| 3-F04 | phase3_transport_verify实际本机Nginx/Gunicorn/Django TLS、跳转、Secure Cookie、HSTS、可信/非可信peer、PG local及拒绝不安全跨机配置；保存最终配置摘要。不是完整Docker部署或独立执行器TLS证明 |
| 3-F05／3-B03 | auth_crypto/users认证、bootstrap、正式文件权限／身份／撤销和缺钥就绪失败；默认密码／浏览器Coze／旧FRP秘密配送／dotenv／Fernet派生关闭。生产账号吊销、真实设施未操作 |
| 3-F06 | 16项真实age/PG：一致性点及4096+1行计数/摘要、空库恢复、错/缺钥、截断含重算外层hash、导出/加密/恢复失败、argv无秘密；新增真实B/FileKeyResolver在线公钥与独立离线私钥组合。完整文件恢复留第6期 |
| 3-F07／3-F08 | 注册/改密校验、专用带盐PBKDF2-SHA256、1200000成本及旧低成本登录升级；正式Token头拒绝不查旧Token表，Session继续。真实调用方／Token存量未核验，只限本机隔离批准 |
| G01／G04／G05／G06 | phase3_audit检查基线祖先／主区／本期范围／M0与其他旧测试不变／依赖、源码和证据摘要、权限、已知样本及秘密形状、真实看护。唯一获批声明测试按基线全文精确校验仅phase=2→3的一行差异，仍列在变更表、仍接受依赖扫描。没有完成/独立验收时不把进程活着当验收通过 |
| G02 | 本节全部原/新测试、check/drift、前端构建；按15:36批准仅推进当前整仓正例的适用阶段，历史规则断言不变，冻结候选上pure/default/bound必须全绿 |
| G03 | phase3_metrics保留500条指纹；仅三类300正反例＋100教学行经过六模型／两embedding最终捕获及模型响应；无教学例外，批准教学误伤分母0为null。第四族100条明确不适用，不扩检测；已知凭据/字段/旧匹配形状另用针对测试。M7统计用测试durable sink，真实B/PG证据单列 |
| G07 | phase3_rollback真实正式启动后删除测试拥有的策略/数据key文件，验证外发0、内容/字段失败关闭、旧provider/Token不复活、框架独立密钥/密码哈希仍可用；不改源码/真实数据/密钥版本或unknown配额 |

`unit`导出 `<label>-captures.json`，integration导出 `<label>-captures/`，只含已断言的受保护业务载荷和去query官方端点，不含认证头/OAuth材料。每个capture仍须结合本次命令最终通过状态；单个捕获存在不是整套测试通过证明。E3失败历史保留，包括测试策略安装权限错误、统计入口误把禁止的第四族当自动识别的首轮结果；修正口径不等于支持第四类。

**G02处置授权：**R记录用户于2026-11-05 15:36批准把 `test_phase2_boundaries.py` 当前阶段整仓零违规正例的适用阶段更新为phase=3；其余phase1/2历史断言及其他旧测试不改，依赖扫描器没有自动升级或排除名单。原失败保留，冻结候选必须重新全量验证；未全部通过不能写完成标记，第4期须另经独立亲验放行。准确成绩以R/E3为准。

## 8. 第4期：策略持久化、所有者字段与API

基线为第3期已独立验收的4619af208156420d6a01a1937846d5a4473c3665。D4/D5/D9及两项metadata补批已落实；严格隔离合成、不连接生产、不联系真实厂商、无第5期开工。本节是复验入口，不是候选/通过声明。工作树过程成绩与最终冻结候选成绩分开记录。

`verify_phase4 --label <新标签> <manage.py参数>`固定走既有专用PG、原CleanupRunner及E4不可覆盖证据。新增测试入口：

```sh
.venv/bin/python -B -m tools.data_security.verify_phase4 --label accept4-policy test audit.test_phase4_policies audit.test_phase4_policy_api --noinput -v 2 --testrunner=baseline_fix_test_cleanup.CleanupRunner
.venv/bin/python -B -m tools.data_security.verify_phase4 --label accept4-fields test users.test_phase4_fields agent_runtime.test_phase4_fields student_profiles.test_phase4_fields legal.test_phase4_fields audit.test_phase4_fields --noinput -v 2 --testrunner=baseline_fix_test_cleanup.CleanupRunner
.venv/bin/python -B -m tools.data_security.verify_phase4 --label accept4-rotation-m9 test audit.test_phase4_rotation audit.test_phase4_m9 --noinput -v 2 --testrunner=baseline_fix_test_cleanup.CleanupRunner
.venv/bin/python -B -m unittest tools.data_security.test_phase4_evidence -v
```

最后一项仅验证备份验证工具写出的回执：成功/失败两种退出码、原日志字节及SHA-256、0600权限；子进程由捕获替代，不启动数据库或备份工具，不计入真实备份16项。

过程重试仅续未完成/失败项，已通过项不为消耗时间而重跑。最终冻结候选需要完整累计回归，不以分次通过伪装某次整轮完成。普通manage.py、显式bound、纯层发现分别运行；重用verify_phase2/3时将EVIDENCE显式设E4，保留其底层入口不预绑定默认组合。mainline、独立导出、check/drift、官方捕获、备份/TLS与回退沿§7集合，不因第4期新增测试删掉前期门禁。

### 8.1 回退探针的适用阶段

`phase2_rollback`验证的是第2期尚未正式装配时“屏蔽核心/application/B后，旧Django仍可启动”的断接性质。第3期起正式settings在启动边界导入B，不能再把该断接方式作为第4期的兼容回退方案。E4额外运行的`p4-cumulative-phase2-rollback-01`在`django.setup()`加载settings时被探针自己的`DisconnectedCore`拒绝，退出1及原日志保留；它没有运行到后面的check/路由/鉴权断言，也不计作这些断言通过。

本期G07沿第3期已采用的正式失败关闭口径，并增加字段格式兼容恢复；不是删除累计门禁或把旧退出1改判退出0：

| 适用范围 | 探针／证据 | 必须保留的性质 |
|---|---|---|
| 第2期未装配快照 | 原`phase2_rollback`，脚本与断言不改 | 断接后旧入口兼容；当前正式树的退出1只作历史诊断，不作为当前启动应成功的要求 |
| 第3–4期正式装配 | `phase3_rollback`／`p4-cumulative-phase3-rollback-01` | 缺策略/数据钥时停止外发和敏感写入，外发0，旧provider/Token不复活，独立框架密钥及密码哈希保留 |
| 第4期已有sealed字段 | `test_configuration_recovery_preserves_formats_and_refuses_unbound_rollback`／`p4-audit-title-recovery-01`，owner逆schema拒绝用例 | 缺新钥停止且不覆盖密文，禁无绑定读写；恢复同一批准材料后兼容v1/v2，原列仍空，不降密钥版本或恢复明文双写 |

`p4-rollback-applicability-01.json`记录源码/原结果哈希和以上技术处置，属于现有证据核对，不是又执行了一次回退或候选验收。普通manage.py、bound、pure累计要求不变；最终候选仍需准确绑定结果。

### 8.2 本期门禁覆盖

| 门禁 | 当前实现对应复验 |
|---|---|
| 4-B01/F01 | file/ORM共享PolicyRepository契约、不可变版本、CAS、批准/过期/撤销/固定binding、ORM故障不回落；policy_api只接受四种synthetic case，无正文/上下文/密钥接口 |
| 4-F02 | users 3字段、memory/judging 7字段、profile 2字段、legal 3字段，共15种每种100值；SQL完整行副本原文零命中、跨对象不同密文、显式业务读取；获批redacted JSON/标题/任务副本及admin另验；legal.test_phase4_fields新增编排显式读→轻量agent上下文→送模前保护→原列仍空的完整调用测试 |
| 4-F03 | owner角色矩阵、CourseDataGrant真实范围、错误/过期课程、缺request；M9 legacy过渡也遮蔽，实际admin change响应无原文，统计/列表范围相同 |
| 4-F04/F06 | rotation十项（含配置恢复/拒绝无绑定回退）：v1→v2新写/旧只读/逐行CAS重加密/中断重入，双索引deadline与清零退出，缺新钥/坏密文停止，M5撤销及跨用途拒绝，密码哈希不变 |
| 4-F05/C08 | tools.data_security.phase4_backfill_cases：真实22-owner（含AIAuditLog最小化）、每owner100条legacy数据，实际B/FileKeyResolver/age备份与独立离线空库恢复，投影摘要匹配后prepare，失败计数/重试、断点重入、源变动拒绝、重复邮箱人工修改不合并、2200行核对/1500字段授权解密/100行AI审计最小化/SQL零命中、关闭旧读并加22表cutoff、旧写与无绑定读取拒绝、备份残留清理；DB实际Fernet候选计数，不靠源码推断历史 |
| 4-F07 | tools.data_security.phase4_browser_verify.py与phase4_browser_driver.mjs，真实正式settings/URLConf、独立合成库、真实登录/管理员固定预览/非管理员拒绝/非法正文拒绝/存储与网络核对；前端构建单列，运行环境不能导航时必须记未验 |
| 4-B02/G01/G04 | phase4依赖扫描与test_phase4_dependencies：M0–B矩阵不扩大，source精确授权、历史phase仍严格、业务不能导入crypto/key/B、迁移无HTTP；模型仍在owner |
| G02–G07 | 保留原普通/bound/pure、mainline/export、捕获/日志、500样本/三类统计、源码及证据卫生、真实看护和兼容回退。无有效候选完成/独立验收时下一期必须拒绝 |

真实备份回填入口是独立unittest工具，须显式`DS_PHASE4_BACKFILL_RUN=1`，指定`DS_PHASE4_AGE_TOOLS`为已验证age工具根、`DS_PHASE4_CONTROLLED_PARENT`为仓库/E4外0700目录、`DS_PHASE4_BACKFILL_OBSERVATIONS`为新的E4元数据文件，并使用isolation.environment、正式ctf_backend.settings与空的DATA_SECURITY_CONFIG/DATABASE_URL。工具自己创建唯一命名的src/dst合成数据库并执行schema；finally清理自己创建的库/临时材料，不接管默认测试库。完整底层命令、时间/HEAD/hash以E4实际执行记录为准，不复制密钥到证据。

当前镜像Muse Browser 155.0.8059.91在loopback导航返回`ERR_BLOCKED_BY_LOCAL_NETWORK_ACCESS_CHECKS`，已有E4最小复现。未关闭/绕过该安全检查，页面角色/preview交互未跑到，无截图，不计4-F07通过。环境限制不重开已解除的D4/D5/D9，也不能以构建成功覆盖。

独立验收必须核对R的准确候选与当时树状态、全部证据及明确未治理对象；旧物理schema槽保留为空与物理列删除不同，历史RAG/账本治理不能冒充本期完成。只有全部门禁可验，执行者才可给本期完成信号；当前没有该结论。

## 9. 第5期：表格与源计划契约

基线3c8fc8e3包含四期候选34ce6059与显示层补修。2026-11-06 12:12用户明确解除P5-SOURCE-BASIS，只允许本期隔离合成golden的虚构批准；不能据此更改生产B、mainline真实批准门或公共Proposed/draft状态。实际结果与候选以R/E5为准，以下是可重复入口，不是独立验收结论。

所有命令从W执行，标签不可复用；`verify_phase5`写E5，记录命令/cwd/解释器/时间/HEAD/退出码/输出hash，仍复用已有PG身份核验及SafeResult。准确候选追加`--expect-head <完整SHA>`，执行前后均强制该HEAD且clean并留回执。默认/显式bound串行使用原测试数据库、原18域及一期已验收的CleanupRunner（只收尾所属线程连接），**default直接manage.py，不预绑定**。mainline内部纯/PG继续采用其原显式测试装配；未经装配的失败不改写成通过。长累计任务须留足运行时间，中止的无回执日志不能记通过。

```sh
.venv/bin/python -B -m tools.data_security.verify_phase5 --label accept5-default default
.venv/bin/python -B -m tools.data_security.verify_phase5 --label accept5-bound bound
.venv/bin/python -B -m tools.data_security.verify_phase5 --label accept5-pure pure
.venv/bin/python -B -m tools.data_security.verify_phase5 --label accept5-mainline mainline
.venv/bin/python -B -m tools.data_security.verify_phase5 --label accept5-mainline-pg mainline-pg
.venv/bin/python -B -m tools.data_security.verify_phase5 --label accept5-export export
.venv/bin/python -B -m tools.data_security.verify_phase5 --label accept5-check django check
.venv/bin/python -B -m tools.data_security.verify_phase5 --label accept5-drift django makemigrations --check --dry-run
.venv/bin/python -B -m tools.data_security.verify_phase5 --label accept5-goldens python -m tools.data_security.phase5_goldens
.venv/bin/python -B -m tools.data_security.verify_phase5 --label accept5-dependencies python -m tools.data_security.dependencies
.venv/bin/python -B -m tools.data_security.verify_phase5 --label accept5-core-metrics python -m tools.data_security.phase2_metrics
.venv/bin/python -B -m tools.data_security.verify_phase5 --label accept5-provider-metrics python -m tools.data_security.phase3_metrics
.venv/bin/python -B -m tools.data_security.verify_phase5 --label accept5-rollback python -m tools.data_security.phase5_rollback
.venv/bin/python -B -m tools.data_security.verify_phase5 --label accept5-frontend frontend
.venv/bin/python -B -m tools.data_security.phase5_package_verify --label accept5-wheel
```

| 门禁 | 证据入口和判定 |
|---|---|
| 5-F01 | test_phase5_codec/test_source_plans覆盖CSV/XLSX、mainline/旧v1正常/边界/拒绝；test_phase5_pipeline把实际输入字节经Codec→owner治理元数据→SourcePlanAdapter→M1→Codec，独立断言行列/保护结果及固定输出hash；phase5_goldens仅导出输入/源scope/源计划/目标计划/期望输出/实际输出摘要及版本，不导出原文 |
| 5-B01 | 源转换subprocess拒绝Django/network/core导入；普通wheel空venv验证无Django和源路径注入；同输入/绑定/时限得到相同plan_hash，输出ZIP时间及workbook属性固定；缺parser/config owner证据、源漂移/未知版本不能降级 |
| 5-B02 | test_phase5_dependencies与完整扫描，具体模块授权且历史phase1–4仍拒绝未来模块；M8只M0/M8/解析库/包装边界，固定替换唯一M1实现，经注入调用；旧门面不读settings或复制算法 |
| 5-F02 | 缺源批准、unresolved、未知范围、坐标/Unicode映射不可靠、整格/列非法升级、重复标题、scope外sheet/列、零列、旧v1未知字段/不可表达替换、公式表头碰撞、资源/ZIP/XML/类型拒绝；治理JSON预算超限不发布任务成功或原文旁路 |
| G01/G04 | 基线祖先/主区只读/阶段声明、M0及B默认批准不变、完整依赖扫描；只新增表格共享库，无交付/配额/新审计链装配 |
| G02 | 默认/bound各624和pure164历史基线全部保留，加新测试后以实际发现计数为准；mainline157/PG58与新增治理PG、export58、前端/check/drift及三四期原捕获/字段/格式恢复累计；Docker旧环境skip仍为环境受限未验，不算Docker通过 |
| G03 | 原500条冻结合成集和原三类/教学来源统计经phase2/phase3 metrics复验；第四族不新增自动识别。表格golden证明适配语义，不替代真实启用出口指标；输出摘要不是授权 |
| G05/G06 | E5不可覆盖记录、证据权限/hash和秘密形状检查、真实同SID看护/PID/两个日志观察；未独立亲验必须拒绝下一期；实际厂商调用0，生产变更0 |
| G07 | phase5_rollback停新M8后维持三期正式保护失败关闭，四期sealed配置恢复继续累计；不落回raw payload/明文列、不降密钥版本、不释放unknown配额 |

ParsedArtifact新增纯测试与`mainline1.tests.postgres_parsed_artifact_cases`验证受限树、原配置/范围绑定、覆盖/Unicode/元数据预算，以及真实PG原子发布/插入失败/取消/owner ACL。旧postgres_cases仅把两条旧raw payload断言换成等价的版本化snapshot/source断言并增加无raw字段检查；原数量及任务语义不删。两个当前整仓扫描正例随授权阶段改为5，未知阶段探针改为6；历史规则检查仍保留。

主域之外的check/drift通过`verify_phase5 --domain mainline|export ... django ...`运行。原真实备份与TLS工具的`--evidence`显式指向E5；原22-owner回填和CLI/Fernet两项各自通过`verify_phase5 ... backfill <完整unittest名称>`运行，驱动只注入原隔离许可和库外材料目录，观察文件也写E5。`phase5_audit`核对源码/证据hash、旧测试方法无删除及实际看护，审计成功不是对任何失败测试的豁免；最终门禁须逐条读取退出码。四期界面在基线已亲验、本期无前端源码改动，仍实际构建及累计API回归，不把旧截图说成五期新截图。

首轮入口/中间开发失败保留原日志，不把后续重试抹成首次通过。完整候选SHA冻结后重跑累计门禁，执行完成不等于独立验收，亲验与第6期授权仍分开。
