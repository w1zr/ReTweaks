"""Local auto-clicker: start/stop hotkey plus an emergency-stop hotkey (Esc always stops too), no input
recording. RETWEAKS additions (combined app): clicks-per-second mode, random interval range, start delay,
run-time limit and session stats."""
from contextlib import contextmanager
import ctypes as c
from ctypes import wintypes as w
import json
import queue
import random
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

ULONG_PTR=w.WPARAM
class POINT(c.Structure): _fields_=[('x',w.LONG),('y',w.LONG)]
class MOUSE(c.Structure): _fields_=[('dx',w.LONG),('dy',w.LONG),('data',w.DWORD),('flags',w.DWORD),('time',w.DWORD),('extra',ULONG_PTR)]
class UNION(c.Union): _fields_=[('mouse',MOUSE)]
class INPUT(c.Structure): _fields_=[('type',w.DWORD),('u',UNION)]
user=c.WinDLL('user32',use_last_error=True)
kernel=c.WinDLL('kernel32',use_last_error=True)
user.SendInput.argtypes=[w.UINT,c.POINTER(INPUT),c.c_int];user.SendInput.restype=w.UINT
user.PostThreadMessageW.argtypes=[w.DWORD,w.UINT,w.WPARAM,w.LPARAM]

@contextmanager
def physical_pixels():
    previous=None
    try:
        user.SetThreadDpiAwarenessContext.argtypes=[c.c_void_p]
        user.SetThreadDpiAwarenessContext.restype=c.c_void_p
        previous=user.SetThreadDpiAwarenessContext(c.c_void_p(-4))
    except AttributeError:pass
    try:yield
    finally:
        if previous:user.SetThreadDpiAwarenessContext(previous)

BUTTONS={'left':(2,4),'right':(8,16),'middle':(32,64)}
KEYS={f'F{i}':111+i for i in range(1,13)}
# Extra hotkey choices from RETWEAKS (Windows virtual-key codes).
KEYS.update({'Pause':0x13,'Scroll Lock':0x91,'Insert':0x2D,'Home':0x24,'End':0x23,'Page Up':0x21,'Page Down':0x22})
SPEED_MODES=('Interval (ms)','Clicks per second')
# New keys have defaults, so configurations saved by older versions still load unchanged.
DEFAULT={'interval_ms':100,'button':'left','double':False,'click_count':0,'fixed':False,'x':0,'y':0,'click_key':'F6',
         'speed_mode':'Interval (ms)','cps':10.0,'random':False,'random_min_ms':80,'random_max_ms':120,
         'start_delay_s':0.0,'run_seconds':0,'stop_key':'F8'}
INT_KEYS=('interval_ms','click_count','x','y','random_min_ms','random_max_ms','run_seconds')
FLOAT_KEYS=('cps','start_delay_s')
CPS_MIN,CPS_MAX=0.1,100.0        # 100 clicks per second = the 10 ms minimum interval
DELAY_MAX_S=10.0

def config_valid(data):
    if not isinstance(data,dict):raise ValueError('Invalid configuration.')
    result={**DEFAULT,**{k:v for k,v in data.items() if k in DEFAULT}}
    for key,low,high in [('interval_ms',10,3600000),('click_count',0,10000000),('x',-100000,100000),('y',-100000,100000),
                         ('random_min_ms',10,3600000),('random_max_ms',10,3600000),('run_seconds',0,86400)]:
        value=result[key]
        if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:raise ValueError(f'Invalid {key}.')
    for key,low,high in [('cps',CPS_MIN,CPS_MAX),('start_delay_s',0.0,DELAY_MAX_S)]:
        value=result[key]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or value!=value or not low<=value<=high:
            raise ValueError(f'Invalid {key}: use {low:g} to {high:g}.')
        result[key]=float(value)
    if result['random_min_ms']>result['random_max_ms']:raise ValueError('The random minimum must not be above the random maximum.')
    if result['button'] not in BUTTONS or any(type(result[k]) is not bool for k in ('double','fixed','random')):raise ValueError('Invalid click options.')
    if result['speed_mode'] not in SPEED_MODES:raise ValueError('Invalid speed mode.')
    if result['click_key'] not in KEYS or result['stop_key'] not in KEYS:raise ValueError('Choose a hotkey from the list.')
    if result['click_key']==result['stop_key']:raise ValueError('The start/stop hotkey and the emergency stop hotkey must be different keys.')
    return result

def next_interval_s(settings,rng=random):
    """Seconds to wait before the next click cycle."""
    if settings['random']:return rng.uniform(settings['random_min_ms'],settings['random_max_ms'])/1000
    if settings['speed_mode']=='Clicks per second':return 1/settings['cps']
    return settings['interval_ms']/1000

class Native:
    def cursor(self):
        with physical_pixels():
            p=POINT();user.GetCursorPos(c.byref(p));return [p.x,p.y]
    def down(self,vk):return bool(user.GetAsyncKeyState(vk)&0x8000)
    def emit(self,kind,v):
        if kind=='move':
            # Virtual desktop mapping supports monitors with negative coordinates.
            with physical_pixels():x,y,width,height=[user.GetSystemMetrics(i) for i in (76,77,78,79)]
            dx=round((v[0]-x)*65535/max(1,width-1));dy=round((v[1]-y)*65535/max(1,height-1))
            item=INPUT(type=0,u=UNION(mouse=MOUSE(dx,dy,0,0xC001,0,0)))
        elif kind=='button':
            flags=BUTTONS[('left','right','middle')[v[0]]][0 if v[1] else 1]
            item=INPUT(type=0,u=UNION(mouse=MOUSE(0,0,0,flags,0,0)))
        else:raise ValueError('Unsupported click input.')
        if user.SendInput(1,c.byref(item),c.sizeof(INPUT))!=1:raise OSError('Windows blocked automated clicking. Use a target at the same permission level as RETWEAKS.')

class Engine:
    def __init__(self,native=None):
        self.native=native or Native();self.mode='idle';self.status='Ready';self.stop_event=threading.Event();self.thread=None
        self.stats={'cycles':0,'clicks':0,'started':None,'elapsed':0.0,'reason':None}
    def stop(self):self.stop_event.set()
    def start(self,mode,settings):
        if mode!='clicking':raise ValueError('Only auto clicking is supported.')
        if self.mode!='idle':raise ValueError('Stop the clicker first.')
        settings=config_valid(settings);self.mode='clicking';self.status='Clicking';self.stop_event=threading.Event()
        task_stop=self.stop_event
        self.thread=threading.Thread(target=self._run,args=(settings,task_stop),daemon=True);self.thread.start()
        stop_vk=KEYS[settings['stop_key']]
        def emergency():
            # Esc and the emergency-stop key are read directly, so they work even if a hotkey
            # couldn't be registered or another window has focus.
            while self.stop_event is task_stop and self.mode!='idle' and not task_stop.wait(.02):
                if self.native.down(27) or self.native.down(stop_vk):
                    self.stats['reason']='emergency';task_stop.set();return
        threading.Thread(target=emergency,daemon=True).start()
    def _run(self,settings,stop):
        held=None
        def emit(kind,values):
            nonlocal held
            self.native.emit(kind,values)
            if kind=='button':held=values[0] if values[1] else None
        self.stats={'cycles':0,'clicks':0,'started':None,'elapsed':0.0,'reason':None}
        try:
            count=0;which=('left','right','middle').index(settings['button'])
            if settings['start_delay_s']>0:
                self.status=f"Starting in {settings['start_delay_s']:g} s"
                if stop.wait(settings['start_delay_s']):
                    self.status='Stopped';return
            started=time.perf_counter();self.stats['started']=started
            while not stop.is_set():
                if settings['fixed']:emit('move',[settings['x'],settings['y']])
                for i in range(2 if settings['double'] else 1):
                    if stop.is_set():break
                    emit('button',[which,1]);emit('button',[which,0]);self.stats['clicks']+=1
                    if settings['double'] and i==0 and stop.wait(.04):break
                count+=1;self.stats['cycles']=count;self.stats['elapsed']=time.perf_counter()-started
                self.status=f'Clicking - {count} cycles'
                if settings['click_count'] and count>=settings['click_count']:self.stats['reason']='count';break
                if settings['run_seconds'] and self.stats['elapsed']>=settings['run_seconds']:self.stats['reason']='time';break
                wait=next_interval_s(settings)
                if settings['run_seconds']:wait=min(wait,max(0.0,settings['run_seconds']-self.stats['elapsed']))
                if stop.wait(wait):break
                self.stats['elapsed']=time.perf_counter()-started
                if settings['run_seconds'] and self.stats['elapsed']>=settings['run_seconds']:self.stats['reason']='time';break
            if self.stats['started']:self.stats['elapsed']=time.perf_counter()-self.stats['started']
            if stop.is_set():
                self.stats['reason']=self.stats['reason'] or 'user'
                self.status='Emergency stop' if self.stats['reason']=='emergency' else 'Stopped'
            else:self.status='Finished'
        except Exception as exc:self.status=str(exc);self.stats['reason']='error'
        finally:
            if held is not None:
                try:self.native.emit('button',[held,0])
                except OSError:pass
            self.mode='idle'

class Hotkeys:
    """Dedicated Windows message loop; registered function keys are consumed by Windows."""
    def __init__(self,events):
        self.events=events;self.commands=queue.Queue();self.thread_id=0;self.closed=False
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def update(self,settings):
        self.commands.put(dict(settings))
        if self.thread_id:user.PostThreadMessageW(self.thread_id,0x8001,0,0)
    def close(self):
        self.closed=True
        if self.thread_id:user.PostThreadMessageW(self.thread_id,0x12,0,0)
    def run(self):
        message=w.MSG();user.PeekMessageW(c.byref(message),None,0,0,0)
        self.thread_id=kernel.GetCurrentThreadId();active={}
        def unregister():
            user.UnregisterHotKey(None,1);user.UnregisterHotKey(None,2)
        def register(settings):
            if not user.RegisterHotKey(None,1,0x4000,KEYS[settings['click_key']]):return settings['click_key']
            stop=settings.get('stop_key')
            if stop and not user.RegisterHotKey(None,2,0x4000,KEYS[stop]):return stop
            return None
        try:
            while not self.closed:
                while not self.commands.empty():
                    requested=self.commands.get();unregister();failed=register(requested)
                    if failed:
                        unregister()
                        if active:register(active)
                        self.events.put(('hotkey_error',f'{failed} is already in use. Choose another key and apply hotkeys.'))
                    else:active=requested;self.events.put(('hotkeys',requested))
                if self.closed or user.GetMessageW(c.byref(message),None,0,0)<=0:break
                if message.message==0x312 and int(message.wParam)==1:self.events.put(('toggle','clicking'))
                elif message.message==0x312 and int(message.wParam)==2:self.events.put(('emergency',None))
        finally:unregister();self.thread_id=0

class AutomationPage:
    def __init__(self,hub,tab,g,root_path):
        self.hub=hub;self.g=g;self.engine=Engine();self.pending=None;self.closed=False;self.root_path=root_path
        body=hub.page(tab,'Auto clicker','Set your click speed, button, position and repeat count. Your hotkey starts or stops clicking; the emergency-stop key and Esc always stop.')
        self.vars={k:tk.BooleanVar(value=v) if type(v) is bool else tk.StringVar(value=f'{v:g}' if isinstance(v,float) else str(v)) for k,v in DEFAULT.items()}
        self.status=hub.label(body,'Ready - F6: start / stop | F8 or Esc: emergency stop',11)
        self.stats_label=hub.label(body,'Session: no clicks yet',10,g['MUTED'])
        hub.label(body,"You're responsible for following the rules of each game or service. Many online games and "
                  "anti-cheat systems don't allow automated clicking. RETWEAKS has no stealth or anti-cheat bypass features.",9,g['MUTED'])
        self.controls=hub.box(body,'Auto clicker','Choose a speed, button and repeat limit. Zero cycles and zero seconds mean repeat until stopped.')
        self.field(self.controls,'Speed','speed_mode',list(SPEED_MODES))
        for label,key in [('Interval (ms, 10 to 3,600,000)','interval_ms'),(f'Clicks per second ({CPS_MIN:g} to {CPS_MAX:g})','cps'),
                          ('Click cycles (0 = unlimited)','click_count'),('Stop after seconds (0 = no limit)','run_seconds'),
                          (f'Start delay (seconds, 0 to {DELAY_MAX_S:g})','start_delay_s')]:self.field(self.controls,label,key)
        self.check(self.controls,'Random interval between the minimum and maximum below (overrides the speed)','random')
        rnd=tk.Frame(self.controls,bg=g['PANEL']);rnd.pack(fill='x',padx=16,pady=4)
        self.field(rnd,'Random minimum (ms)','random_min_ms');self.field(rnd,'Random maximum (ms)','random_max_ms')
        self.field(self.controls,'Mouse button','button',list(BUTTONS))
        self.check(self.controls,'Double click','double');self.check(self.controls,'Click at fixed coordinates','fixed')
        row=tk.Frame(self.controls,bg=g['PANEL']);row.pack(fill='x',padx=16,pady=4)
        self.field(row,'X','x');self.field(row,'Y','y')
        g['RButton'](self.controls,'Pick cursor position in 3 seconds',self.pick).pack(anchor='w',padx=16,pady=6)
        self.buttons(self.controls,[('Start / stop clicker',lambda:self.toggle('clicking')),('Stop clicking',self.stop)])
        settings=hub.box(body,'Hotkeys & configuration','The hotkeys work while RETWEAKS is open, including when another app has focus. The emergency-stop key and Esc always stop clicking. Save and load your clicker settings.')
        self.field(settings,'Start / stop hotkey','click_key',list(KEYS))
        self.field(settings,'Emergency stop hotkey','stop_key',list(KEYS))
        self.active_keys={'click_key':DEFAULT['click_key'],'stop_key':DEFAULT['stop_key']}
        self.hotkey_events=queue.Queue();self.hotkeys=Hotkeys(self.hotkey_events);self.hotkeys.update(self.active_keys)
        self.buttons(settings,[('Apply hotkeys',self.apply_keys),('Save configuration',self.save),('Load configuration',self.load)])
        hub.bind('<Destroy>',self.destroy,add='+');self.job=hub.after(25,self.poll)
    def field(self,parent,label,key,choices=None):
        row=tk.Frame(parent,bg=self.g['PANEL']);row.pack(fill='x',padx=16,pady=4)
        tk.Label(row,text=label,bg=self.g['PANEL'],fg=self.g['FG'],anchor='w',width=32).pack(side='left')
        if choices:
            entry=self.g['RSelect'](row,choices,width=220,command=self.vars[key].set)
            entry.set(self.vars[key].get())
            self.vars[key].trace_add('write',lambda *_,e=entry,k=key:e.set(self.vars[k].get()))
        else:entry=self.g['REntry'](row,self.vars[key],width_px=220)
        entry.pack(side='left')
    def check(self,parent,label,key):
        self.g['RCheck'](parent,label,self.vars[key]).pack(anchor='w',padx=16,pady=3)
    def buttons(self,parent,items):
        row=tk.Frame(parent,bg=self.g['PANEL']);row.pack(fill='x',padx=16,pady=8)
        for text,command in items:self.g['RButton'](row,text,command).pack(side='left',padx=(0,8))
    def settings(self):
        values={k:v.get() for k,v in self.vars.items()}
        for key in INT_KEYS:
            try:values[key]=int(str(values[key]).strip())
            except ValueError:raise ValueError(f'{key.replace("_"," ")} must be a whole number.')
        for key in FLOAT_KEYS:
            try:values[key]=float(str(values[key]).strip())
            except ValueError:raise ValueError(f'{key.replace("_"," ")} must be a number.')
        return config_valid(values)
    def apply_keys(self):
        if self.pending or self.engine.mode!='idle':
            messagebox.showinfo('Hotkeys','Stop clicking before changing the hotkey.',parent=self.hub);return
        try:
            config=self.settings();self.hotkeys.update({k:config[k] for k in self.active_keys});self.engine.status='Applying hotkey...'
        except ValueError as exc:messagebox.showerror('Hotkeys',str(exc),parent=self.hub)
    def stop(self):
        if self.pending:self.hub.after_cancel(self.pending);self.pending=None
        self.engine.stop();self.engine.status='Stopped'
    def toggle(self,mode='clicking'):
        if mode!='clicking':return
        if self.pending or self.engine.mode!='idle':self.stop();return
        try:
            settings=self.settings();settings.update(self.active_keys);self.engine.start('clicking',settings)
        except ValueError as exc:messagebox.showerror('Auto clicker',str(exc),parent=self.hub)
    def pick(self):
        if self.pending or self.engine.mode!='idle':return
        self.engine.status='Move the cursor to the target - capturing in 3 seconds'
        def capture():
            self.pending=None;x,y=self.engine.native.cursor();self.vars['x'].set(str(x));self.vars['y'].set(str(y));self.vars['fixed'].set(True);self.engine.status=f'Position selected: {x}, {y}'
        self.pending=self.hub.after(3000,capture)
    def save(self):
        if self.pending or self.engine.mode!='idle':messagebox.showinfo('Configuration','Stop clicking before saving.',parent=self.hub);return
        try:
            settings=self.settings();path=filedialog.asksaveasfilename(parent=self.hub,title='Save clicker configuration',defaultextension='.json',initialfile='RETWEAKS-clicker.json',filetypes=[('RETWEAKS configuration','*.json')])
            if path:
                from pathlib import Path
                Path(path).write_text(json.dumps({'version':3,'settings':settings},indent=2),encoding='utf-8');self.engine.status='Configuration saved'
        except (OSError,ValueError) as exc:messagebox.showerror('Save',str(exc),parent=self.hub)
    def load(self):
        if self.pending or self.engine.mode!='idle':messagebox.showinfo('Configuration','Stop clicking before loading.',parent=self.hub);return
        path=filedialog.askopenfilename(parent=self.hub,filetypes=[('RETWEAKS configuration','*.json')])
        if not path:return
        try:
            from pathlib import Path
            if Path(path).stat().st_size>20000000:raise ValueError('Configuration is too large.')
            data=json.loads(Path(path).read_text(encoding='utf-8'));settings=config_valid(data['settings'])
            if data.get('version') not in (1,2,3):raise ValueError('Unsupported configuration version.')
            for k,v in settings.items():self.vars[k].set(f'{v:g}' if isinstance(v,float) else v)
            self.apply_keys();self.engine.status='Clicker settings loaded'
        except (OSError,ValueError,KeyError,TypeError) as exc:messagebox.showerror('Load',str(exc),parent=self.hub)
    def poll(self):
        if self.closed:return
        escape=self.engine.native.down(27)
        if escape:self.stop()
        while not self.hotkey_events.empty():
            kind,data=self.hotkey_events.get()
            if kind=='toggle' and not escape:self.toggle(data)
            elif kind=='emergency':self.engine.stats['reason']='emergency';self.stop();self.engine.status='Emergency stop'
            elif kind=='hotkeys':self.active_keys={**self.active_keys,**data};self.engine.status='Hotkeys applied'
            else:self.engine.status=data
        self.status.config(text=f"{self.engine.status}\n{self.active_keys['click_key']}: start / stop | "
                                f"{self.active_keys.get('stop_key','F8')} or Esc: emergency stop")
        st=self.engine.stats
        if st.get('started'):
            rate=st['clicks']/st['elapsed'] if st['elapsed']>0 else 0
            reason={'user':'stopped by you','emergency':'emergency stop','count':'click count reached',
                    'time':'time limit reached','error':'stopped by an error'}.get(st.get('reason'),'running' if self.engine.mode!='idle' else '')
            self.stats_label.config(text=f"Session: {st['clicks']} clicks in {st['cycles']} cycles, {st['elapsed']:.1f} s, "
                                         f"about {rate:.1f} clicks/s" + (f" ({reason})" if reason else ''))
        self.job=self.hub.after(25,self.poll)
    def destroy(self,event):
        if event.widget is self.hub:
            self.closed=True;self.stop();self.hotkeys.close()
            if self.engine.thread:self.engine.thread.join(timeout=1)
            self.hotkeys.thread.join(timeout=1)
