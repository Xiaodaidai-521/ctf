"""
Coze SDK 注入工具
用于在容器页面的 HTML 中动态嵌入 Coze AI 助手
"""
from django.conf import settings


def get_coze_sdk_script():
    """
    生成 Coze SDK 注入脚本

    Returns:
        str: Coze SDK 脚本代码，如果未启用则返回空字符串
    """
    if not getattr(settings, 'COZE_SDK_ENABLED', False):
        return ''

    bot_id = getattr(settings, 'COZE_BOT_ID', '')
    token = getattr(settings, 'COZE_TOKEN', '')
    widget_title = getattr(settings, 'COZE_WIDGET_TITLE', 'CTF 助手')

    if not bot_id or not token:
        return ''

    script = f'''
<!-- Coze SDK - AI 助手 -->
<script src="https://lf-cdn.coze.cn/obj/unpkg/flow-platform/chat-app-sdk/1.2.0-beta.19/libs/cn/index.js"></script>
<script>
  new CozeWebSDK.WebChatClient({{
    config: {{
      bot_id: '{bot_id}',
    }},
    componentProps: {{
      title: '{widget_title}',
    }},
    auth: {{
      type: 'token',
      token: '{token}',
      onRefreshToken: function () {{
        return '{token}'
      }}
    }}
  }});
</script>
'''
    return script


def inject_coze_sdk(html_content):
    """
    在 HTML 内容中注入 Coze SDK 脚本

    Args:
        html_content: 原始 HTML 内容

    Returns:
        str: 注入后的 HTML 内容
    """
    if not getattr(settings, 'COZE_SDK_ENABLED', False):
        return html_content

    script = get_coze_sdk_script()
    if not script:
        return html_content

    # 在 </body> 标签前插入脚本
    if '</body>' in html_content:
        return html_content.replace('</body>', f'{script}\n</body>')
    # 如果没有 </body> 标签，直接在末尾添加
    elif '</html>' in html_content:
        return html_content.replace('</html>', f'{script}\n</html>')
    else:
        return html_content + script


def is_html_response(content_type):
    """
    判断响应是否为 HTML

    Args:
        content_type: 响应的 Content-Type 头

    Returns:
        bool: 如果是 HTML 返回 True
    """
    if not content_type:
        return False
    content_type_lower = content_type.lower()
    return 'text/html' in content_type_lower
