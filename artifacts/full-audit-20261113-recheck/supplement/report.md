# 内部组件与独立受控导出补充复测（2026-11-13）

本轮使用 Python 3.12.8 / Django 6.0.3 的隔离 venv、已核验身份的合成 PostgreSQL 集群及 `tools.full_audit.batch.execute()` 的网络隔离。证据以 `final-summary.json` 和各组命令/结果 JSON 为准；没有沿用前轮通过数。

| 测试组 | 测试数 | 通过 | 未通过 | 命令退出 |
| --- | --- | --- | --- | --- |
| mainline1 纯逻辑 | 157 | 157 | 0 | 0 |
| mainline1 PostgreSQL 事务、多连接、独立进程 | 67 | 67 | 0 | 0 |
| 安全工具纯逻辑 | 12 方法 | 11 | 1 方法中的 2 个 subtest | 1 |
| controlled-export 最终完整发现 | 105 | 76 | 29 errors | 1 |
| controlled-export Windows native 配置 ACL 专项 | 2 | 2 | 0 | 0 |

最后 2 项已包含在 controlled-export 的 105 项里，不能再累加。安全工具的 2 个 subtest 失败属于同一个测试方法，原 runner 输出的 `tests=12, passed=11, failures=2` 也不能作为 13 个测试求和。

平台 Django check、makemigrations --check --dry-run、showmigrations --plan，以及 controlled-export check、makemigrations --check --dry-run 均退出 0。数据库测试使用 `--keepdb` 保留唯一合成测试库，以避免重复 DROP DATABASE 全集群 checkpoint 等待；fsync、事务断言与权限守卫均保留。

## 本轮解决的问题

- 受保护策略 RevealRequest 模型外键改为 `settings.AUTH_USER_MODEL`，与现有 swappable 迁移一致。修复前 controlled-export 在执行测试前发生 4 个 E300/E307 系统错误；修复后真实运行了整组 103 项，再包含本轮新增的 2 个 native ACL 项完成 105 项复测。该服务的系统检查和迁移一致性均通过，没有通过屏蔽 system check 得到结果。
- 独立服务启动配置权限检查改用平台现有原生 `is_private_path`。Windows 正确 DACL 不再被 POSIX mode 误拒绝；非私有配置仍拒绝。两个真实 Windows ACL 回归通过。

## 剩余失败及覆盖边界

| 失败组 | 数量 | 实际原因 |
| --- | --- | --- |
| controlled_export.tests.test_phase6_b2_http | 8 errors | Linux chmod 夹具的配置/目录不满足 Windows 权限边界，AUTHORIZATION_DENIED |
| controlled_export.tests.test_phase6_b3_recovery_pg | 4 errors | 同类权限夹具拒绝，未执行到真实恢复效果验收 |
| controlled_export.tests.test_phase6_private_preparation | 13 errors | phase3 的 key/manifest 夹具不满足 Windows native DACL，FileKeyResolver 返回 KEY_UNAVAILABLE |
| controlled_export.tests.test_phase6_b2_boundaries | 1 error | phase3 配置/密钥夹具仍不满足 Windows 私有边界 |
| controlled_export.tests.test_phase6_b3_recovery | 3 errors | 测试仅对配置 chmod(0600)，未设置 native DACL，配置被拒绝 |
| tools.data_security.test_phase4_evidence.BackupReceiptTests.test_log_hash_binds_exact_output_and_preserves_exit_code | 2 failed subtests | Windows stat mode 0666 与断言 0600 不相等。载荷字节、log_sha256、退出码、stdout 先前断言通过；不能将此视为备份/恢复成功。工具实际 age runner 为 Linux 专用路径。 |

没有修改这些测试断言，也没有在测试 harness 中放宽校验、添加假备份证明、强行返回成功或改用不等价的权限模拟。需要选定 Linux 验收环境，或明确投入把备份工具、配置与密钥 fixture 迁移为原生 Windows 权限方式；不能用本轮 76 个成功测试证明受保护模式/恢复全链路通过。

旧 103 项首次复跑在完成测试后等待 DROP DATABASE checkpoint，306 秒后退出 1；最终 105 项通过 `--keepdb` 在 43 秒内完成并有完整结果 JSON，`source_changes=[]`。主报告应选最终 105 项，不叠加首次 103 项。

部署和需要用户定夺/真实联调的独立清单见 `../runtime/report.md`。实际导出生产授权、共享交付与真实恢复联调仍受参考服务阶段和正式环境边界限制；本轮未接入父项目公共 HTTP 路由。
