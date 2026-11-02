"""Small Windows file-association icons; only extension metadata is queried."""
import ctypes as c
from ctypes import wintypes as w
import os
import tkinter as tk

class FileIcons:
    def __init__(self,master):self.master=master;self.cache={}
    def get(self,path,folder=False):
        ext=os.path.splitext(path)[1].lower()
        key='folder' if folder else ext
        if key in self.cache:return self.cache[key]
        if len(self.cache)>=128:return self.cache.get('')
        try:image=self.load('folder' if folder else 'file'+ext,folder)
        except Exception:
            image=tk.PhotoImage(master=self.master,width=16,height=16)
            image.put('#e8bd59' if folder else '#dddddf',to=(2,3,14,14))
        self.cache[key]=image;return image
    def load(self,name,folder):
        from PIL import ImageTk
        return ImageTk.PhotoImage(shell_icon(name,0x10 if folder else 0x80,0x111),master=self.master)


def exe_from_command(command):
    """The program file in a startup command line ('"C:\\a b\\x.exe" --min' -> C:\\a b\\x.exe), env vars expanded."""
    text=os.path.expandvars((command or '').strip())
    if text.startswith('"'):return text[1:].split('"',1)[0]
    low=text.lower()
    for ext in ('.exe','.lnk','.bat','.cmd','.com','.msc','.vbs','.ps1','.dll'):
        i=low.find(ext)
        if i>0:return text[:i+len(ext)]
    return text.split(' ',1)[0]


def app_icon(command):
    """16x16 RGBA PIL image of a program's own icon (no Tk; safe on a worker thread), or None.
    A missing file gets Windows' generic icon for its file type, so a row is never blank without reason."""
    path=exe_from_command(command)
    if not path:return None
    try:
        if os.path.isfile(path):return shell_icon(path,0,0x101)            # SHGFI_ICON | SHGFI_SMALLICON
        ext=os.path.splitext(path)[1] or '.exe'
        return shell_icon('file'+ext,0x80,0x111)                          # + SHGFI_USEFILEATTRIBUTES
    except Exception:
        return None


def shell_icon(name,attributes,flags):
    """Draw the icon Windows' shell gives `name` into a 16x16 RGBA PIL image."""
    from PIL import Image
    class Info(c.Structure):
        _fields_=[('icon',w.HICON),('index',c.c_int),('attributes',w.DWORD),('name',w.WCHAR*260),('type',w.WCHAR*80)]
    class Header(c.Structure):
        _fields_=[('size',w.DWORD),('width',w.LONG),('height',w.LONG),('planes',w.WORD),('bits',w.WORD),('compression',w.DWORD),('image_size',w.DWORD),('xp',w.LONG),('yp',w.LONG),('used',w.DWORD),('important',w.DWORD)]
    shell=c.windll.shell32;user=c.windll.user32;gdi=c.windll.gdi32
    shell.SHGetFileInfoW.argtypes=[w.LPCWSTR,w.DWORD,c.POINTER(Info),c.c_uint,c.c_uint];shell.SHGetFileInfoW.restype=c.c_size_t
    info=Info()
    if not shell.SHGetFileInfoW(name,attributes,c.byref(info),c.sizeof(info),flags) or not info.icon:raise OSError('No icon')
    gdi.CreateCompatibleDC.argtypes=[w.HDC];gdi.CreateCompatibleDC.restype=w.HDC
    gdi.CreateDIBSection.argtypes=[w.HDC,c.c_void_p,w.UINT,c.POINTER(c.c_void_p),w.HANDLE,w.DWORD];gdi.CreateDIBSection.restype=w.HBITMAP
    gdi.SelectObject.argtypes=[w.HDC,w.HANDLE];gdi.SelectObject.restype=w.HANDLE
    gdi.DeleteObject.argtypes=[w.HANDLE];gdi.DeleteDC.argtypes=[w.HDC]
    user.DrawIconEx.argtypes=[w.HDC,c.c_int,c.c_int,w.HICON,c.c_int,c.c_int,w.UINT,w.HBRUSH,w.UINT]
    user.DestroyIcon.argtypes=[w.HICON]
    dc=gdi.CreateCompatibleDC(None);bitmap=None;old=None
    try:
        header=Header(c.sizeof(Header),16,-16,1,32,0,0,0,0,0,0);bits=c.c_void_p()
        bitmap=gdi.CreateDIBSection(dc,c.byref(header),0,c.byref(bits),None,0)
        if not bitmap or not bits.value:raise OSError('Icon bitmap unavailable')
        old=gdi.SelectObject(dc,bitmap)
        c.memset(bits,0,16*16*4)
        if not user.DrawIconEx(dc,0,0,info.icon,16,16,0,None,3):raise OSError('Cannot draw icon')
        return Image.frombytes('RGBA',(16,16),c.string_at(bits,16*16*4),'raw','BGRA')
    finally:
        if old:gdi.SelectObject(dc,old)
        if bitmap:gdi.DeleteObject(bitmap)
        if dc:gdi.DeleteDC(dc)
        user.DestroyIcon(info.icon)
