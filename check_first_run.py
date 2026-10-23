"""First-run preferences and a real .lnk in a test folder, never the desktop."""
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
from first_run import offer_desktop_shortcut,create_desktop_shortcut

with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
    root=Path(directory)
    assert root.resolve().parent==Path(__file__).resolve().parent
    target_dir=root / "Portable build's folder with spaces"
    target_dir.mkdir()
    target=target_dir/'RETWEAKS.exe';target.write_bytes(b'non-executable shortcut target fixture')
    desktop=root/'Test desktop';desktop.mkdir()
    link=create_desktop_shortcut(target,desktop)
    assert link==desktop/'RETWEAKS.lnk' and link.stat().st_size>0
    inspect=r'''[Console]::InputEncoding=New-Object System.Text.UTF8Encoding($false); $p=[Console]::In.ReadToEnd(); $s=(New-Object -ComObject WScript.Shell).CreateShortcut($p); @{target=$s.TargetPath;working=$s.WorkingDirectory;arguments=$s.Arguments;icon=$s.IconLocation} | ConvertTo-Json -Compress'''
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',inspect],input=str(link),capture_output=True,text=True,encoding='utf-8',creationflags=0x08000000,timeout=15)
    assert result.returncode==0,result.stderr
    details=json.loads(result.stdout.lstrip('\ufeff'))
    assert Path(details['target'])==target and Path(details['working'])==target_dir
    assert details['arguments']=='' and str(target) in details['icon']
    with patch('first_run.messagebox.askyesno',return_value=False) as ask,patch('first_run.create_desktop_shortcut') as create:
        assert not offer_desktop_shortcut(None,root/'declined',target)
        assert not offer_desktop_shortcut(None,root/'declined',target)
        assert ask.call_count==1;create.assert_not_called()
    with patch('first_run.messagebox.askyesno',return_value=True) as ask,patch('first_run.create_desktop_shortcut',return_value=link) as create:
        assert offer_desktop_shortcut(None,root/'accepted',target)
        assert not offer_desktop_shortcut(None,root/'accepted',target)
        assert ask.call_count==1 and create.call_count==1
    with patch('first_run.messagebox.askyesno',return_value=True),patch('first_run.create_desktop_shortcut',side_effect=OSError('Not writable')),patch('first_run.messagebox.showerror') as error:
        assert not offer_desktop_shortcut(None,root/'failed',target)
        assert not (root/'failed'/'first_run.json').exists()
        error.assert_called_once()
print('PASS: one-time Yes/No prompt, remembered choice, retry after failure, and real shortcut target/icon/working-directory handling with spaces. Actual desktop untouched.')

import retweaks as app
import hubplus
import automation
from unittest.mock import Mock
class Hotkeys:
    def __init__(self,*args):self.thread=Mock()
    def update(self,*args):pass
    def close(self):pass
automation.Hotkeys=Hotkeys
app.Hub._load_info=lambda self:None
hubplus.write_json=lambda *args:None
hubplus.install(vars(app))
seen=[]
def offered(parent,settings):
    seen.append((parent.state(),hasattr(parent,'intro')))
with patch.object(hubplus.sys,'frozen',True,create=True),patch('hubplus.offer_desktop_shortcut',side_effect=offered):
    hub=app.Hub(enable_ai=False)
    try:
        assert seen==[('withdrawn',False)]
        hub.update()
        assert hub.intro.window.winfo_ismapped() and not hub.intro.closed
    finally:hub.destroy()
print('PASS: packaged startup offers shortcut before the preserved opening animation; no actual prompt or desktop change in the integration test.')
