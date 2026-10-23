"""RETWEAKS chip logo for the window, sidebar and startup screen (images from tools/make_branding.py)."""
import sys
from pathlib import Path
import tkinter as tk
ASSETS=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'assets'
APP_ID='retweaks.pcoptimizer.suite.v1'   # same taskbar ID as the original RETWEAKS app
def logo(master,size=48,frame=None):
    """The chip at one of 16/32/40/48/96/256 px, or startup frame 0..20 of the chip scan."""
    name=f'chip-{size}.png' if frame is None else f'chip-scan-{frame}.png'
    return tk.PhotoImage(master=master,file=str(ASSETS/name))
feather=logo   # old name used by older code and checks
def window_icon(root):
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        try:root.iconbitmap(default=str(ASSETS/'taskbar.ico'))
        except tk.TclError:pass
    # black-tile icons (create_logo.py) so the chip is visible on a light taskbar; fall back to the chip
    try:root._brand_icons=[tk.PhotoImage(master=root,file=str(ASSETS/f'winicon-{n}.png')) for n in (16,32,48,256)]
    except tk.TclError:root._brand_icons=[logo(root,n) for n in (16,32,48,256)]
    root.iconphoto(True,*root._brand_icons)
