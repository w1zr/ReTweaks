"""Visual theme choices and live in-app background controls for Settings."""
import tkinter as tk
from tkinter import filedialog

import appearance as ap
from core import wallpaper
from rt_pages.common import button_row, card, label, run_bg


class BackgroundControls:
    def __init__(self, page, parent, g):
        self.page, self.hub, self.g = page, page.hub, g
        body = card(parent, g, 'Backgrounds & animation',
                    'Choose an animation or picture for ReTweaks. Desktop wallpapers have their own page.')
        label(body, 'Animation preview', g, 12, bold=True)
        row=button_row(body,g)
        self.style=g['RSelect'](row,list(ap.ANIMATIONS),width=200,command=self.change)
        self.hub.animation_selector=self.style
        self.style.set(self.hub.animation);self.style.pack(side='left',padx=(0,8))
        g['RButton'](row,'Windows wallpapers…',lambda:self.hub.show_tab(self.hub.rt_tabs['Backgrounds'])).pack(side='left')
        # A larger preview without changing the height of the user's existing banners.
        self.preview = ap.Accent(body, lambda: {key:g[key] for key in ('PANEL','LINE','ACC')},
                                 lambda:self.hub.animation,
                                 lambda:dict(self.hub.settings,animation_height=150))
        self.preview.pack(fill='x', padx=16, pady=6)
        self.hub.accents.append(self.preview)
        self.advanced_button = g['RButton'](body, 'More animation options', self.toggle_advanced)
        self.advanced_button.pack(anchor='w', padx=16, pady=6)
        self.advanced = tk.Frame(body, bg=body.cget('bg'))
        self.selectors = {}
        options = [
            ('Speed', 'animation_speed', {'Slow':.5,'Normal':1,'Fast':1.5,'Very fast':2}, 1),
            ('Brightness', 'animation_intensity', {'Subtle':35,'Balanced':65,'Bright':100}, 100),
            ('Detail', 'animation_density', {'Low':50,'Normal':100,'High':150}, 100),
            ('Frame rate', 'animation_fps', {'Low power · 10 FPS':10,'Balanced · 20 FPS':20,'Smooth · 30 FPS':30}, 20),
            ('Banner size', 'animation_height', {'Compact':64,'Medium':100,'Large':150}, 64),
        ]
        for title,key,values,default in options:
            row = button_row(self.advanced,g)
            label(row,title,g,10,padx=0)
            control = g['RSelect'](row,list(values),width=210,
                                   command=lambda value,k=key,choices=values:self.set_option(k,choices[value]))
            current = self.hub.settings.get(key,default)
            control.set(next((name for name,val in values.items() if val==current),next(name for name,val in values.items() if val==default)))
            control.pack(side='left')
            self.selectors[key]=control
        row=button_row(body,g)
        g['RButton'](row,'Choose background picture…',self.choose_picture).pack(side='left',padx=(0,8))
        g['RButton'](row,'Pause animation',lambda:self.change('Off')).pack(side='left')
        self.message=label(body,'Pictures fill the accent banners. Animations pause when hidden; frame rate is capped at 30 FPS.',g,9,g['MUTED'])
        self.refresh()

    def toggle_advanced(self):
        if self.advanced.winfo_manager():
            self.advanced.pack_forget()
            self.advanced_button.label='More animation options'
        else:
            self.advanced.pack(fill='x',after=self.advanced_button)
            self.advanced_button.label='Fewer animation options'
        self.advanced_button._draw()

    def refresh(self):
        self.style.set(self.hub.animation)
        self.preview.refresh()

    def set_option(self,key,value):
        self.page.set_setting(key,value)
        for accent in self.hub.accents:accent.refresh()

    def change(self,style):
        self.hub.change_animation(style)
        self.hub.animation_selector.set(style)
        self.style.set(style)
        self.preview.refresh()

    def choose_picture(self):
        path=filedialog.askopenfilename(parent=self.hub,title='Choose a ReTweaks background picture',
                                       filetypes=[('Images','*.png *.jpg *.jpeg *.webp *.bmp')])
        if not path:return
        self.message.config(text='Preparing the selected picture…')
        def ready(result):
            if isinstance(result,Exception):self.message.config(text=str(result));return
            self.page.set_setting('app_background_image',str(result))
            self.change('Picture')
            self.message.config(text='Picture applied to the ReTweaks accent banners. Original file preserved.')
        run_bg(self.hub,lambda:wallpaper.prepare_image(path),ready)
