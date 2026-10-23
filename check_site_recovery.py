"""Real WebView2 recovery against a local HTTP fixture, no external requests."""
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import queue
import threading
import time
import tkinter as tk
from embedded_site import EmbeddedSite

counts=Counter()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        path=self.path.split('?')[0];counts[path]+=1
        code=200;title='Fixture ready'
        if path=='/transient' and counts[path]<=2:code=503
        elif path=='/missing' and counts[path]<=2:code=404
        elif path=='/spa' and counts[path]==1:title='Page not found'
        elif path=='/forbidden':code=403
        elif path=='/rate':code=429
        elif path=='/always-fail':code=500
        self.send_response(code);self.send_header('Content-Type','text/html');self.send_header('Cache-Control','no-store');self.end_headers()
        self.wfile.write(f'<!doctype html><title>{title}</title><h1>{title}</h1>'.encode())
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}'
root=tk.Tk();root.geometry('900x620');frame=tk.Frame(root);frame.pack(fill='both',expand=True);root.update()
events=queue.Queue();bridge=EmbeddedSite(frame,lambda:{'BG':'#101214'},events,offline_test=True,builder=True,test_url=base+'/transient')
def wait(kind,timeout=20):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        root.update()
        try:_,event=events.get_nowait()
        except queue.Empty:time.sleep(.01);continue
        if event['type']=='retrying':print(event['message'])
        if event['type']==kind:return event
        if event['type']=='error':raise AssertionError((event,dict(counts)))
    raise AssertionError('No '+kind)
def navigate(path):
    bridge.send({'op':'test-navigate','url':base+path})
try:
    bridge.start();wait('loaded');assert counts['/transient']==3,counts
    bridge.send({'op':'inspect'});state=wait('state')
    assert state['direct'] and state['loaded'] and state['httpStatus']==200,state
    process=bridge.process
    for path,expected in (('/missing',3),('/spa',2)):
        navigate(path);wait('loaded');assert counts[path]==expected,counts
    for path in ('/forbidden','/rate'):
        navigate(path);wait('notice');time.sleep(.5);root.update();assert counts[path]==1,counts
    navigate('/always-fail')
    deadline=time.monotonic()+20;error=None
    while time.monotonic()<deadline:
        root.update()
        try:_,event=events.get_nowait()
        except queue.Empty:time.sleep(.01);continue
        if event['type']=='error':error=event;break
    assert error and counts['/always-fail']==4,(error,counts)
    # Explicit retry is still possible after the automatic budget is exhausted.
    navigate('/healthy');wait('loaded');assert bridge.process is process
    bridge.send({'op':'visibility','visible':False});frame.pack_forget();root.update()
    frame.pack(fill='both',expand=True);root.update();bridge.send({'op':'visibility','visible':True})
    bridge.send({'op':'inspect'});state=wait('state')
    assert state['loaded'] and counts['/healthy']==1,state
    print('PASS: automatic 503/404/SPA recovery, bounded retries, no 403/429 loops, direct in-tab navigation, preserved loaded page on hide/show. Local HTTP only.')
finally:
    bridge.close(wait=True);root.destroy();server.shutdown();server.server_close()
