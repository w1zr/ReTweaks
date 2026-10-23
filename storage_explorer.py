"""Read-only drive overview and responsive directory browser."""
import ctypes
import datetime
import os
from pathlib import Path
import queue
import shutil
import string
import subprocess
import threading
import tkinter as tk
from tkinter import ttk
from file_icons import FileIcons


def list_drives():
    roots=[]
    if os.name=='nt':
        mask=ctypes.windll.kernel32.GetLogicalDrives()
        roots=[letter+':\\' for i,letter in enumerate(string.ascii_uppercase) if mask&(1<<i)]
    else:roots=['/']
    result=[]
    for root in roots:
        try:
            total,used,free=shutil.disk_usage(root)
            system='';label=''
            if os.name=='nt':
                name=ctypes.create_unicode_buffer(261);fs=ctypes.create_unicode_buffer(261)
                if ctypes.windll.kernel32.GetVolumeInformationW(ctypes.c_wchar_p(root),name,261,None,None,None,fs,261):
                    label=name.value;system=fs.value
            result.append(dict(path=root,label=label,system=system or '—',total=total,used=used,free=free))
        except OSError:continue
    return result


def scan_directory(path,cancel=None):
    path=Path(path).expanduser().resolve(strict=True)
    rows=[];skipped=0;limited=False
    with os.scandir(path) as entries:
        for entry in entries:
            if cancel and cancel.is_set():return None
            if len(rows)>=50000:limited=True;break
            try:
                folder=entry.is_dir(follow_symlinks=True)
                stat=entry.stat(follow_symlinks=False)
                rows.append(dict(name=entry.name,path=entry.path,folder=folder,size=None if folder else stat.st_size,
                    kind=('Folder link' if entry.is_symlink() else 'Folder') if folder else (Path(entry.name).suffix.upper().lstrip('.')+' file' if Path(entry.name).suffix else 'File'),
                    modified=stat.st_mtime))
            except OSError:skipped+=1
    return dict(path=str(path),rows=rows,skipped=skipped,limited=limited)


def size_text(value):
    if value is None:return '—'
    value=float(value)
    for unit in ('B','KB','MB','GB','TB'):
        if value<1024 or unit=='TB':return f'{value:,.1f} {unit}'
        value/=1024


class StorageExplorer:
    def __init__(self,hub,tab,g):
        self.hub=hub;self.tab=tab;self.g=g;self.closed=False;self.generation=0
        self.events=queue.Queue();self.cancel=threading.Event();self.history=[];self.current=None
        self.rows=[];self.shown={};self.drive_rows={};self.order=('name',False);self.paint_job=None
        self.path=tk.StringVar(value=str(Path.home()));self.query=tk.StringVar()
        g['page_header'](tab,'RETWEAKS','Storage Explorer','Explore drives and folders, compare space usage, and find your files.')
        body=tk.Frame(tab,bg=g['BG']);body.pack(fill='both',expand=True,padx=14,pady=(0,12))
        self.style=ttk.Style(hub)
        self.drives=self.table(body,('drive','system','total','used','free','usage'),
            ('Device / Drive','File system','Capacity','Used space','Free space','Utilization'),height=4)
        self.drives.bind('<Double-1>',self.open_drive)
        bar=tk.Frame(body,bg=g['BG']);bar.pack(fill='x',pady=10)
        for title,fn in (('Back',self.back),('Up',self.up),('Home',lambda:self.navigate(Path.home()))):
            g['RButton'](bar,title,fn).pack(side='left',padx=(0,6))
        entry=g['REntry'](bar,self.path);entry.pack(side='left',fill='x',expand=True,padx=6)
        entry.bind('<Return>',lambda e:self.navigate(self.path.get()))
        # REntry contains the editable Tk entry.
        for child in entry.winfo_children():child.bind('<Return>',lambda e:self.navigate(self.path.get()))
        g['RButton'](bar,'Go',lambda:self.navigate(self.path.get()),kind='primary').pack(side='left',padx=(0,6))
        g['RButton'](bar,'Refresh',self.refresh).pack(side='left')
        actions=tk.Frame(body,bg=g['BG']);actions.pack(fill='x',pady=(0,8))
        g['RButton'](actions,'Show in File Explorer',self.show_in_explorer).pack(side='left',padx=(0,8))
        g['RButton'](actions,'Copy path',self.copy_path).pack(side='left')
        tk.Label(actions,text='Filter:',bg=g['BG'],fg=g['MUTED']).pack(side='left',padx=(24,8))
        g['REntry'](actions,self.query).pack(side='left',fill='x',expand=True)
        self.files=self.table(body,('name','size','kind','modified','path'),
            ('Name','Size','Type','Modified','Path'),height=8,expand=True)
        self.files.column('name',width=260);self.files.column('path',width=350)
        self.files.column('size',width=100,anchor='e');self.files.column('modified',width=150)
        self.icons=FileIcons(hub)
        self.files.configure(show='tree headings',displaycolumns=('size','kind','modified','path'))
        self.files.heading('#0',text='Name',command=lambda:self.sort('name'))
        self.files.column('#0',width=260,minwidth=150)
        for column in ('name','size','kind','modified','path'):
            self.files.heading(column,command=lambda c=column:self.sort(c))
        self.files.bind('<Double-1>',self.open_folder)
        self.files.bind('<Return>',self.open_folder)
        self.files.bind('<Alt-Up>',lambda e:self.up());self.files.bind('<Alt-Left>',lambda e:self.back())
        self.status=tk.Label(body,text='Loading drives…',bg=g['BG'],fg=g['MUTED'],anchor='w',justify='left')
        self.status.pack(fill='x',pady=8)
        tools=tk.Frame(body,bg=g['BG']);tools.pack(fill='x')
        for title,target in (('Windows storage settings','ms-settings:storagesense'),('Disk Cleanup','cleanmgr.exe'),('Optimize drives','dfrgui.exe')):
            g['RButton'](tools,title,lambda t=target:hub.launch(t)).pack(side='left',padx=(0,8))
        g['RButton'](tools,'Scan system drive',lambda:hub.task('Disk scan','chkdsk $env:SystemDrive')).pack(side='left')
        # Reserve the footer before letting the file table consume spare height.
        tools.pack_configure(side='bottom',before=self.files.master)
        self.status.pack_configure(side='bottom',before=self.files.master)
        self.query.trace_add('write',lambda *args:self.paint())
        hub.bind('<Destroy>',self.destroy,add='+');self.job=hub.after(100,self.poll)
        self.refresh_drives();self.navigate(Path.home())

    def table(self,parent,columns,headings,height,expand=False):
        frame=tk.Frame(parent,bg=self.g['BG']);frame.pack(fill='both' if expand else 'x',expand=expand)
        tree=ttk.Treeview(frame,columns=columns,show='headings',height=height,selectmode='browse',style='Storage.Treeview')
        vs=ttk.Scrollbar(frame,orient='vertical',command=tree.yview,style='Storage.Vertical.TScrollbar')
        hs=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview,style='Storage.Horizontal.TScrollbar')
        tree.configure(yscrollcommand=vs.set,xscrollcommand=hs.set)
        frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
        tree.grid(row=0,column=0,sticky='nsew');vs.grid(row=0,column=1,sticky='ns');hs.grid(row=1,column=0,sticky='ew')
        for col,title in zip(columns,headings):tree.heading(col,text=title);tree.column(col,width=140,minwidth=90)
        return tree

    def theme(self):
        g=self.g
        colors=tuple(g[k] for k in ('PANEL','PANEL2','FG','ACC'))
        if colors==getattr(self,'_theme_colors',None):return
        self._theme_colors=colors
        self.style.configure('Storage.Treeview',background=g['PANEL'],fieldbackground=g['PANEL'],foreground=g['FG'],rowheight=30,borderwidth=0,bordercolor=g['LINE'],lightcolor=g['PANEL'],darkcolor=g['PANEL'],font=(g['UI'],10))
        self.style.configure('Storage.Treeview.Heading',background=g['PANEL2'],foreground=g['FG'],font=(g['UI'],10,'bold'),padding=(8,10),relief='flat')
        self.style.map('Storage.Treeview',background=[('selected',g['PANEL2'])],foreground=[('selected',g['FG'])])
        for orientation in ('Vertical','Horizontal'):
            name=f'Storage.{orientation}.TScrollbar'
            self.style.configure(name,background=g['PANEL2'],troughcolor=g['PANEL'],arrowcolor=g['MUTED'],bordercolor=g['PANEL'],lightcolor=g['PANEL2'],darkcolor=g['PANEL2'])
            self.style.map(name,background=[('active',g['LINE'])])
        self.files.tag_configure('folder',foreground=g['ACC'])

    def refresh_drives(self):
        def worker():
            try:self.events.put(('drives',list_drives()))
            except Exception as exc:self.events.put(('drive_error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def navigate(self,path,record=True):
        text=os.path.expandvars(str(path).strip().strip('"'))
        if not text:return
        if not Path(text).is_absolute():text=str(Path(self.current or Path.home())/text)
        self.generation+=1;generation=self.generation
        self.cancel.set();self.cancel=threading.Event();cancel=self.cancel
        self.status.configure(text='Reading folder…')
        def worker():
            try:self.events.put(('folder',generation,scan_directory(text,cancel),record))
            except Exception as exc:self.events.put(('error',generation,str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        self.job=None
        if self.closed:return
        self.theme()
        try:
            while True:
                event=self.events.get_nowait()
                if event[0]=='drives':
                    self.drives.delete(*self.drives.get_children());self.drive_rows={}
                    for i,drive in enumerate(event[1]):
                        key=str(i);self.drive_rows[key]=drive
                        percent=round(100*drive['used']/drive['total']) if drive['total'] else 0
                        self.drives.insert('', 'end',iid=key,values=(drive['path']+('  '+drive['label'] if drive['label'] else ''),drive['system'],size_text(drive['total']),size_text(drive['used']),size_text(drive['free']),f'{percent}%'))
                elif event[0]=='folder' and event[1]==self.generation and event[2] is not None:
                    data=event[2]
                    if event[3] and self.current and self.current!=data['path']:self.history.append(self.current)
                    self.current=data['path'];self.path.set(self.current);self.rows=data['rows']
                    self.extra=(' • Some items were inaccessible' if data['skipped'] else '')+(' • Showing first 50,000 items' if data['limited'] else '')
                    self.paint()
                elif event[0]=='error' and event[1]==self.generation:
                    self.path.set(self.current or str(Path.home()));self.status.configure(text='Cannot open this folder: '+event[2])
                elif event[0]=='drive_error':self.status.configure(text='Cannot read drives: '+event[1])
        except queue.Empty:pass
        self.job=self.hub.after(120,self.poll)

    def sort(self,column):
        self.order=(column,not self.order[1] if self.order[0]==column else False);self.paint()

    def paint(self):
        if self.closed:return
        if self.paint_job:self.hub.after_cancel(self.paint_job);self.paint_job=None
        selected=self.selected();selected_path=selected['path'] if selected else None
        self.files.delete(*self.files.get_children());self.shown={}
        query=self.query.get().casefold();column,reverse=self.order
        rows=[r for r in self.rows if query in r['name'].casefold()]
        def key(row):
            value=row[column]
            return value.casefold() if isinstance(value,str) else (-1 if value is None else value)
        rows.sort(key=key,reverse=reverse);rows.sort(key=lambda r:not r['folder'])
        self.status.configure(text=f'{len(rows):,} shown / {len(self.rows):,} items'+getattr(self,'extra','')+' • Double-click a folder to browse')
        def batch(start=0):
            self.paint_job=None
            if self.closed:return
            for index,row in enumerate(rows[start:start+250],start):
                key=str(index);self.shown[key]=row
                try:modified=datetime.datetime.fromtimestamp(row['modified']).strftime('%Y-%m-%d %H:%M')
                except (ValueError,OSError):modified='—'
                self.files.insert('','end',iid=key,text=row['name'],image=self.icons.get(row['path'],row['folder']),values=(row['name'],size_text(row['size']),row['kind'],modified,row['path']),tags=('folder',) if row['folder'] else ())
                if row['path']==selected_path:self.files.selection_set(key)
            if start+250<len(rows):self.paint_job=self.hub.after(1,lambda:batch(start+250))
        batch()

    def selected(self):
        selection=self.files.selection()
        return self.shown.get(selection[0]) if selection else None

    def open_folder(self,event=None):
        item=self.selected()
        if item and item['folder']:self.navigate(item['path'])

    def open_drive(self,event=None):
        selection=self.drives.selection()
        if selection:self.navigate(self.drive_rows[selection[0]]['path'])

    def back(self):
        if self.history:self.navigate(self.history.pop(),record=False)

    def up(self):
        if self.current:self.navigate(Path(self.current).parent)

    def refresh(self):
        self.refresh_drives();self.navigate(self.current or Path.home(),record=False)

    def show_in_explorer(self):
        selected=self.selected()
        try:
            if selected:subprocess.Popen(['explorer.exe','/select,'+selected['path']])
            elif self.current:os.startfile(self.current)
        except OSError as exc:self.status.configure(text=f'Cannot open File Explorer: {exc}')

    def copy_path(self):
        selected=self.selected();text=selected['path'] if selected else self.current
        if text:self.hub.clipboard_clear();self.hub.clipboard_append(text)

    def destroy(self,event):
        if event.widget is not self.hub:return
        self.closed=True;self.cancel.set()
        for job in (self.job,self.paint_job):
            if job:self.hub.after_cancel(job)
        self.job=self.paint_job=None
