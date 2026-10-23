"""Mixer UI checks with fake audio; never changes Windows audio settings."""
from unittest.mock import Mock
import tkinter as tk
import retweaks as app
import hubplus
import automation

class Hotkeys:
    def __init__(self,*args):self.thread=Mock()
    def update(self,*args):pass
    def close(self):pass

class FakeAudio:
    def __init__(self):self.writes=[]
    def snapshot(self):
        return dict(devices=[dict(key=('device',str(i)),id=str(i),flow=i%2,name='Test device '+str(i),level=40,mute=False,default=i<2,calls=i<2) for i in range(4)],
            sessions=[dict(key=('session','0','app'),name='Test app',device='Test output',level=65,mute=False)],errors=[])
    def set_level(self,key,value):self.writes.append(('level',key,float(value)))
    def set_mute(self,key,value):self.writes.append(('mute',key,value))
    def set_default(self,key,calls=False):self.writes.append(('default',key,calls))

automation.Hotkeys=Hotkeys
app.Hub._load_info=lambda self:None
hubplus.write_json=lambda *args:None
hubplus.install(vars(app))
hub=app.Hub(show_intro=False,enable_ai=False)
errors=[];hub.report_callback_exception=lambda *args:errors.append(args)
try:
    panel=hub.audio_panel;panel.backend=FakeAudio()
    hub.show_tab(27);panel.refresh();hub.update()
    assert len(hub.tabs)>=28 and len(panel.views[0]['rows'])==3
    panel.refresh();hub.update();assert not panel.backend.writes
    panel.pop_out();hub.update();assert len(panel.views)==2
    panel.pop_out();assert len(panel.views)==2
    panel.refresh();hub.update();assert not panel.backend.writes
    panel.action_level(('session','0','app'),32,panel.views[0])
    assert panel.backend.writes[-1]==('level',('session','0','app'),32)
    panel.action(lambda:panel.backend.set_mute(('device','1'),True))
    assert panel.backend.writes[-1]==('mute',('device','1'),True)
    panel.action(lambda:panel.backend.set_default('2',True))
    assert panel.backend.writes[-1]==('default','2',True)
    # ---- Volume lock (RETWEAKS): Lock appears only on the default speaker/mic rows, saves the setting,
    # puts a changed volume back on the next tick, follows the slider and never touches mute.
    saved=[];hub.settings={};hub.save_settings=lambda:saved.append(dict(hub.settings))
    class FakeLock:
        def __init__(self):self.level={'output':40,'input':40};self.writes=[]
        def read(self,kind):return (self.level[kind],False)
        def write(self,kind,p):self.writes.append((kind,p));self.level[kind]=p
    lock=FakeLock();panel.lock_io=lock
    rows=panel.views[0]['rows']
    out_row=rows[('device','0')];in_row=rows[('device','1')]
    assert out_row['lock_kind']=='output' and in_row['lock_kind']=='input'
    assert not any(r.get('lock_kind') for k,r in rows.items() if k[0]=='session')
    out_row['lock'].set(True);out_row['value'].set(55)
    panel.set_lock('output',55)
    assert hub.settings['audio_lock_output']==55 and saved
    lock.level['output']=20;panel.lock_tick();assert lock.writes[-1]==('output',55) and lock.level['output']==55
    n=len(lock.writes);panel.lock_tick();assert len(lock.writes)==n        # nothing to fix: no write
    assert all(isinstance(p,int) and k in ('output','input') for k,p in lock.writes)   # volume only, never mute
    panel.set_lock('output',None);lock.level['output']=10;panel.lock_tick()
    assert hub.settings['audio_lock_output'] is None and lock.level['output']==10   # off: left alone
    panel.set_lock('input',30);lock.level['input']=90;panel.lock_tick();assert lock.level['input']==30
    for bad in (-5,101,'x',True):
        hub.settings['audio_lock_input']=bad;assert panel.lock_value('input') is None
    hub.settings['audio_lock_input']=None
    panel.backend.snapshot=lambda:dict(devices=[],sessions=[],errors=[])
    panel.refresh();hub.update();assert not panel.views[0]['rows']
    for theme in ('Forest','Graphite'):hub.apply_theme(theme,save=False);hub.update()
    panel.window.event_generate('<<Unused>>')
    close=panel.window.protocol('WM_DELETE_WINDOW');panel.window.tk.call(close)
    hub.update();assert len(panel.views)==1 and panel.window is None
    # Linux test displays can't 'zoom' (maximize) a window; that Windows-only state is not a mixer error.
    errors=[e for e in errors if 'zoomed' not in str(e[1])]
    assert not errors,errors
finally:hub.destroy()
assert panel.closed and panel.job is None and panel.lock_job is None
print('PASS: mixer tab, no refresh writes, synchronized pop-out, single window, volume/mute/default dispatch, unplugged devices, themes, volume lock (default devices only, saved, enforced, off leaves volume alone, bad values ignored) and cleanup.')
