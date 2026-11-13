# 数据实验室交接修复与验证

日期：2026-11-13（Asia/Shanghai）。对应续查问题 **01**，以及调试中新发现的 **25：Windows 安全启动文件权限兼容缺陷**。

服务端保存的证据现在可以交给模块六，使用已有的数据实验室专用核验器检查复核位置、四轮回放判断和只读执行状态。通过程序核验后仍保留人工评阅待办，模块一接收的是待人工复核事实，不能把程序通过当成教师签收或真实数据保护已经执行。

## 改动

- `skill_review/services/submissions.py` 接受仅由内部调用传递的 `data_lab_evidence`，交给 `data_lab.verification.validate_context` 重新读取并锁定已保存证据，校验归属、尝试、摘要和请求引用。公开模块六 JSON 提交不能伪造该上下文；已有提交的重试也先经过上下文校验。幂等键同时绑定原尝试，不能跨尝试复用。
- `skill_review/services/verification.py` 按任务核验器选择 `data_lab.verification.verify_submission`，将证据专用量表版本用于结果和人工待办。普通技能核验继续使用原规则核验器。
- 已有证据先保存、核验失败回滚模块六写入、交接失败保留结果和冻结通知的机制得到联通与验证：重试不重新扫描、不伪造成绩、不重复生成核验结果或能力事实。
- 增加 `data_lab/tests/test_submission_bridge.py` 的四项真实接口/故障回归。修正一个旧审计测试的事件筛选条件：按交接确认元数据筛选，继续检查事件长度、修正版本和幂等稳定性。
- `ctf_backend/security_bootstrap.py` 原先直接用 POSIX 权限位检查配置和恢复证明文件；Windows 即使已经设置了正确独占 DACL，`st_mode` 仍可为 `0666`，从而错误拒绝启动。两处现在在 Windows 使用现有原生拥有者/DACL/非重解析点校验，在 POSIX 保持原来禁止组和其他用户写入的规则。新增真实 NTFS ACL 的允许、拒绝和恢复证明回归。

## 实际验证

| 运行 | 结果 | 证据 |
| --- | --- | --- |
| 原有提交和完整无模型流程专项 | 16/16 通过 | `artifacts/full-audit-20261113/logic-fix-data-lab-focused.log` |
| 扩大联合回归 | 206 项：161 通过、1 失败、44 错误 | `artifacts/full-audit-20261113/logic-fix-data-lab-joint.json` |
| 联合回归中的数据实验室全组，含新增四项 | 63/63 通过 | 同上，逐测试 ID 有记录 |
| 联合回归中的反馈核心逻辑 | 55/55 通过 | 同上 |
| 联合回归中的模块五可信证据交接 | 4/4 通过 | 同上；服务端证据绑定、客户端不可伪造、禁模型完整 HTTP 流程、交接失败可恢复 |
| 技能核验全组 | 联合回归 39/40 通过；剩余一个旧审计筛选测试修正后单独复跑 1/1 通过 | `artifacts/full-audit-20261113/logic-fix-data-lab-audit-handoff.json` |
| Windows 安全启动文件权限与原生私钥边界 | 10/10 通过：新增 5 项及原有原生 ACL 5 项 | `artifacts/full-audit-20261113/logic-fix-bootstrap-windows.log` |
| 44 项私有附件回归的真实 NTFS ACL 与启动权限修复后复跑 | 44 项均在 `setUp` 报错，0 项通过；29 项到达 `data_security/adapters/persistence/audit.py:48` 的 POSIX checkpoint 目录权限检查，另 15 项继承的 resources fixture 需同样设置原生权限 | `artifacts/logic-fixes-20261113/data-lab/windows-acl-after-bootstrap-fix-tests.json` |
| 剩余 15 项 resources fixture 原生 ACL 适配后复跑 | 15 项均在 `setUp` 被同一个 `audit.py:48` 门禁拒绝，0 项通过；15 组 fixture 原生权限均确认私有 | `artifacts/logic-fixes-20261113/data-lab/windows-acl-resource-fixtures-tests.json` 和 `windows-acl-resource-fixtures-observations.json` |

联合逻辑回归合计 **162 个不同的验证项已通过**；16 项最初专项包含于联合回归，不重复计数。Windows 兼容性另有 10 项通过。没有声称 206 项完整联合回归全部通过。44 项反馈私有附件测试在建立安全文件夹/密钥的 fixture 阶段失败，尚未执行其业务断言。

全部使用现成、身份校验过的隔离 PostgreSQL 集群和独立合成测试数据库；没有修改真实业务库或真实数据，没有调用付费模型或启动真实靶场。模块五接口验收使用本地 HTTP fixture，不能替代真实 Docker/FRP 环境验收。

## 尚需环境或人工参与

1. 反馈私有附件的 44 项回归需要在目标 Linux 环境联调。已修正临时 fixture 的盘符路径，配置、manifest、密钥和要求 `0700` 的目录均设置为真实独占 DACL；29 组反馈 fixture 与随后适配的 15 组 resources fixture 原生权限观测全部确认私有。分组继续核验后的 44 个不同测试均进入下游 `DjangoAuditSink`，在 `data_security/adapters/persistence/audit.py:48` 被要求 POSIX `0700/geteuid` 的 checkpoint 目录门禁拒绝，尚未执行其业务断言。`private_store`、维护、备份等还使用 `getuid/O_NOFOLLOW/目录 fsync` 等 POSIX 文件语义，本次范围没有扩大为整套 Windows 移植。完整 44 项复跑与剩余 15 项复跑是相同测试的阶段验证，不能加总为 59 项新测试。真实 ACL 与新阻断证据见 `artifacts/logic-fixes-20261113/data-lab/windows-acl-after-bootstrap-fix-observations.json`、`windows-acl-resource-fixtures-observations.json` 及各自测试日志；**问题 25 只表示配置/恢复证明权限兼容已修复，不能代表这 44 项通过**。
2. 教师需要核定合成材料、依据卡、人工量表、判断理由、能力结论和复测标准；自动程序核验不能代替这项课程签收。
3. 在真实课程环境完成一次学生提交、教师评阅、模块一成长展示和复测的页面验收。代码断链和可模拟故障已由自动测试定位、修复与验证，不需要用户再手工复现这些异常。

原始人工评阅要求和模块七/八“未连接”状态继续保留；本次没有把待评阅或未连接状态改成成功。
