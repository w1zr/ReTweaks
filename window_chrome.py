from branding import feather
from core.version import BRAND
"""Theme-aware custom caption with native resize/minimize/maximize and fullscreen."""
import ctypes
from ctypes import wintypes
import tkinter as tk
import tkinter.font as tkfont
import re
from appearance import blend

_fonts={}
def _label_font(g):
    spec=(g['UI'],9,'bold')
    if spec not in _fonts:_fonts[spec]=tkfont.Font(font=spec)
    return _fonts[spec]

class WindowChrome(tk.Canvas):
    def __init__(self,root,g):
        super().__init__(root,height=48,bg=g['BG'],highlightthickness=0,bd=0)
        self.root=root;self.g=g;self.fullscreen=False;self.saved=None;self.hover=None;self.buttons={};self.native_ready=False;self.drag=None;self.pressed=None;self.closed=False;self.transition=0;self.windowed_geometry=None;self._applying=False
        self.pack(side='top',fill='x',before=next(w for w in root.winfo_children() if not isinstance(w,tk.Toplevel)))
        self.bind('<Configure>',lambda event:self.refresh())
        self.bind('<Motion>',self.motion);self.bind('<B1-Motion>',self.drag_motion);self.bind('<ButtonRelease-1>',self.release);self.bind('<Leave>',lambda event:self.set_hover(None))
        self.bind('<Button-1>',self.press);self.bind('<Double-Button-1>',self.double)
        root.bind('<F11>',lambda event:self.toggle_fullscreen(),add='+')
        root.bind('<Escape>',lambda event:self.escape(),add='+')
        root.bind('<Map>',lambda event:self.apply_native() if event.widget is root else None,add='+')
        root.bind('<Configure>',self.configured,add='+')
        root.bind('<Destroy>',lambda event:setattr(self,'closed',True) if event.widget is root else None,add='+')
        root.after_idle(self.apply_native)
    def hwnd(self):
        user=ctypes.WinDLL('user32',use_last_error=True)
        user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];user.GetAncestor.restype=wintypes.HWND
        return user,user.GetAncestor(self.root.winfo_id(),2)
    def apply_native(self):
        if self.closed or self._applying:return
        if self.fullscreen:self.refresh();return
        self._applying=True
        try:
            user,hwnd=self.hwnd()
            if not hwnd:return
            get_style=user.GetWindowLongPtrW;get_style.argtypes=[wintypes.HWND,ctypes.c_int];get_style.restype=ctypes.c_ssize_t
            set_style=user.SetWindowLongPtrW;set_style.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t];set_style.restype=ctypes.c_ssize_t
            # Keep the normal resizable/taskbar window, replacing only the caption.
            style=get_style(hwnd,-16)
            geometry=self.root.geometry() if self.root.state()=='normal' else None
            if style & 0x00C00000:set_style(hwnd,-16,style & ~0x00C00000)
            user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
            if style & 0x00C00000:
                user.SetWindowPos(hwnd,None,0,0,0,0,0x37)
                if geometry:self.set_client_geometry(geometry)
            try:
                dwm=ctypes.WinDLL('dwmapi');dwm.DwmSetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
                accent=self.g['ACC'];color=int(accent[1:3],16)|(int(accent[3:5],16)<<8)|(int(accent[5:7],16)<<16)
                for attr,value in ((20,1),(33,2),(34,color)):
                    data=wintypes.DWORD(value);dwm.DwmSetWindowAttribute(hwnd,attr,ctypes.byref(data),ctypes.sizeof(data))
            except (OSError,AttributeError):pass
            self.native_ready=True
        except (OSError,AttributeError,tk.TclError):pass
        finally:self._applying=False
        self.refresh()
    def set_client_geometry(self,geometry):
        match=re.fullmatch(r'(\d+)x(\d+)(.*)',geometry)
        if not match:return
        width,height=int(match[1]),int(match[2]);position=match[3]
        requested_width,requested_height=width,height
        # Tk caches its original caption frame metrics. Measure the actual client
        # after layout instead of accumulating that mismatch on every restore.
        for _ in range(3):
            self.root.geometry(f'{max(1,requested_width)}x{max(1,requested_height)}{position}')
            self.root.update_idletasks()
            dw=self.root.winfo_width()-width;dh=self.root.winfo_height()-height
            if not dw and not dh:break
            requested_width-=dw;requested_height-=dh
    def configured(self,event):
        if event.widget is self.root:
            if not self.fullscreen and self.root.state()=='normal' and not self._applying and not self.drag:
                if self.root.winfo_width()>=self.root.minsize()[0]:self.windowed_geometry=self.root.geometry()
            self.refresh()
    def refresh(self):
        if self.closed:return
        try:
            if not self.winfo_exists():return
        except tk.TclError:return
        g=self.g;w=max(300,self.winfo_width());self.configure(bg=g['BG']);self.delete('all')
        self.create_polygon(g['rr'](7,5,w-7,46,21),smooth=True,fill=g['SIDE'],outline=blend(g['SIDE'],g['LINE'],.38),width=1)
        # Owner request 2026-10-22: no chip/wordmark here (the sidebar header already shows them).
        menu=callable(getattr(self.root,'toggle_sidebar',None))
        # the menu button fits its label (translated labels can be longer than 'Hide sidebar'; rt_i18n)
        label='Show sidebar' if getattr(self.root,'sidebar_collapsed',False) else 'Hide sidebar'
        try:
            import rt_i18n;shown=rt_i18n.tr(label)
        except Exception:shown=label
        try:menu_right=max(164,53+int(_label_font(g).measure(shown))+14)
        except Exception:menu_right=164
        offset=menu_right+2 if menu else 0
        search=getattr(self.root,'global_search',None)     # top-bar search (rt_search)
        if search is not None:
            try:search.place(self,w)
            except Exception as e:print('search bar',e)
        positions=[('minimize',w-128,w-92),('maximize',w-88,w-52),('close',w-48,w-12)]
        self.buttons={name:(left,10,right,40) for name,left,right in positions}
        if menu:self.buttons['menu']=(14,8,menu_right,42)
        for name,(left,top,right,bottom) in self.buttons.items():
            if self.hover==name and name!='menu':self.create_oval(left+3,top,right-3,bottom,fill=g['PANEL2'],outline='')
            x=(left+right)/2;y=25;color=g['ACC']
            if name=='menu':
                self.create_polygon(g['rr'](left,top,right,bottom,17),smooth=True,fill=g['PANEL2'] if self.hover==name else g['PANEL'],outline=blend(g['PANEL'],g['LINE'],.45),width=1)
                self.create_polygon(g['rr'](25,17,42,33,4),smooth=True,fill='',outline=color,width=1.3)
                self.create_line(30,18,30,32,fill=color,width=1.3)
                collapsed=getattr(self.root,'sidebar_collapsed',False)
                points=(34,22,38,25,34,28) if collapsed else (38,22,34,25,38,28)
                self.create_line(*points,fill=color,width=1.5)
                self.create_text(53,25,text='Show sidebar' if collapsed else 'Hide sidebar',anchor='w',fill=g['FG'],font=(g['UI'],9,'bold'),tags='sidebar-toggle-label')
            elif name=='minimize':self.create_line(x-6,y+4,x+6,y+4,fill=color,width=1.5)
            elif name=='maximize':
                if self.root.state()=='zoomed' or self.fullscreen:
                    self.create_rectangle(x-3,y-7,x+7,y+3,outline=color,width=1.3)
                    self.create_rectangle(x-7,y-3,x+3,y+7,outline=color,fill=g['SIDE'],width=1.3)
                else:self.create_rectangle(x-6,y-6,x+6,y+6,outline=color,width=1.3)
            else:
                self.create_line(x-5,y-5,x+5,y+5,fill=color,width=1.5);self.create_line(x-5,y+5,x+5,y-5,fill=color,width=1.5)
    def hit(self,x,y):return next((name for name,(a,b,c,d) in self.buttons.items() if a<=x<=c and b<=y<=d),None)
    def set_hover(self,name):
        if name!=self.hover:self.hover=name;self.configure(cursor='hand2' if name else '');self.refresh()
    def motion(self,event):self.set_hover(self.hit(event.x,event.y))
    def press(self,event):
        self.pressed=self.hit(event.x,event.y);self.drag=None
        if self.pressed or self.fullscreen:return
        self.drag={'x':event.x_root,'y':event.y_root,'window_x':self.root.winfo_x(),'window_y':self.root.winfo_y(),
                   'maximized':self.root.state()=='zoomed','ratio':(event.x_root-self.root.winfo_x())/max(1,self.root.winfo_width()),'offset_y':event.y_root-self.root.winfo_y()}
    def drag_motion(self,event):
        if self.pressed or not self.drag or self.fullscreen or self.closed:return
        drag=self.drag
        if abs(event.x_root-drag['x'])+abs(event.y_root-drag['y'])<4:return
        if drag['maximized']:
            self.root.state('normal')
            if self.windowed_geometry:self.set_client_geometry(self.windowed_geometry)
            self.root.update_idletasks()
            drag.update(maximized=False,x=event.x_root,y=event.y_root,
                        window_x=round(event.x_root-self.root.winfo_width()*drag['ratio']),
                        window_y=event.y_root-drag['offset_y'])
        x=drag['window_x']+event.x_root-drag['x'];y=drag['window_y']+event.y_root-drag['y']
        # Reposition only our window; never enter a native caption/system-menu loop.
        try:
            user,hwnd=self.hwnd()
            user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
            user.SetWindowPos(hwnd,None,x,y,0,0,0x15)
        except (OSError,AttributeError,tk.TclError):pass
    def release(self,event):
        action=self.pressed;self.pressed=None;self.drag=None
        if action is None or self.hit(event.x,event.y)!=action:return
        if action=='close':getattr(self.root,'request_close',self.root.destroy)()
        elif action=='menu':self.root.toggle_sidebar()
        elif action=='minimize':self.minimize()
        elif action=='maximize':self.maximize()
    def double(self,event):
        self.pressed=None;self.drag=None
        if not self.hit(event.x,event.y):self.maximize()
    def leave_fullscreen(self,restore=True):
        if not self.fullscreen:return
        self.fullscreen=False;self.root.attributes('-fullscreen',False)
        if restore and self.saved:
            state,geometry=self.saved
            if state=='zoomed':self.root.state('zoomed')
            else:self.root.state('normal');self.root.geometry(geometry)
        self.transition+=1;token=self.transition
        saved=self.saved
        def finish():
            if self.closed or self.fullscreen or self.transition!=token:return
            self.apply_native()
            if restore and saved and self.root.state()!='iconic':
                state,geometry=saved
                if state=='zoomed':self.root.state('zoomed')
                else:self.root.state('normal');self.set_client_geometry(geometry)
        self.root.after(40,finish);self.refresh()
    def toggle_fullscreen(self):
        if self.fullscreen:self.leave_fullscreen()
        else:
            self.transition+=1
            self.saved=(self.root.state(),self.root.geometry());self.fullscreen=True;self.root.attributes('-fullscreen',True);self.refresh()
        return 'break'
    def escape(self):
        if self.fullscreen:self.leave_fullscreen();return 'break'
    def maximize(self):
        if not self.fullscreen and self.root.state()=='normal':self.windowed_geometry=self.root.geometry()
        self.leave_fullscreen(restore=False);self.transition+=1
        self.root.state('normal' if self.root.state()=='zoomed' else 'zoomed');self.root.after_idle(self.apply_native);self.refresh()
    def minimize(self):
        self.leave_fullscreen(restore=False);self.transition+=1;self.root.iconify()
