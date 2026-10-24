"""Actual Tk sidebar scroll bounds, including a filtered menu shorter than its viewport."""
import time
import tkinter as tk

import retweaks as app
from rt_pages import REGISTRY
from rt_sidebar import Sidebar

root=tk.Tk();root.geometry('500x650')
root.settings={}
root.rt_tabs={name:30+i for i,(name,_,_) in enumerate(REGISTRY)}
root.show_tab=lambda index:None
side_frame=tk.Frame(root,bg=app.SIDE,width=240)
side_frame.pack(fill='both',expand=True)
side=Sidebar(root,side_frame,vars(app))
root.update()
def wheel(units):
    side.canvas.wheel_scroll(units)
    deadline=time.monotonic()+.08
    while time.monotonic()<deadline:root.update();time.sleep(.005)
def bounded():
    origin=side.canvas.canvasy(0)
    region=root.tk.splitlist(side.canvas.cget('scrollregion'))
    limit=max(0,float(region[3])-side.canvas.winfo_height())
    assert -.01<=origin<=limit+1,(origin,limit)
wheel(-1000);bounded()
wheel(1000);bounded()
side.query.set('network');root.update()
assert side.holder.winfo_height()<side.canvas.winfo_height()
for amount in (-1000,1000,-1000):
    wheel(amount);bounded();assert abs(side.canvas.canvasy(0))<1
side.query.set('');root.update()
wheel(-1000);bounded()
assert {'Drivers','File Transfers','Backgrounds','App Starter'}<=set(side.buttons)
assert len(side.buttons)==21
root.destroy()
print('PASS: sidebar clamps top/bottom, filtered short menu stays at origin, restored direct entries are visible.')
