"""Grouped navigation over existing pages; original routes and lifecycle stay intact."""
import tkinter as tk

# (section label, original page name, original target). No page objects are rebuilt.
GROUPS = {
    'Dashboard': [('Overview','Dashboard','Dashboard'),('Quick start','Quick start','Dashboard')],
    'Hardware & cooling': [('Hardware','Hardware','Hardware'),('PC specs','PC specs',4),
                 ('Temperatures','Temperatures','Temperatures'),('Fans','Fan control','Fan control'),
                 ('RGB lighting','RGB lighting','RGB lighting'),('Display','Display','Display')],
    'Health & recovery': [('Health check','Health Check','Health Check'),('Backups & fixes','Backups & fixes',11)],
    'Benchmark & FPS': [('Graphics benchmark','Benchmark',8),('FPS test & overlay','FPS overlay','FPS overlay'),
                  ('Comparisons','Snapshots','Snapshots')],
    'Tweaks & presets': [('Manual tweaks','Individual tweaks',1),('Presets','Presets',15),('CTT library','CTT library',2),
               ('Windows tweaks','Windows tweaks',17),('Customize','Customize',10)],
    'Gaming tools': [('Game profiles','Game profiles',3),('Config files','Game config files','Game config files'),
               ('Program rules','Program rules','Program rules'),('Crosshair','Crosshair','Crosshair'),
               ('Auto clicker','Auto clicker',21),('Mouse tests','Fun tools','Fun tools')],
    'Storage & cleanup': [('Storage','Storage',9),('Cleanup','Cleanup','Cleanup')],
    'Windows appearance': [('Windhawk','Windhawk',29),
                    ('Transparent TB','Transparent TB (taskbar)','Transparent TB (taskbar)')],
    'Windows tools': [('Startup apps','Startup apps','Startup apps'),
                      ('Run','Run','Run'),('Utilities','Tools',16),('Advanced','Advanced tools',12),
                      ('Windows Activation','Windows Activation',28),('Daily Tools','Daily Tools',26)],
    'PC planning': [('3D PC Builder','3D PC Builder',25),('Bottleneck','Bottleneck',19),
                    ('PC value','PC Value Checker',24)],
    'Help & activity': [('Help','Help',6),('Tips','Tips',5),('Activity','Activity',7)],
}

NAV = [
    ('MONITOR', [('Dashboard','Dashboard'),('Hardware & cooling','Hardware & cooling'),('Health & recovery','Health & recovery'),
                 ('Benchmark & FPS','Benchmark & FPS')]),
    ('OPTIMIZE', [('Tweaks & presets','Tweaks & presets'),('Gaming tools','Gaming tools'),('Network','Network'),('Drivers',22)]),
    ('TOOLS', [('Storage & cleanup','Storage & cleanup'),('File Transfers','File Transfers'),('Windows backgrounds','Backgrounds'),('Windows appearance','Windows appearance'),
               ('App Starter',23),
               ('Windows tools','Windows tools'),('PC planning','PC planning'),('Audio Mixer',27),
               ('Browser','Browser'),('AI assistant',20),('Help & activity','Help & activity')]),
]


GROUP_ALIASES = {'Hardware': 'Hardware & cooling', 'Benchmark': 'Benchmark & FPS', 'Tweaks': 'Tweaks & presets', 'Games': 'Gaming tools', 'Storage': 'Storage & cleanup', 'Appearance': 'Windows appearance', 'System tools': 'Windows tools', 'PC builder': 'PC planning', 'Help': 'Help & activity', 'Storage & transfers': 'Storage & cleanup'}

def preferred_section(settings,group):
    saved=settings.get('navigation_sections')
    if not isinstance(saved,dict):return None
    if group in saved:return saved[group]
    return next((saved[old] for old,new in GROUP_ALIASES.items() if new==group and old in saved),None)


def target_index(hub,target):
    return target if isinstance(target,int) else hub.rt_tabs.get(target)


def group_for_index(hub,index):
    return next((name for name,sections in GROUPS.items()
                 if any(target_index(hub,target)==index for _,_,target in sections)),None)


def group_for_name(name):
    return next((group for group,sections in GROUPS.items()
                 if any(alias==name for _,alias,_ in sections)),GROUP_ALIASES.get(name,name))


class SectionNavigation:
    def __init__(self,hub,g):
        self.hub,self.g=hub,g
        self.frame=tk.Frame(hub.content,bg=g['BG'])
        self.group=None
        self.buttons=[]
        self.frame.bind('<Configure>',lambda event:self.layout(event.width))
        self.width=0

    def show(self,index):
        group=group_for_index(self.hub,index)
        if not group or len({target_index(self.hub,t) for _,_,t in GROUPS[group]}) == 1:
            self.frame.pack_forget();self.group=None;return
        if group!=self.group:
            for child in self.frame.winfo_children():child.destroy()
            self.group=group;self.buttons=[];self.width=0
            tk.Label(self.frame,text=group,bg=self.g['BG'],fg=self.g['MUTED'],font=(self.g['UI'],10,'bold'),
                     anchor='w').pack(fill='x',pady=(0,5))
            self.chips=tk.Frame(self.frame,bg=self.g['BG']);self.chips.pack(fill='x')
            for title,alias,target in GROUPS[group]:
                target=target_index(self.hub,target)
                if target is None:continue
                button=self.g['RButton'](self.chips,title,lambda i=target:self.hub.show_tab(i),kind='ghost')
                self.buttons.append((button,target,alias))
        for button,target,alias in self.buttons:
            button.set_kind('primary' if target==index else 'ghost')
            if target==index:
                preferences=self.hub.settings.get('navigation_sections')
                saved=dict(preferences) if isinstance(preferences,dict) else {}
                if saved.get(group)!=alias:
                    saved[group]=alias;self.hub.settings['navigation_sections']=saved
                    self.hub.save_settings()
        self.frame.pack(fill='x',padx=(26,12),pady=(12,0),before=self.hub.tabs[index])
        self.layout(max(240,self.hub.content.winfo_width()-38))

    def layout(self,width):
        if not self.buttons or width==self.width:return
        self.width=width
        row=column=used=0
        for button,_,_ in self.buttons:
            size=button.bw+8
            if used and used+size>width:
                row+=1;column=used=0
            button.grid(row=row,column=column,sticky='w',padx=(0,8),pady=(0,5))
            used+=size;column+=1
