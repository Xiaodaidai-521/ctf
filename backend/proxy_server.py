#!/usr/bin/env python3
"""
简单的HTTP代理服务器，处理路径重写
"""
from flask import Flask, request, Response
import requests

app = Flask(__name__)

FRP_SERVER = 'http://frps-server:9123'

@app.route('/challenge/<path:path>')
def proxy_challenge(path):
    """
    代理/challenge/路径到FRP服务器，移除/challenge/前缀
    """
    # 构建目标URL
    target_url = f"{FRP_SERVER}/{path}"
    
    # 转发所有查询参数
    if request.query_string:
        target_url += f"?{request.query_string.decode('utf-8')}"
    
    try:
        # 转发请求
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers={k: v for k, v in request.headers if k != 'Host'},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=30
        )
        
        # 构建响应
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(k, v) for k, v in resp.headers.items()
                   if k.lower() not in excluded_headers]
        
        return Response(resp.content, resp.status_code, headers)
    except Exception as e:
        return Response(f"Proxy Error: {str(e)}", 502)

@app.route('/health')
def health():
    return "healthy\n"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False)
