# eNSP / VirtualBox 与 Docker 分时使用说明

核查日期：2026-10-08。适用本机：Windows 11 家庭版，VirtualBox 5.2.44，eNSP 1.2.00.510，Docker Desktop 4.81.0，WSL 2.7.3。

## 1. 本次查错结论

| 检查项 | 实测 | 含义 |
| --- | --- | --- |
| Windows | 11 家庭中文版，Build 26200 | 使用 WSL2 运行 Linux 容器，不要求完整 Hyper-V 管理角色 |
| VirtualBox | 5.2.44r139111 | 属于旧版本；不能套用 VirtualBox 6+ 的 Hyper-V 共存说明 |
| eNSP | 1.2.00.510 | VirtualBox 注册的六个虚拟机均位于 Huawei/eNSP 目录，暂保留现有配套版本 |
| HypervisorPresent | True | Windows Hypervisor 当前实际运行 |
| VirtualizationBasedSecurityStatus | 2 | VBS 当前运行；不能仅看“Windows 功能”是否勾选 Hyper-V |
| VBoxDrv / VBoxNetAdp / VBoxNetLwf / VBoxUSBMon | Running | VirtualBox 驱动已加载；不代表当时有虚拟机在运行 |
| vmcompute / hns / WSLService | Running | Windows 虚拟计算、网络及 WSL 服务存在并在运行 |
| com.docker.service | Stopped / Manual | 不能单独据此判断故障；WSL2 模式不总需要该特权辅助服务 |
| Docker 最新致命日志 | Secrets Engine 无法移除 engine.sock | 本次启动的直接阻断点是本地通信文件，不是已经证明的 VirtualBox 冲突 |

此前还出现过 dockerInference 通信文件错误。移开 Docker/run 后，日志进一步暴露 engine.sock 错误；本会话重命名 docker-secrets-engine 目录被 Windows 拒绝。Docker 引擎尚未恢复。

没有做停用 VirtualBox 驱动前后的对照实验，不能宣称“已证明 VirtualBox 导致 Docker 本次崩溃”。旧版 VirtualBox 与 Windows Hypervisor 的兼容风险，以及 Docker 通信文件故障，应分别处理。已保存本机核查摘要到 `virtualization-evidence-20261008.json`。

参考：[Microsoft WSL FAQ](https://learn.microsoft.com/en-us/windows/wsl/faq)、[Docker WSL2 辅助服务说明](https://docs.docker.com/desktop/setup/install/windows-permission-requirements/)。[Docker 官方仓库 issue #15064](https://github.com/docker/for-win/issues/15064) 有相近的 socket 故障报告；它是用户报告，不能作为本机根因已确认或修复有效的证明。

## 2. 需要切换哪一层

**保留 BIOS/UEFI 中 Intel VT-x / AMD-V / SVM 为 Enabled。切换的是 Windows Hypervisor 的启动状态。**

| 配置 | eNSP 模式 | Docker 模式 |
| --- | --- | --- |
| BIOS 硬件虚拟化 | 开启 | 开启 |
| Windows hypervisorlaunchtype | off | auto |
| 重启后的 HypervisorPresent | 应为 False | 应为 True |
| eNSP / VirtualBox 5.2 | 使用 | 关闭虚拟机 |
| Docker Desktop / WSL2 | 不可用，退出应用 | 使用 |
| Windows 可选组件 | 可以保留安装 | 保留 WSL、Virtual Machine Platform |

停止 Docker 窗口、停止 com.docker.service、执行 wsl --shutdown，都不等于卸载本次启动时已经加载的 Windows Hypervisor。模式切换需要真正“重新启动”，锁屏、睡眠、休眠不算。

这套流程减少抢占硬件虚拟化的冲突，但不保证老版本 eNSP 在 Windows 11 上的全部驱动、网卡和设备模拟问题都被解决。本次不升级 VirtualBox，以免打破现有 eNSP 配套。

## 3. 一次性准备

1. 在开始菜单搜索 PowerShell，右键“以管理员身份运行”。所有 bcdedit 命令都在该窗口执行。
2. 若启用了设备加密/BitLocker，先确认自己能取得恢复密钥；启动配置变更可能触发恢复验证。不要为了切换直接关闭 Secure Boot 或解密磁盘。
3. 备份当前启动配置（只需首次操作时执行）：

```powershell
$bcdBackup = Join-Path $env:USERPROFILE ('bcd-before-lab-switch-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
bcdedit.exe /export $bcdBackup
bcdedit.exe /enum
```

确认命令成功后再继续。下面省略启动项 ID，Microsoft 文档规定这会修改当前系统启动项，避免 PowerShell 中花括号被错误解释。参考：[BCDEdit /set](https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/bcdedit--set)。

## 4. 切换到 eNSP / VirtualBox

1. 保存工作，正常停止正在练习的容器；从 Docker 托盘选择 Quit Docker Desktop。
2. 在管理员 PowerShell 执行：

```powershell
wsl.exe --shutdown
bcdedit.exe /set hypervisorlaunchtype off
```

3. 确认 bcdedit 报告操作成功，再通过“开始 → 电源 → 重启”重启电脑。
4. 重启后，在 PowerShell 检查：

```powershell
(Get-CimInstance Win32_ComputerSystem).HypervisorPresent
```

只有输出 **False** 才说明本次 Windows 启动未运行 Hypervisor。此时启动 eNSP，再启动一个 AR 设备验证。任务管理器中“虚拟化：已启用”是正常的，它表示 BIOS 的硬件能力仍然开启。

本模式下 Docker/WSL2 无法启动是预期行为，不要因此重装 Docker。可关闭 Docker Desktop 的登录自动启动，改为在 Docker 模式手动启动它。

## 5. 切回 Docker / WSL2

1. 在 eNSP 内保存拓扑并停止设备，退出 eNSP 与 VirtualBox，避免强制结束有运行状态的虚拟机。
2. 在管理员 PowerShell 执行：

```powershell
bcdedit.exe /set hypervisorlaunchtype auto
```

3. 确认成功后重启电脑，检查：

```powershell
(Get-CimInstance Win32_ComputerSystem).HypervisorPresent
wsl.exe --status
```

4. 预期 HypervisorPresent 为 True；启动 Docker Desktop，等待引擎就绪，再执行：

```powershell
docker version
docker info --format '{{.OSType}}'
```

验收要求：docker version 同时显示 Client 和 Server，OSType 为 linux。只有 Client 版本号不能证明容器引擎已运行。然后回到平台启动 Juice Shop。

## 6. 切换不生效时

### off + 重启后仍然 True

先在管理员 PowerShell 用 `bcdedit.exe /enum` 确认当前系统启动项的 hypervisorlaunchtype 为 Off。不要只检查命令曾经执行成功。

运行 `msinfo32`，查看“基于虚拟化的安全性”；本机核查时 VBS 状态为运行中。再检查“Windows 安全中心 → 设备安全性 → 内核隔离 → 内存完整性”。如果该功能仍让 Hypervisor 保持运行，需要评估后关闭并再次重启；这会降低依赖虚拟化的内核保护，切回 Docker 后应按原状态恢复。不要仅凭本机 VBS=2 就认定内存完整性一定开启，当前读取并未确认它的开关值。

如果由组织策略、Credential Guard 或 UEFI 锁定控制，按 Microsoft 的对应故障文档处理；不要批量删除 DeviceGuard 注册表或关闭全部安全功能。[Microsoft 虚拟化冲突排查](https://learn.microsoft.com/en-us/troubleshoot/windows-client/application-management/virtualization-apps-not-work-with-hyper-v)。

### auto + 重启后仍然 False

在管理员 PowerShell 查看组件状态：

```powershell
Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform
Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
```

若缺失，再启用对应组件并重启。本机曾正常运行 WSL2 容器，不需要每次切换都反复卸载/安装这些组件。Windows 家庭版看不到完整 Hyper-V 角色，并不等于不能运行 WSL2。

### Hypervisor=True，但 Docker 仍报 engine.sock / dockerInference

这说明切换已生效，但 Docker 的独立启动故障仍存在。不要继续来回切换 Hypervisor，也不要执行 Docker 恢复出厂设置或 `wsl --unregister docker-desktop`。

先正常退出 Docker，保留诊断日志。之前的重命名目录恢复方案没有在本机成功，且系统返回拒绝访问；需在你自己的交互式 Windows 会话中进一步检查文件占用/权限，或通过 Docker 官方支持诊断。重启、管理员权限或升级均不能保证解决这种残留 socket 故障。

## 7. 配套建议与实施边界

- 本机采用 eNSP 1.2.00.510 + 现有 VirtualBox 5.2.44；Docker 使用 WSL2 Linux 引擎，靠重启切换 Windows Hypervisor。此为基于实测版本的分时运行方案，不是华为认证兼容清单。
- 最终 Linux 服务器直接运行 Docker Engine + Compose，平台与靶场部署按 `juice-shop-linux.md` 执行，无需 Windows 的 VirtualBox/WSL 切换。
- 本次仅检查并编写说明，没有修改 BCD、Windows 可选组件、VBS、BIOS、VirtualBox 驱动或重启系统。
- 本会话读取 Windows 可选组件和 BCD 时分别遇到“需要提升”“拒绝访问”，所以切换步骤必须由你在管理员 PowerShell 中执行，尚未声称两种模式均已验收。
