"""Shell checks (Linux via tools/linux_shim.py): close hides to the tray when it's on, Quit really ends,
reopen from the tray plays the startup animation and leaves the window fully visible, update bar."""
import time
from unittest.mock import Mock
import retweaks as app
import hubplus
import automation
import rt_shell

class Hotkeys:
    def __init__(self,*a):self.thread=Mock()
    def update(self,*a):pass
    def close(self):pass
automation.Hotkeys=Hotkeys
app.Hub._load_info=lambda self:None
hubplus.write_json=lambda *a:None
hubplus.install(vars(app))

class FakeTray:
    def __init__(self,hub):self.icon=None;self.error=None;self.notes=[]
    def start(self):self.icon=object();return True
    def stop(self):self.icon=None
    def notify(self,t,x):self.notes.append(t)
rt_shell.Tray=FakeTray
saved=[]
hub=app.Hub(show_intro=False,enable_ai=False)
hub.save_settings=lambda:saved.append(dict(hub.settings)) or True
hub.settings['tray_on_close']=True
hub.settings['check_updates']=False
shell=rt_shell.Shell(hub,vars(app),['Moved A -> B'])
hub.update()
# close -> tray
hub.request_close();hub.update()
assert hub.state()=='withdrawn' and shell.tray.notes, 'close should hide to the tray'
# reopen from tray -> animation, then fully visible
rt_shell.reopen(hub)
intro=hub._reopen_intro
assert intro is not None
end=time.time()+6
while not intro.closed and time.time()<end:
    hub.update();time.sleep(0.01)
hub.update()
assert intro.closed and hub.state()!='withdrawn' and float(hub.attributes('-alpha'))==1.0
# update bar
shell.show_update_bar({'version':'v9.9','exe_url':'x','sha_url':'y'});hub.update()
assert shell.bar.winfo_ismapped() and 'v9.9' in shell.bar_text.cget('text')
shell.hide_update_bar();hub.update()
assert not shell.bar.winfo_ismapped()
# tray off -> close quits for real
shell.set_tray(False)
assert hub.settings['tray_on_close'] is False and saved[-1]['tray_on_close'] is False
hub.request_close()
try:
    hub.winfo_exists();alive=True
except Exception:
    alive=False
assert not alive or getattr(hub,'_quitting',False)
print('PASS: tray close/reopen with animation, update bar, quit when tray is off.')
