"""Maximized startup and reversible sidebar collapse without network."""
from unittest.mock import Mock,patch
from types import SimpleNamespace
import time
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
hub=app.Hub(show_intro=False,enable_ai=False)
errors=[];hub.report_callback_exception=lambda *args:errors.append(args)
def pump():
    for _ in range(9):hub.update();time.sleep(.025)
try:
    pump()
    assert hub.state()=='zoomed' and not hub.sidebar_collapsed
    assert hub.sidebar.winfo_ismapped() and 'menu' in hub.chrome.buttons
    narrow=hub.content.winfo_width()
    hub.pc_value.parts['CPU'].set('Preserved component')
    with patch.object(hub,'launch') as external:
        hub.nav[19].command();pump()
        assert hub.cur_tab==19 and not hub.sidebar_collapsed
        assert hub.sidebar.winfo_ismapped()
        assert hub.content.winfo_width()==narrow
        external.assert_not_called()
    hub.toggle_sidebar();hub.update()
    assert hub.sidebar_fade.job is not None
    time.sleep(.065);hub.update()
    halfway=hub.sidebar_slot.winfo_width()          # base app v1.5: the slot (and content) resize during the slide
    assert 0<halfway<244,halfway
    assert hub.sidebar.winfo_x()==0
    assert hub.sidebar.winfo_width()==244
    assert narrow<hub.content.winfo_width()<=narrow+245,(narrow,hub.content.winfo_width(),halfway)
    pump()
    assert not hub.sidebar.winfo_ismapped()
    assert hub.content.winfo_width()>=narrow+200
    assert hub.site_frame.winfo_width()>narrow
    assert hub.site_frame.winfo_width()==hub.content.winfo_width()
    assert hub.site_frame.winfo_height()==hub.content.winfo_height()
    assert not hub.site_status.winfo_manager()
    assert not any(isinstance(widget,app.RButton) for widget in hub.tabs[19].winfo_children())
    assert hub.sidebar_fade.job is None and hub.sidebar_fade.overlay is None
    with patch.object(hub,'launch') as external:
        hub.nav[25].command();pump()
        assert hub.cur_tab==25 and hub.sidebar_collapsed
        external.assert_not_called()
    assert hub.builder_frame.winfo_width()==hub.content.winfo_width()
    assert hub.builder_frame.winfo_height()==hub.content.winfo_height()
    assert not hub.builder_status.winfo_manager()
    assert not any(isinstance(widget,app.RButton) for widget in hub.tabs[25].winfo_children())
    label=hub.chrome.find_withtag('sidebar-toggle-label')[0]
    assert hub.chrome.itemcget(label,'text')=='Show sidebar'
    left,top,right,bottom=hub.chrome.buttons['menu']
    click=SimpleNamespace(x=(left+right)/2,y=(top+bottom)/2)
    hub.chrome.press(click);hub.chrome.release(click);pump()
    assert not hub.sidebar_collapsed and hub.sidebar.winfo_ismapped()
    assert hub.content.winfo_width()==narrow
    label=hub.chrome.find_withtag('sidebar-toggle-label')[0]
    assert hub.chrome.itemcget(label,'text')=='Hide sidebar'
    hub.nav[24].command();pump()
    assert hub.cur_tab==24 and not hub.sidebar_collapsed
    assert hub.pc_value.parts['CPU'].get()=='Preserved component'
    assert not hub.sidebar_collapsed and hub.sidebar.winfo_ismapped()
    for _ in range(7):
        hub.toggle_sidebar();hub.update();time.sleep(.008)
    pump()
    assert hub.sidebar_collapsed and not hub.sidebar.winfo_ismapped()
    assert hub.sidebar_fade.overlay is None and hub.sidebar_fade.job is None
    assert hub.pc_value.parts['CPU'].get()=='Preserved component'
    hub.chrome.maximize();pump();assert hub.state()=='normal'
    hub.iconify();pump();hub.deiconify();pump()
    assert hub.state()=='normal'  # Startup maximization does not override later choices.
    assert not errors,errors
finally:hub.destroy()
print('PASS: maximized launch, sidebar stays open on tab selection, animated manual collapse, expanded website area, menu restore, preserved page inputs and normal window restore.')
