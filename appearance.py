from branding import logo as feather
from core.version import BRAND
"""Local palettes and small canvas accents, without image or network dependencies."""
import math
import time
import tkinter as tk

ANIMATIONS=('Off','Particles','Constellation','Fireflies','Double Helix','Orbit','Waves','Grid',
            'Aurora','Starfield','Rain','Pulse','Picture')

def blend(a,b,t):
    x=tuple(int(a[i:i+2],16) for i in (1,3,5));y=tuple(int(b[i:i+2],16) for i in (1,3,5))
    return '#%02x%02x%02x'%tuple(round(v+(z-v)*t) for v,z in zip(x,y))

THEMES={
    'Graphite':('#09090b','#101012','#151518','#222226','#303035','#eeeef0'),
    'Midnight':('#0c121b','#101925','#162130','#1e2e40','#2d435a','#71b7ed'),
    'Forest':('#101613','#151e19','#1b2720','#24352b','#344a3c','#7cc6a1'),
    'Ember':('#191310','#211a16','#2a211b','#372b23','#4d3c30','#e0aa72'),
    'Silver':('#1b1d20','#212428','#292d32','#343a40','#474f57','#c1cbd3'),
    'Blackout':('#000000','#030303','#070707','#101010','#202020','#f5f5f5'),   # base app v1.5
}

# ---------------------------------------------------------------- RETWEAKS themes (combined app, 2026-10-22)
# the base app's palette model has 6 colours (background, sidebar, panel, raised panel, line, accent); text colours
# are fixed light tones. RETWEAKS' dark themes map onto that model; its accent themes are Graphite + accent.
BASE_THEMES=tuple(THEMES)
RETWEAKS_ACCENTS={'Pink':'#e91e63','Blue':'#3b82f6','Purple':'#a855f7','Red':'#ef4444','Green':'#22c55e','Cyan':'#06b6d4'}
RETWEAKS_FULL={   # from core/themes.py FULL_THEMES: bg, sidebar, card, card_hover, border, accent
    'Super Black':('#000000','#050505','#0a0a0a','#141414','#1f1f1f','#a3a3a3'),
    'Galaxy':('#0c0a1d','#100d24','#171334','#1e1940','#2b2452','#8b5cf6'),
    'Ocean':('#0a1220','#0d1628','#111d33','#16243d','#1f3050','#22d3ee'),
}
# RETWEAKS theme names whose the base app equivalent already exists (same name, or a clashing name):
# RETWEAKS 'Midnight' was black/grey (the base app's 'Midnight' is blue) -> Graphite. 'Light' isn't ported:
# the base app's text colours are fixed light tones outside the palette, so a light background would be unreadable.
RETWEAKS_NAME_MAP={'Midnight':'Graphite','Light':'Graphite','Ember':'Ember','Forest':'Forest'}
_g=THEMES['Graphite']
for _n,_t in RETWEAKS_FULL.items():THEMES[_n]=_t
for _n,_a in RETWEAKS_ACCENTS.items():THEMES[_n]=_g[:5]+(_a,)
# Fixed (non-palette) colours used by retweaks.py widgets; a palette colour must never equal one of them,
# because recolor() finds widgets by colour value (an accent equal to the text colour would recolour text).
RESERVED={'#f5f5f6','#aaaab0','#77777f','#141416','#b8b8c0','#69c59b','#e07e81','#ffffff','#000001'}
CUSTOM={}            # theme maker themes: name -> 6-colour tuple (from settings 'custom_themes')
CUSTOM_COLORS={}     # name -> the 10 editable RETWEAKS colours (kept for share codes)
_custom_accent=None


def _distinct(colors):
    """Nudges colours so the 6 palette roles never share a value with each other or a reserved colour."""
    out=[]
    for c in colors:
        c=c.lower()
        while c in out or c in RESERVED:
            r,gg,b=(int(c[i:i+2],16) for i in (1,3,5))
            b=b+1 if b<255 else b-1
            c='#%02x%02x%02x'%(r,gg,b)
        out.append(c)
    return tuple(out)


def theme_names():
    return list(THEMES)+[n for n in CUSTOM if n not in THEMES]


def builtin_names():
    """Names users can't reuse for their own themes (the base app's and RETWEAKS' built-ins)."""
    return set(THEMES)|set(RETWEAKS_NAME_MAP)|{'Light'}


def register_custom(saved):
    """saved: settings['custom_themes'] = {name: {10 editable colours}}. Bad entries are skipped, never deleted."""
    from core import themes as rt
    CUSTOM.clear();CUSTOM_COLORS.clear()
    for name,colors in (saved or {}).items():
        if not isinstance(name,str) or name in builtin_names() or not rt.validate_colors(colors)[0]:continue
        t=rt.build_palette(colors)
        CUSTOM[name]=(t['bg'],t['sidebar'],t['card'],t['card_hover'],t['border'],t['accent'])
        CUSTOM_COLORS[name]={k:colors[k].lower() for k in rt.EDITABLE_KEYS}


def set_custom_accent(hex_color):
    """RETWEAKS' custom accent (validated #rrggbb or None): replaces the theme's accent colour."""
    global _custom_accent
    _custom_accent=hex_color.lower() if isinstance(hex_color,str) and len(hex_color)==7 else None


def map_retweaks_theme(name):
    """A RETWEAKS v1.x theme name -> the theme to use in the combined app (None if unknown)."""
    if not isinstance(name,str):return None
    if name in RETWEAKS_NAME_MAP:return RETWEAKS_NAME_MAP[name]
    if name in THEMES or name in CUSTOM:return name
    return None


def colors_of(name):
    """The 6 palette colours of any theme (custom accent not applied)."""
    return CUSTOM.get(name) or THEMES.get(name) or THEMES['Graphite']


def palette(name,colors=None):
    bg,side,panel,panel2,line,accent=colors or colors_of(name)
    if _custom_accent and colors is None:accent=_custom_accent
    bg,side,panel,panel2,line,accent=_distinct((bg,side,panel,panel2,line,accent))
    return dict(BG=bg,SIDE=side,PANEL=panel,PANEL2=panel2,LINE=line,ACC=accent,
                HERO=panel2,HERO2=panel,HERO_EDGE=line,NAV_ACTIVE=panel2,
                NAV_HOVER=panel,EDGE_HOVER=accent,ACC2=accent)

def recolor(root,g,old,new):
    roles={old[k]:k for k in new if k in old}
    def resolve(value):return roles.get(value) if isinstance(value,str) else None
    # Preserve default widget colors when dialogs or new rows are created later.
    def defaults(fn):
        values=getattr(fn,'__defaults__',None)
        if values:
            bindings=getattr(fn,'_theme_defaults',None)
            if bindings is None:
                bindings=[resolve(v) for v in values];fn._theme_defaults=bindings
            fn.__defaults__=tuple(new[role] if role else v for role,v in zip(bindings,values))
    for obj in list(g.values()):
        if isinstance(obj,type) and obj.__module__==g['__name__']:
            for method in vars(obj).values():defaults(method)
        elif callable(obj):defaults(obj)
    style_roles=getattr(root,'_button_theme_roles',{})
    for kind,style in g['RButton'].KINDS.items():
        for key,value in style.items():
            role=style_roles.setdefault((kind,key),resolve(value))
            if role:style[key]=new[role]
    root._button_theme_roles=style_roles
    def visit(widget):
        bindings=getattr(widget,'_theme_roles',{})
        supported=set(widget.keys())
        changes={}
        for option in ('bg','fg','insertbackground','selectbackground','highlightbackground'):
            if option not in supported:continue
            try:
                value=widget.cget(option)
                role=bindings.setdefault(('option',option),resolve(value))
                if role and value!=new[role]:changes[option]=new[role]
            except tk.TclError:pass
        if changes:widget.configure(**changes)
        for key,value in list(vars(widget).items()):
            role=bindings.setdefault(('attribute',key),resolve(value))
            if role:setattr(widget,key,new[role])
        if isinstance(widget,tk.Canvas):
            for item in widget.find_all():
                changes={}
                for option in ('fill','outline'):
                    try:
                        value=widget.itemcget(item,option)
                        role=bindings.setdefault(('item',item,option),resolve(value))
                        if role and value!=new[role]:changes[option]=new[role]
                    except tk.TclError:pass
                if changes:widget.itemconfigure(item,**changes)
            live=set(widget.find_all())
            bindings={key:role for key,role in bindings.items() if key[0]!='item' or key[1] in live}
        widget._theme_roles=bindings
        for child in widget.winfo_children():visit(child)
    visit(root)
    g.update(new)
    # Repaint blended hover/active shades that are not exact palette colors.
    def repaint(widget):
        if isinstance(widget,g['Card']):
            if hasattr(widget,'_hov_base'):
                widget._hov_base=widget.edge
                widget._hov_color=g['mix'](new['LINE'],new['ACC'],0.55)
            from types import SimpleNamespace
            widget._on_size(SimpleNamespace(width=max(2,widget.winfo_width()),height=max(2,widget.winfo_height())))
        elif isinstance(widget,tuple(g[k] for k in ('RButton','NavItem','RCheck','RSelect','RScrollbar'))):
            widget._draw()
        elif isinstance(widget,g['Bar']):widget._draw(max(2,widget.winfo_width()))
        for child in widget.winfo_children():repaint(child)
    repaint(root)

class Accent(tk.Canvas):
    """Animation is limited to a short banner; hidden windows stop drawing."""
    def __init__(self,parent,colors,style,options=None):
        self.colors=colors;self.style=style;self.phase=0;self.job=None
        self.options=options or (lambda:{})
        self.last_time=time.monotonic()
        self.picture=None;self.picture_key=None
        super().__init__(parent,height=64,bg=colors()['PANEL'],highlightthickness=0)
        self.bind('<Destroy>',self.dispose,add='+')
        self.bind('<Map>',lambda event:self.refresh(),add='+')
        self.bind('<Unmap>',lambda event:self.pause(),add='+')
        self.bind('<Configure>',lambda event:self.refresh(),add='+')
        self.tick()

    def dispose(self,event):
        if event.widget is self and self.job:
            self.after_cancel(self.job);self.job=None

    def pause(self):
        if self.job:self.after_cancel(self.job);self.job=None

    def number(self,key,default,low,high):
        try:return max(low,min(high,float(self.options().get(key,default))))
        except (TypeError,ValueError):return default

    def tick(self):
        self.job=None
        mode=self.style()
        height=int(self.number('animation_height',64,64,180))
        if int(self.cget('height'))!=height:self.configure(height=height)
        if self.winfo_viewable():
            self.delete('all')
            p=self.colors();self.configure(bg=p['PANEL'])
            intensity=self.number('animation_intensity',100,15,100)/100
            p=dict(p,ACC=blend(p['PANEL'],p['ACC'],intensity),LINE=blend(p['PANEL'],p['LINE'],intensity))
            density=self.number('animation_density',100,35,160)/100
            w=max(200,self.winfo_width());t=self.phase
            if mode=='Waves':
                for row in range(3):
                    points=[]
                    for x in range(0,w+12,12):points.extend((x,31+row*9+math.sin(x/85+t+row)*10))
                    self.create_line(*points,fill=p['ACC'] if row==0 else p['LINE'],width=2,smooth=True)
            elif mode=='Particles':
                count=max(12,min(120,math.ceil(w/30*density)))
                for i in range(count):
                    x=((i+.5)*w/count+t*14)%w;y=12+(i*29)%42+math.sin(t+i)*5
                    self.create_oval(x,y,x+3,y+3,fill=p['ACC'] if i%4==0 else p['LINE'],outline='')
            elif mode=='Grid':
                for x in range(-64,w+64,32):
                    shift=(t*10)%32
                    self.create_line(x+shift,0,x+shift-40,64,fill=p['LINE'])
                self.create_line(0,46,w,46,fill=p['ACC'])
            elif mode=='Double Helix':
                strands=[[],[]]
                for x in range(8,w,8):
                    phase=x/44+t
                    ys=(32+19*math.sin(phase),32-19*math.sin(phase))
                    for i in (0,1):strands[i].extend((x,ys[i]))
                    if x%24==8:self.create_line(x,ys[0],x,ys[1],fill=p['LINE'])
                for i,points in enumerate(strands):
                    if len(points)>=4:self.create_line(*points,fill=p['ACC'] if i==0 else blend(p['PANEL'],p['ACC'],0.4),width=2,smooth=True)
            elif mode=='Constellation':
                count=max(10,min(64,math.ceil(w/40*density)))
                stars=[(((i+.5)*w/count+t*(3+i%3))%w,12+(i*19)%40+math.sin(t/2+i)*4) for i in range(count)]
                for i,(x,y) in enumerate(stars):
                    for xx,yy in stars[i+1:]:
                        if (x-xx)**2+(y-yy)**2<75**2:self.create_line(x,y,xx,yy,fill=p['LINE'])
                    self.create_oval(x-1,y-1,x+2,y+2,fill=blend(p['PANEL'],p['ACC'],0.65),outline='')
            elif mode=='Fireflies':
                count=max(10,min(96,math.ceil(w/34*density)))
                for i in range(count):
                    x=((i+.5)*w/count+t*7)%w;y=30+math.sin(t/2+i*2)*20
                    glow=0.2+0.55*(math.sin(t+i)+1)/2
                    self.create_oval(x-4,y-4,x+4,y+4,fill=blend(p['PANEL'],p['ACC'],glow*0.15),outline='')
                    self.create_oval(x-1,y-1,x+1,y+1,fill=blend(p['PANEL'],p['ACC'],glow),outline='')
            elif mode=='Orbit':
                for i in range(5):
                    cx=w*(i+0.5)/5
                    self.create_oval(cx-35,18,cx+35,46,outline=p['LINE'])
                    x=cx+35*math.cos(t+i);y=32+14*math.sin(t+i)
                    self.create_oval(x-2,y-2,x+2,y+2,fill=p['ACC'],outline='')
            elif mode=='Aurora':
                for band in range(7):
                    points=[]
                    for x in range(-16,w+32,16):
                        y=30+math.sin(x/180+t*.3+band*.25)*14+math.cos(x/90-t*.2)*5
                        points.extend((x,y+band*3))
                    self.create_line(*points,fill=blend(p['PANEL'],p['ACC'],.12+band*.055),width=5,smooth=True)
            elif mode=='Starfield':
                for i in range(max(20,int(w/15*density))):
                    distance=((i*.619+t*.16)%1)
                    angle=i*2.39996
                    x=w/2+math.cos(angle)*distance*w*.6
                    y=32+math.sin(angle)*distance*42
                    r=.6+distance*1.5
                    self.create_oval(x-r,y-r,x+r,y+r,fill=blend(p['PANEL'],p['ACC'],.2+distance*.8),outline='')
            elif mode=='Rain':
                for i in range(max(15,int(w/18*density))):
                    x=(i*61.8+t*5)%w;y=(i*37+t*(18+i%11))%82-16
                    self.create_line(x,y,x-3,y+8+i%6,fill=blend(p['PANEL'],p['ACC'],.2+(i%5)*.12))
            elif mode=='Pulse':
                for ring in range(6):
                    radius=((t*12+ring*32)%192)
                    self.create_oval(w/2-radius*3,32-radius,w/2+radius*3,32+radius,
                                     outline=blend(p['PANEL'],p['ACC'],max(.05,1-radius/192)*.65),width=2)
            elif mode=='Picture':
                from PIL import Image,ImageOps,ImageTk
                path=self.options().get('app_background_image','')
                key=(path,w,height)
                if key!=self.picture_key:
                    self.picture=None;self.picture_key=key
                    try:
                        with Image.open(path) as original:
                            self.picture=ImageTk.PhotoImage(ImageOps.fit(original.convert('RGB'),(w,height)),master=self)
                    except (OSError,ValueError):pass
                if self.picture:self.create_image(0,0,image=self.picture,anchor='nw')
                else:self.create_text(w/2,height/2,text='Choose a picture in Settings → Backgrounds',fill=p['ACC'])
            if mode!='Picture' and height!=64:self.scale('all',0,0,1,height/64)
            now=time.monotonic()
            self.phase+=min(.15,max(0,now-self.last_time))*self.number('animation_speed',1,.25,2.5)
            self.last_time=now
            if mode not in ('Off','Picture'):
                fps=int(self.number('animation_fps',20,10,30))
                self.job=self.after(round(1000/fps),self.tick)

    def refresh(self):
        if self.job:self.after_cancel(self.job);self.job=None
        self.last_time=time.monotonic()
        self.delete('all');self.tick()

class Intro:
    """RETWEAKS startup screen: the original RETWEAKS splash (ui/splash.py), slowed down
    (owner request 2026-10-22: "use the old retweaks animation, but make it longer").

    600 x 360, centred on the work area, no version number. The chip outline draws, the pins light up,
    a scan line sweeps and the R traces in (about 2.4 s; frames pre-rendered from the original drawing
    code by tools/make_branding.py into assets/splash), then the wordmark and an honest status line.
    If loading takes longer, the scan line keeps sweeping until loading really finishes; then 0.3 s on
    the finished logo and a 0.55 s cross-fade into the main window. No other waiting."""

    def __init__(self, root, colors, status="Starting\u2026", on_done=None):
        import time, json, os
        self.root = root; self.colors = colors; self.closed = False; self.job = None; self.frame = 0
        self.on_done = on_done
        self.t0 = time.monotonic(); self.ready_at = None; self.fade_start = None; self._time = time.monotonic
        folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'splash')
        with open(os.path.join(folder, 'timing.json'), encoding='utf-8') as f:
            self.timing = tm = json.load(f)
        self.REVEAL, self.HOLD, self.FADE = tm['reveal_end'], tm['hold'], tm['fade']
        self.fps = tm['fps']
        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.reveal = [tk.PhotoImage(master=self.window, file=os.path.join(folder, f'reveal-{i:03d}.png'))
                       for i in range(tm['reveal_frames'])]
        self.loop = [tk.PhotoImage(master=self.window, file=os.path.join(folder, f'loop-{i:03d}.png'))
                     for i in range(tm['loop_frames'])]
        w, h = 600, 360
        x0, y0, aw, ah = self._work_area(root)
        self.window.geometry(f'{w}x{h}+{x0 + (aw - w) // 2}+{y0 + (ah - h) // 2}')
        self.bg = tm['bg']
        self.canvas = tk.Canvas(self.window, bg=self.bg, highlightthickness=1,
                                highlightbackground=tm['border'], bd=0)
        self.canvas.pack(fill='both', expand=True)
        import tkinter.font as tkfont
        families = set(tkfont.families(root))
        face = next((f for f in ('Segoe UI', 'Inter', 'DejaVu Sans') if f in families), 'Segoe UI')
        self.chip = self.canvas.create_image(w / 2, 62 + 60, image=self.reveal[0])
        self.word = self.canvas.create_text(w / 2, 214, text=BRAND, font=(face, 22, 'bold'),
                                            fill=self.bg)
        self.status = self.canvas.create_text(w / 2, 258, text=status, font=(face, 9), fill=self.bg)
        self.window.bind('<Destroy>', self.destroyed, add='+')
        self.window.lift()
        try:self.window.attributes('-topmost', True)
        except tk.TclError:pass
        self.tick()

    @staticmethod
    def _work_area(root):
        """The usable area of the primary screen (Windows: without the taskbar)."""
        try:
            import ctypes
            from ctypes import wintypes
            r = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):   # SPI_GETWORKAREA
                if r.right > r.left and r.bottom > r.top:
                    return r.left, r.top, r.right - r.left, r.bottom - r.top
        except Exception:
            pass
        return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()

    def destroyed(self, event):
        if event.widget is self.window and self.job:
            try:self.root.after_cancel(self.job)
            except tk.TclError:pass
            self.job = None

    def pump(self, status=None):
        """Called while the app is being built so the animation keeps moving."""
        if self.closed:return
        if status:
            try:self.canvas.itemconfigure(self.status, text=status)
            except tk.TclError:pass
        self._draw()
        try:self.window.update()
        except tk.TclError:pass

    def ready(self):
        """Loading really finished: finish the reveal at normal speed, hold, then cross-fade."""
        if self.ready_at is None:
            self.ready_at = self._time()
            try:self.canvas.itemconfigure(self.status, text='Ready')
            except tk.TclError:pass

    def _draw(self):
        t = self._time() - self.t0
        if t < self.REVEAL:
            img = self.reveal[min(len(self.reveal) - 1, int(t * self.fps))]
        elif self.ready_at is None:
            # still loading: the scan line keeps sweeping down and up (the original's SCAN_LOOP)
            img = self.loop[int((t - self.REVEAL) * self.fps) % len(self.loop)]
        else:
            img = self.reveal[-1]
        w0, w1 = self.timing['word']
        word = max(0.0, min(1.0, (t - w0) / max(0.01, w1 - w0)))
        try:
            self.canvas.itemconfigure(self.chip, image=img)
            self.canvas.itemconfigure(self.word, fill=blend(self.bg, self.timing['logo'], word))
            self.canvas.itemconfigure(self.status, fill=blend(self.bg, self.timing['subtext'], word))
        except tk.TclError:
            pass
        return t

    def tick(self):
        if self.closed:return
        self.job = None
        t = self._draw()
        now = self._time()
        if self.ready_at is not None and t >= self.REVEAL:
            if self.fade_start is None and now - max(self.ready_at, self.t0 + self.REVEAL) >= self.HOLD:
                try:
                    self.root.attributes('-alpha', 0.0)
                except tk.TclError:
                    pass
                self.root.deiconify(); self.window.lift()
                # 2.1: let the window map and paint while invisible, then start the fade clock, so its first
                # paint doesn't eat the fade (owner: the fade into the app "isn't really a fade")
                try:
                    self.root.update(); self.root.update_idletasks()
                except tk.TclError:
                    pass
                self.fade_start = now = self._time()
            if self.fade_start is not None:
                x = min(1.0, (now - self.fade_start) / self.FADE)
                f = x * x * (3 - 2 * x)
                try:
                    self.window.attributes('-alpha', 1 - f)
                    self.root.attributes('-alpha', f)
                except tk.TclError:
                    self.finish(); return
                if x >= 1.0:
                    self.finish(); return
        self.job = self.root.after(16, self.tick)

    def finish(self):
        if self.closed:return
        self.closed = True
        if self.job:
            try:self.root.after_cancel(self.job)
            except tk.TclError:pass
            self.job = None
        try:self.window.destroy()
        except tk.TclError:pass
        try:self.root.attributes('-alpha', 1.0)
        except tk.TclError:pass
        self.root.deiconify()
        if self.on_done:
            try:self.on_done()
            except Exception:pass
