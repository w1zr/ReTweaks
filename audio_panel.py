"""Local Windows Core Audio mixer and synchronized detachable Tk views.

RETWEAKS addition (combined app): volume lock for the default speaker and default microphone
(core/audio_lock.py; settings audio_lock_output / audio_lock_input, None = off). It is checked every
0.5 s while RETWEAKS runs, even with this page hidden, follows whichever device is the default and
never touches mute."""
import os
import tkinter as tk
from tkinter import ttk
from volume_slider import VolumeSlider


class WindowsAudio:
    def __init__(self):
        from pycaw.utils import AudioUtilities, AudioSession
        from pycaw.api.audiopolicy import IAudioSessionControl2
        from pycaw.constants import ERole
        self.api=AudioUtilities;self.session_type=AudioSession
        self.session_interface=IAudioSessionControl2;self.roles=ERole
        self.targets={}

    def snapshot(self):
        devices=[];sessions=[];targets={};errors=[]
        defaults={}
        enumerator=self.api.GetDeviceEnumerator()
        for flow in (0,1):
            for role in (1,2):
                try:defaults[flow,role]=enumerator.GetDefaultAudioEndpoint(flow,role).GetId()
                except OSError:pass
            for dev in self.api.GetAllDevices(data_flow=flow,device_state=1):
                try:
                    key=('device',dev.id);volume=dev.EndpointVolume
                    targets[key]=(volume,True)
                    devices.append(dict(key=key,id=dev.id,flow=flow,name=dev.FriendlyName or 'Audio device',
                        level=volume.GetMasterVolumeLevelScalar()*100,mute=bool(volume.GetMute()),
                        default=defaults.get((flow,1))==dev.id,calls=defaults.get((flow,2))==dev.id))
                    if flow!=0:continue
                    entries=dev.AudioSessionManager.GetSessionEnumerator()
                    for i in range(entries.GetCount()):
                        try:
                            session=self.session_type(entries.GetSession(i).QueryInterface(self.session_interface))
                            if session.State==2:continue
                            key=('session',dev.id,session.InstanceIdentifier)
                            volume=session.SimpleAudioVolume
                            process=session.Process
                            name=session.DisplayName or (process.name() if process else 'System sounds')
                            targets[key]=(volume,False)
                            sessions.append(dict(key=key,name=name,device=dev.FriendlyName or 'Output',
                                level=volume.GetMasterVolume()*100,mute=bool(volume.GetMute())))
                        except Exception:continue
                except Exception as exc:errors.append(f'{dev.FriendlyName}: {exc}')
        self.targets=targets
        return dict(devices=devices,sessions=sessions,errors=errors)

    def set_level(self,key,value):
        volume,endpoint=self.targets[key];value=max(0,min(100,float(value)))/100
        if endpoint:volume.SetMasterVolumeLevelScalar(value,None)
        else:volume.SetMasterVolume(value,None)

    def set_mute(self,key,value):
        volume,_=self.targets[key];volume.SetMute(bool(value),None)

    def set_default(self,device_id,calls=False):
        roles=[self.roles.eCommunications] if calls else [self.roles.eConsole,self.roles.eMultimedia]
        self.api.SetDefaultDevice(device_id,roles=roles)


class LockIO:
    """Reads/writes the DEFAULT speaker or microphone level for the volume lock (RETWEAKS core/audio)."""
    def __init__(self):
        from core.audio import AudioBackend
        self.backend=AudioBackend()
    def read(self,kind):
        return self.backend.master_state() if kind=='output' else self.backend.input_state()
    def write(self,kind,percent):
        if kind=='output':self.backend.set_master_volume(percent)
        else:self.backend.set_input_volume(percent)


class AudioPanel:
    def __init__(self,hub,tab,g,backend=None,lock_io=None):
        self.hub=hub;self.tab=tab;self.g=g;self.backend=backend;self.views=[]
        self.window=None;self.closed=False;self.job=None;self.state=None
        self.lock_io=lock_io;self.lock_job=None;self.volume_lock=None;self.lock_error=''
        from core import audio_lock
        self.audio_lock=audio_lock
        body=hub.page(tab,'Audio Mixer','Control app volumes, speakers and microphones. Pop the mixer out to keep it beside your other apps.')
        bar=tk.Frame(body,bg=g['BG']);bar.pack(fill='x',padx=16,pady=8)
        g['RButton'](bar,'Pop out mixer',self.pop_out,kind='primary').pack(side='left',padx=(0,10))
        g['RButton'](bar,'Windows sound settings',lambda:os.startfile('ms-settings:sound')).pack(side='left')
        self.add_view(body)
        hub.bind('<Destroy>',self.destroy,add='+')
        self.job=hub.after(400,self.tick)
        self.lock_job=hub.after(self.audio_lock.INTERVAL_MS,self.lock_tick)

    # ---- volume lock (RETWEAKS)
    def lock_value(self,kind):
        settings=getattr(self.hub,'settings',None) or {}
        return self.audio_lock.clean_lock(settings.get(self.audio_lock.KEYS[kind]))

    def set_lock(self,kind,percent):
        """percent None turns the lock off. Saved in RETWEAKS settings right away."""
        settings=getattr(self.hub,'settings',None)
        if settings is None:return
        settings[self.audio_lock.KEYS[kind]]=self.audio_lock.clean_lock(percent)
        if hasattr(self.hub,'save_settings'):self.hub.save_settings()
        what=('Lock ' if percent is not None else 'Unlock ')+('microphone' if kind=='input' else 'speaker')+' volume'
        if hasattr(self.hub,'log_action'):
            self.hub.log_action('Volume lock',what,f'{percent}%' if percent is not None else 'Off')
        for view in self.views:
            for row in view['rows'].values():
                if row.get('lock_kind')==kind:
                    row['updating']=True;row['lock'].set(percent is not None);row['updating']=False

    def lock_tick(self):
        self.lock_job=None
        if self.closed:return
        if any(self.lock_value(k) is not None for k in self.audio_lock.KEYS):
            try:
                if self.lock_io is None:self.lock_io=LockIO()
                if self.volume_lock is None:
                    self.volume_lock=self.audio_lock.VolumeLock(
                        read=lambda k:self.lock_io.read(k),write=lambda k,p:self.lock_io.write(k,p),
                        get_lock=lambda k:self.lock_value(k),log=getattr(self.hub,'log_action',None))
                self.volume_lock.tick();self.lock_error=''
            except Exception as exc:
                self.lock_error=f'Volume lock is unavailable: {exc}'
        self.lock_job=self.hub.after(self.audio_lock.INTERVAL_MS,self.lock_tick)

    def add_view(self,parent):
        g=self.g
        status=tk.Label(parent,text='Open this panel to load audio devices.',bg=g['BG'],fg=g['MUTED'],anchor='w',wraplength=650)
        status.pack(fill='x',padx=16,pady=8)
        content=tk.Frame(parent,bg=g['BG']);content.pack(fill='both',expand=True,padx=16)
        view=dict(parent=parent,status=status,content=content,signature=None,rows={},selected={})
        self.views.append(view)
        if self.state:self.render(view,self.state)

    def pop_out(self):
        if self.window and self.window.winfo_exists():self.window.deiconify();self.window.lift();return
        g=self.g;win=tk.Toplevel(self.hub);self.window=win
        win.title('RETWEAKS — Audio Mixer');win.geometry('740x760');win.minsize(540,440);win.configure(bg=g['BG'])
        from branding import window_icon
        window_icon(win)
        top=tk.Frame(win,bg=g['BG']);top.pack(fill='x',padx=20,pady=14)
        tk.Label(top,text='Audio Mixer',font=(g['UI'],20,'bold'),bg=g['BG'],fg=g['FG']).pack(side='left')
        pinned=tk.BooleanVar(win,value=False)
        g['RCheck'](top,'Always on top',pinned,command=lambda:win.attributes('-topmost',pinned.get())).pack(side='right')
        body=self.hub._scroll_area(win);self.add_view(body)
        def close():
            self.views=[v for v in self.views if v['parent'] is not body]
            win.destroy();self.window=None
        win.protocol('WM_DELETE_WINDOW',close)
        self.refresh()

    def action(self,fn):
        try:fn()
        except Exception as exc:
            for view in self._live_views():view['status'].configure(text=f'Windows could not apply this change: {exc}')
            return
        self.refresh()

    def _live_views(self):
        """Drops views whose window is gone (e.g. the pop-out destroyed without its close button),
        so one dead view can't stop the mixer from updating."""
        def alive(v):
            try:return bool(v['status'].winfo_exists())
            except tk.TclError:return False
        self.views=[v for v in self.views if alive(v)]
        if self.window is not None:
            try:
                if not self.window.winfo_exists():self.window=None
            except tk.TclError:self.window=None
        return self.views

    def refresh(self):
        self._live_views()
        try:
            if self.backend is None:self.backend=WindowsAudio()
            self.state=self.backend.snapshot()
            for view in list(self.views):self.render(view,self.state)
        except Exception as exc:
            for view in self.views:view['status'].configure(text=f'Audio devices are unavailable. Check Windows Audio and reconnect your device. {exc}')

    def tick(self):
        self.job=None
        if self.closed:return
        try:
            self._live_views()
            if self.tab.winfo_viewable() or (self.window and self.window.winfo_viewable()):self.refresh()
        except tk.TclError:
            pass
        finally:
            if not self.closed:self.job=self.hub.after(1500,self.tick)

    def render(self,view,state):
        g=self.g;items=state['devices']+state['sessions']
        if any(row['dragging'] or row.get('editing') for row in view['rows'].values()):return
        signature=tuple((item['key'],item['name'],item.get('default'),item.get('calls')) for item in items)
        if signature!=view['signature']:
            for widget in view['content'].winfo_children():widget.destroy()
            view['rows']={};view['signature']=signature
            for flow,title in ((0,'Speakers & output'),(1,'Microphones & input')):
                devices=[d for d in state['devices'] if d['flow']==flow]
                self.heading(view['content'],title)
                if devices:
                    selected=next((d for d in devices if d['id']==view['selected'].get(flow)),None)
                    if selected is None:selected=next((d for d in devices if d['default']),devices[0])
                    view['selected'][flow]=selected['id']
                    names=[f"{i+1}. {d['name']}"+(' • Default' if d['default'] else '') for i,d in enumerate(devices)]
                    picker=g['RSelect'](view['content'],names,width=520)       # base app v1.5: rounded picker
                    picker.pack(anchor='w',pady=(0,8));picker.current(devices.index(selected))
                    def choose(value,flow=flow,devices=devices,names=names):
                        if value not in names:return
                        index=names.index(value)
                        view['selected'][flow]=devices[index]['id'];view['signature']=None
                        self.render(view,self.state)
                    picker.command=choose
                    self.row(view,selected,True)
                if not devices:self.note(view['content'],'No connected devices found.')
            self.heading(view['content'],'Application volumes')
            self.note(view['content'],'Apps appear after they create an audio session. Changes apply immediately; closing the mixer keeps your Windows volume settings.')
            for item in state['sessions']:self.row(view,item,False)
            if not state['sessions']:self.note(view['content'],'Play audio in an app to show it here.')
        for item in items:
            row=view['rows'].get(item['key'])
            if row and not row['dragging']:
                row['updating']=True
                row['value'].set(round(item['level']))
                row['percent'].configure(text=f"{round(item['level'])}%")
                row['mute'].set(item['mute'])
                if row.get('lock_kind'):row['lock'].set(self.lock_value(row['lock_kind']) is not None)
                row['updating']=False
        view['status'].configure(text=self.lock_error or ('Some devices could not be read. Reconnect them or open Windows sound settings.' if state['errors'] else 'Live Windows audio • Changes apply immediately'))

    def heading(self,parent,text):
        tk.Label(parent,text=text,bg=self.g['BG'],fg=self.g['FG'],font=(self.g['UI'],15,'bold'),anchor='w').pack(fill='x',pady=(14,8))

    def note(self,parent,text):
        label=tk.Label(parent,text=text,bg=self.g['BG'],fg=self.g['MUTED'],anchor='w',justify='left',wraplength=600)
        label.pack(fill='x',pady=5)
        label.bind('<Configure>',lambda e:label.configure(wraplength=max(250,e.width-12)))

    def row(self,view,item,device):
        g=self.g;key=item['key'];card=g['Card'](view['content']);card.pack(fill='x',pady=5)
        flags=(' • Default' if item.get('default') else '')+(' • Calls' if item.get('calls') else '')
        title=tk.Label(card.body,text=item['name']+flags,bg=g['PANEL'],fg=g['FG'],font=(g['UI'],11,'bold'),anchor='w',justify='left')
        title.pack(fill='x',padx=14,pady=(10,2));card.wrap(title,28)
        if not device:
            label=tk.Label(card.body,text=item['device'],bg=g['PANEL'],fg=g['MUTED'],anchor='w');label.pack(fill='x',padx=14);card.wrap(label,28)
        controls=tk.Frame(card.body,bg=g['PANEL']);controls.pack(fill='x',padx=14,pady=8)
        row=dict(value=tk.DoubleVar(value=item['level']),mute=tk.BooleanVar(value=item['mute']),dragging=False,updating=True)
        view['rows'][key]=row
        percent=tk.Label(controls,width=5,text=f"{round(item['level'])}%",bg=g['PANEL'],fg=g['FG']);percent.pack(side='right');row['percent']=percent
        kind=('output','input')[item['flow']] if device and item.get('default') else None
        def level(value):
            percent.configure(text=f'{round(float(value))}%')
            self.action_level(key,value,view)
            # Moving a locked default device's slider in RETWEAKS moves the lock with it.
            if kind and self.lock_value(kind) is not None:self.set_lock(kind,round(float(value)))
        slider=VolumeSlider(controls,row['value'],g,level,on_drag=lambda active:row.update(dragging=active))
        row['slider']=slider
        slider.pack(side='left',fill='x',expand=True,padx=(0,14))
        g['RCheck'](controls,'Mute',row['mute'],command=lambda:self.action(lambda:self.backend.set_mute(key,row['mute'].get()))).pack(side='left')
        if kind:
            # Volume lock: holds the DEFAULT device at this %; RETWEAKS puts it back within half a second.
            row['lock_kind']=kind;row['lock']=tk.BooleanVar(value=self.lock_value(kind) is not None)
            def toggle_lock(kind=kind,row=row):
                if row['updating']:return
                self.set_lock(kind,round(row['value'].get()) if row['lock'].get() else None)
            g['RCheck'](controls,'Lock',row['lock'],command=toggle_lock).pack(side='left',padx=(10,0))
        if kind:
            note=tk.Label(card.body,text=('Lock keeps the default '+('speaker' if kind=='output' else 'microphone')+
                ' volume where you set it. If an app or Windows changes it, RETWEAKS puts it back within half a second, '
                'even with this page closed. It follows whichever device is the default and never changes mute.'),
                bg=g['PANEL'],fg=g['MUTED'],anchor='w',justify='left',font=(g['UI'],8))
            note.pack(fill='x',padx=14);card.wrap(note,28)
        if device:
            actions=tk.Frame(card.body,bg=g['PANEL']);actions.pack(fill='x',padx=14,pady=(0,10))
            g['RButton'](actions,'Use as default',lambda:self.action(lambda:self.backend.set_default(item['id']))).pack(side='left',padx=(0,8))
            g['RButton'](actions,'Use for calls',lambda:self.action(lambda:self.backend.set_default(item['id'],True))).pack(side='left')
        row['updating']=False

    def action_level(self,key,value,view):
        try:self.backend.set_level(key,value)
        except Exception as exc:view['status'].configure(text=f'Unable to change volume: {exc}')

    def destroy(self,event):
        if event.widget is not self.hub:return
        self.closed=True
        if self.job:self.hub.after_cancel(self.job);self.job=None
        if self.lock_job:self.hub.after_cancel(self.lock_job);self.lock_job=None
        self.backend=None
