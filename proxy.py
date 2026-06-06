#!/usr/bin/env python3
"""
本地代理 + 静态文件一体化服务
- 浏览器请求 /proxy/<path> 时，转发到 https://dashscope.aliyuncs.com/<path>
- 浏览器请求其他路径时，从当前目录返回静态文件（HTML 等）
- 自动处理 CORS 预检，绕过阿里百炼 compatible-mode 不支持 CORS 的问题
"""
import json
import os
import sys
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get('PORT', '8000'))
TARGET_HOST = 'https://dashscope.aliyuncs.com'

MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")

    def _set_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Max-Age', '86400')

    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/proxy/'):
            self._proxy('GET')
            return
        self._serve_static()

    def do_POST(self):
        if self.path.startswith('/proxy/'):
            self._proxy('POST')
            return
        self.send_error(404)

    def _proxy(self, method):
        # /proxy/<sub-path> -> https://dashscope.aliyuncs.com/<sub-path>
        sub = self.path[len('/proxy/'):]
        target = f'{TARGET_HOST}/{sub}'
        length = int(self.headers.get('Content-Length', '0') or '0')
        body = self.rfile.read(length) if length > 0 else None

        fwd_headers = {}
        for k in ('Content-Type', 'Authorization', 'Accept', 'User-Agent'):
            v = self.headers.get(k)
            if v:
                fwd_headers[k] = v

        try:
            req = urllib.request.Request(target, data=body, method=method, headers=fwd_headers)
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = resp.read()
                self.send_response(resp.status)
                ctype = resp.headers.get('Content-Type', 'application/json')
                self.send_header('Content-Type', ctype)
                self._set_cors()
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            try:
                data = e.read()
            except Exception:
                data = json.dumps({'error': {'message': str(e)}}).encode('utf-8')
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self._set_cors()
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            err = json.dumps({'error': {'message': f'代理异常: {e}'}}).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self._set_cors()
            self.end_headers()
            self.wfile.write(err)

    def _serve_static(self):
        path = self.path.split('?')[0] or '/'
        if path == '/':
            path = '/index.html'
        full = os.path.join(ROOT, path.lstrip('/'))
        if not os.path.isfile(full):
            self.send_error(404, 'Not Found')
            return
        try:
            with open(full, 'rb') as f:
                data = f.read()
        except OSError:
            self.send_error(500)
            return
        ext = os.path.splitext(full)[1].lower()
        ctype = MIME.get(ext, 'application/octet-stream')
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)


def main():
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print(f'代理 + 静态服务已启动: http://127.0.0.1:{PORT}/index.html')
    print(f'代理前缀: /proxy/  ->  {TARGET_HOST}/')
    print('按 Ctrl+C 停止')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')


if __name__ == '__main__':
    main()
