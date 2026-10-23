"""RETWEAKS startup screen checks (no network or tuning changes): the chip-scan splash shows while the
app loads, has no version number and no orbit animation, then cross-fades into the main window."""
import time
from unittest.mock import Mock
import retweaks as app
import hubplus
import automation

class Hotkeys:
    def __init__(self,*args):self.thread=Mock()
    def update(self,*args):pass
    def close(self):pass

automation.Hotkeys=Hotkeys
app.Hub._load_info=lambda self:None
hubplus.write_json=lambda *args:None
hubplus.install(vars(app))
hub=app.Hub(enable_ai=False)
errors=[]
hub.report_callback_exception=lambda *args:errors.append(args)
try:
    intro=hub.intro
    hub.update()
    assert hub.state()=='withdrawn' and intro.window.winfo_exists()
    assert intro.canvas.itemcget(intro.word,'text')=='ReTweaks'
    texts=[intro.canvas.itemcget(i,'text') for i in intro.canvas.find_all() if intro.canvas.type(i)=='text']
    from core.version import __version__
    assert not any(__version__ in t for t in texts), texts           # no version number
    assert all(intro.canvas.type(i) in ('image','text') for i in intro.canvas.find_all())   # no orbit ovals
    assert intro.ready_at is not None                                 # loading finished -> ready
    w=intro.window.winfo_width();sw=hub.winfo_screenwidth()
    assert 560<=w<=sw
    end=time.time()+5
    while not intro.closed and time.time()<end:
        hub.update();time.sleep(0.01)
    took=intro._time()-max(intro.ready_at,intro.t0+intro.REVEAL)   # time after loading + reveal
    assert intro.closed and hub.state()!='withdrawn', 'splash did not finish'
    assert took<intro.HOLD+intro.FADE+0.5, took                       # only the hold + cross-fade
    assert float(hub.attributes('-alpha'))==1.0
    assert hub.cur_tab==hub.rt_tabs['Dashboard']                     # home = RETWEAKS dashboard
    assert not errors,errors
finally:
    hub.destroy()
print('PASS: chip-scan splash while loading, no version, no orbits, cross-fades into the Dashboard.')
