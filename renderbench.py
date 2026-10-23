"""One-shot loopback bridge for the bundled WebGL benchmark. No external service."""
import json
import math
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

TEST='webgl-4d-720p-v1'

def validate(data):
    if not isinstance(data,dict):raise ValueError('Invalid result')
    if data.get('test')!=TEST:raise ValueError('Wrong benchmark version')
    for key in ('fps','low_fps','duration','frames'):
        if type(data.get(key)) not in (int,float) or not math.isfinite(data[key]) or data[key]<=0:raise ValueError('Invalid measurement')
    if not 19<=data['duration']<=35:raise ValueError('Incomplete run')
    if data['low_fps']>data['fps']*1.1:raise ValueError('Invalid frame timing')
    if abs(data['fps']-data['frames']/data['duration'])>max(1,data['fps']*.02):raise ValueError('Inconsistent frame count')
    return {k:data[k] for k in ('test','fps','low_fps','duration','frames')}|{'score':round(data['fps']*100),'renderer':str(data.get('renderer','Unknown'))[:200]}

class Session:
    def __init__(self,callback):
        self.cancelled=False;self.delivered=False
        self.token=secrets.token_urlsafe(24)
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def respond(self,code,body,kind):
                self.send_response(code);self.send_header('Content-Type',kind)
                self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
            def do_GET(self):
                if self.path!='/'+owner.token:
                    self.respond(404,b'Not found','text/plain');return
                body=Path(__file__).with_name('renderbench.html').read_text(encoding='utf-8').replace('__TOKEN__',owner.token)
                self.respond(200,body.encode(),'text/html; charset=utf-8')
            def do_POST(self):
                if self.path!='/result/'+owner.token or owner.delivered or owner.cancelled:
                    self.respond(403,b'Expired session','text/plain');return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=8192:raise ValueError('Invalid payload size')
                    data=validate(json.loads(self.rfile.read(size)))
                except (ValueError,TypeError,KeyError):
                    self.respond(400,b'Invalid result','text/plain');return
                owner.delivered=True;callback('benchmark',data)
                self.respond(200,b'OK','text/plain')
        self.server=HTTPServer(('127.0.0.1',0),Handler)
        self.server.timeout=0.5
        self.url=f'http://127.0.0.1:{self.server.server_port}/{self.token}'
        def serve():
            deadline=time.monotonic()+180
            try:
                while not self.cancelled and not self.delivered and time.monotonic()<deadline:self.server.handle_request()
            finally:
                self.server.server_close()
                if not self.delivered:callback('benchmark_cancelled',None)
        threading.Thread(target=serve,daemon=True).start()

    def cancel(self):self.cancelled=True
