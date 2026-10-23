"""Daily tools UI smoke and file-action checks using generated fixtures and mocked dialogs."""
import tempfile,time,hashlib
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
import automation,hubplus,retweaks as app

automation.Hotkeys=lambda *args:Mock()
app.Hub._load_info=lambda self:None
hubplus.write_json=lambda *args:None
hubplus.install(vars(app))
hub=app.Hub(show_intro=False,enable_ai=False);errors=[];hub.report_callback_exception=lambda *args:errors.append(args)
def pump():
    for _ in range(10):hub.update();time.sleep(.02)
def button(window,title):
    children=list(window.winfo_children())
    while children:
        child=children.pop()
        if getattr(child,'label',None)==title:return child
        children.extend(child.winfo_children())
    raise AssertionError(title)
def settle(state):
    deadline=time.monotonic()+5
    while state['busy'] and time.monotonic()<deadline:pump()
    assert not state['busy']
try:
    hub.show_tab(26);pump();page=hub.daily_tools
    assert len(hub.tabs)==27 and hub.nav[26].winfo_manager()=='pack'
    with patch('daily_tools.ctypes.windll.kernel32.SetThreadExecutionState',return_value=1) as power:
        page.awake.set(True);page.keep_awake();assert power.call_args.args==(0x80000003,)
        page.awake.set(False);page.keep_awake();assert power.call_args.args==(0x80000000,)
    with patch.object(hub,'attributes') as attributes:
        page.top.set(True);page.on_top();attributes.assert_called_with('-topmost',True)
        page.top.set(False)
    for name in ['ocr','converter','pdf','text_tool','checksum','color']:getattr(page,name)();pump()
    assert len(page.windows)==6
    count=len(hub.winfo_children());page.ocr();assert len(hub.winfo_children())==count
    text=page.windows['text'];text['text'].insert('1.0','a\na\nb');text['action'].set('Remove duplicate lines');text['apply']();assert text['text'].get('1.0','end-1c')=='a\nb'
    button(text['window'],'Undo').command();assert text['text'].get('1.0','end-1c')=='a\na\nb'
    with tempfile.TemporaryDirectory(dir=Path('verification').resolve(),prefix='daily-ui-') as directory:
        root=Path(directory);assert root.resolve().is_relative_to(Path('verification').resolve())
        source=root/'sample.png';Image.new('RGB',(400,200),'red').save(source)
        with patch('daily_tools.filedialog.askopenfilename',return_value=str(source)),patch('daily_tools.kit.extract_text',return_value={'text':'sample text','language':'English'}):
            state=page.windows['ocr'];button(state['window'],'Choose image').command();settle(state);assert state['text'].get('1.0','end-1c')=='sample text'
        converter=page.windows['converter'];converter['paths'][:]=[str(source)];converter['width'].set('100');converter['format'].set('PNG')
        with patch('daily_tools.filedialog.askdirectory',return_value=str(root)):
            button(converter['window'],'Convert to new files').command();settle(converter)
        with Image.open(root/'sample_converted.png') as result:assert result.size==(100,50)
        pdf=page.windows['pdf'];pdf['paths'][:]=[str(source)]
        with patch('daily_tools.filedialog.askdirectory',return_value=str(root)):
            button(pdf['window'],'Create PDF').command();settle(pdf)
        assert (root/'RETWEAKS_images.pdf').is_file()
        checksum=page.windows['checksum']
        with patch('daily_tools.filedialog.askopenfilename',return_value=str(source)):
            button(checksum['window'],'Choose file').command();settle(checksum)
        assert checksum['digest']==hashlib.sha256(source.read_bytes()).hexdigest()
        color=page.windows['color']
        with patch('daily_tools.filedialog.askopenfilename',return_value=str(source)):button(color['window'],'Choose image').command();pump()
        assert color['image'].getpixel((100,100))==(255,0,0)
    assert not errors,errors
finally:hub.destroy()
print('PASS: 27 tabs, all six local tool windows, single-instance dialogs, async OCR/conversion/PDF/hash, text undo, color source pixels, and mocked awake/on-top controls.')
