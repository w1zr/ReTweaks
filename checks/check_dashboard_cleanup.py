"""Checks the merged home, unique controls and contextual AI without applying tweaks."""
import os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['APPDATA']=tempfile.mkdtemp()
os.environ['LOCALAPPDATA']=tempfile.mkdtemp()
import retweaks as app,hubplus
app.Hub._load_info=lambda self:None
hubplus.install(vars(app))
hub=app.Hub(show_intro=False,enable_ai=False)
hub.geometry('1440x900+0+0')
errors=[]
hub.report_callback_exception=lambda *args:errors.append(args)
hub.update()
assert all(page is not None for page in hub.rt_pages.values()),[k for k,v in hub.rt_pages.items() if v is None]
def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)
def labels(widget):
    result=[]
    for w in walk(widget):
        if hasattr(w,'label'):result.append(w.label)
    return result
home=hub.rt_tabs['Dashboard']
hub.show_tab(0);hub.update()
assert hub.cur_tab==home and not hub.section_nav.frame.winfo_manager()
dash=hub.rt_pages['Dashboard']
for caption in ['Browse presets','Find drivers','Open App Starter','Review recommendation','Toggle Windows Game Mode']:
    assert labels(hub.tabs[home]).count(caption)==1,caption
assert hub.rec_lbl in list(walk(dash.body))
assert hub.detected in list(walk(dash.body))
hub._show_info({'cpu':'Test CPU','gpu':'Test GPU','ram':'16'},app.PRESET_ORDER[0],'Test recommendation',[])
assert 'Recommended for your PC' in hub.rec_lbl.cget('text')
for name in ['Settings','Backgrounds','Browser','File Transfers','About']:
    assert 'Explain selected tweaks' not in labels(hub.tabs[hub.rt_tabs[name]]),name
assert 'Explain selected tweaks' in labels(hub.tabs[1])
page=hub.rt_pages['Settings'];bg=page.background_controls
hub.show_tab(hub.rt_tabs['Settings']);hub.update()
assert not bg.advanced.winfo_manager()
assert hub.animation_selector is bg.style
import appearance
selectors=[w for w in walk(hub.tabs[hub.rt_tabs['Settings']]) if isinstance(w,app.RSelect)]
assert sum(list(getattr(w,'values',[]))==list(appearance.ANIMATIONS) for w in selectors)==1
assert sum(isinstance(w,appearance.Accent) for w in walk(hub.tabs[hub.rt_tabs['Settings']]))==1
bg.toggle_advanced();hub.update();assert bg.advanced.winfo_manager()=='pack'
bg.set_option('animation_speed',1.5);bg.change('Aurora')
from rt_pages.settings_store import load
assert load()['animation_speed']==1.5
bg.toggle_advanced();assert not bg.advanced.winfo_manager()
assert not errors,errors
hub.destroy()
print('PASS: all pages load, merged Dashboard routes/actions/recommendation, unique background selector/preview, collapsed options, relevant AI help and persisted animation speed.')
