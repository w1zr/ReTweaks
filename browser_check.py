"""Exercise the real bundled browser with an isolated profile and local home page."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk

from embedded_browser import ai_folder, command

REQUIRED = ('EmbeddedBrowser.exe', 'Microsoft.Web.WebView2.Core.dll',
            'Microsoft.Web.WebView2.WinForms.dll', 'WebView2Loader.dll')


def verify(report):
    folder = ai_folder()
    missing = [name for name in REQUIRED if not (folder / name).is_file()]
    if missing:
        raise RuntimeError('Missing bundled browser files: ' + ', '.join(missing))
    report['files'] = list(REQUIRED)
    root = tk.Tk()
    root.withdraw()
    frame = tk.Frame(root, width=640, height=400)
    frame.pack(fill='both', expand=True)
    root.update_idletasks()
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix='browser-check-', dir=report['directory'],ignore_cleanup_errors=True) as temporary:
            events = queue.Queue()
            flags = 0x08000000 if sys.platform == 'win32' else 0
            process = subprocess.Popen([*command(frame.winfo_id()), '--offline-test', str(Path(temporary)/'profile')],
                                       cwd=str(folder), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, text=True, encoding='utf-8', creationflags=flags)
            def read():
                for line in process.stdout:
                    try:events.put(json.loads(line))
                    except ValueError:pass
            threading.Thread(target=read, daemon=True).start()
            def send(payload):
                process.stdin.write(json.dumps(payload)+'\n');process.stdin.flush()
            send({'op':'theme','BG':'#09090b','PANEL':'#151518','FG':'#f5f5f6','MUTED':'#aaaab0',
                  'LINE':'#303035','ACC':'#eeeef0','data':{'bookmarks':[],'history':[],'engines':[{'name':name,'template':template} for name,template in __import__('core.browser_data',fromlist=['SEARCH_ENGINES']).SEARCH_ENGINES.items()]}})
            deadline = time.monotonic()+45
            ready = inspected = menu_checked = shortcut_checked = False
            while time.monotonic()<deadline:
                root.update()
                try:event = events.get(timeout=.05)
                except queue.Empty:
                    if process.poll() is not None:
                        raise RuntimeError('Browser helper exited before initialization.')
                    continue
                if event.get('type')=='error':raise RuntimeError(event.get('message','Browser error'))
                if event.get('type')=='ready':
                    ready=True
                    send({'op':'test-engine-menu'});send({'op':'test-global-search'});send({'op':'inspect'})
                if event.get('type')=='global-search':
                    shortcut_checked=True;report['global_search_shortcut']=True
                if event.get('type')=='menu-state':
                    choices=event.get('choices',[])
                    if not choices or not event.get('rounded') or not event.get('renderer'):
                        raise RuntimeError('Search engine submenu is missing its themed rounded renderer.')
                    if any(c.get('foreground')!=event.get('foreground') or c.get('background')!=event.get('background') or c.get('foreground')==c.get('background') for c in choices):
                        raise RuntimeError('Search engine menu text does not match the active theme.')
                    if sum(bool(c.get('selected')) for c in choices)!=1:
                        raise RuntimeError('Search engine menu selection is incorrect.')
                    menu_checked=True;report['engine_menu']={'rounded':True,'themed':True,'choices':len(choices)}
                if event.get('type')=='state':
                    if not event.get('embedded'):raise RuntimeError('Browser window was not embedded in its parent.')
                    report['state']={key:event.get(key) for key in ('embedded','tabs','url','width','height')}
                    document=json.loads(event.get('document') or 'null')
                    if isinstance(document,str):document=json.loads(document)
                    if isinstance(document,dict) and document.get('title'):
                        report['title']=document['title'];inspected=True
                    if not inspected:send({'op':'inspect'})
                if ready and inspected and menu_checked and shortcut_checked:break
            if not ready or not inspected or not menu_checked or not shortcut_checked:raise RuntimeError('Browser initialization or local page inspection timed out.')
            report['ready']=True
            send({'op':'close'})
            try:process.wait(timeout=8)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
    finally:
        if process and process.poll() is None:
            process.terminate();process.wait(timeout=5)
        root.destroy()


def main():
    directory = Path(sys.executable).parent if getattr(sys,'frozen',False) else Path.cwd()/'verification'
    directory.mkdir(parents=True,exist_ok=True)
    report={'directory':str(directory),'ok':False}
    try:
        verify(report);report['ok']=True
    except Exception as exc:report['error']=str(exc)
    (directory/'browser-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['ok'] else 1
