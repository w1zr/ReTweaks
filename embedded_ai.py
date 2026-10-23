"""Lifecycle and theme bridge for the in-tab Windows Forms AI control."""
import json
import queue
import subprocess
import threading
from pathlib import Path

class EmbeddedAI:
    def __init__(self,parent,colors,events,offline_test=False):
        self.parent=parent;self.colors=colors;self.events=events;self.process=None;self.closed=False
        self.offline_test=offline_test
        self._writer_process=None;self._commands=None;self._pending_state={};self._writer_lock=threading.Lock()

    def start(self):
        if self.closed or (self.process is not None and self.process.poll() is None):return
        folder=Path(__file__).with_name('ai')
        exe=folder/'EmbeddedAI.exe'
        if not exe.is_file() or not (folder/'GeminiChat.exe').is_file():
            self.events.put(('ai_event',{'type':'error','message':'Embedded AI files are missing from this build.'}));return
        try:
            args=[str(exe),str(self.parent.winfo_id())]+(['--offline-test'] if self.offline_test else [])
            self.process=subprocess.Popen(args,cwd=str(folder),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',bufsize=1,creationflags=0x08000000)
            self.send({'op':'theme',**self.colors()})
        except OSError:
            self.events.put(('ai_event',{'type':'error','message':'AI could not start. Try reopening the tab.'}));return
        process=self.process
        def read():
            try:
                for raw in process.stdout:
                    try:data=json.loads(raw)
                    except ValueError:continue
                    if isinstance(data,dict):self.events.put(('ai_event',data))
            except (OSError,ValueError):pass
            finally:
                if not self.closed:self.events.put(('ai_event',{'type':'stopped','message':'AI stopped. Use Retry AI to reload it.'}))
        threading.Thread(target=read,daemon=True).start()

    def send(self,command):
        process=self.process
        if process is None or process.poll() is not None:return False
        # Never wait on a native UI process or a full pipe on Tk's event thread.
        with self._writer_lock:
            if self._writer_process is not process:
                self._writer_process=process
                commands=queue.Queue(maxsize=128);self._commands=commands;pending={};self._pending_state=pending
                def write():
                    try:
                        while process.poll() is None:
                            try:lines=[commands.get(timeout=.05)]
                            except queue.Empty:
                                with self._writer_lock:
                                    lines=list(pending.values());pending.clear()
                            for line in lines:process.stdin.write(line);process.stdin.flush()
                    except (OSError,ValueError):pass
                threading.Thread(target=write,daemon=True).start()
            op=command.get('op');line=json.dumps(command,ensure_ascii=True)+'\n'
            self._pending_state.pop(op,None)
            try:self._commands.put_nowait(line);return True
            except queue.Full:
                if op in ('visibility','theme'):
                    self._pending_state[op]=line;return True
                return False

    def update_theme(self):return self.send({'op':'theme',**self.colors()})

    def close(self,wait=False):
        if self.closed:return
        self.closed=True;self.send({'op':'close'})
        process=self.process
        if process is not None:
            def reap():
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:process.terminate();process.wait(timeout=2)
                    except (OSError,subprocess.TimeoutExpired):pass
                for pipe in (process.stdin,process.stdout):
                    if pipe:
                        try:pipe.close()
                        except OSError:pass
            if wait:reap()
            else:threading.Thread(target=reap,daemon=True).start()
