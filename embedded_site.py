"""Asynchronous native browser lifecycle for the website tabs."""
import json
from pathlib import Path
import subprocess
import threading
from embedded_ai import EmbeddedAI

URL = 'https://pc-builds.com/bottleneck-calculator/'

class EmbeddedSite(EmbeddedAI):
    def __init__(self, parent, colors, events, offline_test=False, builder=False, test_url=None, activation=False, windhawk=False):
        super().__init__(parent, colors, events, offline_test=offline_test)
        self.test_url=test_url
        self.builder = builder
        self.activation = activation
        self.windhawk = windhawk
        self.event_name = 'windhawk_event' if windhawk else ('activation_event' if activation else ('builder_event' if builder else 'site_event'))

    def start(self):
        if self.closed or getattr(self, 'starting', False) or (self.process is not None and self.process.poll() is None):
            return
        folder = Path(__file__).with_name('ai')
        args = [str(folder / 'EmbeddedSite.exe'), str(self.parent.winfo_id())]
        if self.offline_test:
            args += ['--offline-test', str(Path(__file__).with_name('verification') / ('webview-builder-profile' if self.builder else 'webview-profile'))]
        initial = {'op':'theme', 'builder':self.builder, 'activation':self.activation, 'windhawk':self.windhawk, **self.colors()}
        if self.offline_test and self.test_url:initial['test_url']=self.test_url
        self.starting = True
        def post(data):
            if not self.closed:self.events.put((self.event_name, {**data, '_bridge_id':id(self)}))
        def launch():
            try:
                process = subprocess.Popen(args, cwd=str(folder), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.DEVNULL, text=True, encoding='utf-8', bufsize=1, creationflags=0x08000000)
                # Complete the initialization handshake before exposing this process
                # to visibility commands from tab switches. Runs off the Tk thread.
                process.stdin.write(json.dumps(initial,ensure_ascii=True)+'\n');process.stdin.flush()
                self.process = process
                if self.closed:
                    process.terminate();process.wait(timeout=3)
                    for pipe in (process.stdin,process.stdout):pipe.close()
                    return
            except (OSError,subprocess.TimeoutExpired):
                post({'type':'error', 'message':'The embedded browser could not start. Check that Microsoft Edge WebView2 Runtime is installed.'})
                return
            finally:self.starting = False
            try:
                for raw in process.stdout:
                    try:data=json.loads(raw)
                    except ValueError:continue
                    if isinstance(data,dict) and self.process is process:post(data)
            except (OSError,ValueError):pass
            finally:
                if not self.closed and self.process is process:post({'type':'stopped','message':'Browser stopped. Recovering automatically...'})
        threading.Thread(target=launch, daemon=True).start()
