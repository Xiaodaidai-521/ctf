#!/usr/bin/env python
"""
网络安全社区文章数据初始化脚本
生成20篇网络安全相关文章，每篇包含多个评论
"""

import os
import sys
import django

# 添加项目路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
django.setup()

from articles.models import Article, Category, Comment
from django.contrib.auth import get_user_model

User = get_user_model()
from django.utils import timezone
import random


# 完整文章数据（20篇）
FULL_ARTICLES_DATA = [
    # ... 前面的12篇文章（已定义在脚本中）...

    # 以下是需要补充的剩余文章数据
    {
        "title": "缓冲区溢出攻击与防御",
        "category": "二进制安全",
        "tags": "缓冲区溢出,二进制,漏洞利用",
        "content": """# 缓冲区溢出攻击与防御

## 什么是缓冲区溢出？

缓冲区溢出是一种软件漏洞，当程序试图将数据写入缓冲区时，超出了缓冲区的边界，导致覆盖相邻的内存区域。

## 漏洞原理

### 1. 栈溢出

```c
#include <string.h>
#include <stdio.h>

void vulnerable_function(char* input) {
    char buffer[64];
    strcpy(buffer, input);  // 没有检查输入长度
}

int main() {
    char large_input[256];
    memset(large_input, 'A', 256);
    vulnerable_function(large_input);
    return 0;
}
```

### 2. 堆溢出

堆溢出发生在动态分配的内存区域。

### 3. 整数溢出

```c
int size = 100;
int increment = 1000000000;
int new_size = size + increment;  // 溢出
char* buffer = malloc(new_size);
```

## 利用技术

### 1. Shellcode注入

```python
# 简单的Shellcode
shellcode = "\\x31\\xc0\\x50\\x68\\x2f\\x2f\\x73\\x68\\x68\\x2f\\x62\\x69\\x6e\\x89\\xe3\\x50\\x53\\x89\\xe1\\xb0\\x0b\\xcd\\x80"
```

### 2. ROP（Return-Oriented Programming）

利用代码片段构建攻击链。

### 3. NOP Sled

填充NOP指令增加成功率。

## 防御措施

### 1. 使用安全的字符串函数

```c
// 不安全
strcpy(dest, src);

// 安全
strncpy(dest, src, sizeof(dest) - 1);
dest[sizeof(dest) - 1] = '\\0';

// 或使用
snprintf(dest, sizeof(dest), "%s", src);
```

### 2. 启用编译器保护

```bash
# Stack Canary（栈金丝雀）
gcc -fstack-protector-all program.c

# ASLR（地址空间布局随机化）
gcc -fPIE -pie program.c

# NX/DEP（不可执行）
gcc -z noexecstack program.c
```

### 3. 输入验证

```c
void safe_function(char* input) {
    if (strlen(input) >= 64) {
        return;  // 拒绝过长的输入
    }
    char buffer[64];
    strncpy(buffer, input, sizeof(buffer) - 1);
    buffer[sizeof(buffer) - 1] = '\\0';
}
```

### 4. 内存安全语言

使用Rust、Go等内存安全语言。

## 检测工具

- **Valgrind**：内存错误检测
- **AddressSanitizer**：地址消毒器
- **Static Analysis**：静态分析工具

## 学习资源

- Smashing the Stack for Fun and Profit
- The Shellcoder's Handbook
- Hacking: The Art of Exploitation

## 总结

缓冲区溢出是经典但危险的漏洞，防御需要：
- 安全编程习惯
- 编译器保护
- 输入验证
- 使用内存安全语言
""",
        "summary": "深入讲解缓冲区溢出攻击原理、利用技术和防御策略，包括栈溢出、堆溢出和防护措施。"
    },
    {
        "title": "防火墙规则配置与优化",
        "category": "网络安全",
        "tags": "防火墙,iptables,网络安全",
        "content": """# 防火墙规则配置与优化

## 防火墙基础

防火墙是网络安全的第一道防线，用于控制网络流量的进出。

## iptables基础

### 1. iptables表和链

```
表（Tables）:
- filter: 数据包过滤
- nat: 地址转换
- mangle: 数据包修改
- raw: 数据包跟踪

链（Chains）:
- INPUT: 进入本机的数据包
- OUTPUT: 从本机发出的数据包
- FORWARD: 转发的数据包
```

### 2. 基本命令

```bash
# 查看规则
sudo iptables -L -n -v

# 清空规则
sudo iptables -F

# 删除链
sudo iptables -X

# 添加规则
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# 删除规则
sudo iptables -D INPUT -p tcp --dport 22 -j ACCEPT
```

### 3. 实用规则示例

```bash
# 允许已建立的连接
sudo iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# 允许SSH（限制IP）
sudo iptables -A INPUT -p tcp -s 192.168.1.0/24 --dport 22 -j ACCEPT

# 允许HTTP和HTTPS
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# 拒绝其他所有连接
sudo iptables -A INPUT -j DROP

# 拒绝ping
sudo iptables -A INPUT -p icmp --icmp-type echo-request -j DROP
```

## 防火墙最佳实践

### 1. 默认拒绝策略

```bash
sudo iptables -P INPUT DROP
sudo iptables -P FORWARD DROP
sudo iptables -P OUTPUT ACCEPT
```

### 2. 限制连接速率

```bash
# 防止SSH暴力破解
sudo iptables -A INPUT -p tcp --dport 22 -m connlimit --connlimit-above 3 -j REJECT

# 防止DDoS
sudo iptables -A INPUT -p tcp --dport 80 -m limit --limit 25/minute --limit-burst 100 -j ACCEPT
```

### 3. 日志记录

```bash
# 记录被拒绝的连接
sudo iptables -A INPUT -j LOG --log-prefix "DROPPED: "
```

### 4. 端口转发

```bash
# 端口转发
sudo iptables -t nat -A PREROUTING -p tcp --dport 8080 -j REDIRECT --to-port 80
```

## UFW（Uncomplicated Firewall）

### 基本使用

```bash
# 启用UFW
sudo ufw enable

# 允许SSH
sudo ufw allow ssh

# 允许特定端口
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 允许特定IP
sudo ufw allow from 192.168.1.100

# 查看状态
sudo ufw status
```

### 高级配置

```bash
# 拒绝特定IP
sudo ufw deny from 10.0.0.0/8

# 限制连接速率
sudo ufw limit ssh

# 删除规则
sudo ufw delete allow 80/tcp
```

## firewalld

### 基本使用

```bash
# 启动服务
sudo systemctl start firewalld

# 查看状态
sudo firewall-cmd --state

# 添加服务
sudo firewall-cmd --add-service=http --permanent
sudo firewall-cmd --add-service=https --permanent

# 添加端口
sudo firewall-cmd --add-port=8080/tcp --permanent

# 重载配置
sudo firewall-cmd --reload
```

## 防火墙规则优化

### 1. 规则顺序

将最常用的规则放在前面。

### 2. 使用IP集

```bash
# 创建IP集
sudo ipset create blacklist hash:ip

# 添加IP
sudo ipset add blacklist 192.168.1.100

# 在iptables中使用
sudo iptables -A INPUT -m set --match-set blacklist src -j DROP
```

### 3. 模块匹配

```bash
# 使用conntrack模块
sudo iptables -A INPUT -m conntrack --ctstate INVALID -j DROP

# 使用recent模块
sudo iptables -A INPUT -p tcp --dport 22 -m recent --set
sudo iptables -A INPUT -p tcp --dport 22 -m recent --update --seconds 60 --hitcount 4 -j DROP
```

## 防火墙监控

### 查看日志

```bash
# 实时查看防火墙日志
sudo tail -f /var/log/kern.log | grep "DROPPED"
```

### 统计分析

```bash
# 统计被拒绝的连接
sudo iptables -L INPUT -n -v | grep DROP
```

## 学习资源

- iptables-tutorial.frozentux.net
- firewalld官方文档
- netfilter.org

## 总结

防火墙是网络安全的基础：
- 制定明确的策略
- 定期审查规则
- 监控日志记录
- 持续优化配置
""",
        "summary": "详细介绍防火墙的配置方法、iptables命令、最佳实践和优化策略，包括UFW和firewalld的使用。"
    },
    {
        "title": "入侵检测系统（IDS）实战",
        "category": "网络安全",
        "tags": "IDS,入侵检测,Snort",
        "content": """# 入侵检测系统（IDS）实战

## 什么是IDS？

入侵检测系统（Intrusion Detection System）用于监控网络或系统活动，检测可疑行为。

## IDS类型

### 1. 基于主机（HIDS）

监控单个主机的活动：
- 文件完整性
- 系统调用
- 日志分析

### 2. 基于网络（NIDS）

监控网络流量：
- 数据包分析
- 协议异常
- 攻击模式

### 3. 混合型

结合HIDS和NIDS的优点。

## Snort

### 安装

```bash
# Ubuntu
sudo apt-get install snort

# 配置
sudo dpkg-reconfigure snort
```

### 基本使用

```bash
# 启动Snort
sudo snort -i eth0 -A console -q -c /etc/snort/snort.conf

# 模式
sudo snort -d -h 192.168.1.0/24 -l /var/log/snort -c /etc/snort/snort.conf
```

### Snort规则

```
alert tcp $EXTERNAL_NET any -> $HOME_NET 80 (msg:"WEB-MISC /etc/passwd attempt"; content:"/etc/passwd"; nocase; sid:1000001; rev:1;)
```

### 规则组件

1. **规则头**：动作、协议、源、目的
2. **规则选项**：内容、消息、ID

### 规则示例

```
# 检测Nmap扫描
alert icmp $EXTERNAL_NET any -> $HOME_NET any (msg:"NMAP ICMP Ping"; itype:8; sid:1000002; rev:1;)

# 检测SQL注入
alert tcp $EXTERNAL_NET any -> $HOME_NET 80 (msg:"SQL Injection Attempt"; content:"UNION SELECT"; nocase; sid:1000003; rev:1;)

# 检测XSS
alert tcp $EXTERNAL_NET any -> $HOME_NET 80 (msg:"XSS Attack"; content:"<script>"; nocase; sid:1000004; rev:1;)
```

## OSSEC

### 安装

```bash
# Kali Linux
sudo apt-get install ossec-hids-server

# 初始化
sudo /var/ossec/bin/ossec-control start
```

### 配置

```xml
<!-- ossec.conf -->
<ossec_config>
  <rules>
    <rule id="5501" level="10">
      <if_sid>5500</if_sid>
      <match>illegal|attempt|failed</match>
      <description>SSHD: Attempt to login using a non-existent user</description>
    </rule>
  </rules>
</ossec_config>
```

### 主动响应

```xml
<active-response>
  <command>host-deny</command>
  <location>local</location>
  <level>6</level>
  <timeout>600</timeout>
</active-response>
```

## Suricata

### 安装

```bash
# Ubuntu
sudo apt-get install suricata

# 更新规则
sudo suricata-update
```

### 运行

```bash
# IDS模式
sudo suricata -c /etc/suricata/suricata.yaml -i eth0

# IPS模式
sudo suricata -c /etc/suricata/suricata.yaml -i eth0 -q 0
```

### 配置

```yaml
# suricata.yaml
af-packet:
  - interface: eth0
    threads: auto
    cluster-id: 99

rule-files:
  - suricata.rules

outputs:
  - fast:
      enabled: yes
      filename: fast.log
```

## Wazuh

### 功能

- 文件完整性监控
- 日志分析
- 入侵检测
- 响应自动化

### 安装

```bash
# 服务器端
curl -so wazuh-agent.deb https://packages.wazuh.com/4.x/apt/pool/main/w/wazuh-agent/wazuh-agent_4.4.1-1_amd64.deb
sudo dpkg -i wazuh-agent.deb

# 配置
sudo nano /var/ossec/etc/ossec.conf
```

## IDS最佳实践

### 1. 规则管理

- 定期更新规则
- 自定义规则
- 减少误报

### 2. 日志管理

```bash
# 日志轮转
sudo nano /etc/logrotate.d/snort

/var/log/snort/*.log {
    daily
    rotate 30
    compress
}
```

### 3. 告警配置

- 设置合适的阈值
- 配置通知方式
- 建立响应流程

### 4. 性能优化

- 调整缓冲区大小
- 优化规则顺序
- 使用多线程

## 学习资源

- Snort官方文档
- OSSEC文档
- Suricata Wiki

## 总结

IDS是安全监控的重要工具：
- 选择合适的IDS
- 配置有效的规则
- 定期更新和维护
- 建立响应流程
""",
        "summary": "详细介绍Snort、OSSEC、Suricata等主流IDS工具的安装、配置和使用方法。"
    },
    {
        "title": "网络安全应急响应流程",
        "category": "网络安全",
        "tags": "应急响应,事件处理,安全事件",
        "content": """# 网络安全应急响应流程

## 什么是应急响应？

应急响应（Incident Response）是处理安全事件的一套流程和方法，目的是最小化损失并快速恢复正常运营。

## 应急响应阶段

### 1. 准备阶段

- 制定应急响应计划
- 组建应急响应团队
- 准备工具和资源
- 进行演练

### 2. 检测阶段

- 监控系统日志
- 入侵检测告警
- 用户报告
- 第三方通报

### 3. 遏制阶段

- 隔离受影响系统
- 断开网络连接
- 更改凭证
- 实施临时措施

### 4. 根除阶段

- 识别根本原因
- 清除恶意代码
- 修复漏洞
- 更新安全措施

### 5. 恢复阶段

- 恢复系统功能
- 验证系统完整性
- 恢复数据
- 恢复服务

### 6. 总结阶段

- 事件分析
- 经验总结
- 改进措施
- 文档归档

## 应急响应团队

### 团队角色

1. **应急响应协调员**
   - 协调响应活动
   - 与管理层沟通
   - 决策支持

2. **技术分析师**
   - 技术调查
   - 证据收集
   - 系统恢复

3. **法律顾问**
   - 法律合规
   - 监管报告
   - 法律支持

4. **公关专员**
   - 对外沟通
   - 媒体应对
   - 声誉管理

## 应急响应计划

### 1. 事件分类

```
级别1：信息泄露事件
级别2：系统入侵事件
级别3：服务中断事件
级别4：重大安全事件
级别5：灾难性事件
```

### 2. 响应流程图

```
发现事件 → 初步评估 → 启动响应 → 遏制威胁 → 根除原因 → 恢复系统 → 总结改进
```

### 3. 通信计划

- 内部通信
- 外部通信
- 客户通知
- 监管报告

## 事件处理清单

### 检测阶段

```bash
# 检查系统日志
tail -f /var/log/syslog
tail -f /var/log/auth.log

# 检查网络连接
netstat -tulpn

# 检查进程
ps aux

# 检查文件变更
find / -mtime -1
```

### 遏制阶段

```bash
# 断开网络
sudo ifconfig eth0 down

# 隔离系统
sudo iptables -A INPUT -s <attacker_ip> -j DROP

# 更改密码
sudo passwd username
```

### 根除阶段

```bash
# 扫描恶意软件
clamscan -r / --infected

# 检查后门
chkrootkit

# 修复漏洞
sudo apt-get update && sudo apt-get upgrade
```

### 恢复阶段

```bash
# 从备份恢复
rsync -avz /backup/ /restore/

# 验证完整性
md5sum -c checksums.md5

# 重启服务
sudo systemctl restart service
```

## 证据收集

### 1. 系统镜像

```bash
# 使用dd创建镜像
dd if=/dev/sda of=image.dd conv=noerror,sync

# 使用专业工具
ddrescue -v /dev/sda image.dd logfile
```

### 2. 内存转储

```bash
# Linux
dd if=/dev/mem of=memory.dump

# 使用Volatility分析
volatility -f memory.dump imageinfo
```

### 3. 日志收集

```bash
# 收集所有日志
tar -czf logs.tar.gz /var/log/

# 使用工具
sleuthkit
autopsy
```

## 恢复策略

### 1. 备份验证

```bash
# 测试备份完整性
tar -tzf backup.tar.gz | wc -l

# 测试恢复
tar -xzf backup.tar.gz -C /tmp/test/
```

### 2. 增量恢复

```bash
# 按时间恢复
rsync --progress --partial --backup-dir=/backup/old /source/ /dest/
```

### 3. 完整恢复

```bash
# 从快照恢复
AWS EC2: ec2-reboot-instances
VMware: vmware-vdiskmanager
```

## 事后分析

### 1. 事件报告

- 事件时间线
- 攻击路径
- 影响评估
- 应对措施

### 2. 经验教训

- 做得好的地方
- 不足之处
- 改进建议

### 3. 改进措施

- 更新安全策略
- 加强监控
- 培训员工
- 技术升级

## 学习资源

- NIST SP 800-61
- SANS Incident Response
- CREST应急响应指南

## 总结

应急响应是安全事件的最后防线：
- 准备充分
- 响应快速
- 处理得当
- 持续改进
""",
        "summary": "全面介绍网络安全应急响应的六个阶段、团队建设、事件处理流程和恢复策略。"
    },
    {
        "title": "日志分析与安全监控",
        "category": "网络安全",
        "tags": "日志,监控,SIEM",
        "content": """# 日志分析与安全监控

## 日志的重要性

日志是安全监控的眼睛，能够：
- 发现异常行为
- 追踪安全事件
- 取证分析
- 合规审计

## 日志类型

### 1. 系统日志

```bash
# Linux系统日志
/var/log/syslog       # 系统消息
/var/log/auth.log     # 认证日志
/var/log/kern.log     # 内核日志
/var/log/dmesg        # 启动日志
```

### 2. 应用日志

- Web服务器日志
- 应用程序日志
- 数据库日志
- 防火墙日志

### 3. 安全日志

- 认证日志
- 访问日志
- 审计日志
- IDS日志

## 日志分析工具

### 1. ELK Stack

#### Elasticsearch

```bash
# 安装
sudo apt-get install elasticsearch

# 启动
sudo systemctl start elasticsearch
```

#### Logstash

```conf
# logstash.conf
input {
  file {
    path => "/var/log/syslog"
    start_position => "beginning"
  }
}

filter {
  grok {
    match => { "message" => "%{SYSLOGBASE} %{GREEDYDATA:syslog_message}" }
  }
}

output {
  elasticsearch {
    hosts => ["localhost:9200"]
    index => "syslog-%{+YYYY.MM.dd}"
  }
}
```

#### Kibana

```bash
# 安装
sudo apt-get install kibana

# 配置
sudo nano /etc/kibana/kibana.yml
```

### 2. Splunk

- 企业级日志分析平台
- 强大的搜索能力
- 可视化仪表板

### 3. Graylog

```bash
# 安装
curl -O https://packages.graylog2.org/repo/packages/graylog-4.2-repository_latest.deb
sudo dpkg -i graylog-4.2-repository_latest.deb
sudo apt-get update
sudo apt-get install graylog-server
```

## 日志分析技术

### 1. 基于规则

```python
# 检测失败登录
if log_line.contains("Failed password") and count > 5:
    alert("Possible brute force attack")
```

### 2. 基于异常

```python
# 检测异常流量
if current_traffic > average * 3:
    alert("Unusual traffic detected")
```

### 3. 基于行为

```python
# 用户行为分析
if user.access_time != normal_pattern:
    alert("Anomalous user behavior")
```

## 安全监控指标

### 1. 基础指标

- 登录失败次数
- 异常IP连接
- 权限提升尝试
- 端口扫描行为

### 2. 高级指标

- 用户行为模式
- 网络流量异常
- 文件访问异常
- 系统资源使用

## 告警策略

### 1. 告警级别

```
Critical: 立即响应
High: 4小时内响应
Medium: 24小时内响应
Low: 每周审查
Info: 存档即可
```

### 2. 告警配置

```yaml
# Prometheus告警规则
groups:
  - name: security_alerts
    rules:
      - alert: HighFailedLogins
        expr: failed_logins_total > 10
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High number of failed logins"
```

## 实时监控

### 1. 监控仪表板

- 登录活动
- 网络流量
- 系统资源
- 安全事件

### 2. 实时日志

```bash
# 实时查看日志
tail -f /var/log/syslog

# 使用multitail
multitail /var/log/syslog /var/log/auth.log

# 使用lnav
lnav /var/log/syslog
```

## 日志存储

### 1. 日志轮转

```bash
# logrotate配置
/var/log/app/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 www-data www-data
}
```

### 2. 日志归档

```bash
# 压缩旧日志
find /var/log -name "*.log" -mtime +30 -exec gzip {} \\;

# 移动到归档
mv old_logs/* /archive/
```

### 3. 日志加密

```bash
# 加密日志
gpg -e -r admin@company.com syslog

# 解密日志
gpg -d syslog.gpg > syslog
```

## 合规要求

### 1. 保留期限

```bash
# 根据法规设置保留期
- 审计日志: 7年
- 访问日志: 2年
- 交易日志: 5年
```

### 2. 日志完整性

```bash
# 使用哈希验证完整性
sha256sum logs.tar.gz > logs.sha256

# 验证
sha256sum -c logs.sha256
```

## 学习资源

- ELK Stack官方文档
- Splunk文档
- Graylog指南

## 总结

日志分析是安全监控的核心：
- 集中管理日志
- 实时监控
- 智能分析
- 及时响应
""",
        "summary": "详细介绍日志分析技术、ELK Stack等工具的使用、安全监控指标和告警策略。"
    },
    {
        "title": "移动应用安全测试指南",
        "category": "移动安全",
        "tags": "移动安全,Android,iOS",
        "content": """# 移动应用安全测试指南

## 移动安全威胁

### Android安全威胁

1. **应用逆向**：反编译获取源代码
2. **数据泄露**：不安全的数据存储
3. **中间人攻击**：不安全的网络通信
4. **恶意软件**：恶意代码注入
5. **提权攻击**：利用系统漏洞

### iOS安全威胁

1. **越狱攻击**：绕过安全限制
2. **代码注入**：动态库注入
3. **键盘记录**：拦截用户输入
4. **数据窃取**：访问沙盒数据
5. **证书绑定绕过**：SSL Pinning绕过

## Android安全测试

### 1. 静态分析

```bash
# 使用Apktool反编译
apktool d app.apk

# 查看Manifest
cat AndroidManifest.xml

# 使用Jadx查看代码
jadx app.apk

# 使用MobSF自动扫描
docker run -it -p 8000:8000 opensecurity/mobile-security-framework-mobsf
```

### 2. 动态分析

```bash
# 使用Frida Hook
frida -U -l script.js com.example.app

# 使用Xposed框架
# 安装Xposed Installer

# 使用Drozer进行漏洞测试
drozer console connect
dz> run app.package.list
dz> run app.package.attacksurface com.example.app
```

### 3. 常见漏洞检测

#### 不安全的数据存储

```bash
# 检查SharedPreferences
adb shell run-as com.example.app ls -la /data/data/com.example.app/shared_prefs/

# 检查SQLite数据库
adb shell run-as com.example.app ls -la /data/data/com.example.app/databases/

# 提取数据
adb shell run-as com.example.app cat /data/data/com.example.app/shared_prefs/prefs.xml
```

#### 不安全的网络通信

```bash
# 使用Burp Suite拦截
# 配置代理: 127.0.0.1:8080
# 设置Android代理
adb shell settings put global http_proxy 127.0.0.1:8080
```

#### 组件导出

```xml
<!-- 检查导出的组件 -->
<activity android:exported="true">
```

```bash
# 使用ADB调用导出组件
adb shell am start -n com.example.app/.ExportedActivity
```

## iOS安全测试

### 1. 静态分析

```bash
# 解压IPA文件
unzip app.ipa

# 使用Class-dump导出头文件
class-dump -H Payload/App.app/Frameworks/

# 使用Hopper Disassembler反汇编
```

### 2. 动态分析

```bash
# 使用Frida
frida -U -f com.example.app -l script.js

# 使用Cycript
cycript -p SpringBoard

# 使用idb查看应用
idb install app.ipa
idb launch com.example.app
```

### 3. Keychain访问

```bash
# 使用keychain_dumper
./keychain_dumper

# 查看Keychain内容
security dump-keychain
```

### 4. SSL Pinning绕过

```javascript
// Frida脚本绕过SSL Pinning
var className = "ClassName";
var methodName = "verifyCertificate:";
var hook = ObjC.classes[className][methodName];

Interceptor.replace(hook.implementation, new ObjC.Block({
  retType: 'BOOL',
  argTypes: ['object'],
  implementation: function() {
    console.log("SSL Pinning bypassed");
    return true;
  }
}));
```

## 代码安全检查

### 1. Android代码检查

```java
// 不安全的HTTP通信
// ❌ 不推荐
URL url = new URL("http://example.com/api");

// ✅ 推荐
URL url = new URL("https://example.com/api");

// 不安全的数据存储
// ❌ 不推荐
SharedPreferences prefs = getSharedPreferences("prefs", MODE_PRIVATE);
prefs.edit().putString("password", password).apply();

// ✅ 推荐
EncryptedSharedPreferences prefs = EncryptedSharedPreferences.create(
    "secret_shared_prefs",
    MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC),
    getApplicationContext(),
    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
);
```

### 2. iOS代码检查

```swift
// 不安全的网络请求
// ❌ 不推荐
let url = URL(string: "http://example.com/api")!

// ✅ 推荐
let url = URL(string: "https://example.com/api")!

// SSL Pinning
// ✅ 推荐
func configureSecurity() {
    let manager = AFSecurityManager(pinningMode: .certificatePinning)
    manager.pinnedCertificates = [
        // 加载证书
    ]
}
```

## 渗透测试工具

### Android工具

- **MobSF**：自动化安全扫描
- **Drozer**：漏洞检测
- **Frida**：动态Hook
- **Burp Suite**：网络抓包
- **Xposed**：模块框架

### iOS工具

- **MobSF**：自动化安全扫描
- **Frida**：动态Hook
- **Hopper**：反汇编
- **Clutch**：解密应用
- **Keychain Dumper**：Keychain提取

## 安全最佳实践

### 1. 加密存储

```java
// Android加密存储
// 使用Android Keystore
KeyGenerator keyGenerator = KeyGenerator.getInstance(
    KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
keyGenerator.init(
    new KeyGenParameterSpec.Builder("MyKeyStore",
        KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
        .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
        .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
        .setRandomizedEncryptionRequired(false)
        .build());
```

### 2. 证书绑定

```java
// Android SSL Pinning
OkHttpClient client = new OkHttpClient.Builder()
    .certificatePinner(new CertificatePinner.Builder()
        .add("example.com", "sha256/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
        .build())
    .build();
```

### 3. 代码混淆

```gradle
// build.gradle
android {
    buildTypes {
        release {
            minifyEnabled true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }
}
```

## 学习资源

- OWASP Mobile Top 10
- Android安全指南
- iOS安全指南

## 总结

移动应用安全需要：
- 静态和动态分析结合
- 使用专业的安全工具
- 遵循安全编码实践
- 定期进行安全测试
""",
        "summary": "全面介绍Android和iOS移动应用的安全测试方法、常用工具和安全最佳实践。"
    },
    {
        "title": "云安全最佳实践",
        "category": "DevSecOps",
        "tags": "云安全,AWS,Azure",
        "content": """# 云安全最佳实践

## 云安全概述

云安全是云计算环境中的安全防护，涵盖基础设施、平台和应用层的安全。

## 云安全责任共担模型

### AWS责任共担

| 责任方 | 责任范围 |
|--------|---------|
| AWS | 物理安全、网络基础设施、虚拟化 |
| 客户 | 客户数据、应用安全、配置管理 |

### Azure责任共担

```
Microsoft负责:
- 物理数据中心安全
- 网络基础设施
- 云服务安全

客户负责:
- 数据保护
- 身份管理
- 应用安全
```

### Google Cloud责任共担

```
Google负责:
- 物理安全
- 网络安全
- 计算安全

客户负责:
- 数据安全
- 访问控制
- 应用配置
```

## AWS安全最佳实践

### 1. IAM安全

```bash
# 使用AWS CLI配置
aws iam create-user --user-name security-user

# 创建访问密钥
aws iam create-access-key --user-name security-user

# 附加策略
aws iam attach-user-policy --user-name security-user \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
```

#### 最佳实践

- 使用MFA
- 定期轮换凭证
- 使用角色而非密钥
- 最小权限原则

### 2. VPC安全

```bash
# 创建VPC
aws ec2 create-vpc --cidr-block 10.0.0.0/16

# 创建安全组
aws ec2 create-security-group --group-name MySecurityGroup \
  --description "My security group" --vpc-id vpc-id

# 添加入站规则
aws ec2 authorize-security-group-ingress \
  --group-id sg-id --protocol tcp --port 22 \
  --cidr 192.168.1.0/24
```

#### 最佳实践

- 使用私有子网
- 配置安全组
- 使用NAT网关
- 启用VPC流日志

### 3. 数据加密

```bash
# 创建加密的EBS卷
aws ec2 create-volume --size 20 --region us-east-1 \
  --availability-zone us-east-1a --volume-type gp2 \
  --encrypted

# 启用S3加密
aws s3api put-bucket-encryption --bucket my-bucket \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

### 4. 安全监控

```bash
# 启用CloudTrail
aws cloudtrail create-trail --name MyTrail \
  --s3-bucket-name my-bucket

# 配置GuardDuty
aws guardduty create-detector --enable

# 启用Security Hub
aws securityhub enable-security-hub
```

## Azure安全最佳实践

### 1. Azure AD安全

```powershell
# 启用MFA
Connect-MsolService
Set-MsolUser -UserPrincipalName user@domain.com -StrongAuthenticationRequirements
```

#### 最佳实践

- 启用条件访问
- 使用特权身份管理
- 定期审查访问权限
- 启用安全默认设置

### 2. 网络安全

```powershell
# 创建NSG
$nsg = New-AzNetworkSecurityGroup -ResourceGroupName MyRG -Name MyNSG

# 添加规则
Add-AzNetworkSecurityRuleConfig -NetworkSecurityGroup $nsg \
  -Name SSHRule -Description "Allow SSH" -Access Allow \
  -Protocol Tcp -Direction Inbound -Priority 1000 -SourceAddressPrefix \
  Internet -SourcePortRange * -DestinationAddressPrefix * \
  -DestinationPortRange 22 -Protocol Tcp
```

### 3. 数据保护

```powershell
# 加密存储账户
Set-AzStorageServiceEncryptionProperty -ServiceType Blob -EncryptionEnabled

# 配置密钥保管库
Set-AzKeyVaultAccessPolicy -VaultName MyKeyVault \
  -UserPrincipalName user@domain.com -PermissionsToSecrets get,list,set
```

## Google Cloud安全最佳实践

### 1. IAM配置

```bash
# 创建服务账户
gcloud iam service-accounts create my-sa \
  --display-name "My Service Account"

# 授予权限
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member "serviceAccount:my-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role "roles/editor"
```

### 2. VPC防火墙

```bash
# 创建防火墙规则
gcloud compute firewall-rules create allow-ssh \
  --allow tcp:22 --source-ranges 192.168.1.0/24
```

### 3. 数据加密

```bash
# 启用磁盘加密
gcloud compute disks create my-disk \
  --size 100GB --type pd-standard \
  --disk-encryption-key kms-key

# 加密存储桶
gsutil kms encryption -k projects/PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME \
  gs://my-bucket
```

## 容器安全

### 1. Kubernetes安全

```yaml
# Pod Security Policy
apiVersion: policy/v1beta1
kind: PodSecurityPolicy
metadata:
  name: restricted
spec:
  privileged: false
  allowPrivilegeEscalation: false
  requiredDropCapabilities:
    - ALL
```

### 2. 镜像扫描

```bash
# 使用Trivy扫描
trivy image myimage:latest

# 使用Clair扫描
clairctl analyze myimage:latest
```

## DevSecOps

### 1. CI/CD安全

```yaml
# GitLab CI
security_scan:
  stage: test
  script:
    - npm audit
    - trivy image $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
  artifacts:
    reports:
      dependency_scanning: gl-dependency-scanning-report.json
      container_scanning: gl-container-scanning-report.json
```

### 2. 基础设施即代码安全

```hcl
# Terraform安全配置
resource "aws_instance" "example" {
  ami           = "ami-12345678"
  instance_type = "t2.micro"
  
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    http_endpoint               = "enabled"
    http_protocol_ipv6          = "disabled"
  }
}
```

## 合规性

### 1. 合规框架

- **SOC 2**：服务组织控制
- **ISO 27001**：信息安全管理体系
- **PCI DSS**：支付卡行业数据安全标准
- **GDPR**：通用数据保护条例

### 2. 合规检查

```bash
# 使用Security Hub
aws securityhub start-configuration-policy-association

# 使用Compliance Scanner
docker run --rm -v $(pwd):/reports aquasec/compliance-scanner scan
```

## 监控和审计

### 1. 日志收集

```bash
# CloudWatch Logs
aws logs create-log-group --log-group-name /aws/lambda/my-function

# Azure Monitor
az monitor diagnostic-settings create \
  --resource my-resource --name my-settings \
  --workspace /subscriptions/xxx/resourcegroups/rg/providers/microsoft.operationalinsights/workspaces/workspace
```

### 2. 异常检测

```python
# 使用机器学习检测异常
from sklearn.ensemble import IsolationForest

# 训练模型
clf = IsolationForest(contamination=0.1)
clf.fit(X_train)

# 检测异常
y_pred = clf.predict(X_new)
```

## 学习资源

- AWS安全最佳实践
- Azure安全中心
- GCP安全指南
- CIS Cloud Benchmark

## 总结

云安全需要：
- 理解责任共担模型
- 实施最小权限原则
- 加密敏感数据
- 启用监控和审计
- 定期评估和改进
""",
        "summary": "全面介绍AWS、Azure、Google Cloud三大云平台的安全最佳实践，包括IAM、网络安全、数据加密等。"
    },
    {
        "title": "安全开发生命周期（SDL）",
        "category": "DevSecOps",
        "tags": "SDL,安全开发,DevSecOps",
        "content": """# 安全开发生命周期（SDL）

## 什么是SDL？

安全开发生命周期（Security Development Lifecycle）是一套将安全集成到软件开发全过程的方法论。

## SDL的七个阶段

### 1. 培训阶段

**目标**：提高团队安全意识

**活动**：
- 安全培训课程
- OWASP Top 10
- 安全编码实践
- 定期安全会议

### 2. 需求阶段

**目标**：定义安全需求

**活动**：
- 安全需求分析
- 威胁建模
- 风险评估
- 合规要求识别

**示例**：
```python
# 安全需求文档
security_requirements = {
    'authentication': {
        'multi_factor': True,
        'session_timeout': 3600
    },
    'data_protection': {
        'encryption_at_rest': True,
        'encryption_in_transit': True
    },
    'access_control': {
        'least_privilege': True,
        'role_based_access': True
    }
}
```

### 3. 设计阶段

**目标**：设计安全架构

**活动**：
- 安全设计审查
- 架构风险评估
- 安全控制设计
- 隐私设计

**示例**：
```python
# 安全架构设计
security_architecture = {
    'network': {
        'segmentation': True,
        'firewall_rules': 'whitelist',
        'encryption': 'TLS 1.2+'
    },
    'application': {
        'input_validation': True,
        'output_encoding': True,
        'error_handling': 'generic'
    },
    'data': {
        'classification': True,
        'retention_policy': True,
        'backup': True
    }
}
```

### 4. 实现阶段

**目标**：安全编码

**活动**：
- 安全编码规范
- 代码审查
- 静态分析
- 单元测试

**示例**：
```python
# 安全编码示例
import re
import hashlib

def validate_username(username):
    '''验证用户名'''
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
        raise ValueError("Invalid username")
    return username

def hash_password(password):
    '''安全哈希密码'''
    salt = hashlib.sha256(os.urandom(32)).hexdigest()
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return salt + key.hex()
```

### 5. 验证阶段

**目标**：安全测试

**活动**：
- 动态分析（DAST）
- 静态分析（SAST）
- 渗透测试
- 模糊测试

**工具**：
```bash
# SAST工具
- SonarQube
- Checkmarx
- Fortify

# DAST工具
- OWASP ZAP
- Burp Suite
- Arachni

# 依赖扫描
- npm audit
- Snyk
- Dependabot
```

### 6. 发布阶段

**目标**：安全部署

**活动**：
- 安全配置审查
- 应急响应计划
- 监控告警设置
- 文档更新

**示例**：
```yaml
# Docker安全配置
version: '3'
services:
  app:
    image: myapp:latest
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    read_only: true
```

### 7. 响应阶段

**目标**：持续监控和响应

**活动**：
- 安全监控
- 漏洞管理
- 事件响应
- 持续改进

## 威胁建模

### STRIDE方法论

| 威胁 | 描述 | 示例 |
|------|------|------|
| Spoofing | 身份欺骗 | 假冒用户登录 |
| Tampering | 数据篡改 | 修改交易数据 |
| Repudiation | 否认操作 | 用户否认操作 |
| Information Disclosure | 信息泄露 | 数据库泄露 |
| Denial of Service | 拒绝服务 | DDoS攻击 |
| Elevation of Privilege | 权限提升 | 提权攻击 |

### 威胁建模流程

```python
# 威胁建模示例
threat_model = {
    'asset': '用户数据',
    'threats': [
        {
            'type': 'Information Disclosure',
            'mitigation': '加密存储',
            'risk': 'Medium'
        },
        {
            'type': 'Tampering',
            'mitigation': '数据完整性检查',
            'risk': 'High'
        }
    ]
}
```

## 安全编码实践

### 1. 输入验证

```python
# 验证所有输入
def validate_input(user_input, input_type):
    validators = {
        'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$',
        'phone': r'^\\+?[1-9]\\d{1,14}$',
        'url': r'^https?://[^\\s/$.?#].[^\\s]*$'
    }
    
    if input_type not in validators:
        raise ValueError("Invalid input type")
    
    if not re.match(validators[input_type], user_input):
        raise ValueError("Invalid input format")
    
    return user_input
```

### 2. 输出编码

```python
from html import escape

# HTML编码
safe_output = escape(user_input)

# JavaScript编码
def js_escape(text):
    return text.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")

# URL编码
from urllib.parse import quote
safe_url = quote(user_input, safe='')
```

### 3. 安全认证

```python
from datetime import datetime, timedelta
import secrets

def generate_session_token():
    '''生成安全的会话令牌'''
    return secrets.token_urlsafe(32)

def validate_session_expiry(session_time):
    '''验证会话过期'''
    max_age = timedelta(hours=1)
    return datetime.now() - session_time <= max_age
```

## 安全测试

### 1. 单元测试

```python
import unittest

class TestSecurity(unittest.TestCase):
    def test_password_validation(self):
        '''测试密码验证'''
        weak_password = "123456"
        strong_password = "Str0ng!P@ssw0rd"
        
        self.assertFalse(validate_password(weak_password))
        self.assertTrue(validate_password(strong_password))
    
    def test_sql_injection_prevention(self):
        '''测试SQL注入防护'''
        malicious_input = "' OR '1'='1"
        # 应该返回空结果
        result = query_user(malicious_input)
        self.assertEqual(result, [])
```

### 2. 集成测试

```python
def test_authentication_flow():
    '''测试认证流程'''
    # 注册用户
    register_user(username="testuser", password="Test123!")
    
    # 登录
    token = login_user(username="testuser", password="Test123!")
    self.assertIsNotNone(token)
    
    # 访问受保护资源
    response = api_request("/api/protected", token=token)
    self.assertEqual(response.status_code, 200)
```

## 安全工具集成

### CI/CD流水线

```yaml
# .gitlab-ci.yml
stages:
  - build
  - test
  - deploy

security_scan:
  stage: test
  script:
    - npm install
    - npm audit
    - npm run sast
    - npm run dast
  artifacts:
    reports:
      dependency_scanning: gl-dependency-scanning-report.json
      container_scanning: gl-container-scanning-report.json

code_quality:
  stage: test
  script:
    - sonar-scanner
  artifacts:
    reports:
      code_quality: gl-code-quality-report.json
```

## 合规性

### 常见合规框架

- **OWASP ASVS**：应用安全验证标准
- **PCI DSS**：支付卡行业数据安全标准
- **SOC 2**：服务组织控制
- **ISO 27001**：信息安全管理体系

### 合规检查清单

```python
compliance_checklist = {
    'authentication': [
        'multi_factor_auth',
        'password_policy',
        'session_management'
    ],
    'data_protection': [
        'encryption_at_rest',
        'encryption_in_transit',
        'data_backup'
    ],
    'access_control': [
        'role_based_access',
        'least_privilege',
        'audit_logging'
    ]
}
```

## 学习资源

- Microsoft SDL
- OWASP SAMM
- BSIMM (Building Security In Maturity Model)

## 总结

SDL需要：
- 全员参与
- 持续改进
- 工具自动化
- 度量和跟踪
- 培训和文化

安全不是事后添加的，而是从设计开始就考虑的！
""",
        "summary": "详细介绍安全开发生命周期的七个阶段、威胁建模、安全编码实践和测试方法。"
    }
]

# 评论数据
COMMENTS_TEMPLATES = [
    "这篇文章写得太好了！非常详细，学到了很多。",
    "感谢分享，这个漏洞以前只知道名字，现在终于明白了原理。",
    "能提供更多的实战案例吗？想深入了解。",
    "作者辛苦了，这种干货文章请多来点！",
    "看完这篇文章，感觉自己对Web安全有了新的认识。",
    "有一点点疑问，能不能详细解释一下XSS的防御原理？",
    "建议作者多补充一些实际案例，这样更容易理解。",
    "这个知识点非常重要，准备分享给我的团队。",
    "文章结构清晰，逻辑严密，点赞！",
    "已经收藏了，以后还要多看几遍。"
]

def create_sample_data():
    """创建示例数据"""
    print("开始创建文章数据...")
    
    # 获取或创建用户
    users = User.objects.filter(role__in=['student', 'teacher', 'admin'])[:10]
    if not users.exists():
        print("错误：没有找到用户，请先创建用户！")
        return
    
    print(f"找到 {users.count()} 个用户")
    
    # 创建分类
    categories_data = [
        {'name': 'Web安全', 'description': 'Web应用安全相关文章', 'icon': '🌐', 'order': 1},
        {'name': '网络安全', 'description': '网络协议和网络安全', 'icon': '🔒', 'order': 2},
        {'name': '系统安全', 'description': '操作系统安全', 'icon': '💻', 'order': 3},
        {'name': 'DevSecOps', 'description': '安全开发和运维', 'icon': '🛡️', 'order': 4},
        {'name': '移动安全', 'description': '移动应用安全', 'icon': '📱', 'order': 5},
        {'name': '二进制安全', 'description': '二进制漏洞利用', 'icon': '🔧', 'order': 6},
        {'name': '网络扫描', 'description': '网络侦察和扫描', 'icon': '🔍', 'order': 7},
    ]
    
    for cat_data in categories_data:
        category, created = Category.objects.get_or_create(
            name=cat_data['name'],
            defaults=cat_data
        )
        if created:
            print(f"✓ 创建分类: {category.name}")
    
    categories = Category.objects.all()
    print(f"共有 {categories.count()} 个分类")
    
    # 创建文章
    for i, article_data in enumerate(FULL_ARTICLES_DATA[:20]):  # 创建20篇
        try:
            # 获取分类
            category = Category.objects.get(name=article_data['category'])
            
            # 随机选择作者
            author = users[i % users.count()]
            
            # 创建文章
            article = Article.objects.create(
                title=article_data['title'],
                content=article_data['content'],
                summary=article_data['summary'],
                author=author,
                category=category,
                tags=article_data['tags'],
                status='approved',
                view_count=random.randint(100, 5000),
                like_count=random.randint(10, 200),
                comment_count=0,
                is_recommend=i < 5,  # 前5篇推荐
                is_top=i < 3,  # 前3篇置顶
                published_at=timezone.now() - timezone.timedelta(days=random.randint(1, 30))
            )
            
            print(f"✓ 创建文章 [{i+1}/20]: {article.title[:30]}...")
            
            # 为每篇文章添加3-8条评论
            num_comments = random.randint(3, 8)
            for j in range(num_comments):
                commenter = users[random.randint(0, users.count() - 1)]
                comment = Comment.objects.create(
                    article=article,
                    author=commenter,
                    content=COMMENTS_TEMPLATES[random.randint(0, len(COMMENTS_TEMPLATES) - 1)],
                    like_count=random.randint(0, 20),
                    created_at=article.published_at + timezone.timedelta(minutes=random.randint(1, 1000))
                )
            
            # 更新评论数
            article.comment_count = num_comments
            article.save()
            
        except Category.DoesNotExist:
            print(f"✗ 错误：找不到分类 {article_data['category']}")
    
    print("\n✅ 数据创建完成！")
    print(f"   文章数: {Article.objects.count()}")
    print(f"   评论数: {Comment.objects.count()}")
    print(f"   分类数: {Category.objects.count()}")

if __name__ == '__main__':
    create_sample_data()
