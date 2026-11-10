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

## 10. 第6期：真实锁、回执与故障矩阵（实施中）

基线19c7b639；E6为`~/workspace/data-security-seven-phases/evidence/phase-06/`。`verify_phase6`复用五期驱动，只切换证据目的地；default仍直接manage.py＋原18域，bound才显式预绑定。使用不可复用label，准确候选加`--expect-head <40位SHA>`，运行前后核对HEAD／clean。不直接用verify_phase5把本期证据误写E5。

```sh
.venv/bin/python -B -m tools.data_security.verify_phase6 --label dev6-entry unit data_security.tests.test_phase6_verification
.venv/bin/python -B -m tools.data_security.verify_phase6 --label dev6-dependencies python -m tools.data_security.dependencies --phase 6
.venv/bin/python -B -m tools.data_security.verify_phase6 --label dev6-drift django makemigrations --check --dry-run
# 全部产品实施完成、准确候选冻结后分别执行，不把本表当已运行证明：
.venv/bin/python -B -m tools.data_security.verify_phase6 --label accept6-default --expect-head <40位SHA> default
.venv/bin/python -B -m tools.data_security.verify_phase6 --label accept6-bound --expect-head <40位SHA> bound
.venv/bin/python -B -m tools.data_security.verify_phase6 --label accept6-pure --expect-head <40位SHA> pure
```

| 门禁 | 当前已有测试与仍缺项目 |
|---|---|
| 6-F01 | ReportAuthenticator／ReportProof认证组件新增12项逐项聚合通过：完整执行／对象／计划／算法及摘要绑定、伪造hash/MAC、缺报告／proof、未扫／期限／来源／错钥／用途隔离拒绝；TableReportExecutor新增12项通过，覆盖实际字节复检、漏动作／遗漏sheet、scope投影、标题及未表示OOXML通道、文件验真／认证失败／处理中到期；实际PG私有报告3项通过；新ReportRepository的10项PG逐项聚合通过（首轮全失败，第二轮3过／7失败，只续7项通过）。内部ExportFlow.commit新增11项编排单测分轮通过（成功路径显式使用替身），逻辑回执6项PG通过；owner当前审批／完整Flow接线未完成，不替代完整门禁 |
| 6-F02 | export_risk.tests.test_external_hold／test_flow_recheck：外部hold无双预占、当前授权、scope／审批／环境／期限、claiming复核、竞争prepare／claim；pg_blocking_pids断言真实bucket锁阻塞并持锁跨期限。export_quota.test_phase6_port：完整绑定、commit／release／reconcile幂等、unknown、回执失败及UoW回滚、竞争结算。test_phase6_quota_bridge：经实际M6端口取较短hold期限、绑定漂移／unknown／过期拒绝。新增真实PG提交段3项通过：真实私有报告／MAC／当前ORM策略及风险／额度／v1审计接线，旧链拒绝时全库效果回滚、真实结算后故障回滚、准备后策略退役拒绝。随后audit-v2-flow-postgres-01的真实新链成功／同绑定重放、入链后故障整体回滚、无v2配置拒绝3项全过；Flow完整执行及全阶段矩阵仍缺 |
| 6-B01/B02 | QuotaPort／UoW／DjangoRiskPort已实现；export_risk.tests.test_phase6_port覆盖原DTO／decision引用、一次issue领取、恢复recheck、绑定／当前授权、短事务回滚和竞争单赢家。新增consume要求外层UoW，复核后消费原授权，不写额度；原14项＋新增consume4项及回执仓储6项共24项PG全过。Flow已有commit提交段及内部release／reconcile，后者新增8项单测和6项PG通过；内部execute／reserve／prepare及unknown分流新增12项单测通过，执行／受影响提交／故障PG共19项分两组通过；恢复审计增量90项纯测试及22项PG通过、B正式装配及四端口同契约未完成，不得因此勾通过 |
| 6-F03/F04 | resources.test_phase6_private_store局部端口验证：候选／验真／发布／读密文、篡改／截断／错钥／跨对象、伪造state、孤儿及短UoW回滚；原15项分两次聚合通过，新增20 MiB端口往返通过。crypto-capacity先复现base64超限，修复显式binary格式后新6项＋受影响原服务／契约共40项通过，原语／字段另16项通过。尚缺实际上传／HTTP下载／分享／清理接线、全清单原文扫描及资源实测；仅交换保护实证按2026-11-06 16:05批准环境受限未验，不计通过 |
| 6-F05/F06 | 新v2认证链9项＋受影响旧审计持久化14项，共23项真实PG全部通过：实际MAC、载荷／时间／序号／顺序／插删、只读key、锁竞争及UoW回滚。随后库外checkpoint8项＋受影响新旧链／真实交付4项共12项PG全部通过（audit-checkpoint-postgres-01）：已锚定尾部删除拒绝、后缀窗口、可信显式引用、缺／坏／权限不符文件拒绝和未提交／fsync失败不宣称成功。定期维护／恢复接线、旧链归档桥接和完整DB＋files空环境恢复及RPO/RTO仍未验；旧v1和DB-only结果不替代 |
| 6-F07/G02 | 原默认／bound624及pure241基线保留，数量按新增实际发现增长；局部工作树通过不能代替准确候选累计，默认不得预绑定 |
| 蜜标 | 三类合成plant／check、模型／日志／交付告警入新链与不误报对照未实施，不用后台定时巡检替代工具 |
| G04/G07 | 六期逐源窄授权、历史阶段仍拒未来模块；新增提交段／0005后扫描608文件违规0，前轮0004迁移deletion窄授权遗漏失败证据保留；SecurityEventV2阶段42 DTO／20 ports的39项通过；再增AuditCheckpoint后当前43 DTO／20 ports，新检查点2＋契约30＋import1＋依赖4共37项通过，护栏保留；audit 0007后609文件无违规且drift无变化。提交段首轮45项44过／1失败（数量越界错误码不明确），修复后仅续失败＋新增锁后期限＋受影响成功路径3项通过；不是一次完整suite。M8原goldens与AST证据保留；0005后drift无变化，回退／完整恢复未验 |

受限历史认证增量：`retained-auth-unit-01`新增只读MAC验证4项、报告认证当前13项、原CryptoService4项和契约／import／依赖35项，共56项全过。`retained-auth-postgres-01`新增存储报告read-only验证及受影响原往返／旧链回滚3项全过；不改库内proof、不重新签发、不延长授权。`retained-auth-scan-01`608文件无违规。该轮尚未验证新链；随后audit-v2-postgres-01通过实际新链增量，库外checkpoint的后续增量见6-F05行；真实密钥轮换仍未验。

提交段改发v2证据后，audit-v2-flow-unit-01中的11项全部通过，另1 ERROR为命令误写不存在的旧网关类名；保留退出1日志，仅续正确test_phase3_audit_gateway模块14项（audit-v2-gateway-unit-02）全过，不重跑已绿提交段。

预占前准入增量：`risk-admission-postgres-01`新增6项＋原风险端口18项＋受影响真实v2交付1项，共25项真实PG全过、无skip、退出0。涵盖deny／defer／待审批／不支持义务、当前授权allowlists／subject／domain／environment／期限、审批撤销、失效决策、DB故障和实际`pg_blocking_pids`锁等待跨期限；全部准入不查hold、不创建额度或执行授权。`risk-admission-boundaries-01`4项、`risk-admission-scan-01`609文件零违规均通过。完整Flow执行／失败恢复仍待实施。

准备所有权增量：`preparation-fence-unit-01`的import／依赖／原提交段共16项通过，`preparation-fence-scan-01`检查610文件零违规。PG原选择集31项，01–03迁移中断，04逐项通过9项后中断；05–09没有新增完成项。10只续剩余22项，20通过／2失败、退出1：坏回执被拒但返回通用MISSING_FIELD错误码，旧记录intent计算误把wire列表交给M0规范器。分别在DB解码边界转换为REPORT_MISMATCH、直接按ds-json-v1编码旧wire；不改断言。`preparation-fence-drift-01`无变化、退出0。原日志／选择集保留；两个失败随后在export-recovery-postgres-01均通过，与04／10组成原31项逐项聚合通过，不是一次完整suite。

内部恢复增量：新增release／reconcile编排8项，连同受影响提交段11项及import／依赖5项，`export-recovery-unit-01`共24项通过；`export-recovery-scan-01`610文件零违规。PG选择两项真实失败＋两项受解码改动影响回执用例＋受影响真实v2提交1项＋新增恢复6项，共11项，`export-recovery-postgres-01`全部通过、无skip、退出0（224.783秒）。包含真实提交后确认丢失仍报unknown、同操作重放、未知额度不能release、报告锁内终止后零对账、quota写后故障整体回滚及并发不双退。`export-recovery-working-tree-01`核对结果hash和原31项逐项聚合，M8 parse／serialize与基线AST一致，不是候选累计验收。新恢复权限是显式合成供应器，不是正式owner批准；该轮尚无恢复审计或正式owner入口，后续恢复审计增量单独列证。

内部execute增量：`export-execute-unit-01`新增12项编排测试＋受影响提交11／恢复8／import与依赖5，共36项全部通过，退出0。验证唯一准备权、一次reserve后才issue／加载、已知失败的授权恢复、UNKNOWN保留与不改写已交付、竞争者不abort赢家。提交成功路径使用显式替身，不当真实v2证据。`export-execute-scan-01`610生产文件零违规。`export-execute-postgres-01`新execute8项＋受夹具拆分影响的原commit5项共13项全部通过、无skip、退出0（264.901秒）。从无预占／执行授权／报告／私有对象起，验证真实转换／复检／加密／v2链及2行结算、锁外大I/O、准备竞争不终止赢家、准入撤销／策略退役、已知错误释放和unknown保留；真实reserve或最终交付提交后确认丢失均不重复执行或抹掉成功。只预建构造完整binding所需的真实风险决策，不提前reserve／claim。原5个commit测试断言不变。`export-execute-failures-postgres-01`新增6项全部通过、无skip、退出0（112.002秒）：相同幂等键不同完整binding拒绝，真实reserve写后错误完整回滚且不cleanup，loader失败时恢复权限撤销保留hold，真实报告保存后UNKNOWN保留密文且不重做，真实quota结算后失败及实际v2／回执写后异常先全库回滚、再隔离并全额登记unknown。`export-execute-working-tree-01`核对4份结果hash、受测源码未变、M8 parse／serialize基线AST一致和同SID看护身份；这是dirty时点快照，不是候选冻结。原准备31项和无关恢复组未重复跑。默认／bound入口未更改。

恢复身份与审计增量：`recovery-audit-unit-01`新事件3／恢复身份审计3及受影响契约、Gateway、提交／执行／恢复、import／依赖共90项全过；`recovery-audit-scan-01`610生产文件零违规，当前44 DTO／20 ports。恢复供应器改为返回当前ProtectionContext，布尔true也拒绝；同UoW记录独立QuotaRecoveryEvent及v2回执，审计失败不提交恢复效果。`recovery-audit-postgres-01`选择恢复10／execute7／故障4／v1拒绝对照1共22项全部通过、无skip、退出0（442.400秒），运行前后14份受测源码hash一致。原“无审计行”断言只针对旧成功交付改为严格schema／operation／额度／actor断言，不将合法恢复事件误判成交付；原状态／账务／密文／回滚检查保留。正式业务ACL／owner／B仍未实现。

恢复事件数据库边界增量：`recovery-audit-wire-postgres-01`选择新3项＋原v2／旧链／只读检查点对照3项，原3项通过，新3项在setUp因隔离TMPDIR继承setgid（02700）而失败，退出1。保留日志，只将测试owner新建目录显式chmod0700，与原检查点夹具一致；产品权限检查不放宽。`recovery-audit-wire-postgres-02`仅续新3项全部通过、无skip、退出0（67.199秒）：坏载荷在verify／checkpoint／追加均返回类型化错误且无新增行，重算无密钥摘要不能伪造恢复actor／授权，恢复与普通v2混链接受同一显式检查点。分派改为字段索引，沿用原KeyError／TypeError处理；没有另增异常吞噬。`recovery-audit-wire-scan-01`610生产文件零违规。两个PG组形成6项逐项聚合，不将首轮失败抹去，也不是一次clean候选suite。

B认证链装配增量：`audit-bootstrap-boundaries-01`原三／四／六期依赖护栏20项全部通过，`audit-bootstrap-scan-01`610生产文件零违规，无新增依赖授权。`audit-bootstrap-postgres-01`仅选择新7项及受构造顺序调整影响的旧B6项，共13项全部通过、无skip、退出0（266.097秒），5份受测源码hash运行前后相同；真实FileKeyResolver／受控配置／PG审计，不用FakeKeys冒充正式装配。新配置只在evaluation显式启用，旧无配置仍拒绝新事件；未新增真实配置或生产批准，业务owner／恢复ACL仍未接线。`audit-bootstrap-startup-postgres-01`仅新增实际新配置启动1项及受影响ORM2／字段1，共4项全部通过、无skip、退出0（66.646秒）；子进程使用隔离测试库，实际django.setup后bridge／outbox共用同一新链Gateway并写入恢复事件，错误显式锚点阻止启动且无新增链条。旧ORM故障不回文件、显式ORM装配及100条字段保护不递归断言保留，前轮13项不重跑。

显式恢复权限增量：`recovery-permission-postgres-01`含新权限7、权限锁2、内部Flow4；实际日志13项均有ok，且0007在隔离PG应用，但会话结束后未留下runner汇总／退出码／结果JSON，故只登记13项逐项已观察ok，不宣称完整suite成功。原日志与10份受测源码hash经核对保存于`recovery-permission-postgres-01-interruption.json`；未重跑这13项。仅新增完整Flow报告锁场景，`recovery-permission-flow-lock-postgres-01`1项（到期／撤销两个场景）全部通过、无skip、退出0（21.145秒）；实际观察pg_blocking_pids，锁释放后拒绝恢复，报告abort回滚，原全额hold及密文保留，未新增审计。共享setUp只移动位置，原13项测试方法AST不变。`recovery-permission-boundaries-01`受影响护栏4项通过；`recovery-permission-scan-01`612生产文件零违规，`recovery-permission-drift-01`退出0无迁移差异。没有修改默认／bound／pure入口；许可签发、可信业务身份和正式B接线仍待完成。

私有备份局部增量：`private-backup-postgres-01`新增6项真实隔离PG／age测试全过、无skip、退出0（23.745秒），覆盖同快照数据库＋M6密文往返、候选不自动发布、快照后提交不混入、引用源文件丢失／变动不注册、文件包缺失／截断、缺声明key／错age私钥及代码版本／非空目录／旧v1读取器拒绝。测试使用有效CipherEnvelope与简化四列M6命名表，不是完整业务schema恢复。`private-backup-legacy-postgres-01`仅受共享适配器及夹具拆分影响的旧v1往返／快照／正式B＋FileKeyResolver三项全过（16.626秒），原测试及夹具方法AST保持，默认B不启用v2。

`private-backup-increment-postgres-01`只增4项全部通过、无skip、退出0（18.342秒）：文件age加密／pg_dump失败不登记任一包；认证manifest目录不符在SQL前失败；pg_restore失败保留密文而无成功记录，非空目录重试拒绝；总私有密文25,167,894字节、文件age包25,186,504字节（超过20 MiB）实际往返。`private-backup-increment-observations-01.json`记录适配器Python分配峰值339,846字节，1,926次文件读取均≤65,536字节，create约0.535秒、restore约0.682秒；夹具加密、age／PG进程RSS及完整业务链不在该分配观测内，不能用此代替6-F04或完整RPO／RTO。原6项不重跑、方法及setUp AST不变，产品源码未再修改。

`private-backup-scan-01`612生产文件零违规；只为既有backup源增加stat／tarfile标准库窄授权。`private-backup-boundaries-01`因调用遗漏隔离入口变量而在加载测试前退出1（ISOLATED_TEST_OPT_IN_REQUIRED），原日志保留；02补齐原隔离环境后4项护栏全过，未改产品／断言／网络围栏。完整文件引用／所有key正确性、业务任务／分享、链／检查点与恢复开通仍未完成，不把局部v2结果算作6-F06通过。

备份B显式接线增量：`private-backup-bootstrap-postgres-01`新增1项全部通过（6.341秒、退出0），在真实B／FileKeyResolver下验证旧schema拒绝v2选项，缺项／坏key结构／未知实现路径拒绝，新schema无选项仍保持v1，显式v2在线公钥创建、独立离线文件key恢复后实际解密合成内容；在线没有恢复私钥，离线key不授予在线身份。`private-backup-bootstrap-legacy-postgres-01`仅受本次B字段分派影响的原正式v1备份1项通过（6.324秒），不是重跑原三项；`private-backup-bootstrap-scan-01`612文件零违规。此增量仍用简化M6表，不是业务恢复开通，未增加恢复私钥在线配置。

完整主库恢复增量：`tools.data_security.phase6_recovery_cases`沿用显式隔离备份入口，真实迁移完整主Django库，经现有合成owner执行实际ExportFlow交付，加入候选、回滚形成的未登记密文孤儿、恢复许可及旧v1事件／库外新链检查点。`main-schema-recovery-postgres-01`首轮1 FAIL、退出1（96.488秒）：新测试误把v1追加回执的outbox时间当成verify回执的ledger时间。仅修正为完整比较备份前后verify回执，仍核其entry_ref／sequence／hash与追加回执一致；不改产品或旧测试。`main-schema-recovery-postgres-02`仅续此1项全过、无skip、退出0（93.895秒），12份受测源码留hash。

`main-schema-recovery-observations-02.json`记录178张主库表恢复、12个有序投影、2个引用私有密文；实际报告MAC、解密输出摘要、交付／quota回执、恢复许可、新旧链和显式原检查点通过，候选仍不可读，源孤儿不入包。坏检查点及替换声明data／audit key的实际字节后，独立验真拒绝；该失败发生在恢复后，不伪称BackupPort先验拒绝错误业务key。备份约0.350秒、恢复约18.846秒只是一轮小规模合成主库观测，不代表独立执行器、任务／分享、全部文件／key、保留政策或整体RPO／RTO达标，也未实现恢复开通服务。无关已过局部组未重跑。

蜜标内部工具增量：`canary-unit-01`共46项全部通过（0.384秒、无skip、退出0），其中新工具11项、受影响契约30项／无环境导入1项／六期依赖4项。新增CanarySeed使注册数成为45 DTO／20 Protocol；原导入副作用探针及识别器不删改。三类合成值通过原M1检测，覆盖三种目标标签、明确synthetic、授权True／错对象拒绝、精确命中／脱敏对照／近似长token不误报、JSON键与嵌套／不拼片段、binary未扫拒绝、显式预算、旧链／错误回执及TEST-NET候选来源歧义。

`canary-audit-postgres-01`新增2项真实PG全过（41.067秒、无skip、退出0），普通manage.py入口不预绑定：MODEL／EMBEDDING／LOG／EXPORT四种上下文的元数据事件实际进入同一ds.audit.v2链并逐条verify，无命中对照不新增，旧链条数保持0；未配置新链或audit key不可用时无成功记录。目标写入及授权仍为显式合成回调，不是业务落地，outlet标签也不是实际出口挂接。`canary-scan-01`614生产Python文件零违规；仅将新增M4模块纳入六期清单，无矩阵／外部依赖放宽，M8 parse／serialize和原M1识别AST不变。上述局部组不替代蜜标端到端门禁或准确候选累计。

蜜标出口增量：M0新增CanaryCheckPort，当前45 DTO／21 Protocol，TableSnapshot检查只用于EXPORT。`canary-egress-unit-01`因调用漏DS_TEST_PG_PORT在网络围栏初始化时退出1，未加载测试；`02`使用原完整隔离环境，新增表格检查2项／实际模型出口4项、受影响原蜜标11项／六厂商14项／契约30项／import1项／依赖4项，共66项全部通过（0.981秒、无skip、退出0）。新模型用例只替换终端HTTP／WS传输，真实保护后的业务payload与检查内容相等；另明确故障注入ProtectionPort原样返回，六厂商chat／stream及两embedding共14场景告警并零key解析／零发送；未改原三期断言。

`canary-output-unit-01`新增日志4项／表格5项及受影响原日志4项／表格12项，共25项：20项通过、5项新表格setup错误，退出1。新实现和夹具误用ObjectContext.object_ref，改用既有object_uuid；`02`仅续5项，4通过、1新clean断言失败，退出1。该断言错用输入工作表顺序；按五期既有legacy输出顺序Archive→明细修正精确预期，不改M8或弱化断言；`03`仅续该1项通过（0.146秒、退出0）。这25项是分组开发聚合通过，不冒充一次全绿suite。实际CSV字节注入三类原样值、实际XLSX标题注入TEST-NET值，均在加密／写候选前告警拒绝；原metadata-only日志仍不渲染原文，最终格式化故障才触发新链告警，失败固定输出且不递归日志。`canary-egress-scan-01`614生产文件零违规，依赖矩阵未放宽。

`canary-egress-postgres-01`仅新增3项真实PG全部通过（64.035秒、无skip、退出0），普通manage.py入口无预绑定，实际模型／embedding、日志StreamHandler和表格serialize→parse出口接到唯一Gateway／DjangoAuditSink；clean对照无新链告警，故障注入原样值写ds.audit.v2并实际verify，拒绝发送／原文日志／新候选写入，旧链0条。模型传输只用终端替身，没有真实厂商调用；审计密码使用既有AuditChainFixture的合成FakeKeys，模型provider key用原临时FileKeyResolver。业务权限／埋点仍是显式合成owner回调，不把本轮当正式B启用、智能体注册或完整蜜标门禁。

蜜标运行时增量：`canary-runtime-unit-01`新增8项reference-only工具边界＋受影响六期依赖5项，共13项全部通过（0.096秒、无skip、退出0）。闭合工具参数拒绝模型自报正文／身份／授权／路径；匿名、停用、当前授权撤销、生产上下文、True假批准、读取失败、非法回执及带正文异常均不能变成clean／planted；实际内容只由owner加载。`canary-runtime-scan-01`615生产Python文件零违规，仅增加M9模块声明和跨M4／M6、ORM及线程负例，依赖矩阵／排除不变。

`canary-runtime-postgres-01`新运行时4项＋原AgentGateway6项／API3项，共13项全部通过（67.158秒、无skip、退出0），普通manage.py入口无预绑定。显式注册后由真实网关调用plant／check，合成产物命中经唯一Gateway／Sink入ds.audit.v2并verify，clean对照不告警；其他用户（含admin）、未知引用、已撤销合成许可及数据库停用但内存尚活跃的用户均拒绝，无产物加载／埋点。绑定安全工具的学习任务仍只运行原三项只读工具，没有隐式埋点、模型额外调用或AgentRun蜜标正文记录。审计密码仍用原合成FakeKeys，授权和产物仍为明确测试owner，不冒充业务持久化、正式B注册或蜜标全门禁。原agent_runtime/tests.py与LearningToolRegistry字节保持基线。

额度同契约增量：新增tests内`MemoryQuotaPort`独立有状态实现，和原`DjangoQuotaPort`继承同一`QuotaContract`的14项案例，无实现分支或不同预期。覆盖完整binding／配置、缺失与跨环境、期限边界、无双占／不续TTL、非法数量／证据拒绝、错误不留hold、unknown全额保留、实际结算量、跨请求容量和原回执精确重放。`quota-contract-unit-01`共16项全部通过（14共享＋2实际提交段消费，0.059秒、无skip、退出0）；`quota-contract-postgres-01`同14项全部通过（0.467秒、无skip、退出0，含建库迁移销毁74.856秒），普通manage.py入口不预绑定。原额度／Flow测试及生产源码字节不改，不重跑无关已绿组。内存实现不模拟持久化、并发、DB故障或UoW回滚；原PG专用验证仍独立有效，不能把这两组当作6-B01四端口全过，Risk／PrivateStore／AuditSink同契约仍待。

私有存储同契约增量：新增tests内`MemoryPrivateStore`保存独立登记元数据与规范密文bytes，实际调用原CryptoPort验真；和原DjangoPrivateStore原样继承12项`PrivateStoreContract`。统一验证身份／状态／幂等、错钥／跨对象／salt／nonce／tag拒绝、截断／篡改／缺失、不可覆盖部分密文、孤儿重登记及对象数量／字节占用。`private-contract-unit-01`共14项全部通过（12共享＋2真实TableReportExecutor消费，0.088秒、无skip、退出0）；`private-contract-postgres-01`同12项全部通过（0.676秒、无skip、退出0；含建库迁移销毁64.706秒），普通manage.py、专用PG与本次拥有的私有根，无预绑定。前者已通过后仅核源码hash，不重跑；原生产代码／测试／冻结语义未变。内存不证明权限、fsync、锁、UoW回滚或持久恢复，12项的小规模字节观测不替代20 MiB完整链、崩溃清理和G06；授权到期仍由上层owner检查。6-B01的Risk／AuditSink同契约仍待，整期未完成。

审计同契约增量：tests内独立`MemoryAuditSink`与原`DjangoAuditSink`继承同一`AuditSinkContract`的15项，无实现分支或不同预期，经过真实AuditGateway／CryptoPort。覆盖durable升级、原回执重放、event_id冲突、普通／恢复／旧事件版本隔离、失败不发布、时间顺序、保留只读key、篡改与检查点内容寻址／幂等／覆盖窗口。`audit-contract-unit-01`为13通过、1失败、1错误（退出1）；修新内存v1 wire摘要和新夹具audit-auth前缀后，`02`仅续2项通过（0.026秒、退出0），15项为分轮开发聚合。

审计PG `01`工具120秒时限中断，3项逐项ok但无正常退出；`02`剩余12项为11通过、1失败（237.927秒、退出1）。失败为新PG夹具只patch timezone.now，未控制旧链DateTimeField在导入时捕获的默认回调，导致两种回执时间不同；只修新夹具get_default时钟，不改正式代码或相同回执断言。`03`／`04`均在建库迁移阶段随会话中断、0测试执行，无退出码；`05`以标准manage.py --keepdb续完已核归属且审计记录为空的隔离测试库迁移，只运行失败项与同受时钟影响的旧链对照2项，全部通过（36.030秒、退出0，总79.424秒）。15项按01／02／05逐项聚合，所有失败／中断日志及selection保留，不冒充一次全绿suite或clean候选累计；无预绑定。内存不替代PG锁、外层UoW、真实重启、fsync、权限或库外锚保存，原专项不重跑。Risk同契约及其余整期门禁仍待。

风险同契约增量：tests内独立`MemoryRiskPort`和原`DjangoRiskPort`原样继承19项`RiskContract`，分别搭配有状态内存／正式额度端口。核准入不读hold、完整绑定、当前授权／审批、独占期限、期限只收紧、一次领取／重建后复核、unknown保留、consume作用域／终态、原DTO和准确错误及资源数量。`risk-contract-unit-01`19项全部通过（0.058秒、无skip、退出0）；`risk-contract-isolation-01`独立进程实际导入新实现／共享测试，无Django、ORM或正式仓储模块，退出0。`risk-contract-postgres-01`同19项全部通过（384.997秒、无skip、退出0；总390.110秒），普通manage.py --keepdb、原专用PG，测试库按keepdb保留。两侧本轮各自完整19项退出0，无失败或中断，不以审计旧轮的逐项聚合冒充全候选累计。内存work仅标记作用域，不证明回滚／并发／持久恢复；原PG专项、默认／bound／pure入口和既有生产源码不改，不重跑无关成功组。

上传解析边界增量：`private-upload-boundary-unit-01`运行新增真实Django multipart的13项及受影响源级依赖3项，共16项；15通过、1错误（0.383秒、退出1）。错误是新unittest夹具直接enable override_settings时LazySettings未初始化，并非上传用例失败；仅修夹具先读取普通DEFAULT_CHARSET，不调用B或预绑定安全能力。`02`仅续该1项通过（0.067秒、退出0）；16项是分轮开发聚合，不称一次全绿suite。覆盖20 MiB成功、20 MiB＋1拒绝、更严注入限额、两个合格对象不误当总请求超限、原驻留对象数限制、缺失／伪造part长度、截断、传输及view异常清理、已解析请求不可补绑、原资源与封面validator消费。测试将Django默认内存阈值压到1 byte并禁止TemporaryUploadedFile构造，本次临时目录始终为空；这不是全业务G06扫描、交换保护、进程崩溃或完整链资源证据。`private-upload-boundary-scan-01`检查616生产Python文件零违规、退出0；仅新增本源的解析器及io窄授权和负例，矩阵不扩大。B／实际业务／ASGI前置缓冲尚未接线，6-F03／F04未勾过，旧成功组未重跑。

资源私有上传owner增量：`resource-private-upload-postgres-01`用普通manage.py／专用PG／真实B、FileKeyResolver、multipart和PrivateStore运行新10项及受影响旧上传10／下载3项，共23项，22通过、1失败（205.505秒、退出1）。resources.0004迁移成功。唯一失败是新测试把入库重取后的空cover.name预期为None；Django FileField将空FieldFile存成空字符串。只修这一精确预期，不改产品代码或空文件／私有引用断言；`02`仅续失败1项通过（17.534秒、退出0），23项为分轮开发聚合，不冒充一次完整suite。覆盖实际原件和PNG加密／验真、0600、无普通临时或FileField落盘、当前数据库角色／active复核、伪造客户端引用／状态忽略、封面与DB失败候选保留、旧审核不能开放下载、显式缺服务拒绝、原格式validator及unbound基线。仅合成测试子类注入，不代表默认HTTP、ASGI或完整文件生命周期已接线。

`resource-private-upload-unit-01`新增6项M4准备编排测试和4项新增／受影响依赖测试，共10项完整通过（0.047秒、退出0）：真实CryptoPort／内存PrivateStore、不可发布／读取、跨field认证失败、坏payload／Limits、各端口错误、写后截断、只读key拒绝；M4禁止I/O／业务／M6依赖，资源owner／serializer只消费M0，B仅精确放行新owner。`resource-private-upload-scan-01`检查619生产Python文件零违规，`drift-01`无模型变化，均退出0；`isolation-01`独立进程导入新M4及其测试，无Django／资源ORM／正式仓储，不重跑测试，退出0。没有重跑前轮multipart或其他无关成功组；当前局部证据不替代默认／bound／pure候选累计、G06、6-F03／F04。

未开通入口拒绝增量：`private-ingress-unit-01`仅生成selection，隔离PG socket拒绝连接导致环境准备失败，0项测试启动、无runner结果JSON；原preflight单独保留。经既有owned-restart核目录／归属后重启专用PG，随后`unit-02`运行新入口8项＋新增／受影响依赖4项，共12项全部通过（0.042秒、退出0），没有重跑已过上传解析／owner组。`legacy-guard-01`仅续受分期startup授权影响的原三期反向导入探针1项，通过、退出0。新PHASE6_STARTUP只给根asgi精确guard符号，旧阶段授权及M1／M8不变。

`private-ingress-startup-formal-01`以仓库外合成v1配置执行真实framework_startup／start_application、原URL解析及根application，WSGI两种路径与ASGI四种路径／挂载组合均503、未读body／receive，普通上传和ASGI spool构造均被禁止；原SessionAuthentication／DisabledTokenAuthentication仍在，退出0。`startup-unbound-01`独立新进程无配置，原ASGIHandler及middleware列表不被绑定，退出0。可复验命令为隔离environment下`python -B -m tools.data_security.phase6_ingress_cases formal|unbound`，不使用测试入口预绑定替代真实启动。`private-ingress-scan-01`为当前生产依赖扫描，结果见JSON／log；此处拒绝而非可用上传，不当完整业务G06、资源指标或候选default／bound／pure累计。

反馈私有附件增量：`feedback-private-upload-postgres-01`以普通manage.py、专用PG和真实B／FileKeyResolver／PrivateStore运行新13项及原PermissionAndAttachmentTests两项，共15项全部通过（6.247秒、退出0），feedback_center.0003迁移成功。验证学生／提交者与teacher／admin／superuser权限、当前数据库role／active／superuser及工单归属、staff可见性、客户端伪造引用忽略、实际加密／0600／无FileField写入、缺服务／准备失败／DB失败、候选保留与所有私有下载关闭。原扩展名及10 MiB业务限制保留；拒绝普通磁盘上传对象的负例只创建本次合成临时夹具并清理。原两项按未绑定基线实际上传／下载合成附件，不把该旧明文行为当作私有门禁通过。

`feedback-private-upload-unit-01`运行受改动影响的原入口8项、新反馈路径3项及新增／受影响依赖2项，共13项全部通过（0.036秒、退出0）。B注入UUID路径完整匹配，WSGI／ASGI在body／receive之前拒绝，覆盖尾斜线、挂载、FORCE_SCRIPT_NAME，详情／下载／相似路径仍透传。`startup-formal-01`及`startup-unbound-01`分别以真实启动和原反馈路由验证正式WSGI两路径／ASGI四组合拒绝、未绑定应用不变，均退出0；复验在隔离environment中给原phase6_ingress_cases追加`--owner feedback`，不预绑定。`scan-01`核622生产Python文件零违规、`drift-01`无变化，均退出0。未修改M0／M1／M8或ALLOWED／阶段声明，未重跑不受影响的资源owner、multipart或完整累计。此组未开放可用上传／下载，不替代全业务原文扫描、资源实测、关键新链审计或完整恢复。

反馈上传新链审计增量：`feedback-upload-audit-postgres-01`在原专用PG、普通manage.py无预绑定运行受影响13项及新增真实事务6项；18通过、1错误（125.563秒、退出1）。唯一错误是新测试将含list的持久JSON传给只接受不可变契约类型的canonical_bytes；改用json.dumps检查实际落库事件，原文及文件名不得出现的断言不变，不改产品或M0。`02`只续失败1项通过（21.220秒、退出0）；19项为分轮聚合，不冒充一次全绿suite。核加密／文件准备先于短atomic，附件与PROTECTION新链事件同库提交、metadata摘要绑定、旧v1及仅outbox回执拒绝、实际入链后DB失败整体回滚、真实提交后确认丢失保留附件／事件并返回UNKNOWN；密文均不发布／不删，下载仍503。`feedback-upload-audit-scan-01`核622生产Python文件零违规、退出0；未改迁移或重跑无关成功组。资源上传新链审计、上传unknown对账及完整文件生命周期仍待。

资源上传新链审计增量：`resource-upload-audit-postgres-01`以普通manage.py、原专用PG、无预绑定运行受影响原10项和新增真实事务6项，共16项一次完整通过（301.740秒、无skip、退出0）。原件与封面在事务前完成加密／验真，Resource与两条独立PROTECTION事件同库提交；每条绑定自身密文摘要、实际字节数和相同的整个资源metadata摘要，事件不含标题／描述／文件名／原文。验证第二条审计拒绝时回滚第一条及Resource、两条真实入链后DB失败整体回滚、旧v1／仅outbox拒绝、实际提交确认丢失保留Resource及两事件并返回UNKNOWN，旧审核approved仍不能下载。原10项继续验证权限／引用／故障候选、原格式校验和unbound基线；没有重跑无关反馈／入口或旧资源上传下载套件。`resource-upload-audit-scan-01`核622生产源码零违规、退出0；未改迁移、M0／M1／M8、ALLOWED或阶段声明。可用上传、unknown对账、可信引用加载、完整下载／分享／清理及恢复仍未完成。

可信审计读取增量：原AuditSink增加read_authenticated，正式／独立内存实现复用各自整链验证后返回已认证DTO；共享案例新增7项，本轮只选择新7＋受扫描重构影响旧12项，不重跑另外3项。`audit-read-unit-01`为同19项及M0签名／独立导入2探针，20通过／1夹具错误（0.349秒、退出1）；只将新测试key_ref尾段改为与version=v2一致，未放宽KeyReference约束或读取断言。`unit-02`仅续失败1项通过（0.010秒、退出0），前20项不重跑。首轮源码可精确反向重建匹配selection摘要。

`audit-read-postgres-01`原runner中断，无退出结果JSON，日志只有17项ok、1项ERROR，最后1项未执行；ERROR无完整PG traceback，不把内存堆栈冒充PG堆栈。原日志及interruption记录保留，不补造退出码；`postgres-02`仅续这2项，41.553秒、退出0。续跑预检曾因专用PG停止而连接拒绝，0项启动；经原owned-restart核归属恢复，owner=ds_phase1、active_clients=0后才开跑。19项仅为分轮开发聚合，不是一次完整suite／候选累计。另新增`audit-read-transaction-postgres-01`1项真实外层UoW测试通过（15.944秒、退出0）：读取可看到自身未提交事件，不调用签发、不提交外层事务，回滚后事件消失，明确提交后才保留。该结果不等于业务授权或unknown恢复许可。

读取案例覆盖普通／恢复事件、旧链／仅durable／缺目标／跨链拒绝、伪造正文及重算无密钥hash、坏后缀、显式检查点／已锚定截尾、只读和保留key／缺key、非法引用及证据不变。`audit-read-scan-01`核622生产Python文件零违规、退出0，其后只修夹具、增测试和文档，未再改生产源码或扫描授权。M0只增原Protocol的方法，DTO／Protocol种类不增；M1／M8不变。业务owner可信引用消费、当前权限、unknown对账及完整生命周期仍待，读取拒绝不等于确切无交付。

反馈可信引用消费增量：`feedback-private-reference-postgres-01`新增6项真实PG／B／私有上传测试，120.529秒、无skip、退出0，一次完整通过。验证当前student／submitter／teacher／admin／superuser返回绑定的内部引用；停用／降权／工单归属变更与staff可见性在读审计前复核；全部上传metadata字段、交换引用／Context、换工单／project、审计拒绝／不符事件／仅剩裸事件记录均不能放行。调用链不签发、打开或解密文件、不publish，密文及verified状态不变，原HTTP下载仍503。B仅注入原Sink读取callable，旧create逻辑及B其余逻辑精确反向重建匹配前快照；未重复旧上传／入口成功组。新测试中的不符事件返回值是owner拒绝分支夹具，不冒称真实链可签伪造；成功路径及缺链负例使用实际新链。

`feedback-private-reference-scan-01`核622生产源码零违规、退出0；未增加M0类型、依赖许可或迁移，M1／M8不变。该能力只是当前权限与认证引用加载，不等于完整文件验真、发布、下载授权、持久提交或unknown对账；资源owner对应消费与完整生命周期仍待。

资源可信引用消费增量：`resource-private-reference-postgres-01`新6项真实PG一次全过，120.622秒、无skip、退出0；原件／封面分别认证且不返回部分引用，当前上传者／is_staff权限先于读取，完整metadata／status／换绑／坏链／仅裸事件均拒绝，不读文件、不publish。B补齐原Sink认证读取注入。该轮源码早于reconcile，后者不能借用这6项结果声称已验。

已提交上传观察增量：`private-upload-reconcile-postgres-01`8项中资源4项及反馈2项通过，反馈2项失败，156.756秒、退出1。新反馈夹具将自增pk错当attachment UUID；只修新测试调用参数，反向重建匹配首轮selection hash，产品代码／断言未改。`postgres-02`只续失败2项及同文件受影响2项，4项全过，78.295秒、退出0；原失败保留，8个ID按两轮聚合，不是一次完整suite。真实提交后确认丢失可重新观察且无重写／发布；外层未提交atomic和autocommit=False拒绝，自身读事务退出故障仍UNKNOWN，当前停用／工单移转或缺认证链不成功，回滚后残留密文不自动删除。`private-upload-reconcile-boundaries-01`两个受影响owner护栏通过；`scan-01`622生产Python文件零违规。没有新增M0类型、迁移或权限矩阵修改；HTTP操作引用、负向准备／清理对账、下载／分享及整期门禁仍待。

恢复许可owner增量：`recovery-permission-owner-postgres-01`仅新7项真实PG，一次全过，无skip，137.458秒、退出0。覆盖实际B签发／撤销及新链验证、当前Django权限与active身份（缓存role不授予管理权限）、受领用户／完整binding、期限与参数拒绝、旧v1回执拒绝、入链后DB错误整体回滚及实际提交后确认丢失保留许可引用。`recovery-entry-postgres-01`仅新2项真实PG全过，37.651秒、退出0：B仅暴露原Flow两恢复方法，明确许可下unknown准备被隔离并零结算，重复观察不二次预占／结算；装配后用户停用则回滚报告隔离、保留全部unknown容量。两组源码时点不同，B抽取共用owner组装以复用同一Gateway，后两项验证当前装配，前7项不重复跑。

`recovery-permission-owner-boundaries-01`新owner与受影响窄授权护栏2项通过；其后`recovery-entry-scan-01`623生产文件零违规。只给audit owner M0消费、B精确owner符号和原M6恢复模块transaction授权，未改全局矩阵／阶段声明／M0／迁移／原Flow与Quota逻辑。无默认HTTP或账号权限变更，不冒称完整交付owner／恢复开通／6-B02完成。

备份保留增量：`backup-retention-unit-01`选新6项及受影响M0／独立导入／阶段护栏6项，11过1错；新夹具传入+08:00时间，违反原M0必须UTC规则。仅把该夹具转换成UTC，不改M0或产品／断言；`unit-02`只续这一项，0.006秒通过。两轮是12个ID的聚合，不冒称一次完整suite。新增SERVER_ONLY BackupRetentionRecord，46 DTO／21 Protocol，原隔离探针未删，数量与新类型断言随实际契约更新。

`backup-retention-preflight-01`在PG身份检查连接拒绝，未启动测试、未生成测试结果；随后原isolation受管重启并验证专用集群。`backup-retention-postgres-01`6项均在新fixture setup发生TypeError（把含super()的其他类方法直接用于非子类），0项进入测试体、退出1；只提取共用PrivateBackupFixture并正确继承，原夹具／旧测试可精确反向重建，不重跑已通过旧组。`postgres-02`6项真实PG＋age全部通过、无skip，38.787秒、退出0；日志SHA-256=`ad27f23280b39e7992dd06eaa20a7f6b91bfa245a691a531b675b03ac9d3aac2`。每轮自建合成源／空目标库，夹具按其自有名称删除这些库；不是--keepdb，也不触碰原主测试库。

6项覆盖真实15份受管双包→7日＋4周11份保留及保留点离线恢复、旧无登记v2／孤儿不动、坏新包／缺包／坏登记拒绝清理、服务身份及Limits、创建失败不纳管／v1不可显式纳管、正式B与FileKeyResolver仅在线公钥、双包中断留下retiring并阻断自动继续。不是完整业务文件／任务分享恢复或RPO／RTO证据。`backup-retention-scan-01`624生产Python文件零违规；只增加M4模块阶段声明，ALLOWED矩阵及M1／M8未放宽。另`backup-retention-signatures-01`仅检查本次变化的端口签名护栏1项，通过、退出0。失败预检、失败组与续跑源时点均保留，不把局部D8保留等同6-F06门禁完成。

旧链加密捕获增量：`legacy-archive-postgres-01`仅新9项，全部setup ContractViolation，170.843秒、退出1；新夹具的公钥引用未使用M0规定的用途前缀／版本。只改新KeyReference夹具为有效公钥及有效的缺失／错用途引用，不放宽M0。`postgres-02`选择原9项并failfast，实际3过1失败、后5项未执行，80.145秒、退出1；限额用例把请求expected_count本身设为超限，先触发原count的INVALID_VALUE而非数据库库存LIMIT_EXCEEDED。只将该用例expected_count改为合法的1，使两行数据库库存实际触发原限额检查，断言不改、产品不改。

`legacy-archive-postgres-03`只选该失败项和未执行5项，6项全过、无skip、123.080秒、退出0；日志SHA-256=`de5d7f39b9fbed7f6bbc56702435e63ed34ce3a0c65eaa9e0ab8e04664bfd878`。9个ID是02／03分轮聚合，不是一次全绿suite。每轮先核专用PG身份、test_ds_phase1_main归属和0客户端，普通manage.py --keepdb，无预绑定；保留全部失败及selection，夹具均可精确反向重建此前hash。

覆盖同快照验链／真实age加密和离线解密、源表不变、密文与元数据无合成正文、候选事件经原唯一Gateway写v2并幂等重放／验链、批准count／tail不符及旧链篡改拒绝、未提交事务／错服务身份、数据库行数与单行大小限额、另一PG连接在验链后实际追加且不进入归档、age故障无成功归档／桥接、缺钥／错用途、原默认与快照迭代器验证全部错误字段一致。旧时间和裸事件可被改动而旧摘要仍通过的对照被如实复制，header不宣称两者已认证。此处Gateway调用由测试编排，不是正式审批或桥接入口，源迁移／删除及业务恢复未实现。

`legacy-archive-boundaries-01`新增精确依赖负例1项通过；`legacy-archive-scan-01`625生产Python文件零违规。仅新增M6模块阶段声明及本源Django／audit符号、文件／age管道权限，未放宽ALLOWED，未新增M0类型。原verify_chain仅允许传入有界快照迭代器，逆向恢复入口可逐字节匹配基线，旧hash循环不改。该局部结果不替代6-F05、完整候选累计或生产批准。

旧链当前审批／正式桥接增量：`legacy-archive-owner-postgres-01`仅新7项真实PG＋age，一次全部通过、无skip，135.581秒、退出0；日志SHA-256=`cda91337fd184d9ee9c1b24e6489d65c9263ee518a153a4fdfde9afa486e5ad4`。普通manage.py --keepdb，无预绑定；起跑前核专用集群、测试库owner及0客户端，未重跑旧9项。共享LegacyArchiveFixture提取可精确反向重建上一快照，原9项测试体未改。

7项覆盖显式B、当前数据库权限／active状态覆盖缓存、AUTHORIZATION精确绑定旧count／tail、真实age及唯一Gateway写BACKUP后持久化回执、重启对账幂等；外层未提交事务、错参数／前缀、无新链／生产配置、批准审计失败或旧链回执拒绝。BACKUP写前／真实写后确认丢失、回执文件fsync失败均保留原archive_ref和密文，新B对原event_id对账且不再create；截断密文、坏登记、登记内部一致但与已认证批准不符、篡改批准正文均拒绝重桥接。只覆盖隔离合成归档，不是离线业务恢复或旧源迁移／删除。

`legacy-archive-owner-boundaries-01`新owner／M4精确依赖护栏1项通过；`legacy-archive-owner-scan-01`628生产Python文件零违规。M4不读ORM／文件，owner仅消费M0，B只增加精确owner授权，ALLOWED及阶段边界不变；M0仍46 DTO／21 Protocol。audit.0008只增加自定义权限选项，不自动赋权；测试库应用成功，`legacy-archive-owner-drift-01`退出0且无变化。原M6 create、B其余装配、models其余内容和旧夹具可反向重建上一快照，M1 redaction／M8 parse／serialize保持基线AST。上述局部结果仍不替代默认／bound／pure候选累计或6-F05完整门禁。

目标计划审批增量：`export-plan-owner-postgres-01`新增7项真实PG，日志逐项均ok，但runner在最终汇总／退出记录前中断，无结果JSON，不能称整组退出0。源码与selection全部匹配，原日志SHA-256=`662fa94089dd169b44ca3f2922caceb85ff6d21bdcffc0512b5bee04471f74b1`；另存interruption记录，没有重跑已ok项。覆盖显式B、新M0 Approval两人分离、当前权限／active覆盖缓存、完整目标／binding／context与伪造批准拒绝、未解决／过期／外层事务拒绝、实际入链后故障及旧链回执整体回滚、真实提交后确认丢失保留稳定引用，以及通过pg_blocking_pids确认真实许可行锁等待后复核期限。

`export-plan-consumption-postgres-01`选择新3项，首项在许可表总数应为1的断言失败，18.059秒、退出1，余2项未执行；此前owner组中断，首轮未记录表初始数量，不能确证遗留记录来源或编造实际计数。首轮失败及日志保留。正常失败收尾后实查审批／审计／额度／报告等8表均0行、无其他客户端，`02`仅续失败1项及未执行2项，源码和断言不变，3项一次全部通过、无skip，59.705秒、退出0。普通manage.py --keepdb，无预绑定，不手工删表或放宽计数。验证原真实ExportFlow消费当前目标审批：实际交付2条、单次结算／发布及回执重放不加载原文；预占前撤销不创建hold／报告／候选／执行授权；锁外准备中撤销在提交复核拒绝，保留reserved全额、verified候选和prepared报告，不自动释放。审批和交付／撤销共用真实v2 Gateway；风险／源／输入仍为合成测试供应器，不算正式端到端交付B。

`export-plan-owner-boundaries-01`新增依赖护栏1项通过；`export-plan-owner-scan-01`631生产Python文件零违规；`export-plan-owner-drift-01`security_policies无模型变化、退出0，0008在隔离PG已应用，不自动赋权。owner仅消费M0，M6不写风险／额度或读取源，B精确owner授权；全局ALLOWED／phase-boundary不改，M0类型不增。去掉本轮B函数／模型可精确重建旧快照，原Flow／Quota／Risk及报告仓储hash不变，M1全AST与M8 parse／serialize AST仍等于基线。审批UNKNOWN完整管理对账、可信资产／源计划／请求供应器、HTTP及完整候选累计仍待。

审批UNKNOWN正向对账增量：`export-plan-reconcile-postgres-01`只运行新增4项真实PG，78.480秒、全部通过、无skip、退出0；日志SHA-256=`ceb267cfc8601c65ce4573099fa61beb98f2210d8097d76ebcb7bb2bb2d849c2`。起跑前实查审批／审计／额度／报告等8表0行、专用测试库owner及无其他客户端，普通manage.py --keepdb、无预绑定。真实批准提交确认丢失后重建B，以原draft和stable ref恢复完全相同Approval；禁止identity和record_event调用，重复观察保持1许可／1事件、无quota。另验当前管理权限／停用、外层事务、撤销／到期、缺引用／错binding／context、许可文档换人、原批准事件正文篡改及读事务退出失败；错误不产生新批准或自动清理。

新管理对账经read_authenticated比对原AUTHORIZATION metadata，消除上一增量中“不能按引用找回原批准”的缺口，但仍只是现存有效批准的正向观察，不处理缺行的负向效果判定、重新签发、下载或完整业务恢复。`export-plan-reconcile-boundaries-01`受本轮新M0导入和B接线影响的原护栏1项通过，`scan-01`仍631生产文件零违规；依赖声明／模型／迁移均未改，不重跑已通过drift。原manage／write／authorize及原7项测试可精确反向重建上一快照，B只多注入原认证读取／read_approval；原Flow／Risk／Quota／报告仓储及3项消费测试不变，不重跑无关成功组。

当前工作树累计预检（非候选）：`cumulative-pure-precheck-01`沿原未绑定all入口完整执行478项，477通过／1失败，20.385秒、退出1。唯一失败为旧phase2 MemoryAudit漏实现本期AuditSink新增的read_authenticated；生产契约不改，夹具仅补明确返回AUDIT_UNAVAILABLE的方法，不把内存事件伪装为认证链。原失败测试及其他旧方法／断言保持原样，新增已存／缺失事件均拒绝且不改events的用例。`cumulative-pure-fix-01`只跑原失败1项＋新1项，2项全部通过、0.014秒、退出0；当前479个ID仅为477＋2分轮聚合，不是一次完整pure全绿。原失败、selection及两份source-check均保留；逆向移除新增方法／测试后精确恢复基线文件，原149份工作树文件在文档更新前全部未变，未重跑无关成功项。

保留入口的完整组合：`cumulative-mainline-precheck-01`157项（2.451秒）、`cumulative-mainline-pg-precheck-01`67项（19.204秒）、`cumulative-export-precheck-01`58项（5.887秒）均全部通过、无skip、退出0。mainline沿原显式bound装配，不冒充默认未绑定；独立执行器仍普通manage.py，PG为专用隔离集群／独立测试库，创建与销毁完整结束。`cumulative-frontend-precheck-01`原pnpm build退出0，Vite实测40.82秒，保留大于500 kB chunk警告，未改前端源码、安装依赖或放宽警告阈值。这些证明原组合回归，不证明本期独立执行器私有持久化／恢复已接齐。

默认组合`cumulative-default-precheck-01`发现978项，但启动包装脚本的psycopg2事务上下文退出不关闭连接，遗留自身预检连接使原Django测试库重建失败，退出2、0项执行。原日志保留；仅在包装脚本显式close自身连接，再核其他客户端0，以`02`沿原18域、普通manage.py及原CleanupRunner续跑；不改测试／runner、不预绑定、不强杀连接或手工删库。02在途，退出与完整统计尚待；bound未启动，均不得提前计通过。

随后收到默认02的task stopped通知，但实际核验原PID19827／start_ticks250827、工作区与完整argv匹配，原包装进程也仍存活；`default-runner-continuity-01`时点686项ok、无失败、无最终JSON，未重启或双开。工具任务状态不替代OS进程和真实结果，后续监测覆盖逐项失败、正常退出及无结果退出。完整主Django `cumulative-main-check-precheck-01`与`cumulative-main-drift-precheck-01`各自退出0，正文为无问题／无模型变化；这是check／dry-run，不在测试库启动第二个suite或改迁移。

G03累计：`cumulative-core-metrics-precheck-01`沿冻结500条语料和7种出口枚举，只测M4合成端口。每出口三类各召回50/50、误报0/50；400适用、350处理、50批准教学排除，失败／unknown／未扫已测0，教学误伤0/50、原文命中0；第四族100条明确不适用，真实出口指标仍null／unknown。`cumulative-provider-metrics-precheck-01`沿原文件策略／keys及M7六模型／两embedding最终发送捕获，共3200适用处理，失败／发送原文命中／响应原文命中0、退出0。没有教学例外，误伤分母0为null；真实厂商调用0、生产覆盖null，audit仍测试sink，不冒充PG B或本期完整业务指标。

G06只读开发扫描`hygiene-development-01`检查当前改动源码／E6／R／指定运行与PG日志825文件、5,140,786字节，已知500条语料及原凭据形状无匹配；不是所有秘密／业务文件安全证明。实际发现25份历史证据mode0660，首轮退出1保留；`hygiene-permissions-fix-01`只收紧这25份至0600，逐份正文SHA不变、E6目录0700，不删证据或增加排除项。默认日志仍活跃；完整私有文件／临时／备份／截图扫描未被此结果替代。扫描脚本`.state/phase6_hygiene_01.py`的SHA及实际路径／扫描字节／稳定性逐份留在日志，先捕获stdout后创建输出文件，未用空的自身输出冒充已扫描。

最新续做核验：原默认02的runner与包装PID均已不存在、原task output路径缺失，专用PG停止；02无结果JSON或完整汇总，原日志／151份源码hash核对后归档`default-interruption-02.json`，不补造退出或中断原因。恢复原有受控PG集群后，仅用原18域／CleanupRunner发现978个唯一ID、不执行；原日志完整状态为871 ok＋1 Docker镜像缺失skip。首次107差集selection未执行，核skip后另存02-selection，仅续106个未结束ID，原skip不计通过。`cumulative-default-remainder-02`沿普通manage.py --noinput及原CleanupRunner重建已核owner的隔离测试库，无其他客户端、自身预检连接已close；不预绑定、keepdb、手工清表或强杀。当前在途，bound未启动；续完也仅分轮开发聚合，不当一次完整978退出0。

默认剩余现已收尾：`cumulative-default-remainder-02`106项全部通过、无skip，1120.679秒、退出0，日志SHA-256=`8031aed2d3fae77aca6a9921ba759876efbf7b13d28ffe36898330e06e328ca0`；原CleanupRunner正常销毁测试库。`cumulative-default-aggregate-01`核原871＋新106共977个ok及1个既有Docker skip，覆盖978发现ID、无遗漏／重复，第五期亲验623个ok ID均保留。Docker ID／原因与第五期亲验default／bound逐字相同，原结果hash已核。仅开发聚合，不为中断02补造完整退出。收尾无runner／其他PG客户端、测试库已不存在；`cumulative-bound-precheck-01`现沿原18域／phase2_test_entry django／CleanupRunner串行起跑，显式bound不当默认；完整结果待收，产品／测试源码未改。

bound现已完整收尾：`cumulative-bound-precheck-01`一次执行978项，977通过／1个既有Docker skip，5842.863秒、退出0，日志SHA-256=`5483feeb82e2af38eef8d83b6e68ceee1e2fe36de9c00130bb58f6288180d15e`。原CleanupRunner在所属worker关闭自身连接并正常销毁测试库，收尾无测试runner／其他客户端。`cumulative-suite-parity-01`核7组结果及日志hash，bound与默认开发聚合的ok／skip集合逐项相同；pure仅发现的479 ID与477＋修复2聚合相同。没有重跑pure已过项或给原default／pure补造一次完整成功；产品／测试源码与bound selection相同，仅acceptance改变。这仍是dirty工作树预检，不是完整第6期或干净候选验收。

旧链离线内容验真增量：`legacy-archive-content-postgres-01`新增6项真实PG／age，4通过、1失败、1错误，118.089秒、退出1；失败为测试将原count的INVALID_VALUE误期望为LIMIT_EXCEEDED，错误为缺失KeyReference夹具的key_ref尾段与version不一致，在进入被测方法前被M0拒绝。只修新测试这两处，并保留全部原成功断言及首轮证据，产品代码不改。`legacy-archive-content-postgres-02`仅续该2项，全部通过、无skip，41.418秒、退出0，日志SHA-256=`c914af4c9f24c178e2fb7d9c7f37503eb6f8abf4c60d91feeb717efb7d1e0dda`。6个ID为两轮开发聚合，不是一次全绿suite；普通manage.py／CleanupRunner、无预绑定、无keepdb，两轮正常销毁测试库。

覆盖不访问SQL／不依赖sidecar的真实age＋原v1验链、源表／文件不变、缺钥／错用途／错私钥／错服务身份、密文摘要及age完整认证分别拒绝截断、有效age内坏header／旧链／行顺序／security引用／额外尾部拒绝、单行与计数有界但归档总量可大于单对象限额、权限／symlink与预期桥接绑定拒绝。旧时间和裸事件仍不认证；测试输入证据由夹具提供，本方法不替调用方认证桥接事件或授予恢复／下载。`legacy-archive-content-boundaries-01`原精确依赖护栏1项通过，`legacy-archive-content-scan-01`631生产文件零违规；未改依赖授权／M0／B／迁移，M1及M8冻结AST一致。新接口尚未接owner／B／HTTP，旧源治理、完整恢复与6-F05仍未完成。

归档验真可信入口增量：`legacy-archive-verification-owner-postgres-01`仅新5项与受影响旧B／捕获／对账正反向2项，共7项真实PG／age一次全部通过、无skip，144.355秒、退出0；日志SHA-256=`6b5d4c304af45e9164c39f2a98158850b732ed12b4c68eb05a02ee90dcc3e506`。普通manage.py／CleanupRunner、无预绑定／keepdb，正常销毁测试库。覆盖显式READ_ONLY私钥与默认未启用、当前权限撤销／停用／外层事务在文件访问前拒绝、重启后通过原read_authenticated取得BACKUP并核本地证据、缺失桥接不能由伪造confirmed代替、登记内部一致但与认证事件不符／真实桥接正文篡改不进入解密，以及缺钥／坏文件保留源表和归档。重复verify不写Gateway／create／confirm；原M6内容步骤仍禁止SQL，但owner及认证读取需要可用数据库，不能称整条业务链离线。

`legacy-archive-verification-owner-boundaries-01`原owner／M4精确依赖护栏1项通过，`legacy-archive-verification-owner-scan-01`631生产文件零违规。仅原M4、owner和B增加显式verify接线；原M6／六项内容测试／旧七项owner测试不改，原三份产品文件可逆向重建前一快照，不改依赖授权／M0／迁移／M1／M8。该功能不提供HTTP或历史原文、不恢复数据库、不迁移／删除旧源，也不完成密钥轮换与6-F05整体门禁。

资源实际上传容量增量：`resource-upload-capacity-postgres-01`仅运行新增2项，真实隔离PG、普通manage.py／CleanupRunner，无预绑定／keepdb；一次全部通过、无skip，43.124秒、退出0，正常销毁测试库。日志SHA-256=`3fff6001142b6b4bef05442b8189b8bc5d8c4d54066194088b62db570c17cdda`。20 MiB三类合成标记原件经过真实multipart、原validator、当前owner、M4准备、加密／完整open验真和新链PROTECTION提交；open时不在atomic，原文SHA一致，留下1个verified PrivateObject、1条v2事件、pending资源及空旧FileField，未发布read仍拒绝。唯一0600密文27,963,083字节、SHA与内部引用一致，三标记均未命中、普通MEDIA为空；禁止普通临时上传及FileField保存的原fixture保持不变，正常返回buffer全关。20 MiB＋1在prepare之前RequestDataTooBig并关闭活动buffer，无资源／私有对象／新链记录或文件。

`resource-upload-capacity-observations-01.json`（SHA-256=`dd2462b3cf4830201b57209eeefcbca3a94933baec96d5b0a8387d5df5e605ff`）单次上传区间1.605553秒、12.456770 MiB/s；Python分配峰值219,373,943字节（209.211 MiB），测试runner生命周期RSS高水位前166,195,200／后414,220,288字节（158.496／395.031 MiB）。计时包含multipart构造、原文本校验及tracemalloc开销，不含输入生成、上传后的认证引用读取与文件扫描；RSS不是独立操作峰值或PG／子进程树用量，单次观测不冒称生产吞吐或预算达标。只新增一份测试，未修改产品／旧fixture／Limits／M0／M1／M8／测试入口，不重跑已过上传或累计。正式上传路由仍关闭，跨请求预算、临时对象崩溃清理、完整交付及G06全扫描仍待；tmpfs／交换小项沿批准环境受限未验，6-F04仍不整体记过。

资源上传进程崩溃增量：`resource-upload-crash-postgres-01`只选新增3项，真实隔离PG、普通manage.py／CleanupRunner，无预绑定／keepdb；一次全部通过、无skip，69.130秒、退出0，正常销毁测试库。日志SHA-256=`bedab82917ec0e0f3c2096fe7bfea3a58702c9822ffc6ec7813a01109fb077fc`。每项20 MiB原件均走原显式资源上传组合；fork前关闭父PG连接，测试worker在选定点仅向自身发送SIGKILL，父进程核-9并join／回收。密文fsync后登记前：1文件／0私有行／0资源／0事件；验真后资源创建前：1文件／1 verified行／0资源／0事件；资源与PROTECTION提交后返回view前：1文件／1 verified行／1资源／1事件。三份`resource-upload-crash-observations-01-{ciphertext,verified,committed}.json`分别记录真实状态；每份密文27,963,083字节、0600，三合成标记未命中、MEDIA空。

三窗口均重装原B，伪造published引用仍read拒绝；原密文可完整open且原文SHA一致，检查前后密文保持不变。已提交窗口按已知资源ID两次reconcile只返回原认证引用，无重复资源／私有行／事件或发布。仅新增一份测试，未改产品、旧fixture、限额、依赖或测试入口，未重跑容量两项及无关累计。SIGKILL绕过子进程finally，测试父进程最终清理自有临时目录不算产品崩溃清理；部分密文写入窗口、无业务ID的恢复／负向清理、完整下载交付／恢复与G06全扫描仍待。三项只补实际崩溃残留与隔离观察，不将6-F04或全期门禁勾过，交换小项仍环境受限未验。

资源／反馈私有引用完整主库恢复增量：`upload-owner-recovery-postgres-01`只选原`phase6_recovery_cases.MainSchemaRecoveryAcceptance`新增1项，72.683秒、1 ERROR、退出1；新离线key目录在setgid受控父目录下继承02700，被原FileKeyResolver的精确0700约束拒绝，尚未创建备份或恢复SQL。`upload-owner-recovery-fixture-mode-01.json`在同父新空目录复现，仅为该新增目录补chmod(0700)，不改产品、旧测试、断言或父目录。`upload-owner-recovery-postgres-02`只续同一项，98.310秒、全部通过、无skip、退出0；日志SHA-256=`38471e1556a03ec60101c579d6c436e953eedd127798cd1f2287e999648cbbe4`。沿原显式隔离备份入口，在专用PG中新建本次源／目标库并真实migrate完整主Django schema；不是普通manage.py累计或新恢复协议，未重跑已过组。

真实资源原件／封面和反馈附件经原view、multipart及owner生成，同一个M6根和唯一认证链writer；age v2双包恢复179表，12个有序投影一致，3份私有文件／1资源／1附件／3条新链事件保持。独立保留原FRAMEWORK／DATA／AUDIT ACTIVE引用、policy及明确选定库外锚，用真实FileKeyResolver重装原B，由当前owner重新取得引用，三份密文完整open及原文SHA匹配。停用用户、无权工单用户、资源metadata及反馈摘要篡改拒绝；坏data字节在open拒绝，坏audit字节在B装配／引用认证拒绝，源库及两侧原密文不变。对象仍verified不可read，旧FileField空、MEDIA空，恢复密文及age包0600且三合成标记未命中。`upload-owner-recovery-observations-02.json` SHA-256=`5e367fa797f8617d039396036c1ffea9bd1e9239dab8f56e503cb10d3d02e1c1`，单次create 0.437798秒、restore 20.000859秒；BackupPort的DURABLE不是认证链回执或开通许可，错误业务key字节是在恢复后独立验真拒绝。未实现只读key轮换、旧媒体迁移、独立执行器／分享／任务恢复、自动开通或周期RPO／完整RTO；6-F06和全期不记过。

旧执行器显式私有准备增量：`executor-private-preparation-postgres-01`沿原隔离PG、普通manage.py／IsolatedRunner运行新11＋原相关58共69项，68项ok／1项FAIL、无skip、33.252秒、退出1；日志SHA-256=`111ee13b33744fb19e4d8030871862fc02295f730187e871fca27ffa3744333c`。唯一失败为真实commit确认丢失用例的lost标志未置位，具体被assertRaises捕获的DatabaseError未留存。只读commit-probe复现提交后查询新开事务、恢复autocommit报ProgrammingError，不冒充原失败异常转录。只把该注入器的状态查询移到真实commit前，并要求精确合成异常，保留实际commit及全部后续断言。

另补原expire_stale_attempts对新私有意图的unknown保留分支和两项新旧模式用例。`executor-private-preparation-postgres-02`只续失败1＋新增2项，5.753秒、3项全部通过、无skip、退出0，日志SHA-256=`bcbb46ebb17d3e480e08a74fad9c6a46ea43fcdb1545e5a7b900d8d76de28e90`；未重跑首轮68个ok。当前71个发现ID（新13／原58）为两轮开发聚合，不是一次全绿suite；两轮均正常销毁test_ds_phase1_export。02-selection保存完整发现集、仅续3项、旧测试源码精确逆向重建及另外5份首轮源码hash不变；普通入口未预绑定／keepdb，未重跑主default／bound／pure累计。

新测试用真实FileKeyResolver、M4／M6、隔离PG及CSV三类合成值，覆盖仅verified不可read、真实密文0600／无标记且完整open、prepared不产成功／分享／交付、project／Limits／模式幂等绑定、生产／外层事务／超旧限额拒绝、缺钥、准备确认丢失、真实owner commit后丢确认、授权／lease到期及fence变化、错误准备状态。新过期案例在真实密文准备后以SystemExit模拟worker中断，不称实际SIGKILL；命令保留unknown／repair_required和原密文，重复巡检／请求不重做，旧模式仍stale／failed。新增依赖护栏1项通过；过期分支后scan-02仍632生产文件零违规，原check与全app迁移drift均退出0。未装配正式B／私有HTTP，旧HTTP及临时上传未改，未认证PROTECTION／报告、发布、结算或恢复；不把局部准备当完整执行器或6-F03／6-F07通过。

资源原件内部读取增量：`resource-private-source-postgres-01`仅新增9项及受三处接线影响的旧22项（PrivateStore共享契约12、锁外I/O／回滚2、资源认证引用6、原上传／旧无新链B各1），原隔离PG、普通manage.py／IsolatedRunner，无预绑定／keepdb；31项一次全部通过、无skip，407.167秒、退出0，正常销毁test_ds_phase1_main。日志SHA-256=`de4325c54cf0d384041e0729990ad41cf65e4f8d7a871d4fd886cfe068e0c273`，selection SHA-256=`3b85b75324244a2f457b868b0b47cec6a4479e63c05d1274af9f169f7f5556e4`。没有重跑执行器、恢复、容量、崩溃或default／bound／pure；这31项不是全候选累计。

新增测试经过真实B／FileKeyResolver／资源原件与封面上传及认证新链，验证默认关闭、非bool／无v2装配拒绝、当前上传者／staff及装配后停用／撤权、metadata／项目／缺认证链在文件前拒绝、仅原件完整open且文件I/O／解密不在事务内、外层事务拒绝、candidate／published／未知行及换绑拒绝。DATA缺／错钥在resolver返回边界注入，AUDIT继续用真实resolver，分别得到KEY_UNAVAILABLE／CIPHERTEXT_INVALID；不是物理key文件损坏演练。坏摘要、截断、权限变宽及缺文件均不返回原文或自行修复。正常读取保持全部资源／私有行／两条保护事件和密文不变，原read仍拒绝verified，MEDIA空、0600密文无本例三类合成标记；不当全G06扫描。`resource-private-source-boundaries-01`受影响2项护栏通过（0.011秒、退出0），`scan-01`仍632生产文件零违规；未改原测试、M0、M1／M8、依赖授权或迁移。资源原件仍是BINARY内部载荷，无HTTP、资产版本映射、冻结请求或服务端源计划供应器，不当完整来源／下载或全期门禁通过。

资源原件至交付的合成集成增量：`resource-source-delivery-postgres-01`只运行新5个精确ID，原隔离PG、普通manage.py／IsolatedRunner，无预绑定／keepdb；一次5项全部通过、无skip，96.907秒、退出0，正常销毁test_ds_phase1_main。日志SHA-256=`621bfff458cc9296f23017d545394e75e24d3f17d9aeff33417d556d3231b21e`，selection SHA-256=`bc8d1c54431255e1aa71dffa4570bd7d47a6e2b156bde8b1d4eb17b2087fb90c`。修改文档前171份选择源码hash与运行前一致，旧162份dirty未变，仅新测试成为第163份；无runner／其他PG客户端、测试库不存在，原两库owner不变，检查连接显式关闭。未修改产品或原测试，未重跑旧31项、依赖扫描、恢复、执行器或default／bound／pure，不加算当前完整累计。

本例真实私有TXT原件与封面上传、FileKeyResolver、PROTECTION认证、原件完整打开、原M8转换、当前目标审批、报告／风险／额度／Flow和v2链相连；CSV解释、资产映射、源批准、请求及风险授权明确只由夹具提供。成功交付2条记录，只预占一次；覆盖9格、处理6格、排除3格、命中2处，输出精确匹配原legacy-csv golden，完整open得到CSV而不是裸读封套。原件／封面仍verified，产物published，额度settled=2、授权consumed；新链为两条上传PROTECTION、一条目标AUTHORIZATION及一条DELIVERY，认证交付事件绑定报告与密文摘要。重新装配B／仓储／Flow并回读DTO后仅重放相同回执，不读原件、reserve或publish，原报告规范字节、资源和原两份密文不变；不是OS进程重启演练，也不授予下载。

四个负例分别验证当前原件ACL撤去、裸上传事件不能替代认证、坏原件不变换或修复、真实打开后撤销目标审批阻断最终提交。前3类保留preparing／claiming，最后一类保留prepared／verified；均无DELIVERY，reserved数量2不释放、不结算。本例未提供恢复授权，不能把这些已知错误写成unknown。局部文件0600、两条合成邮箱未命中、MEDIA空；不是三类识别新验或G06全清单扫描。产品仍返回BINARY，原白名单不扩CSV／XLSX，正式默认批准、HTTP拒绝门及M1／M8不改；不代表正式来源供应器、完整业务交付或本期门禁完成。

已交付产物内部读取增量尚未收口：`delivery-read-discovery-failure-01.json`保留新fixture错误导入导致的退出1／0执行；改用现有CipherEnvelope并按原reference语义修新换行断言后，`delivery-read-unit-01`只运行新11项，全部通过、0.117秒、无skip、退出0，日志SHA-256=`d4419458ee3aefef56f8fcb64fb93dfb4b20b6aa20feacdae0be34e78c462a9b`。原phase3_unit_entry、无应用预绑定及PG连接，运行前后选择源码一致。额度子任务首轮缺隔离opt-in退出1／0执行，`quota-read-committed-unit-02`新增8项共享Memory案例全部通过、0.043秒、退出0，日志SHA-256=`c18dd98cbe70092f2180541793a1fbfb72e3ea7507b252c1607d81be1eb7e80d`；不是原14项全套或PG结果。

风险子任务三次API 429后未留下风险实现或完成报告，只有主会话添加的M0声明；12项新额度PG及9项新读取PG草稿均未执行，不计通过。原source-delivery测试的准备部分提取为非测试fixture以复用，原5个测试方法未改、未重跑；该提取未经过PG验证。读取末段还须覆盖比plan／binding更短的consumed授权期限，PG草稿的锁用例须将等待定位到完整open之后的append锁，不能把前置read_authenticated的锁等待算成提交末段验证。协议／依赖探针、读取PG及完整来源／B／HTTP均待后续新块会话，当前成绩不加算default／bound／pure，不作为候选证据。

### 10.1 B1已交付复核与引用恢复增量（非候选，正式来源待授权）

B1先逐份核交接165个dirty文件SHA与基线HEAD，保留前序成果。`b1-delivery-deadline-reproduction-01`因缺网络护栏端口变量退出1、0执行；02实际运行新增1项／两个子场景，均复现额度／审计等待后较短风险期限到期却返回产物的失败。M4最终再次调用原风险复核后，`b1-delivery-read-unit-01`12项一次全过。风险子任务初稿的无行锁假设经主会话审阅纠正，保持decision→authorization锁和不写业务状态；其自报的夹具deepcopy失败及48／49项通过没有独立日志，不当主会话证据。

主会话`b1-risk-read-boundaries-unit-01`按原phase3_unit_entry运行风险31／读取12／依赖及独立导入18，共61项一次全过、0.463秒、无skip、退出0；无PG连接、无应用预绑定。日志SHA-256=`f929c757a11bd0c16e62e466c175cacd8607fa3c5f6357c65780d569a4357950`。`b1-boundaries-unit-01`另有18项通过记录，属于相同护栏的较早轮次，不重复计入累计。`b1-boundaries-scan-01`检查634生产Python文件、违规0；只增M9／0009及精确risk符号授权，不改ALLOWED或阶段口径。M1、M8 SourcePlanAdapter／parse／serialize和mainline1 planning／review冻结AST核对通过。

`b1-quota-read-postgres-01`26项（原14＋新增read_committed12）一次全过，1.033秒、无skip、退出0，正常销毁测试库；日志SHA-256=`5d85e3497bf35a07fb1290065cd357465625a256d0c815d9446f503e32e4bdcc`。`b1-binding-recovery-entry-postgres-01`新binding仓储7项＋原恢复B入口2项一次全过，39.548秒、无skip、退出0；日志SHA-256=`e30a327821e62d8f222cd185d335cf62e30633d334fe423da8015b16630a59ba`。0009在测试库实际应用并正常销毁，尚无独立drift结果，不称原运行库已迁移。新仓储覆盖准备前完整binding、重装读取、旧prepared兼容、旧preparing缺意图UNKNOWN、身份／摘要／环境／坏载荷／DB失败拒绝且不修复；恢复入口保持明确当前权限与唯一额度writer。

`b1-risk-delivery-recovery-postgres-01`已结束：普通manage.py／原隔离PG串行执行210项，200项ok、10项FAIL，无skip，测试耗时1476.440秒，退出1。起止为2026-11-07 19:01:02.869572—19:26:56.805621 UTC，日志SHA-256=`9d65d498543d9eed5b8220a0402e8888861331ac330eb85be98e564b7152da53`。export_risk的187项（含纯研判与真实PG案例）及原件至交付5项逐项ok；内部读取8项ok／1项FAIL；恢复HTTP9项全部FAIL。这些ok是失败组合内的逐项结果，不冒充各小组独立退出0或完整门禁通过。

读取失败位于`resources/test_phase6_delivery_read.py:296`的`assertIn('audit_auditledgerlock', query)`：前一实际Lock／blocking-pids断言已过，但没有证明等待的SQL属于最终审计append，也未到达最后的期限拒绝／状态不变断言。9项HTTP均失败于`audit/test_phase6_recovery_http.py:86`的子进程退出码检查，未进入父测试的HTTP响应／业务效果断言；不能把写了普通django.setup／start_application调用当作已通过正式启动。源码保留setup前只连父runner自有test_ds_phase1_main及无测试恢复callable的约束。安全日志未保留实际等待SQL、子进程退出码值或stderr，根因未确认，不归类为已证实的夹具错误或产品缺陷。失败原件保留；本轮没有诊断修复或续跑，HTTP仍不能按已验入口启用。

`b1-postflight-01.json`核对210个唯一ID、结果／日志SHA和20份既有B1证据；167份源码／阶段声明与在途快照一致。无相关测试进程、无其他PG客户端，两个默认／执行器测试库不存在，原三库owner及专用集群目录正确，检查连接已关闭；diff check通过。该快照不是起跑前选择证据，也不是G06完整扫描、迁移drift或看护验证。

正式来源仍是独立未完成项：现有source-delivery fixture的CSV解释、资产版本、源批准、完整请求及风险输入不构成正式supplier。P6-B1-SOURCE-CONTRACT登记首个正式evaluation来源／源批准与当前使用授权、逐对象格式解释、风险输入权威及mainline1环境冲突的待授权边界。原P5批准不重开，测试许可不接正式B，不改M8／mainline1批准位，不把缺画像／历史当零。B1已将最后在途组的失败结果归档并停止；来源建议未经用户批准，10项失败也未解决。完整交付B和6-F02正式owner矩阵未完成，不启动下一块，无B5候选或default／bound／pure新累计。

PG测试类放在export_risk／export_quota／resources／feedback_center／audit／agent_runtime及controlled_export原域测试目录，不混入data_security纯discover。安全runner成功时丢弃stdout；源码中的print不是额外落盘锁证据。真实结果见各label的JSON退出码及日志，不能给中断任务补造结果。

开发阶段中断续跑允许保留已成功ID、原日志SHA-256、完整discover集及剩余选择集，只跑失败／未完成／受改动影响项。pure-progress-01与03共235项逐项ok、04剩余10项通过；这是245项的聚合开发记录，不是一次完整候选suite。02因缺隔离opt-in启动失败，0项执行；两处旧阶段断言仅把当前树5→6、未知阶段6→7，负例及矩阵不放宽。新增入口测试另有独立label，累计数量随之增长。

本节和R均为执行记录，不替代独立亲验。剩余门禁全部可验（交换小项如实登记）前，无候选完成标记；不推送、不接生产、不进入第7期。

### 10.2 B1四点批准后诊断收尾（2026-11-08；未完成／新风险权威待授权）

§10.1的来源待批／失败未诊断为批准前历史截点。用户已明确四点批准，P6-B1-SOURCE-CONTRACT在受限来源登记、逐对象资源CSV／COLUMN_V1、mainline1拒绝及现有风险权威范围内解除，不重新索要P5或生产批准。

原十项失败复现确认事务内PG活动快照缓存及HTTP fixture未使用HTTPS；只修逐轮刷新／实际主连接阻塞证明和secure=True，原断言、产品安全配置及锁序不改。`b1-failures-fixed-postgres-01`原十项仍8 ok／2 FAIL、259.847s、exit 1；`b1-http-business-diagnosis-postgres-01`最后两项仍2 FAIL、49.471s、exit 1，日志SHA `ccc13db18f4abedd384e7d468f8b541ccbbaff31521586bd46ad02c61d116859`实核。默认503只新增既有5xx的SecurityAuditRecord而业务／额度／许可／认证链不变；unknown release原契约AUTHORIZATION_DENIED映射403，与新HTTP断言的409冲突。后两响应200不证明序列失败后的零结算／回执／审计断言通过，原210项及各失败证据保留，不拆ok为成功suite。

新P6-B1-RISK-AUTHORITY只针对首条COLUMN_V1可用风险权威／条件审批落点；当前正常B没有查到可用路线，mainline1适用性仍false，缺画像仍REQUIRE_APPROVAL，tests-only审批不能替代正式owner，固定政策目录已存在。需指定既有权威路线或另行授权实际必要的持久化供应器，不把来源批准扩成风险批准。正式供应器／完整B／6-F02正式矩阵和6-B02 HTTP验收未完成，收尾停工，默认交付／下载／恢复HTTP不开放，不进下一块。

`b1-authorized-diagnosis-postflight-01.json`核五轮失败／逐ID、53份既有证据0600、170份诊断源码、冻结AST及owned PG无其他客户端／遗留测试库，检查连接关闭。封存后移除临时HTTP诊断，原HTTP全文去掉唯一secure=True即可精确还原批准起点；所有断言保留，当时清理后未重跑。该历史dirty见`b1-resume-blocked-working-tree-01.json`，非候选／G06／drift／看护成绩；09:24批准及续工状态见§10.3和R，不将旧阻断当当前待批。

### 10.3 B1最小风险供应器批准后验证（2026-11-08，实施中）

用户09:24批准按需最小新建，仅实现实际缺失的条件风险许可／审批owner，未同时新建画像／历史／模型供应器。06:50来源四点继续有效。两项HTTP裁定只对齐既有契约：unknown release AUTHORIZATION_DENIED→403不改M4／Quota；默认503保留已有5xx SecurityAuditRecord。独立`b1-http-contract-alignment-postgres-01`完整2 ok、53.797s、exit 0，日志SHA `23634c85d8493af1f9014cb87f878a61218f4981ecac661b349342027a8a092a`；包括后续零对账／重放及全部业务效果断言。旧十项8 ok／2 FAIL、原210失败和各次诊断结果仍保留，不拼接为一次成功suite。

| 证据 | 实际结果及范围 |
| --- | --- |
| b1-formal-owner-boundaries-unit-01／scan-01 | 19护栏通过／640生产Python零违规；早于后续修正，不当最新正式矩阵 |
| b1-source-risk-formal-smoke-postgres-01 | 33项选择、600000 ms中断；仅观察12 ok／1 FAIL／13 ERROR，无完整suite |
| b1-source-risk-diagnosis-postgres-01 | 2项完整1 FAIL／1 ERROR、39.157s、exit 1；确定撤销ID过长及wire列表误用元数据摘要 |
| b1-formal-owner-repairs-smoke-postgres-01 | 环境重启、迁移中断、0测试结果、exit_code=null，独立interruption.json保留 |
| b1-formal-owner-repairs-smoke-postgres-02 | 同8项完整8 ok、194.189s、exit 0；日志SHA `277c76fad36a52ca629e0654e95035e54314ecf1dd7d2773ee12d19be40b0c86` |
| b1-formal-owner-matrix-postgres-01 | 60项完整58 ok／2 FAIL、1472.883s、exit 1；SHA `f1c10cbdf859518daebaa1ac40e44da3025dc676b456fe5a3d11e85422d9fdfa`；新故障见证字段／已交付HTTP状态预期错误保留 |
| b1-formal-flow-regressions-unit-01／02 | 首轮cwd错误触发根目录门，166项／5条SystemExit错误、exit 1；只改执行cwd后同166项全过、4.721s、exit 0，源码／护栏未改 |
| b1-formal-owner-boundaries-scan-02 | 640生产Python零违规、exit 0；与pure首轮失败分列 |
| b1-formal-boundary-waits-postgres-01 | 18项完整17 ok／1 FAIL、542.408s、exit 1；SHA `0fee8cd69b12d79ca1fdc0310af62cc8de5c117dd604e25218e7a0707506c7f3`；三处真实PG等待均通过，唯一目标审批故障注入未拦到已绑定回调 |
| b1-formal-confirmation-competition-postgres-01 | 只修测试的真实回调命中点后，审批恢复＋新双进程竞争2项完整通过、62.734s、exit 0；SHA `e51800b7c24b4308572712cb881f5ec6e38414c736ccbc1524e2b77a8de3451f`，原18项仍记失败 |
| b1-formal-owner-check-01／migration-drift-01 | 普通manage.py check无问题、全app dry-run无变化，各自exit 0；原库未apply／reverse，不当私有迁移／回退验证 |
| b1-current-owner-regressions-discovery-01 | 仅发现450唯一ID，含原210／原十项失败及当前正式77；无数据库连接或实际执行，不当测试成绩 |
| b1-original-failure-group-postgres-01 | 原command／cwd及十ID完整10 ok、245.373s、exit 0；SHA `abd76bcf8a43102df389e2dae88c10933b9918150f609e4ce1f424cfd1f062af`；869份源码未变、PG收尾已核，是自身完整新结果，不是8＋2拼接 |

8项smoke首次跑通普通django.setup／start_application完整B、真实原件和源批准／当前使用、缺画像的真实原policy-m0条件审批、单独目标批准、一次预占／claim／交付／结算及新启动同绑定重放；默认无显式delivery配置仍关闭。真实原研判被认证保存并按原DTO重取，实际assess_risk重算guard通过；重放不重开原件，不新增原decision／授权／reservation或逻辑交付。focused risk独立测试用合成audit port，正式source／delivery用真实v2链，不能混称。postflight核8个完整ID／日志hash／0600以及下一组前置的旧runner／测试库／其他客户端清理。

随后 450 分为原域 373＋正式 77、无重叠且未删 ID；原域 `b1-original-owner-regressions-postgres-01` 因四项静态遗漏主动中断，仅 180 完整 ok／193 无结果，无正常汇总／结果 JSON、exit_code=null。该历史中断和 PG 清理仍保留，不改成 373 通过。只读核查误触发技能的 SQLite／35 单测自述始终不计正式 PG 证据。

主线程后来以原普通启动真实 owner 复现并最小修复四项遗漏，详情见 `b1-formal-authority-review-01.md`：

| 新证据 | 实际结果及范围 |
| --- | --- |
| b1-final-authority-gates-red-postgres-01 | 完整 3 FAIL、120.438s、exit 1；源许可过期／真实策略退役后各返回 41 字节，consumed 授权过期后仍返回 2 条交付回执 |
| b1-approval-authority-red-postgres-01 | 迁移中断、0 测试、exit_code=null；检查和自有 PG 重启／测试库清理另存，不当测试失败或通过 |
| b1-approval-authority-red-postgres-02 | 同 command／cwd／源码完整 4 FAIL、92.645s、exit 1；两个失权审批仍 approved，两个源指针故障丢失实际批准 A 的返回引用 |
| b1-authority-repairs-postgres-01 | 三文件最小修复后原样七项一次完整 7 ok、218.646s、exit 0；SHA `c26752c2e7b3f69b130fe3d218ec57aaf0847f66450e668a6f921d94cf30c14c` |
| b1-final-authority-pure-regressions-01／02 | 首轮漏隔离环境被护栏拒绝、0 测试；补原隔离环境后原入口完整 169 ok、5.094s、exit 0，SHA `3310ec96df5b14aeb4ec2d080aa986da298fb47279910bb17538c10634cf60c6`；首次 postflight 误用描述格式、检查外壳 exit 1 另存，correction 精确核齐旧 166＋新三 ID，不改日志或重跑 |
| b1-authority-repairs-boundaries-scan-01／frozen-boundaries-01 | 640 生产 Python 零违规；M1／冻结 M8／mainline1 AST 与基线相同，diff check 通过，不是 PG 或候选验收 |
| b1-current-owner-regressions-discovery-02 | 仅发现 457 唯一 ID＝原域 373＋正式 84，旧 450／原 210／原十项全部保留；无 Django 数据库连接或测试执行 |
| b1-current-owner-regressions-postgres-01 | 已以普通 manage.py 在同一隔离 PG 单次串行起跑完整 457；当前在途，无通过结论 |

修复后七项实际覆盖五处真实等待的 PID／Lock／主连接阻塞与时序；最终源许可／策略／consumed 风险拒绝均零返回字节，真实 publish／settle／v2 append 后拒绝仍全事务回滚并保留此前 full hold。新审批者失权后许可仍 pending 无批准事件；两个指针故障分别未保存／已保存引用，均返回真实唯一 A，按返回值两次对账不重签，随后唯一交付／2 条结算。postflight 核七 ID、871 份源码未变、日志 hash／0600 及无 runner／测试库／其他客户端；这是原样七项复验，不是完整 84／457 或 B1 收官。

正式owner矩阵已有上述分组实际结果，仍待完整当前选组及相关原域回归。恢复DB故障探针改为实际load_binding的QuerySet.first并要求命中，60项首轮该测试实际通过；object_ref见证和logically_delivered预期修正均在18项中实际ok。三处等待的PID／Lock／blocking_pids／查询与截止／放锁时间已留安全元数据并验证结果，不冒称首次claim桶等待；新竞争用例真实begin=False且所有业务阶段计数0，赢家完成一次后新启动重放保持完整状态。每组postflight分别核精确ID、源码、日志hash、0600和owned PG清理；原失败不拼接成功。新三项迁移在测试库应用不等于drift或回退成功，非候选、无B1或整期完成标记，default／bound／pure候选全量仍归B5。

### 10.4 B2 写入检查与待分发矩阵（2026-11-08；非块验收）

B2 仅在工作副本写实现／测试／文档，Git 只读；本会话未启动 PostgreSQL、未跑 PG 或 SQLite 测试、未应用迁移。所有小检查由副本 `.venv/bin/python -I -B tools/data_security/check_phase6_b2.py` 执行：独立进程清除真实配置，使用 dummy 数据库并将任何 Django `ensure_connection` 调用硬拒绝。check／makemigrations 成功只证明该无数据库配置下的装配与无迁移漂移，不是数据库迁移、事务、故障或 HTTP 全生命周期成绩。

| E6 证据 | 实际结果 |
| --- | --- |
| `b2-small-check-01.log` | 76/76 pure 通过，依赖扫描 1 项未声明执行器 view import；整体失败保留 |
| `b2-small-check-02.log` | 窄声明及独立执行器 B 扫描补齐后 76/76，check／drift／依赖通过 |
| `b2-small-check-03.log` | 86 项、5 failures：新 managed 用例实际触发 `content_hash(BoundedPayload)` 的敏感序列化禁令；不是 PG 失败 |
| `b2-small-check-04.log` | M4、资源、反馈与独立执行器改为内部二进制 SHA-256，不放宽 M0；86/86 及 check／drift／650 生产 Python 依赖扫描通过 |
| `b2-small-check-05.log` | 加 8 项离线扫描器 pure 后 94/94，全阶段通过 |
| `b2-small-check-06.log` | 再补 UTF-16BE／JSON 转义、非规范／symlink 根、gzip 预算与 PDF 成员后 97/97，0 failure/error/skip；check／drift／依赖通过，DB 调用 0 |
| `b2-executor-small-check-01.log`、`02.log` | 独立 executor dummy settings 各 19/19；02 为 managed 哈希修正后复跑，check／drift／依赖通过，DB 调用 0；不是完整执行器 PG 或逻辑交付验收 |
| `b2-pg-backend-collection-01.log` | 只加载 37 个 PG 用例 ID，testsRun=0、collection_only=true；check／drift／依赖通过，DB 调用 0 |
| `b2-pg-executor-collection-01.log` | 只加载 8 个 PG 用例 ID，testsRun=0、collection_only=true；check／drift／依赖通过，DB 调用 0 |

最初 9 份 B2 log 在当前 umask 下为 0660，`b2-evidence-permissions-01.json` 逐份记载收紧至 0600、正文 SHA 不变；原失败日志未覆盖。小检查 runner 已在新文件独占创建后设置 0600。不得将 97＋19、历史已通过子组或 45 个 collected IDs 合算成已跑通的 PG suite／完整候选累计。

**待独立 PG 验证。** 以下均已写用例并仅完成上述导入收集，当前没有实际 PG 结果；须在主会话封存快照上，沿原专用 PG／普通入口执行，保留旧断言及首轮失败，不在工作副本起库。

| 请求／用例 | 目的与拒绝／成功口径 |
| --- | --- |
| B2-PG-HTTP：`resources.test_phase6_b2_http.PrivateResourceHTTPTests`，12 项 | 原件／封面实际 multipart、普通 django.setup 子进程绑定、完整授权读取、原域 ACL、分享幂等／过期／撤销、审计等待后复核、显式清理；FileField／MEDIA 不留原文、响应不称网络收全 |
| B2-PG-HTTP：`feedback_center.tests.test_phase6_b2_http.PrivateFeedbackHTTPTests`，8 项 | 原工单归属／visibility、10 MiB、附件 UUID、分享与当前访问、确认丢失恢复、审计拒绝后的保留／授权清理 |
| B2-PG-UNKNOWN：`resources.test_phase6_b2_unknown.PrivateUploadUnknownTests`，14 项 | 意图先于 I/O，fsync／登记／真正 commit／unlink 确认丢失，部分封面失败，活跃 flock，测试自有 worker 的两个 SIGKILL 窗口；不重复加密／建行／审计，不靠超时接管或缺行清理，published 拒绝删除 |
| B2-PG-EXECUTOR：`controlled_export.tests.test_phase6_b2_http.ExecutorPrivateHTTPTests`，8 项 | 普通独立工程启动、真实文件 key 和私有准备、原 caller／签名／幂等、GET 观察／空 POST 核验、UNKNOWN、正式旧分享／存储关闭；prepared／repair_required 不是 delivered，未新增清理／分享权限 |
| B1 HTTP 兼容：`resources.test_phase6_b2_export_http.ResourceExportHTTPTests`，2 项 | 新 managed v2 资源走实际 B1 来源／风险／目标／Flow；只收两引用，当前源撤销阻断字节，不重复发布／结算 |
| B2-PG-BACKUP：`tools.data_security.phase6_backup_cases.PrivateBackupAcceptance.test_retired_rows_remain_in_database_but_do_not_require_deleted_ciphertext`，1 项 | 两个 live 密文随原 v2 包恢复，第三个 retired 行无文件仍保留 DB 证据；不扩成 B3 恢复开通 |

需并跑工作日志登记的资源／反馈既有 private upload／reference／source、B1 formal delivery／boundary／final gate、独立执行器全部原相关套件及 PrivateBackupAcceptance 原组；当前收集数仅是新增 45 ID。测试侧必须保留运行产物再扫描，fixture 最后的测试目录删除不是产品清理证据；同样不能用 ASGI 边界 mock 的 19 项替代真实服务／存储／事务验证。

**源码限定扫描。** `b2-source-inventory-01.json`／`b2-source-scan-manifest-01.json` 明确选择 backend、frontend（含 dist／静态）、tasks、build、frp 及根部署文件，共 1,148 份、15,060,603 字节，显式登记依赖／缓存／tests／fixtures 等 194 个排除条目及未选 roots；不是整机或运行文件清单。标记文件只含本轮 4 个登记合成原样（资源、反馈、普通启动原件及执行器邮箱），不声称覆盖原 500 条语料。

`b2-source-scan-result-01.json` 实际 `complete=true, passed=false, marker_hit_files=4, runtime_scope_verified=false`，CLI 退出 1。四处均为同一执行器合成邮箱在既有 `mainline1/config/rule-baseline-v1.json` 正例目录、`evaluate_step09.py` 的 RuleTests 驱动及两份内容相同的 build 拷贝；`b2-source-scan-review-01.json` 保存各文件身份／摘要及逐项依据，并再次核对全部 1,148 个扫描摘要。源文件未改、未增加排除／替换标记或把结果改零。该复核只说明命中是已有样例，不证明运行原文不落盘。

**B2-RAW-INVENTORY 待分发。** 独立测试须在清理前（含 partial／UNKNOWN／崩溃残留）与显式终止后分别封存全部实际 private、media、temporary、executor-legacy、backups、logs、evidence、screenshots、production-source 九类；实际空目录也登记，不能拿新建空目录替代已消失的测试目录。使用本轮实际原文与既有语料登记，超过每批 100 项时全清单逐批扫描。标记输入与扫描输出在快照外。不可读、遗漏、变化、图片／PDF／嵌套或不支持格式必须逐项保持未扫；补充人工／解码审查另留证据，不能伪称字节扫描完成 OCR。当前只有工具和其 11 项 pure 检查，没有完整 runtime scan 或 G06 通过结论。

本增量没有执行恢复开通、旧源／密钥轮换、蜜标业务部署或候选全量；没有 B2 块完成或第 6 期完成标记。后续测试、差异修复与裁定由主会话接续。

### 10.5 B3 写入检查与独立测试请求（2026-11-08；非块验收）

B3 在独立工作副本写恢复侧实现，Git 全程只读；本会话未启动 PG、未执行 PG／SQLite／age 验收、未迁移运行库、未部署或开通生产。原 B1/B2 脏树继承部分不计为 B3 新实现。下列日志位于 `/tmp/`，由主会话收集；工作日志为 `~/workspace/data-security-seven-phases/logs/phase-06-block-b3-worklog.md`，没有写并发实施报告。

**实际小检查。** 复用原 `tools/data_security/check_phase6_b2.py`，dummy DB 且任何 Django ensure_connection 硬拒绝。所有下列已执行小组 DB连接尝试0、未起PG；成功 check／drift 不是实际迁移或PG事务证明。

| 日志（完整文件名均以 ds-b3- 开头） | 实际结果／保留失败 |
| --- | --- |
| `ds-b3-small-20261108-r2.log` | 29项、28过／1 FAIL：旧依赖探针要求拒io，而B2既有private_ingress白名单允许io；本会话不改白名单或旧断言，交主agent裁定。check／drift／生产依赖扫描过。 |
| `ds-b3-small-20261108-r4.log` → `r5.log` | r4为24项／3 ERROR，新周期fixture错误公钥namespace；按原契约改为backup-recipient，r5为24/24，不改契约凑绿。 |
| `ds-b3-small-20261108-r8.log` → `r9.log` | r8为37项／1 FAIL／3 ERROR，确为B3对SERVER_ONLY ObjectContext调用from_wire；按原持久层受信构造修两verifier／维护逻辑及新fixture，原契约不改，r9为37/37。 |
| `ds-b3-small-20261108-r10.log` | 40/40，新增本地保留包key清单3项pure；不是实际age密钥轮换。 |
| `ds-b3-small-20261108-r11.log` | 42/42，新增原project namespace及字段明文残留／最小化／email索引检查。 |
| `ds-b3-small-20261108-r12.log` | 当前选组43/43，0 failure/error/skip；另补维护B保留显式project_ref的接线测试。check／drift／658份生产Python依赖扫描均过。 |
| `ds-b3-executor-small-20261108-r1.log` → `r2.log` | r1为13项／1 FAIL：未绑定恢复门仍被wrapper替换原应用对象；只修产品未配置时返回原应用，r2为13/13。 |
| `ds-b3-executor-small-20261108-r3.log`、`r4.log` | 各20/20（12项B3＋8项原B2边界），check／drift／生产扫描过。仅mock／未保存ORM行／本地文件，不是PG、备份或交付成绩。 |

r1／r3／r6／r7等历史截点及首次失败均留工作日志和原文件，不覆盖或拼接为完整suite。恢复生命周期pure使用未保存真实UUIDField行，覆盖cleaned的精确原operation/result/context/stored绑定、退役身份与丢字节、SERVER_ONLY、项目namespace；仍不能代替原owner认证和数据库只读隔离验证。保留包清单使用合成包字节及真实文件哈希，不称age认证；local metadata明确metadata_age_authenticated=False、retirement_allowed=False。

**已写待分发PG／age矩阵。** 所有ID及目的逐项登记工作日志“测试分发请求”。当前仅导入收集：`ds-b3-pg-collection-20261108-r5.log` 一次52 ID，`ds-b3-executor-collection-20261108-r2.log` 4 ID，均testsRun=0、collection_only=true、DB调用0、check／drift／依赖通过。此前主站r4的38、子任务`ds-b3-governance-collection-20261108-r2.log`的14、执行器r1的4仍保留；56只是唯一请求数，不是56通过。

| 模块／类 | 已写数量／验证目的 |
| --- | --- |
| `resources.test_phase6_b3_private_maintenance.PrivateLegacyResourceTests` | 15：stage／迁移／隔离／另行精确删除、当前原owner、确认丢失、路径共享、实际staging重加密、已签对象不换钥；synthetic源专属证明只测试治理边界。 |
| `resources.test_phase6_b3_recovery_verifier.RestoredOwnerVerifierTests` | 11：真实原owner／密文／链，只读PG与选定锚、未锚后缀、unknown／expired保留、原HTTP cleanup后退役引用、旧链不造空genesis；不是完整backup演练。 |
| `tools.data_security.phase6_b3_backup_cases.FullInventoryBackupAcceptance` | 9：全表／opaque密文恢复、错目标／缺错钥／坏包、默认非full周期不顶替、新旧recipient各配离线identity。 |
| `resources.test_phase6_b3_full_recovery.CompleteBackendRecoveryTests` | 3：完整主schema、实际原owner＋age＋明确开通及真实时间；篡改恢复表阻开、缺外部锚拒绝。 |
| `feedback_center.tests.test_phase6_b3_private_maintenance.PrivateLegacyFeedbackTests` | 7：原工单／visibility与当前上传者、stage／迁移／隔离／删旧、坏证明／变化原件／共享路径拒绝。 |
| `audit.test_phase6_b3_legacy_governance.LegacySourceGovernanceTests` | 7：原v1正文／时间保留、源专属证明、先隔离后删、法务FK拒绝SET_NULL／部分删除、坏归档／缺锚拒绝。 |
| `controlled_export.tests.test_phase6_b3_recovery_pg.ExecutorRestoredPreparationTests` | 4：独立执行器原HTTP准备／unknown、只读检查原意图和实际密文、损坏与错context拒绝；不自动发布／清理／交付，不是执行器全备份指标。 |

完整主库组必须在获准封存专用PG中显式启用DS_B3_FULL_RECOVERY_RUN，先由真实preflight备份恢复满足原字段迁移门，再用原FieldBackfill生成最终full包。实际时间仅在正例开通通过后写DS_B3_RECOVERY_EVIDENCE：close至open的四阶段、RPO≤86400s／RTO≤14400s，构造前目标环境准备不计；目前**没有实际数字**，不得用pure合成时钟或历史单次restore耗时填写。该fixture只是一套隔离完整schema和已配置owner，不证明生产容量、所有执行器任务或B5全矩阵。

**仍需独立证据。** 新组之外还须跑原数据／索引／审计钥轮换、checkpoint及旧链组、默认v1/v2备份和D8、B1/B2原owner与执行器回归。字段/报告/逻辑回执核验不续授权，cleaned保留身份不重开在线访问，旧审计时间不升级认证。跨包／归档／checkpoint／opaque引用清单未闭合时不允许毁钥；本地inventory不授退役。全部实际文件在teardown前保留并按原G06九类全清单扫描；当前658份依赖扫描不是原文零命中或runtime完整扫描。本节不改6-F05／6-F06／G01–G07为通过，块裁定与候选全量留主agent／B5。

### B4 写入与小检查截点（2026-11-09；PG／整块裁定待独立测试）

已写三业务表专用 CipherEnvelope 字段及迁移、CanaryRegistration 目录、DjangoCanaryTargets 当前权限／实际产物／显式退役／只读恢复、B 模型／日志／资源导出接线和官方模型工具协议。普通正文不改，不发布、索引或加入学习检索；仅明确的空合成目标可写。机制、三类值、原 M1 识别和 M8 格式语义不重做。B 的恢复回调只追加目录核验及 key 清单合并，未修改 B3 verifier/journal/flow，也未认定 B3 已通过 PG。

| 本树记录 | 实际结果与边界 |
| --- | --- |
| `b4-tool-protocol-pure-4.log`（子任务） | 34 tests 全过、check/drift 过、DB0；当时总退出1，唯一 B AgentGateway import 依赖尚未登记。不是最终整树通过。 |
| `b4-parent-baseline-1.log` | 55/55、check/drift/依赖过、DB0；精确 B 依赖登记后复验。 |
| `b4-owner-pure-1.log` | 26/26、check/drift/依赖过、DB0；含导入基类及继承回归，不称26个全新用例。 |
| `b4-owner-pure-2.log` | 28 tests 中27通过、1错误，退出1；新只读编排夹具用了无 context-manager 的 Mock cursor，返回 ProtectionError 后测试下标 TypeError。仅将该夹具改为 MagicMock，不改产品判断或降低断言。 |
| `b4-final-pure-1.log` | **一次136/136，0 failures/errors/skips，check/drift/依赖全过，数据库连接尝试0，PG未启动。** 含 B4 owner/B/protocol、原蜜标三个出口／registry、table reports、契约／import 与直接受影响 B3 只读编排回归；不是 PG 或全量候选。 |
| `b4-pg-collection-1.log`、`b4-pg-collection-2.log` | 分别收集10、13个 B4 PG ID；testsRun=0、DB0、check/drift/依赖过。新增目录配置不能关闭／旧 READ_ONLY key／closed journal 三项补入第二次，**13不是13通过**。 |
| `b4-source-scan-1.json` | 664生产Python源文件，既有合成 seed 和三类原样标记零命中、无未扫项；source-only，runtime_scope_verified=False。包含M1文件、M8 codec、原seed夹具与B3 flow/journal/verifier同当前B3副本8文件字节比较，全相同；不是运行时原文扫描或B3验收。 |

最终 `git diff --check` 通过（git只读）。PG 13项逐个ID与期望、真实全包恢复／正式资源导出补充请求及受影响累计回归，均在 `~/workspace/data-security-seven-phases/logs/phase-06-block-b4-worklog.md`“测试分发请求”。测试方必须使用封存副本、真实当前权限／业务行／v2链、获准隔离PG；模型只替换最终transport，不联系厂商。全包恢复和正式导出补充请求尚需独立fixture驱动，不以pure或原B3成绩填补。没有实际B4 PG结果、真实厂商成绩或候选全量结果；不能将蜜标门禁／B4整块／第6期记为完成。

## 11. 第七期分轮开发证据（2026-11-10；非候选累计）

E7=`~/workspace/data-security-seven-phases/evidence/phase-07/`。完整逐轮选择、实际命令／cwd、起止、退出码、日志 SHA-256 与源码快照见该目录 `INDEX.md` 和各 label 的 JSON／log／sources；当前全门禁状态见 `GATE-STATUS.md`，不从本文的简表重新拼接测试套件。HEAD 仍为 `19c7b639a4565941cb92bb25bf7958abfe26e6a6` 加继承与本期未提交改动，没有七期候选 SHA。

**执行限制。** 用户 2026-11-10 07:17 已令完整候选 default／bound／pure 全量暂缓；相关性能／总验部分同停，等待再令。中小验证仍用原树登记合成 PG、普通 manage.py test、原 IsolatedRunner／network_guard，不以 SQLite、预绑定默认配置或别树／PG 替代。只复验真实未过／受改动影响方法，不把多轮 ok 拼成单轮全绿；未跑全量不计累计。精确候选命令须在解除暂缓并冻结候选后确定，不在此发起全量。

| 本轮已核实证据 | 实际结果及限制 |
| --- | --- |
| RAG 文本与原文申请管理 | 分别沿 E7 RAG／REVEAL-PROGRESS 和 INDEX 保留原红轮及余项收口，不在本表相加；未替代真实厂商、历史治理或完整入口覆盖验收。 |
| `reveal-requests-pg-fix-07` | 仅最后批准元数据方法独立 1/1，六个 subTest，30.951s、exit 0、源变化 []；不是单轮管理 17/17。 |
| `statistics-pg-red-01` | 16 新方法为 15 ok／1 方法 FAIL；其中 13 PG／HTTP＋2 导入已过，0.518s、exit 1、源变化 []。原失败保留。 |
| `statistics-boundary-fix-02` | 仅余下阶段计数方法独立 1/1，0.009s、exit 0、源变化 []；未使用 DB，不算新增 PG 事务成绩，不拼 16/16。 |
| `reveal-source-pg-red-01` | 新增 12 PG／HTTP＋2 依赖方法，真实首轮独立 14/14、0.868s、exit 0、源变化 []。验证当前 owner／课程／角色、元数据-only SELECT、无解密／签发／写入、真实 lookup 到 pending、旧版本／权限撤销拒绝；不合并旧组。 |
| `reveal-source-dependencies-01` | 最新生产扫描 672 文件／0 违规、exit 0、源变化 []；文件数不是方法数或兼容退出核销。 |
| 三个独立前端构建 | 申请版／统计版／定位版各自 exit 0、源变化 []；最新 `frontend-reveal-source-build-01` 为 3689 模块、42.54s，>500 kB chunk 警告保留。旧构建不外推覆盖新版本。 |
| `frontend-reveal-browser-red-01` | 真实 exit 1，ERR_BLOCKED_BY_LOCAL_NETWORK_ACCESS_CHECKS，未到页面，checks／network 为空；亲看的是错误页，不是产品截图。申请／审批／统计／定位与窄屏未验。 |
| 两轮新增 browser-syntax | 仅 node --check，各 exit 0、源变化 []；没有执行模块、服务、浏览器或交互。当前驱动和交接见 BROWSER-HANDOFF-01，不重复受限导航或绕过检查。 |
| `lifecycle-source-inventory-01` | 12 份所选源码顺序指纹，测试 0、DB 查询 0；范围／授权核对见 LIFECYCLE-SCOPE-01。不是保留执行、全域清点、恢复或重放通过。 |

统计验收口径不变：逐报告／阶段／单位／版本核已验证 Coverage，真实 0/0 与缺分母分开，未知报告按“份”计；不能把 parse／prepared 或事件数量当处理分母。能力启用与验收分开，当前不自动显示已验收。DOM 断言与构建不等于已亲看页面。

P7-PERF-ENV 的本机 4 核／约 7.75 GiB 等效批准保留，P95 阈值不降；环境批准不是性能成绩。图片／OCR 延期、真实厂商联调未授权／未验证、P7-HISTORY-GOV 未批、P7-RETENTION-SCOPE 执行范围待确认、六期候选前置与 C01–C16 退出待核销均单列。7-F06 的完整出口覆盖及七期证据复现、7-F07 的实际到期／派生清理／恢复后重放尚未通过；本目录没有全量 G06 已扫声明，不写七期完成或总验通过。
