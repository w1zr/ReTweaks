"""Fan monitoring/control and local OpenRGB lighting. No hardware writes on page load.

From base app v1.5 (GPL-3.0), added to RETWEAKS 2026-10-22 (owner request). Changes for RETWEAKS: the pages
find their own tab through hub.rt_tabs (keys "Fan control" / "RGB lighting") instead of the base app's fixed tab
numbers. Fan writes go through temperatures.Temperatures -> ai/sensors/SensorHost.exe (LibreHardwareMonitor),
which refuses manual duty below 30% or above the controller's limits, skips pumps, and returns every fan it
touched to automatic control on exit, on lost monitoring (45 s heartbeat lease) and at CPU/GPU >= 85 C."""

FAN_KEY, RGB_KEY = "Fan control", "RGB lighting"


def _tab(hub, key):
    return getattr(hub, "rt_tabs", {}).get(key)

import colorsys
import math
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import colorchooser
import webbrowser
import rgb_service
from rgb_sync import RainbowSync, rainbow_period

def wrap_column(frame):
    def resize(event):
        for child in frame.winfo_children():
            if isinstance(child,tk.Label):child.configure(wraplength=max(160,event.width-32))
    frame.bind('<Configure>',resize,add='+')


class CoolingSelect(tk.Frame):
    """An inline dropdown: no popup grabs, focus races, or animation interference."""
    def __init__(self,parent,values,g,command=None,width=360):
        super().__init__(parent,bg=g['PANEL'])
        self.g=g;self.values=list(values);self.value=self.values[0] if self.values else '';self.command=command;self.menu=None
        self.button=g['RButton'](self,self.value+'  ▾',self._open,width=width,height=38)
        self.button.pack(fill='x')
        def resize(event):self.button.bw=event.width;self.button._draw()
        self.button.bind('<Configure>',resize,add='+')
    def get(self):return self.value
    def set(self,value):self.value=value;self.button.label=value+'  ▾';self.button._draw()
    def _pick(self,value):
        self.set(value);self._close_popup()
        if self.command:self.command(value)
    def _close_popup(self):
        if self.menu is not None:self.menu.destroy();self.menu=None
    def _open(self):
        if self.menu is not None:self._close_popup();return
        self.menu=self.g['Card'](self,radius=18);self.menu.pack(fill='x',pady=(5,0))
        frame=tk.Frame(self.menu.body,bg=self.g['PANEL']);frame.pack(fill='both',expand=True,padx=8,pady=8)
        self.listbox=tk.Listbox(frame,height=min(5,max(1,len(self.values))),bg=self.g['PANEL'],fg=self.g['FG'],selectbackground=self.g['PANEL2'],selectforeground=self.g['ACC'],relief='flat',bd=0,highlightthickness=0,activestyle='none',font=(self.g['UI'],10),exportselection=False)
        scroll=self.g['RScrollbar'](frame,command=self.listbox.yview,bg=self.g['PANEL']);self.listbox.configure(yscrollcommand=scroll.set)
        if len(self.values)>5:scroll.pack(side='right',fill='y')
        self.listbox.pack(fill='both',expand=True)
        for value in self.values:self.listbox.insert('end',value)
        if self.value in self.values:self.listbox.selection_set(self.values.index(self.value));self.listbox.see(self.values.index(self.value))
        def pick(event=None):
            selected=self.listbox.curselection()
            if selected:self._pick(self.values[selected[0]])
            return 'break'
        self.listbox.bind('<ButtonRelease-1>',pick);self.listbox.bind('<Return>',pick);self.listbox.bind('<Escape>',lambda e:self._close_popup())
        self.listbox.bind('<MouseWheel>',lambda e:(self.listbox.yview_scroll(-3 if e.delta>0 else 3,'units'),'break')[1])
        self.listbox.focus_set()


class FanVisual(tk.Canvas):
    def __init__(self,parent,g,**kw):
        super().__init__(parent,bg=g['PANEL'],highlightthickness=0,height=230,width=240,**kw)
        self.g=g;self.angle=0;self.rpm=None;self.color='#a8cfff';self.effect='Static';self.rgb=False;self.ram=False
        self.bind('<Configure>',lambda e:self.draw())
    def draw(self):
        self.delete('all');g=self.g;self.configure(bg=g['PANEL']);x=max(240,self.winfo_width())/2;y=112;r=88
        def lighting(hue):
            base=colorsys.hsv_to_rgb(hue,.6,.95) if any(k in self.effect.lower() for k in ('rainbow','spectrum','wave','cycle')) else tuple(int(self.color[j:j+2],16)/255 for j in (1,3,5))
            brightness=.65+.35*math.sin(time.monotonic()*2) if any(k in self.effect.lower() for k in ('breath','pulse')) else 1
            return '#'+''.join(f'{round(c*brightness*255):02x}' for c in base)
        if self.ram:
            for yy in (62,140):
                left=x-99;right=x+99
                self.create_rectangle(left+8,yy+42,right-8,yy+50,fill='#302e23',outline='')
                for i in range(24):
                    xx=left+13+i*7.2
                    if i!=11:self.create_line(xx,yy+43,xx,yy+50,fill='#a28b50',width=3)
                self.create_polygon(left,yy+8,left+12,yy,right-12,yy,right,yy+8,right-6,yy+43,left+6,yy+43,fill=g['PANEL2'],outline=g['LINE'],width=2)
                for i in range(80):
                    xx=left+13+i*2.15
                    self.create_line(xx,yy+4,xx+2.4,yy+4,fill=lighting((i/80+time.monotonic()*getattr(self,'effect_rate',1)/12)%1),width=5)
                self.create_line(left+22,yy+15,left+45,yy+34,right-45,yy+34,right-22,yy+15,fill=g['LINE'],width=2)
                self.create_text(x,yy+23,text='MEMORY',fill=g['MUTED'],font=(g['UI'],8,'bold'))
            return
        self.create_oval(x-r-7,y-r-7,x+r+7,y+r+7,outline=g['LINE'],width=1)
        self.create_oval(x-r,y-r,x+r,y+r,outline=g['LINE'],width=4)
        if self.rgb:
            for i in range(64):self.create_arc(x-r,y-r,x+r,y+r,start=i*360/64,extent=360/64+.2,style='arc',outline=lighting((i/64+time.monotonic()*getattr(self,'effect_rate',1)/12)%1),width=4)
        for i in range(9):
            a=math.radians(self.angle+i*40);points=[]
            for radius,offset in ((15,0),(46,-17),(72,-8),(73,9),(50,24),(22,19)):
                t=a+math.radians(offset);points.extend((x+radius*math.cos(t),y+radius*math.sin(t)))
            self.create_polygon(points,fill=g['PANEL2'],outline=g['LINE'],smooth=True,splinesteps=24)
        self.create_oval(x-20,y-20,x+20,y+20,fill=g['PANEL'],outline=g['LINE'],width=2)
        self.create_oval(x-4,y-4,x+4,y+4,fill=g['MUTED'],outline='')


class DutySlider(tk.Canvas):
    def __init__(self,parent,g,changed):
        super().__init__(parent,height=55,bg=g['PANEL'],highlightthickness=0,takefocus=True,cursor='hand2')
        self.g=g;self.changed=changed;self.value=60;self.low=30;self.high=100;self.enabled=False
        for event in ('<Button-1>','<B1-Motion>'):self.bind(event,self.drag)
        self.bind('<Left>',lambda e:self.set(self.value-1));self.bind('<Right>',lambda e:self.set(self.value+1));self.bind('<Configure>',lambda e:self.draw())
    def set(self,value):
        if not self.enabled:return
        self.value=max(self.low,min(self.high,round(value)));self.draw();self.changed()
    def drag(self,event):
        self.focus_set();self.set(self.low+(self.high-self.low)*max(0,min(1,(event.x-16)/max(1,self.winfo_width()-32))))
    def draw(self):
        self.delete('all');g=self.g;self.configure(bg=g['PANEL']);w=max(100,self.winfo_width());x=16+(w-32)*(self.value-self.low)/max(1,self.high-self.low)
        self.create_line(16,28,w-16,28,fill=g['LINE'],width=7,capstyle='round')
        if self.enabled:self.create_line(16,28,x,28,fill=g['ACC'],width=7,capstyle='round')
        self.create_oval(x-9,19,x+9,37,fill=g['FG'] if self.enabled else g['MUTED'],outline=g['PANEL'],width=2)


class FanPage:
    def __init__(self,hub,tab,g):
        self.hub,self.g=hub,g;self.signature=None;self.controls=[];self.fans=[];self.closed=False;self.entries={}
        g['page_header'](tab,'COOLING','Fan Control','Your fans. Live speeds. Actual hardware controls.')
        body=hub._scroll_area(tab);self.body=body
        hero=g['Card'](body,radius=28);hero.pack(fill='x',padx=8,pady=8)
        content=tk.Frame(hero.body,bg=g['PANEL']);content.pack(fill='x',padx=20,pady=16)
        self.visual=FanVisual(content,g);self.visual.pack(side='left',padx=(0,18))
        info=tk.Frame(content,bg=g['PANEL']);info.pack(side='left',fill='both',expand=True)
        wrap_column(info)
        hub.label(info,'LIVE FAN SPEED',10,g['MUTED'])
        self.rpm_label=hub.label(info,'Detecting…',30)
        self.reading_status=hub.label(info,'Waiting for a live hardware reading',10,g['MUTED'])
        self.fan_select=CoolingSelect(info,['Detecting fans…'],g,command=lambda _:self.select_control(),width=390);self.fan_select.pack(fill='x',padx=16,pady=8)
        self.select=self.fan_select
        self.summary=hub.label(info,'',10,g['MUTED'])
        card=g['Card'](body,radius=28);card.pack(fill='x',padx=8,pady=8)
        hub.label(card.body,'Speed control',17)
        self.live_duty=hub.label(card.body,'Current duty · waiting for hardware',11,g['MUTED'])
        self.duty=hub.label(card.body,'Target · select a controllable fan',15)
        self.slider=DutySlider(card.body,g,self.draft);self.slider.pack(fill='x',padx=18)
        buttons=tk.Frame(card.body,bg=g['PANEL']);buttons.pack(fill='x',padx=18,pady=8)
        self.apply=g['RButton'](buttons,'Apply speed',self.apply_manual,width=150,height=38);self.apply.pack(side='left',padx=(0,10));self.apply.set_enabled(False)
        self.auto=g['RButton'](buttons,'Automatic',self.automatic,width=150,height=38);self.auto.pack(side='left');self.auto.set_enabled(False)
        self.status=hub.label(card.body,'Detecting hardware controllers…',10,g['MUTED'])
        self.fan_advanced=g['Card'](body,radius=28)
        def toggle_fan_advanced():
            if self.fan_advanced.winfo_manager():self.fan_advanced.pack_forget()
            else:self.fan_advanced.pack(fill='x',padx=8,pady=8)
        hub.action(body,'Advanced fan settings',toggle_fan_advanced)
        hub.label(self.fan_advanced.body,'Manual minimum: 30%, or the controller’s higher limit. Automatic control returns on exit, lost monitoring, or CPU/GPU temperature ≥85°C.',10,g['MUTED'])
        hub.action(self.fan_advanced.body,'Rescan fan controllers',self.scan)
        hub.after(500,self.refresh);hub.after(80,self.animate)
    def scan(self):
        if hasattr(self.hub,'temperatures'):self.hub.temperatures.full_scan()
    def selected_controls(self):
        entry=self.entries.get(self.select.get(),{})
        return entry.get('controls') or ([entry['control']] if entry.get('control') else [])
    def selected(self):
        controls=self.selected_controls();return controls[0] if controls else None
    @staticmethod
    def control_label(row):return row['name']+' · '+row['hardware']
    @staticmethod
    def is_gpu(row):return '/gpu' in row['id'].lower() or 'gpu' in row['name'].lower()
    def select_control(self):
        controls=self.selected_controls();low=max((r['min'] for r in controls),default=30);high=min((r['max'] for r in controls),default=100)
        self.slider.enabled=bool(controls and low<=high);self.apply.set_enabled(self.slider.enabled);self.auto.set_enabled(bool(controls))
        if controls:
            self.slider.low=low;self.slider.high=high;value=controls[0].get('value');self.slider.value=max(low,min(high,value if value is not None else 60))
        self.slider.draw();self.draft();self.refresh_visual()
    def draft(self):
        rows=self.selected_controls();active=bool(rows and all(r.get('manual') and r.get('value') is not None and abs(r['value']-self.slider.value)<1 for r in rows))
        self.duty.config(text=f"Target · {self.slider.value:.0f}% · {len(rows)} control(s) ({'active' if active else 'press Apply speed'})" if self.slider.enabled else 'Monitoring only · no compatible speed controllers selected')
    def apply_manual(self):
        rows=self.selected_controls()
        try:
            if len(rows)>1:self.hub.temperatures.fan_batch('manual_many',[r['id'] for r in rows],self.slider.value)
            elif rows:self.hub.temperatures.fan_command('manual',rows[0]['id'],self.slider.value)
        except ValueError as exc:self.hub.temperatures.fan_status=str(exc)
    def automatic(self):
        rows=self.selected_controls()
        if len(rows)>1:self.hub.temperatures.fan_batch('default_many',[r['id'] for r in rows])
        elif rows:self.hub.temperatures.fan_command('default',rows[0]['id'])
    def refresh_visual(self):
        entry=self.entries.get(self.fan_select.get(),{});control=entry.get('control');row=entry.get('fan')
        if 'controls' in entry:
            controls=entry['controls'];names={self.control_label(c) for c in controls};readings=entry.get('fans') or [f for f in self.fans if self.control_label(f) in names];values=[f['rpm'] for f in readings if f.get('rpm') is not None]
            self.visual.rpm=sum(values)/len(values) if values else None
            self.rpm_label.config(text=f'{min(values):,.0f}–{max(values):,.0f} RPM' if values else 'RPM unavailable')
            self.reading_status.config(text='; '.join(f"{f['name']}: {f['rpm']:,.0f} RPM" if f.get('rpm') is not None else f['name']+': unavailable' for f in readings))
            self.live_duty.config(text=('Selected: '+str(len(controls))+' fan controllers · common duty range '+str(max(c['min'] for c in controls))+'–'+str(min(c['max'] for c in controls))+'%') if controls else 'Monitoring only · hardware does not expose speed control for this group')
            return
        self.visual.rpm=row.get('rpm') if row else None
        self.rpm_label.config(text=f'{self.visual.rpm:,.0f} RPM' if self.visual.rpm is not None else 'RPM unavailable')
        self.reading_status.config(text='Live tachometer reading' if self.visual.rpm else 'Fan stopped / header reports 0 RPM' if self.visual.rpm==0 else 'This controller does not expose an RPM sensor')
        value=control.get('value') if control else None
        self.live_duty.config(text=f"Current duty · {value:.0f}%  ·  {'Manual' if control.get('manual') else 'Automatic'}" if value is not None else 'No writable fan controller reported for this sensor')
    def refresh(self):
        if self.closed:return
        sampler=getattr(self.hub,'temperatures',None)
        fresh=sampler and time.monotonic()-sampler.extended_time<8
        self.fans=sampler.fans if fresh else [];self.controls=sampler.fan_controls if fresh else []
        self.entries={}
        for fan in self.fans:self.entries.setdefault(self.control_label(fan),{})['fan']=fan
        for control in self.controls:self.entries.setdefault(self.control_label(control),{})['control']=control
        system=[c for c in self.controls if not self.is_gpu(c) and 'pump' not in c['name'].lower()]
        gpu=[c for c in self.controls if self.is_gpu(c)]
        system_rpm=[f for f in self.fans if not self.is_gpu(f) and 'pump' not in f['name'].lower()]
        gpu_rpm=[f for f in self.fans if self.is_gpu(f)]
        if system or system_rpm:self.entries['All system fans']={'controls':system,'fans':system_rpm}
        if gpu or gpu_rpm:self.entries['All GPU fans']={'controls':gpu,'fans':gpu_rpm}
        if (system or system_rpm) and (gpu or gpu_rpm):self.entries['Both · system + GPU fans']={'controls':system+gpu,'fans':system_rpm+gpu_rpm}
        signature=tuple(self.entries)
        if signature!=self.signature:
            self.signature=signature;self.fan_select._close_popup()
            self.fan_select.values=list(self.entries) or ['No fan sensors detected']
            if self.select.get() not in self.entries:
                preferred=next((name for name,e in self.entries.items() if e.get('fan',{}).get('rpm') and e.get('control') and 'pump' not in name.lower()),self.fan_select.values[0])
                self.select.set(preferred);self.select_control()
        self.refresh_visual()
        self.draft()
        if not fresh:self.slider.enabled=False;self.apply.set_enabled(False);self.auto.set_enabled(False);self.slider.draw();self.draft()
        self.summary.config(text=f'{len(self.fans)} RPM sensors · {len(self.controls)} controls' if fresh else getattr(sampler,'extended_status','Detecting hardware…'))
        self.status.config(text=sampler.fan_status if sampler else 'Waiting for hardware monitor…')
        self.hub.after(1000,self.refresh)
    def animate(self):
        if self.closed:return
        if self.hub.cur_tab==_tab(self.hub,FAN_KEY) and self.hub.state()!='withdrawn':
            self.visual.angle=(self.visual.angle+(self.visual.rpm or 0)/180)%360;self.visual.draw()
        self.hub.after(60,self.animate)
    def close(self):self.closed=True


class RGBPage:
    def __init__(self,hub,tab,g):
        self.hub,self.g=hub,g;self.events=queue.Queue();self.client=None;self.devices=[];self.color='#a8cfff';self.busy=False;self.closed=False;self.tried=False;self.service=rgb_service.RGBService();self.retry_at=0;self.retry_delay=2;self.pending_request=None;self.rainbow_sync=None
        g['page_header'](tab,'LIGHTING','Fan RGB & RAM','Color your hardware. Preview first, apply when you are ready.')
        body=hub._scroll_area(tab)
        card=g['Card'](body,radius=28);card.pack(fill='x',padx=8,pady=8)
        row=tk.Frame(card.body,bg=g['PANEL']);row.pack(fill='x',padx=20,pady=16)
        left=tk.Frame(row,bg=g['PANEL']);left.pack(side='left',padx=(0,20))
        self.visual=FanVisual(left,g);self.visual.rgb=True;self.visual.pack()
        hub.label(left,'LIGHTING PREVIEW',9,g['MUTED'])
        self.rpm_label=hub.label(left,'Live RPM: detecting…',13)
        self.rpm_source=hub.label(left,'',9,g['MUTED'])
        hub.action(left,'Fan speed controls →',lambda:_tab(hub,FAN_KEY) is not None and hub.show_tab(_tab(hub,FAN_KEY)))
        right=tk.Frame(row,bg=g['PANEL']);right.pack(side='left',fill='both',expand=True)
        wrap_column(right)
        hub.label(right,'Choose what to light up',17)
        groups=tk.Frame(right,bg=g['PANEL']);groups.pack(fill='x',padx=16,pady=6)
        self.group='Fans';self.targets={}
        self.group_buttons={}
        for name in ('Fans','RAM','Fans + RAM'):
            button=g['RButton'](groups,name,lambda n=name:self.choose_group(n),width=115,height=38)
            button.pack(side='left',padx=(0,8));self.group_buttons[name]=button
        self.quick_target=CoolingSelect(right,['Connect lighting first'],g,command=lambda _:self.show_target(),width=350);self.quick_target.pack(fill='x',padx=16,pady=6)
        self.effect=CoolingSelect(right,['Solid color'],g,command=lambda _:self.effect_changed(),width=350);self.effect.pack(fill='x',padx=16,pady=5)
        speed_row=tk.Frame(right,bg=g['PANEL']);speed_row.pack(fill='x',padx=16,pady=2)
        self.speed_label=tk.Label(speed_row,text='Speed · not used for solid colors',bg=g['PANEL'],fg=g['MUTED'],font=(g['UI'],9));self.speed_label.pack(anchor='w')
        self.effect_speed=tk.Scale(speed_row,from_=0,to=100,orient='horizontal',showvalue=False,sliderlength=18,bd=0,highlightthickness=0,bg=g['PANEL'],fg=g['FG'],troughcolor=g['PANEL2'],activebackground=g['ACC'],command=lambda _:self.effect_draft(),width=9)
        self.effect_speed.set(50);self.effect_speed.pack(fill='x');self.effect_speed.config(state='disabled')
        # RETWEAKS: brightness (scales solid colours and the software Rainbow; hardware effects use the
        # controller's own brightness setting when it has one)
        bright_row=tk.Frame(right,bg=g['PANEL']);bright_row.pack(fill='x',padx=16,pady=2)
        self.brightness_label=tk.Label(bright_row,text='Brightness · 100%',bg=g['PANEL'],fg=g['MUTED'],font=(g['UI'],9));self.brightness_label.pack(anchor='w')
        self.brightness=tk.Scale(bright_row,from_=10,to=100,orient='horizontal',showvalue=False,sliderlength=18,bd=0,highlightthickness=0,bg=g['PANEL'],fg=g['FG'],troughcolor=g['PANEL2'],activebackground=g['ACC'],command=lambda _:self.brightness_draft(),width=9)
        self.brightness.set(100);self.brightness.pack(fill='x')
        hub.label(right,'Preview your choices, then press Apply',10,g['MUTED'])
        presets=tk.Frame(right,bg=g['PANEL']);self.color_presets=presets;presets.pack(fill='x',padx=16,pady=4)
        self.preset_buttons={}
        class PresetButton(g['RButton']):
            def __init__(self,parent,name,color,command):
                self.swatch=color
                super().__init__(parent,'  '+name,command,width=96,height=34)
            def _draw(self):
                super()._draw()
                self.create_oval(10,12,20,22,fill=self.swatch,outline='#777777' if self.swatch=='#000000' else self.swatch)
        for i,(name,color) in enumerate((('White','#ffffff'),('Ice','#a8cfff'),('Blue','#0000ff'),('Green','#00ff00'),('Red','#ff0000'),('Purple','#8000ff'),('Amber','#ff8000'),('Cyan','#00ffff'),('Yellow','#ffff00'),('Mint','#56e2aa'),('Off','#000000'))):
            button=PresetButton(presets,name,color,lambda n=name,c=color:self.preset(n,c))
            button.grid(row=i//4,column=i%4,padx=2,pady=3);self.preset_buttons[name]=button
        self.color_label=hub.label(right,'Ice · '+self.color.upper(),11)
        self.rainbow_note=hub.label(right,'',10,g['MUTED']);self.rainbow_note.pack_forget()
        actions=tk.Frame(right,bg=g['PANEL']);self.color_actions=actions;actions.pack(fill='x',padx=16,pady=6)
        self.custom_color_button=g['RButton'](actions,'Custom color',self.choose_color,width=130,height=38);self.custom_color_button.pack(side='left',padx=(0,8))
        self.quick_apply=g['RButton'](actions,'Apply',self.quick_apply_color,width=135,height=38,kind='primary');self.quick_apply.pack(side='left');self.quick_apply.set_enabled(False)
        self.status=hub.label(right,'Detecting RAM and fan lighting automatically…',10,g['MUTED'])
        self.start_button=g['RButton'](right,'Connect lighting',lambda:self.connect(start=True),width=175,height=36)
        self._build_extras(body,g)
        self.advanced_toggle=g['RButton'](body,'Advanced settings ▸',self.toggle_advanced,width=220,height=36);self.advanced_toggle.pack(anchor='w',padx=8,pady=8)
        self.advanced=g['Card'](body,radius=28);card=self.advanced
        hub.label(card.body,'Advanced lighting settings',17)
        hub.label(card.body,'Controller effects, individual zones and first-time header setup. For everyday colors, use the presets above.',10,g['MUTED'])
        self.preview=CoolingSelect(card.body,['Static','Breathing','Rainbow'],g,command=self.preview_effect,width=330);self.preview.set('Static');self.preview.pack(fill='x',padx=18,pady=6);self.visual.effect='Static'
        self.select=CoolingSelect(card.body,['No RGB connection'],g,command=lambda _:self.select_device(),width=500);self.select.pack(fill='x',padx=18,pady=6)
        self.zone=CoolingSelect(card.body,['All lighting'],g,command=lambda _:self.select_zone(),width=500);self.zone.pack(fill='x',padx=18,pady=6)
        self.zone_help=hub.label(card.body,'',10,g['MUTED'])
        count_row=tk.Frame(card.body,bg=g['PANEL']);count_row.pack(fill='x',padx=18,pady=4)
        self.led_count=tk.StringVar(value='0');self.count_entry=g['REntry'](count_row,self.led_count,width_px=95);self.count_entry.pack(side='left',padx=(0,10))
        self.resize_button=g['RButton'](count_row,'Set header LED count',self.resize_zone,width=210,height=34);self.resize_button.pack(side='left');self.resize_button.set_enabled(False)
        self.mode=CoolingSelect(card.body,['No hardware effects available'],g,command=self.preview_effect,width=350);self.mode.pack(fill='x',padx=18,pady=6)
        self.select.button.set_enabled(False);self.zone.button.set_enabled(False);self.mode.button.set_enabled(False)
        buttons=tk.Frame(card.body,bg=g['PANEL']);buttons.pack(fill='x',padx=18,pady=10)
        self.apply=g['RButton'](buttons,'Apply lighting',self.apply_lighting,width=160,height=38);self.apply.pack(side='left',padx=(0,10));self.apply.set_enabled(False)
        hub.label(card.body,'Lighting connects and recovers automatically. Fan lights are identified from reported cooling controllers and motherboard lighting outputs; physical fan names are not exposed by most RGB hubs.',10,g['MUTED'])
        hub.action(card.body,'OpenRGB setup / download ↗',lambda:webbrowser.open('https://openrgb.org/'))
        hub.after(100,self.tick)
    # ---------------------------------------------------------------- RETWEAKS additions (2026-10-22)
    def brightness_draft(self):
        self.brightness_label.config(text=f'Brightness · {self.brightness.get()}% · press Apply')
        if hasattr(self,'status'):self.status.config(text='Preview only · press Apply to update lighting.')
    def _settings(self):
        s=getattr(self.hub,'settings',None)
        return s if isinstance(s,dict) else {}
    def _save_settings(self):
        try:self.hub.save_settings()
        except Exception:pass
    def profiles(self):
        p=self._settings().get('rgb_profiles')
        return {k:v for k,v in p.items() if isinstance(k,str) and isinstance(v,dict)} if isinstance(p,dict) else {}
    def _build_extras(self,body,g):
        hub=self.hub;self.post_queue=[];self.off_devices=set();self.start_profile_pending=None
        card=self.g['Card'](body,radius=28);card.pack(fill='x',padx=8,pady=8);b=card.body
        hub.label(b,'Devices',17)
        hub.label(b,'Turn a lighting controller off or back on. Off sets it to black; On uses the colour and brightness above.',10,g['MUTED'])
        self.power_box=tk.Frame(b,bg=g['PANEL']);self.power_box.pack(fill='x',padx=16,pady=(0,10))
        self.power_vars={}
        hub.label(b,'Lighting profiles',17)
        hub.label(b,'Save what is set above (group, target, effect, colour, speed, brightness and devices turned off) and apply it again in one click.',10,g['MUTED'])
        row=tk.Frame(b,bg=g['PANEL']);row.pack(fill='x',padx=16,pady=4)
        self.profile_select=g['RSelect'](row,list(self.profiles()) or ['No saved profiles'],width=240);self.profile_select.pack(side='left',padx=(0,8))
        g['RButton'](row,'Apply profile',lambda:self.apply_profile(self.profile_select.get()),width=130,height=34).pack(side='left',padx=(0,8))
        g['RButton'](row,'Save current…',self.save_profile,width=130,height=34).pack(side='left',padx=(0,8))
        g['RButton'](row,'Delete',lambda:self.delete_profile(self.profile_select.get()),width=90,height=34,kind='ghost').pack(side='left')
        self.profile_msg=hub.label(b,'',10,g['MUTED'])
        s=self._settings()
        self.apply_on_start=tk.BooleanVar(value=bool(s.get('rgb_apply_on_start',False)))
        start_row=tk.Frame(b,bg=g['PANEL']);start_row.pack(fill='x',padx=16,pady=(4,14))
        g['RCheck'](start_row,'Apply this profile when RETWEAKS starts:',self.apply_on_start,self._save_start).pack(side='left')
        self.start_profile=g['RSelect'](start_row,list(self.profiles()) or ['No saved profiles'],width=200,command=lambda v:self._save_start())
        self.start_profile.pack(side='left',padx=8)
        if s.get('rgb_start_profile') in self.profiles():self.start_profile.set(s['rgb_start_profile'])
        if self.apply_on_start.get() and self.start_profile.get() in self.profiles():
            # only when the user ticked it: connect and apply once the controllers are detected
            self.start_profile_pending=self.start_profile.get();self.hub.after(4000,lambda:self.closed or self.connect(start=True))
    def _refresh_profile_lists(self):
        names=list(self.profiles()) or ['No saved profiles']
        for sel in (self.profile_select,self.start_profile):
            current=sel.get();sel.values=names;sel.set(current if current in names else names[0])
    def _save_start(self):
        s=self._settings();s['rgb_apply_on_start']=bool(self.apply_on_start.get())
        if self.start_profile.get() in self.profiles():s['rgb_start_profile']=self.start_profile.get()
        self._save_settings()
    def current_profile(self):
        return dict(group=self.group,target=self.quick_target.get(),effect=self.effect.get(),color=self.color,
                    speed=int(self.effect_speed.get()),brightness=int(self.brightness.get()),off=sorted(self.off_devices))
    def save_profile(self,name=None):
        if name is None:
            from tkinter import simpledialog
            name=simpledialog.askstring('Save lighting profile','Profile name:',parent=self.hub)
        name=(name or '').strip()[:40]
        if not name:return False
        s=self._settings();profiles=dict(self.profiles());profiles[name]=self.current_profile()
        s['rgb_profiles']=profiles;self._save_settings();self._refresh_profile_lists();self.profile_select.set(name)
        self.profile_msg.config(text=f'Saved "{name}".');return True
    def delete_profile(self,name):
        s=self._settings();profiles=dict(self.profiles())
        if name not in profiles:return False
        del profiles[name];s['rgb_profiles']=profiles
        if s.get('rgb_start_profile')==name:s.pop('rgb_start_profile',None)
        self._save_settings();self._refresh_profile_lists();self.profile_msg.config(text=f'Deleted "{name}".');return True
    def apply_profile(self,name):
        p=self.profiles().get(name)
        if not p:self.profile_msg.config(text='Choose a saved profile first.');return False
        group=p.get('group') if p.get('group') in ('Fans','RAM','Fans + RAM') else 'Fans'
        self.choose_group(group)
        if p.get('target') in self.targets:self.quick_target.set(p['target']);self.show_target()
        if p.get('effect') in self.effect.values:self.effect.set(p['effect']);self.effect_changed(draft=False)
        color=p.get('color')
        if isinstance(color,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',color):self.color=color;self.visual.color=color
        try:self.effect_speed.set(max(0,min(100,int(p.get('speed',50)))))
        except (TypeError,ValueError):pass
        try:self.brightness.set(max(10,min(100,int(p.get('brightness',100)))))
        except (TypeError,ValueError):pass
        if not self.targets.get(self.quick_target.get()):
            self.profile_msg.config(text=f'"{name}": its lighting isn\'t detected right now.');return False
        self.quick_apply_color()
        off=[d for d in p.get('off',[]) if isinstance(d,str)]
        self.post_queue=[(r['label'],False) for r in self.devices if r['device'].name in off]
        self.profile_msg.config(text=f'Applying "{name}"…');return True
    def render_device_power(self):
        if not hasattr(self,'power_box'):return
        for w in self.power_box.winfo_children():w.destroy()
        self.power_vars={}
        if not self.devices:
            tk.Label(self.power_box,text='No lighting controllers detected yet.',bg=self.g['PANEL'],fg=self.g['MUTED'],font=(self.g['UI'],10)).pack(anchor='w');return
        for r in self.devices:
            var=tk.BooleanVar(value=r['device'].name not in self.off_devices);self.power_vars[r['label']]=var
            self.g['RCheck'](self.power_box,r['label'],var,lambda l=r['label'],v=var:self.set_device_power(l,v.get())).pack(anchor='w',pady=2)
    def set_device_power(self,label,on):
        row=next((r for r in self.devices if r['label']==label),None)
        if row is None:return False
        if self.busy:self.post_queue.append((label,on));return False
        key=rgb_service.identity(row['device'],[r['device'] for r in self.devices]);name=row['device'].name
        color=self.color if on else '#000000';bright=self.brightness.get()
        def work():
            from openrgb.utils import RGBColor
            if self.rainbow_sync and key in self.rainbow_sync.keys:
                self.rainbow_sync.stop();self.rainbow_sync=None
            self.service.start()
            if self.client:self.client.disconnect();self.client=None
            client=rgb_service.connect();self.client=client
            matches=rgb_service.find(client.devices,key)
            if len(matches)!=1:raise ValueError(name+' is no longer detected.')
            with rgb_service.LightingWriter():
                rgb_service.write_solid(matches[0],None,rgb_service.scale_color(RGBColor.fromHEX(color),bright if on else 100))
            if on:self.off_devices.discard(name)
            else:self.off_devices.add(name)
            return {'devices':self.device_rows(client),'message':name+(' turned on.' if on else ' turned off.')}
        self.worker(work);return True
    def toggle_advanced(self):
        if self.advanced.winfo_manager():self.advanced.pack_forget();self.advanced_toggle.label='Advanced settings ▸'
        else:self.advanced.pack(fill='x',padx=8,pady=8);self.advanced_toggle.label='Advanced settings ▾'
        self.advanced_toggle._draw()
    def choose_group(self,name):
        self.group=name;self.rebuild_targets()
    def rebuild_targets(self):
        previous=self.quick_target.get();self.targets={}
        # RETWEAKS fix (owner report 2026-10-22: "If I try and change the RAM colors, it only changes one of
        # them"): every RAM stick is its own OpenRGB device, and identical sticks have identical names, so the
        # old name-keyed list kept only one of them. Now "All RAM sticks" (default) drives every stick, and
        # each stick / fan device also gets its own numbered entry.
        if self.group=='RAM':
            sticks=[row['device'] for row in self.devices if row['device'].type.name=='DRAM']
            if len(sticks)>1:
                self.targets[f'All RAM sticks ({len(sticks)})']={'members':[{'device':d,'zone':None,'shared':False} for d in sticks],'zone':None}
            for index,d in enumerate(sticks):
                self.targets[f'RAM stick {index+1} · {d.name}' if len(sticks)>1 else 'RAM · '+d.name]={'device':d,'zone':None}
        fan_devices=[row['device'] for row in self.devices if row['device'].type.name in ('COOLER','LEDSTRIP')] if self.group=='Fans' else []
        if len(fan_devices)>1:
            self.targets[f'All fan lighting devices ({len(fan_devices)})']={'members':[{'device':d,'zone':None,'shared':False} for d in fan_devices],'zone':None}
        for row in self.devices:
            device=row['device'];kind=device.type.name
            if self.group=='Fans':
                if kind in ('COOLER','LEDSTRIP'):
                    n=fan_devices.index(device)+1
                    self.targets[(f'Fan lighting {n} · ' if len(fan_devices)>1 else 'Fan lighting · ')+device.name]={'device':device,'zone':None}
                elif kind=='MOTHERBOARD':
                    zones=rgb_service.fan_zones(device)
                    if zones:
                        ready=[z for z in zones if z.leds]
                        self.targets['All fan lights · '+device.name]={'device':device,'zone':None,'all_fans':True,'shared':True}
                        for index,zone in enumerate(zones):
                            self.targets[f'Fan lights {index+1}'+(' · setup needed' if not zone.leds else '')]={'device':device,'zone':zone}
        if self.group=='Fans + RAM':
            members=[]
            for row in self.devices:
                d=row['device'];kind=d.type.name
                if kind=='DRAM' or kind in ('COOLER','LEDSTRIP') or (kind=='MOTHERBOARD' and rgb_service.fan_zones(d)):
                    members.append({'device':d,'zone':None,'shared':kind=='MOTHERBOARD'})
            if members:self.targets['Fans + RAM · all detected controllers']={'members':members,'zone':None}
        self.quick_target.values=list(self.targets) or ['No '+self.group.lower()+' lighting detected']
        preferred=next((name for name,t in self.targets.items() if t['zone'] is None or (bool(t['zone']) if isinstance(t['zone'],list) else bool(t['zone'].leds))),self.quick_target.values[0])
        self.quick_target.set(previous if previous in self.targets else preferred)
        self.quick_target.button.set_enabled(bool(self.targets))
        for name,button in self.group_buttons.items():button.set_kind('primary' if name==self.group else 'default')
        self.show_target()
    def show_target(self):
        target=self.targets.get(self.quick_target.get());self.visual.ram=self.group=='RAM'
        self.refresh_effects()
        ready=bool(target and (target['zone'] is None or (bool(target['zone']) if isinstance(target['zone'],list) else bool(target['zone'].leds))))
        self.quick_apply.set_enabled(ready and not self.busy)
        for button in self.preset_buttons.values():button.set_enabled(ready)
        if target and not ready:self.status.config(text='This fan header needs its LED count set once in Advanced settings.')
        elif not target:self.status.config(text='Detecting '+self.group.lower()+' lighting automatically. Hardware setup is available in Advanced settings.')
        elif target.get('shared') or target['zone'] is not None:self.status.config(text='Ready. Fan and motherboard lights share this controller’s color.')
        else:self.status.config(text='Ready. Choose color and effect, then press Apply for '+self.group.lower()+'.')
    def refresh_effects(self):
        target=self.targets.get(self.quick_target.get());members=target.get('members',[target]) if target else []
        devices=[m['device'] for m in members]
        effects=['Solid color']
        if devices and all(m.get('zone') is None for m in members):
            shared=all(any(m.name.lower() in ('direct','static') and int(m.color_mode)==1 for m in d.modes) for d in devices)
            if shared:effects.append('Rainbow')
            # RETWEAKS: the controllers' own Breathing / Color cycle modes, offered only when every selected
            # controller reports that mode
            for name in ('Breathing','Color cycle'):
                if all(rgb_service.effect_mode(d,name) is not None for d in devices):effects.append(name)
        previous=self.effect.get();self.effect.values=effects;self.effect.set(previous if previous in effects else 'Solid color');self.effect_changed(draft=False)
    def effect_changed(self,draft=True):
        from openrgb.utils import ModeFlags
        target=self.targets.get(self.quick_target.get());members=target.get('members',[target]) if target else []
        modes=[rgb_service.effect_mode(m['device'],self.effect.get()) for m in members]
        enabled=self.effect.get()=='Rainbow' or self.effect.get()!='Solid color' and any(mode and bool(ModeFlags(getattr(mode,'flags',0)) & ModeFlags.HAS_SPEED) for mode in modes)
        self.effect_speed.config(state='normal' if enabled else 'disabled');self.visual.effect=self.effect.get();self.effect_draft(draft)
        rainbow=self.effect.get()=='Rainbow'
        if rainbow:
            self.color_presets.pack_forget();self.color_label.pack_forget();self.custom_color_button.pack_forget()
            self.rainbow_note.config(text='Rainbow selects its own colors. Fans + RAM uses one synchronized color clock.' if self.group=='Fans + RAM' else 'Rainbow selects its own colors. Adjust speed, then press Apply.')
            self.rainbow_note.pack(fill='x',padx=16,pady=8,before=self.color_actions)
        else:
            self.rainbow_note.pack_forget()
            self.color_label.pack(fill='x',padx=16,pady=6,before=self.color_actions)
            self.color_presets.pack(fill='x',padx=16,pady=4,before=self.color_label)
            self.custom_color_button.pack(side='left',padx=(0,8),before=self.quick_apply)

    def effect_draft(self,draft=True):
        if not hasattr(self,'effect_speed'):return
        enabled=str(self.effect_speed.cget('state'))!='disabled'
        self.visual.effect_rate=12/rainbow_period(self.effect_speed.get())
        self.speed_label.config(text=f'Rainbow cycle · {rainbow_period(self.effect_speed.get()):.1f} seconds · press Apply' if self.effect.get()=='Rainbow' else f'Effect speed · {self.effect_speed.get()}%' if enabled else 'Speed · device default / unavailable' if self.effect.get()!='Solid color' else 'Speed · not used for solid colors')
        if draft and hasattr(self,'status'):self.status.config(text='Preview only · press Apply to update lighting.')
    def preset(self,name,color):
        self.color=color;self.visual.color=color;self.visual.effect=self.effect.get();self.color_label.config(text=name+' · '+color.upper());self.status.config(text='Preview only · press Apply to update lighting.')
    def quick_apply_color(self,intent=None):
        if intent is None:
            target=self.targets.get(self.quick_target.get())
            if not target:return
            specs=[]
            for member in target.get('members',[target]):
                zone=member['zone'];names=None if zone is None else [z.name for z in zone] if isinstance(zone,list) else [zone.name]
                specs.append((rgb_service.identity(member['device'],[r['device'] for r in self.devices]),names))
            intent=(specs,self.color,self.group,self.effect.get(),self.effect_speed.get(),self.brightness.get())
        if self.busy:
            self.pending_request=intent;self.status.config(text='Color queued · applying as soon as the current command finishes.');return
        specs,color,part,effect,speed,*more=intent
        bright=more[0] if more else 100
        def work():
            from openrgb.utils import RGBColor
            for attempt in range(2):
                try:
                    if self.closed:return None
                    keys=[key for key,_ in specs]
                    if effect=='Rainbow' and self.rainbow_sync and self.rainbow_sync.keys==keys and not self.rainbow_sync.stop_event.is_set():
                        self.rainbow_sync.set_speed(speed);self.rainbow_sync.brightness=bright
                        return {'devices':self.devices,'message':f'Rainbow speed applied · {speed}% · {part}'}
                    if self.rainbow_sync:self.rainbow_sync.stop();self.rainbow_sync=None
                    if effect=='Rainbow':
                        sync=RainbowSync(self.service,keys,speed,lambda text:self.events.put(('sync_status',text)),scope=part)
                        sync.brightness=bright;self.rainbow_sync=sync;sync.start()
                        return {'devices':self.devices,'message':f'Rainbow active · {part} · speed {speed}%'}
                    self.service.start()
                    if self.client:self.client.disconnect();self.client=None
                    client=rgb_service.connect();self.client=client;plan=[]
                    for key,names in specs:
                        matches=rgb_service.find(client.devices,key)
                        if len(matches)!=1:raise ValueError('The selected lighting device changed. Waiting for detection to refresh.')
                        d=matches[0];zones=None if names is None else [z for z in getattr(d,'zones',[]) if z.name in names]
                        if names is not None and len(zones)!=len(names):raise ValueError('The selected lighting output is no longer available.')
                        if (rgb_service.solid_mode(d,zone=zones is not None) if effect=='Solid color' else rgb_service.effect_mode(d,effect)) is None:raise ValueError('A selected controller does not support this lighting effect.')
                        plan.append((d,zones))
                    with rgb_service.LightingWriter():
                        for d,zones in plan:
                            if effect=='Solid color':rgb_service.write_solid(d,zones,rgb_service.scale_color(RGBColor.fromHEX(color),bright))
                            else:rgb_service.write_effect(d,effect,rgb_service.scale_color(RGBColor.fromHEX(color),bright),speed,brightness=bright)
                    return {'devices':self.device_rows(client),'message':'Lighting confirmed · '+part+' · '+effect+' · '+color.upper()}
                except ValueError:raise
                except Exception:
                    if attempt:raise
                    if self.client:
                        try:self.client.disconnect()
                        except Exception:pass
                        self.client=None
                    time.sleep(.4)
        self.worker(work)
    @staticmethod
    def device_rows(client):
        return [dict(label=f'{device.id+1}. {device.name} · {device.type.name}',device=device) for device in client.devices if device.leds or getattr(device,'zones',[])]
    def receive_devices(self,rows):
        previous=self.select.get();previous_zone=getattr(self,'zone_map',{}).get(self.zone.get());previous_zone_name=getattr(previous_zone,'name',None);previous_mode=self.mode.get()
        self.devices=rows;self.select.values=[r['label'] for r in rows] or ['Detecting lighting…']
        self.select.set(previous if previous in self.select.values else next((r['label'] for r in rows if r['device'].type.name!='DRAM'),self.select.values[0]))
        self.select_device()
        if previous_zone_name:
            label=next((name for name,z in self.zone_map.items() if z.name==previous_zone_name),None)
            if label:self.zone.set(label);self.select_zone()
        if previous_mode in self.mode.values:self.mode.set(previous_mode)
        self.rebuild_targets();self.retry_delay=2;self.retry_at=time.monotonic()+15
        self.render_device_power()
    def preview_effect(self,value):
        self.visual.effect=value
        self.preview.set('Rainbow' if any(k in value.lower() for k in ('rainbow','spectrum','wave','cycle')) else 'Breathing' if any(k in value.lower() for k in ('breath','pulse')) else 'Static')
    def choose_color(self):
        color=colorchooser.askcolor(self.color,parent=self.hub,title='Lighting color')[1]
        if color:self.color=color;self.visual.color=color;self.color_label.config(text='Custom · '+color.upper());self.status.config(text='Preview only · press Apply to update lighting.')
    def selected(self):return next((r for r in self.devices if r['label']==self.select.get()),None)
    def select_device(self):
        row=self.selected();self.select.button.set_enabled(bool(self.devices))
        self.visual.ram=bool(row and row['device'].type.name=='DRAM')
        self.zone_map={}
        if row:
            for zone in getattr(row['device'],'zones',[]):
                kind='Fan / ARGB header' if any(k in zone.name.upper() for k in ('JRAINBOW','JCORSAIR')) else 'RGB header' if zone.name.upper().startswith('JRGB') else 'Zone'
                self.zone_map[f'{kind}: {zone.name} · {len(zone.leds)} LEDs']=zone
        self.zone.values=['All lighting on this controller']+list(self.zone_map)
        self.zone.set(self.zone.values[0]);self.zone.button.set_enabled(bool(row));self.select_zone()
    def select_zone(self):
        row=self.selected();zone=getattr(self,'zone_map',{}).get(self.zone.get())
        self.resize_button.set_enabled(False)
        if not row:
            self.mode.values=['No hardware modes available'];self.mode.set(self.mode.values[0]);self.mode.button.set_enabled(False);self.apply.set_enabled(False);self.zone_help.config(text='Connect the RGB service to discover controllers and fan headers.');return
        device=row['device']
        if zone:
            self.mode.values=['Static color · selected zone']
            self.led_count.set(str(len(zone.leds)))
            data=device.data.zones[zone.id]
            self.resize_button.set_enabled(data.leds_max>data.leds_min)
            self.zone_help.config(text=f'{zone.name}: {len(zone.leds)} LEDs configured. '+('Enter the actual total LEDs connected to this header before applying color.' if not zone.leds else 'Color targets this zone. Solid-color mode replaces effects across this controller.'))
        else:
            self.mode.values=[m.name for m in device.modes] or ['No hardware modes available']
            self.zone_help.config(text='Fans connected to motherboard RGB headers appear in the zone selector above. Effects on All lighting affect the entire selected controller.')
        self.mode.set(self.mode.values[0]);self.mode.button.set_enabled(bool(device.modes))
        self.apply.set_enabled(bool(device.modes and (zone is None or zone.leds) and not self.busy))
        self.preview_effect(self.mode.get())
    def resize_zone(self):
        row=self.selected();zone=getattr(self,'zone_map',{}).get(self.zone.get())
        if not row or zone is None or self.busy:return
        try:
            value=int(self.led_count.get());data=row['device'].data.zones[zone.id]
            if not data.leds_min<=value<=min(data.leds_max,4096):raise ValueError()
        except (ValueError,TypeError):
            self.status.config(text='Enter a whole LED count within the header’s supported range.');return
        def work():
            zone.resize(value)
            return ('resized',zone.id)
        self.worker(work)
    def worker(self,work,connection=False):
        if self.busy:return
        self.busy=True;self.connection_operation=connection;self.apply.set_enabled(False)
        self.start_button.set_enabled(False)
        self.quick_apply.set_enabled(False)
        def run():
            try:self.events.put(('ok',work()))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=run,daemon=True,name='RETWEAKS RGB').start()
    def connect(self,start=True):
        self.tried=True
        def work():
            if self.client:self.client.disconnect();self.client=None
            if start:self.service.start()
            client=rgb_service.connect()
            if self.closed:client.disconnect();return None
            self.client=client
            return self.device_rows(client)
        if not self.busy:self.status.config(text='Starting RGB service and detecting hardware…' if start else 'Checking local RGB service…')
        self.worker(work,connection=True)
    def apply_lighting(self):
        row=self.selected()
        if not row or self.busy:return
        device=row['device'];mode=self.mode.get();color=self.color;zone=getattr(self,'zone_map',{}).get(self.zone.get())
        def write():
            from openrgb.utils import RGBColor,ModeColors
            if zone is not None:
                rgb_service.write_solid(device,[zone],RGBColor.fromHEX(color));return 'Color confirmed · '+zone.name
            if mode.lower() in ('static','solid','solid color','direct'):
                rgb_service.write_solid(device,None,RGBColor.fromHEX(color));return 'Color confirmed · '+device.name
            device.set_mode(mode)
            if device.modes[device.active_mode].name!=mode:raise ValueError('Device did not confirm the selected lighting mode.')
            active=device.modes[device.active_mode]
            if active.color_mode in (ModeColors.MODE_SPECIFIC,ModeColors.PER_LED):device.set_color(RGBColor.fromHEX(color))
            return 'Lighting command sent to '+device.name+'.'
        def work():
            if self.rainbow_sync:
                self.rainbow_sync.stop();self.rainbow_sync=None
            with rgb_service.LightingWriter():return write()
        self.worker(work)
    def tick(self):
        if self.closed:return
        try:
            while True:
                kind,result=self.events.get_nowait()
                if kind=='sync_status':
                    if self.rainbow_sync:self.status.config(text=result)
                    continue
                self.busy=False
                self.start_button.set_enabled(True)
                if kind=='error':
                    self.rebuild_targets();self.retry_at=time.monotonic()+self.retry_delay;self.retry_delay=min(15,self.retry_delay*2)
                    self.status.config(text=('Lighting reconnects automatically. '+result) if self.connection_operation else 'Color not confirmed; lighting will recover automatically. '+result)
                elif isinstance(result,dict) and 'devices' in result:
                    self.receive_devices(result['devices']);self.status.config(text=result['message'])
                elif isinstance(result,list):
                    self.receive_devices(result)
                    self.status.config(text=(f'Rainbow active · {self.rainbow_sync.scope}' if self.rainbow_sync else 'Lighting connected automatically. Choose a mode, then press Apply.') if result else 'No supported lighting reported. Checking again automatically…')
                elif isinstance(result,tuple) and result[0]=='resized':
                    self.select_device()
                    label=next((name for name,z in self.zone_map.items() if z.id==result[1]),self.zone.values[0])
                    self.zone.set(label);self.select_zone();self.rebuild_targets();self.status.config(text='Header LED count updated. You can apply its color now.')
                else:self.rebuild_targets();self.status.config(text=result or 'Disconnected');self.apply.set_enabled(bool(self.selected()))
        except queue.Empty:pass
        if not self.busy and self.pending_request is not None:
            intent=self.pending_request;self.pending_request=None;self.quick_apply_color(intent)
        elif not self.busy and self.start_profile_pending and self.devices:
            name=self.start_profile_pending;self.start_profile_pending=None;self.apply_profile(name)
        elif not self.busy and self.post_queue:
            label,on=self.post_queue.pop(0);self.set_device_power(label,on)
        if self.hub.cur_tab==_tab(self.hub,RGB_KEY) and self.hub.state()!='withdrawn':
            if not self.busy and (not self.tried or time.monotonic()>=self.retry_at):self.connect(start=True)
            fan=getattr(self.hub,'fan_control',None);rpm=fan.visual.rpm if fan else None
            self.rpm_label.config(text=f'Live fan · {rpm:,.0f} RPM' if rpm is not None else 'Live RPM unavailable')
            self.rpm_source.config(text=fan.fan_select.get().split(' · ')[0] if fan and rpm is not None else 'Select a sensor in Fan Control')
            self.visual.angle=(self.visual.angle+7)%360;self.visual.draw()
        self.hub.after(60,self.tick)
    def close(self):
        self.closed=True
        if self.rainbow_sync:self.rainbow_sync.stop()
        self.service.close()
        if self.client:
            client=self.client;self.client=None
            threading.Thread(target=client.disconnect,daemon=True).start()
