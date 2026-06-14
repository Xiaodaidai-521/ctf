import os
from pathlib import Path
import tempfile
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
django.setup()

from django.test import Client

client = Client()
from django.contrib.auth import get_user_model

User = get_user_model()
admin = User.objects.get(username='admin')
client.login(username='admin', password='admin123')

# 获取资源列表页
response = client.get('/admin/resources/resource/')
if response.status_code == 200:
    content = response.content.decode('utf-8')

    # 保存 HTML 到系统临时目录，避免写死 Unix/Windows 路径
    output_path = Path(tempfile.gettempdir()) / 'admin_resources.html'
    with output_path.open('w', encoding='utf-8') as f:
        f.write(content)
    print(f'HTML 已保存到 {output_path}')

    # 查找关键信息
    print('\n=== 关键信息 ===')
    if 'pagination' in content:
        print('✓ 包含分页')
    if '<table' in content:
        print('✓ 包含表格')
    if '<tbody>' in content:
        print('✓ 包含 tbody')
    if '<tr' in content:
        print('✓ 包含 tr')
        tr_count = content.count('<tr')
        print(f'  tr 标签数量: {tr_count}')

    # 查找包含数据的部分
    import re
    result_count_pattern = r'(\d+)\s*resource'
    matches = re.findall(result_count_pattern, content)
    if matches:
        print(f'\n✓ 找到数量提示: {matches}')
    else:
        print('\n✗ 没有找到数量提示')

    # 查找可能的消息
    message_pattern = r'<p[^>]*class="[^"]*[^>]*>([^<]+)</p>'
    messages = re.findall(message_pattern, content)
    if messages:
        print(f'\n✓ 找到消息:')
        for msg in messages:
            print(f'  - {msg}')

    # 查找表格内容
    table_pattern = r'<table[^>]*>(.*?)</table>'
    tables = re.findall(table_pattern, content, re.DOTALL)
    if tables:
        print(f'\n✓ 找到 {len(tables)} 个表格')
        for i, table in enumerate(tables, 1):
            print(f'\n表格 {i}:')
            # 查找表格中的行
            row_pattern = r'<tr[^>]*>(.*?)</tr>'
            rows = re.findall(row_pattern, table, re.DOTALL)
            print(f'  行数: {len(rows)}')
            if rows:
                print(f'  第一行: {rows[0][:100]}...')

    # 查找表单
    form_pattern = r'<form[^>]*>(.*?)</form>'
    forms = re.findall(form_pattern, content, re.DOTALL)
    if forms:
        print(f'\n✓ 找到 {len(forms)} 个表单')
