"""Rapid tabs/sidebar and native browser restart against local HTTP only."""
from collections import Counter
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import threading
import time
from unittest.mock import Mock,patch
import automation
import embedded_site
import hubplus
import retweaks as app

counts=Counter()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        counts[self.path]+=1;self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
        self.wfile.write(b'<!doctype html><title>Local fixture</title><input placeholder="Preserved field">')
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}'
class Hotkeys:
    def __init__(self,*args):self.thread=Mock()
    def update(self,*args):pass
    def close(self):pass
automation.Hotkeys=Hotkeys
app.Hub._load_info=lambda self:None
hubplus.write_json=lambda *args:None
hubplus.install(vars(app))
def factory(parent,colors,events,builder=False):
    return embedded_site.EmbeddedSite(parent,colors,events,offline_test=True,builder=builder,test_url=base+('/builder' if builder else '/calculator'))
with patch.object(hubplus,'EmbeddedSite',side_effect=factory):
    hub=app.Hub(show_intro=False,enable_ai=False,enable_web=True)
    errors=[];hub.report_callback_exception=lambda *args:errors.append(args)
    def pump_until(condition,timeout=15):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            hub.update()
            if condition():return
            time.sleep(.01)
        raise AssertionError('Timed out')
    try:
        hub.show_tab(19);pump_until(lambda:hub.site_bridge and not hub.site_status.winfo_manager() and counts['/calculator']>=1)
        hub.show_tab(25);pump_until(lambda:hub.builder_bridge and not hub.builder_status.winfo_manager() and counts['/builder']>=1)
        calculator=hub.site_bridge;builder=hub.builder_bridge
        first_process=builder.process
        hub.pc_value.parts['CPU'].set('Retained CPU')
        timings=[]
        for i in range(60):
            start=time.monotonic()
            hub.show_tab((19,25,24,11,3)[i%5])
            if i%3==0:hub.toggle_sidebar()
            hub.update();timings.append(time.monotonic()-start)
        pump_until(lambda:not hub.sidebar_fade.job)
        assert max(timings)<.5,max(timings)
        assert hub.site_bridge is calculator and hub.builder_bridge is builder
        assert counts['/calculator']==1 and counts['/builder']==1,counts
        assert hub.pc_value.parts['CPU'].get()=='Retained CPU'
        hub.show_tab(25);hub.update()
        with patch.object(builder,'send',wraps=builder.send) as send:
            hub.show_tab(25);hub.update();send.assert_not_called()
        first_process.terminate()
        pump_until(lambda:builder.process is not first_process and builder.process is not None and builder.process.poll() is None)
        pump_until(lambda:counts['/builder']==2 and not hub.builder_status.winfo_manager())
        # A stale browser instance cannot turn a healthy page into an error/restart.
        hub.handle_site_event('builder',{'type':'error','_bridge_id':-1,'message':'Stale error'})
        assert not hub.builder_failed and not hub.builder_status.winfo_manager()
        assert not errors,errors
        print(f'PASS: 60 rapid switches/toggles, no browser reloads, preserved fields, no-op repeated selection, automatic crashed-host recovery, stale-event isolation. Worst UI turn: {max(timings)*1000:.0f} ms.')
    finally:hub.destroy();server.shutdown();server.server_close()
