"""Rounded local application and Windows-tool launcher; runs only on an explicit button click."""
import ctypes,os,subprocess
from pathlib import Path
import tkinter as tk
from tkinter import filedialog,messagebox

def split_command(text):
    from ctypes import wintypes as w
    count=ctypes.c_int();api=ctypes.windll.shell32.CommandLineToArgvW
    api.argtypes=[w.LPCWSTR,ctypes.POINTER(ctypes.c_int)];api.restype=ctypes.POINTER(w.LPWSTR)
    pointer=api(text,ctypes.byref(count))
    if not pointer:raise OSError('Could not read this command')
    try:return [pointer[i] for i in range(count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes=[ctypes.c_void_p];ctypes.windll.kernel32.LocalFree(pointer)

class RunPage:
    def __init__(self,hub,tab,g):
        self.hub,self.g=hub,g;b=hub.page(tab,'Run','Open an app, a folder, or a Windows utility. Nothing runs until you choose Open or Run.')
        box=hub.box(b,'What would you like to open?','Enter an executable and its arguments, or browse to an application or folder.')
        self.command=tk.StringVar();entry=g['REntry'](box,self.command);entry.pack(fill='x',padx=18,pady=12)
        row=tk.Frame(box,bg=g['PANEL']);row.pack(fill='x',padx=18,pady=(4,20))
        for title,action in [('Browse app',self.browse),('Choose folder',self.folder),('Open / Run',self.run)]:g['RButton'](row,title,action,height=38,radius=19,kind='primary' if title=='Open / Run' else 'default').pack(side='left',padx=(0,10))
        self.status=hub.label(box,'Ready.',10,g['MUTED'])
        grid=tk.Frame(b,bg=g['BG']);grid.pack(fill='x',pady=12)
        options=[('Task Manager','Processes, CPU, memory and startup apps.','taskmgr.exe'),('Resource Monitor','Detailed activity for CPU, disks and network.','resmon.exe'),('Event Viewer','Windows application and system events.','eventvwr.msc'),('Services','Review Windows service configuration.','services.msc'),('Disk Management','Review disks, partitions and volumes.','diskmgmt.msc'),('System Information','Hardware and Windows specifications.','msinfo32.exe'),('Notepad','A clean page for quick notes.','notepad.exe'),('Calculator','Calculations and conversions.','calc.exe'),('Windows Run','Open the standard Windows Run dialog.','RUN_DIALOG')]
        for index,(title,desc,target) in enumerate(options):
            grid.columnconfigure(index%2,weight=1,uniform='run')
            card=g['Card'](grid,radius=24);card.grid(row=index//2,column=index%2,sticky='nsew',padx=(0,12),pady=7)
            hub.label(card.body,title,16);label=hub.label(card.body,desc,10,g['MUTED']);card.wrap(label)
            g['RButton'](card.body,'Open',lambda value=target:self.launch(value),height=36,radius=18).pack(anchor='w',padx=18,pady=(6,18))
    def browse(self):
        value=filedialog.askopenfilename(filetypes=[('Windows applications','*.exe *.msc'),('All files','*.*')])
        if value:self.command.set(subprocess.list2cmdline([value]))
    def folder(self):
        value=filedialog.askdirectory()
        if value:self.command.set(subprocess.list2cmdline([value]))
    def launch(self,target):
        try:
            if target=='RUN_DIALOG':
                import comtypes.client
                comtypes.client.CreateObject('Shell.Application',dynamic=True).FileRun()
            else:os.startfile(target)
            self.status.config(text='Opened '+target)
        except OSError as exc:messagebox.showerror('Run',str(exc))
    def run(self):
        text=self.command.get().strip()
        if not text:return
        try:
            args=split_command(text)
            if len(args)==1 and (Path(os.path.expandvars(args[0])).exists() or args[0].endswith('.msc')):os.startfile(os.path.expandvars(args[0]))
            else:subprocess.Popen(args,shell=False)
            self.status.config(text='Opened: '+args[0])
        except (OSError,ValueError) as exc:messagebox.showerror('Run',str(exc))
