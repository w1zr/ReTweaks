"""Drag, keyboard and refresh checks without touching Windows audio."""
import tkinter as tk
from types import SimpleNamespace
from volume_slider import VolumeSlider
root=tk.Tk();root.geometry('400x80')
value=tk.DoubleVar(value=30);writes=[];drag=[]
g=dict(PANEL='#151518',LINE='#303035',ACC='#eeeef0',FG='#f5f5f6')
slider=VolumeSlider(root,value,g,writes.append,drag.append);slider.pack(fill='x')
try:
    root.update();value.set(80);root.update();assert not writes
    slider.press(SimpleNamespace(x=12));assert value.get()==0 and slider.dragging
    slider.move(SimpleNamespace(x=slider.winfo_width()+100));assert value.get()==100
    slider.release(SimpleNamespace(x=slider.winfo_width()/2));assert value.get()==50
    assert not slider.dragging and slider.grab_current() is None
    slider.key(SimpleNamespace(keysym='Right'));assert value.get()==51
    slider.key(SimpleNamespace(keysym='Home'));assert value.get()==0
    slider.key(SimpleNamespace(keysym='End'));assert value.get()==100
    count=len(writes);value.set(42);root.update();assert len(writes)==count
    assert drag[:2]==[True,False]
finally:root.destroy()
print('PASS: no refresh writes; click-to-seek, drag bounds, final release, pointer capture and keyboard controls.')
