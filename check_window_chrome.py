"""Own-window checks for custom caption, themes and window state transitions."""
import ctypes,time,tkinter as tk
from types import SimpleNamespace
import retweaks as app
from appearance import palette
from window_chrome import WindowChrome
root=tk.Tk();root.title('RETWEAKS window controls verification');root.geometry('1120x740+50+50');root.minsize(1060,680)
g=vars(app).copy();body=tk.Frame(root,bg=g['BG']);body.pack(fill='both',expand=True)
tk.Label(body,text='RETWEAKS window control verification',bg=g['BG'],fg=g['FG']).pack(pady=40)
chrome=WindowChrome(root,g)
errors=[];root.report_callback_exception=lambda *args:errors.append(args)
def pump():
    for _ in range(6):root.update();time.sleep(.035)
try:
    pump();assert chrome.native_ready
    user,hwnd=chrome.hwnd()
    user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
    assert not user.GetWindowLongPtrW(hwnd,-16)&0x00C00000
    assert user.GetWindowLongPtrW(hwnd,-16)&0x00040000
    normal=root.geometry()
    assert 'fullscreen' not in chrome.buttons
    assert all(chrome.itemcget(i,'text')!='F11' for i in chrome.find_all() if chrome.type(i)=='text')
    chrome.toggle_fullscreen();pump();assert chrome.fullscreen and root.attributes('-fullscreen')
    g.update(palette('Forest'));chrome.apply_native();pump()
    assert any(chrome.itemcget(i,'fill')==g['ACC'] for i in chrome.find_all() if chrome.type(i)=='line')
    chrome.escape();pump();assert not chrome.fullscreen and not root.attributes('-fullscreen')
    assert root.state()=='normal'
    assert root.geometry()==normal,(normal,root.geometry())
    for _ in range(3):
        chrome.toggle_fullscreen();pump();chrome.escape();pump()
        assert root.geometry()==normal,(normal,root.geometry())
    x,y=root.winfo_x(),root.winfo_y()
    start=SimpleNamespace(x=300,y=25,x_root=x+300,y_root=y+25)
    chrome.press(start)
    chrome.drag_motion(SimpleNamespace(x=400,y=70,x_root=start.x_root+100,y_root=start.y_root+45))
    pump()
    assert root.winfo_exists() and root.winfo_x()==x+100 and root.winfo_y()==y+45
    # Releasing a drag over Close must never close the window.
    close=chrome.buttons['close']
    chrome.release(SimpleNamespace(x=(close[0]+close[2])/2,y=25))
    pump();assert root.winfo_exists()
    # A cancelled control click must not fire on mouse-down or outside release.
    chrome.press(SimpleNamespace(x=(close[0]+close[2])/2,y=25))
    assert root.winfo_exists()
    chrome.release(SimpleNamespace(x=300,y=25));pump();assert root.winfo_exists()
    moved_geometry=root.geometry()
    for _ in range(3):
        chrome.maximize();pump();chrome.maximize();pump()
        assert root.geometry()==moved_geometry,(moved_geometry,root.geometry())
    chrome.maximize();pump()
    chrome.press(SimpleNamespace(x=300,y=25,x_root=root.winfo_x()+300,y_root=root.winfo_y()+25))
    chrome.drag_motion(SimpleNamespace(x=380,y=65,x_root=root.winfo_x()+380,y_root=root.winfo_y()+65))
    pump();assert root.state()=='normal' and root.winfo_exists()
    chrome.release(SimpleNamespace(x=300,y=25))
    chrome.maximize();pump();assert root.state()=='zoomed'
    chrome.toggle_fullscreen();pump();chrome.escape();pump();assert root.state()=='zoomed'
    chrome.maximize();pump();assert root.state()=='normal'
    chrome.minimize();pump();assert root.state()=='iconic'
    root.deiconify();pump();assert root.state()=='normal'
    for theme in ('Forest','Ember','Midnight','Graphite'):
        g.update(palette(theme));chrome.apply_native();pump()
        assert chrome.cget('bg')==g['BG']
        assert any(chrome.itemcget(i,'fill')==g['ACC'] for i in chrome.find_all() if chrome.type(i)=='line')
    assert not errors,errors
    print('PASS: safe dragging, drag-over-Close, maximized drag, repeated exact-size restores, fullscreen/Esc, minimize/restore and themes. No PC settings changed.')
finally:root.destroy()
