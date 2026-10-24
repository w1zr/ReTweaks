"""Windows picture backgrounds, favorites and optional Lively video wallpapers."""
from pathlib import Path
import os
import tkinter as tk
from tkinter import filedialog
import webbrowser

from PIL import Image, ImageOps, ImageTk
from core import wallpaper, lively_wallpaper as lively
from rt_pages.common import button_row, card, label, run_bg
from rt_pages import settings_store


class WallpaperPage:
    def __init__(self,hub,tab,g):
        self.hub,self.g=hub,g
        self.busy=self.closed=False
        self.picture=None;self.video=None;self.photo=None;self.preview_image=None
        self.picture_name='';self.buttons=[]
        self.executable=lively.find_executable(hub.settings.get('lively_executable'))
        g['page_header'](tab,'RETWEAKS','Windows backgrounds','Preview pictures, save favorites and optionally add animated Windows wallpapers.')
        root=hub._scroll_area(tab)
        body=card(root,g,'Windows picture wallpaper','Preview first. Apply changes the picture on all monitors; nothing changes just by browsing. If an animated wallpaper covers the desktop, use Stop all below first.')
        self.preview=tk.Canvas(body,width=640,height=250,bg=g['PANEL2'],highlightthickness=1,highlightbackground=g['LINE'])
        self.preview.pack(fill='x',padx=16,pady=10)
        self.preview.create_text(320,125,text='Choose a picture or a preset to preview it',fill=g['MUTED'],font=(g['UI'],11))
        self.preview.bind('<Configure>',lambda event:self.draw_preview())
        row=button_row(body,g)
        self._button(row,'Choose picture…',self.choose_picture)
        self.preset=g['RSelect'](row,list(wallpaper.PRESETS),width=180,command=self.choose_preset)
        self.preset.pack(side='left',padx=8)
        self._button(row,'Preview preset',lambda:self.choose_preset(self.preset.get()))
        row=button_row(body,g)
        label(row,'Picture fit (all monitors)',g,10,padx=0)
        self.fit=g['RSelect'](row,list(wallpaper.POSITIONS),width=130,command=lambda value:self.draw_preview())
        self.fit.set('Fill');self.fit.pack(side='left',padx=(0,8))
        self._button(row,'Apply picture',self.apply_picture,'primary')
        self._button(row,'Restore previous picture',self.restore)
        self.picture_info=label(body,'Preview uses this panel’s shape; Span depends on your monitor layout. Restore returns previous pictures and fit, not a slideshow schedule.',g,9,g['MUTED'])
        row=button_row(body,g)
        self._button(row,'Favorite picture',lambda:self.favorite('picture'))
        self.current_info=label(body,'Current wallpaper: open this page to read Windows settings.',g,9,g['MUTED'])
        self.favorites=card(root,g,'Favorites','Keep your own pictures and video choices in one place.')
        row=button_row(self.favorites,g)
        self.favorite_picker=g['RSelect'](row,['No favorites yet'],width=280)
        self.favorite_picker.pack(side='left',padx=(0,8))
        self._button(row,'Load favorite',self.load_favorite)
        self._button(row,'Remove favorite',self.remove_favorite)

        animated=card(root,g,'Animated desktop wallpapers · optional Lively add-on',
                      'Use local videos/GIFs through the free Lively Wallpaper app. Missing Lively installs automatically when you choose an animated wallpaper action.')
        self.lively_info=label(animated,'Lively: connected executable found.' if self.executable else 'Lively is not connected yet.',g,10)
        row=button_row(animated,g)
        self._button(row,'Install Lively',lambda:self.task(self.install_lively))
        self._button(row,'Locate Lively.exe…',self.locate_lively)
        self._button(row,'Open Lively',lambda:self.lively_action('open'))
        self._button(row,'Official downloads',lambda:webbrowser.open('https://www.rocksdanister.com/lively/'))
        row=button_row(animated,g)
        self._button(row,'Choose video / GIF…',self.choose_video)
        self._button(row,'Preview video',self.preview_video)
        self._button(row,'Favorite video',lambda:self.favorite('video'))
        self.video_info=label(animated,'No video selected. Preview opens the file in your normal Windows player.',g,9,g['MUTED'])
        row=button_row(animated,g)
        label(row,'Lively screen',g,10,padx=0)
        self.monitor=g['RSelect'](row,['Primary','1','2','3','4'],width=100)
        self.monitor.pack(side='left',padx=(0,8))
        self._button(row,'Use animated wallpaper',lambda:self.lively_action('set'),'primary')
        row=button_row(animated,g)
        for title,action in [('Pause','pause'),('Resume','resume'),('Mute','mute'),('Stop all','stop')]:
            self._button(row,title,lambda value=action:self.lively_action(value))
        label(animated,'Open Lively to configure its fullscreen/game and battery pause rules, monitor layout, '
              'library and video playback. Commands show whether they were sent; playback is controlled by Lively. '
              'Stop all closes Lively wallpapers and exposes your Windows picture.',g,9,g['MUTED'])
        self.status=label(root,'',g,10,padx=0)
        self.refresh_favorites()

    def _button(self,row,text,command,kind='default'):
        button=self.g['RButton'](row,text,command,kind=kind)
        button.pack(side='left',padx=(0,7));self.buttons.append(button)

    def task(self,fn,done=None):
        if self.busy or self.closed:return
        self.busy=True
        for button in self.buttons:button.set_enabled(False)
        self.status.config(text='Working…')
        def ready(result):
            if self.closed:return
            self.busy=False
            for button in self.buttons:button.set_enabled(True)
            if isinstance(result,Exception):self.status.config(text=str(result));return
            if done:done(result)
            else:self.status.config(text=str(result))
        run_bg(self.hub,fn,ready)

    def choose_picture(self):
        if self.busy:return
        path=filedialog.askopenfilename(parent=self.hub,title='Choose wallpaper picture',filetypes=[('Images','*.png *.jpg *.jpeg *.webp *.bmp')])
        if path:self.load_picture(path,Path(path).name)

    def load_picture(self,path,name):
        def ready(result):
            self.picture,self.preview_image=result;self.picture_name=name;self.draw_preview()
            self.status.config(text=f'Previewing {name}. Click Apply picture to change Windows.')
        self.task(lambda:self.prepare_preview(wallpaper.prepare_image(path)),ready)

    @staticmethod
    def prepare_preview(path):
        with Image.open(path) as source:
            image=source.convert('RGB');image.thumbnail((1600,900),Image.Resampling.LANCZOS)
        return str(path),image

    def choose_preset(self,name):
        if self.busy:return
        def ready(result):
            self.picture,self.preview_image=result;self.picture_name=name;self.draw_preview()
            self.status.config(text=f'Previewing {name}. Click Apply picture to change Windows.')
        self.task(lambda:self.prepare_preview(wallpaper.preset_image(name)),ready)

    def draw_preview(self):
        if self.preview_image is None or self.closed:return
        width=max(200,self.preview.winfo_width());height=250
        try:
            source=self.preview_image.copy()
            if source:
                mode=self.fit.get()
                image=Image.new('RGB',(width,height),self.g['BG'])
                if mode in ('Fill','Span'):image=ImageOps.fit(source,(width,height))
                elif mode=='Stretch':image=source.resize((width,height),Image.Resampling.LANCZOS)
                elif mode=='Tile':
                    tile=ImageOps.contain(source,(200,130))
                    for x in range(0,width,tile.width):
                        for y in range(0,height,tile.height):image.paste(tile,(x,y))
                else:
                    fitted=ImageOps.contain(source,(width,height))
                    image.paste(fitted,((width-fitted.width)//2,(height-fitted.height)//2))
                self.photo=ImageTk.PhotoImage(image,master=self.preview)
            self.preview.delete('all');self.preview.create_image(0,0,image=self.photo,anchor='nw')
        except OSError as exc:self.status.config(text=str(exc))

    def apply_picture(self):
        if not self.picture:self.status.config(text='Choose a picture or preset first.');return
        path,fit=self.picture,self.fit.get()
        self.task(lambda:wallpaper.apply_picture(path,fit),lambda result:self.status.config(text='Windows confirmed the picture and fit. The previous pictures are saved for Restore.'))

    def restore(self):
        self.task(wallpaper.restore_picture,lambda result:self.status.config(text='Windows confirmed the previous pictures and fit were restored.'))

    def records(self):
        saved=self.hub.settings.get('wallpaper_favorites',[])
        return [r for r in saved if isinstance(r,dict) and r.get('kind') in ('picture','video') and isinstance(r.get('path'),str) and isinstance(r.get('name'),str)] if isinstance(saved,list) else []

    def save_favorites(self,records):
        self.hub.settings['wallpaper_favorites']=records
        settings_store.save(self.hub.settings)
        self.refresh_favorites()

    def favorite(self,kind):
        path=self.picture if kind=='picture' else self.video
        if not path:self.status.config(text='Choose a '+kind+' first.');return
        records=self.records()
        if not any(r['path']==path for r in records):
            records.append({'name':self.picture_name if kind=='picture' else Path(path).name,'path':path,'kind':kind})
            self.save_favorites(records)
        self.status.config(text='Saved to favorites.')

    def refresh_favorites(self):
        self.favorite_rows=self.records()
        self.favorite_picker.values=[f'{i+1}. {r["name"]} ({r["kind"]})' for i,r in enumerate(self.favorite_rows)] or ['No favorites yet']
        self.favorite_picker.set(self.favorite_picker.values[0])

    def selected_favorite(self):
        try:index=self.favorite_picker.values.index(self.favorite_picker.get());return self.favorite_rows[index]
        except (ValueError,IndexError):return None

    def load_favorite(self):
        record=self.selected_favorite()
        if not record:return
        if record['kind']=='picture':self.load_picture(record['path'],record['name'])
        else:self.video=record['path'];self.video_info.config(text=record['name'])

    def remove_favorite(self):
        record=self.selected_favorite()
        if record:self.save_favorites([r for r in self.records() if r!=record])

    def choose_video(self):
        if self.busy:return
        path=filedialog.askopenfilename(parent=self.hub,title='Choose animated wallpaper',filetypes=[('Video / GIF','*.mp4 *.webm *.mkv *.avi *.mov *.gif')])
        if path:self.video=path;self.video_info.config(text=Path(path).name)

    def preview_video(self):
        if not self.video or not Path(self.video).is_file():self.status.config(text='Choose an existing video first.');return
        try:os.startfile(self.video)
        except OSError as exc:self.status.config(text=str(exc))

    def locate_lively(self):
        path=filedialog.askopenfilename(parent=self.hub,title='Locate Lively executable',filetypes=[('Lively executable','*.exe')])
        if not path:return
        found=lively.find_executable(path)
        if not found:self.status.config(text='Choose Lively.exe or the official Lively command utility.');return
        self.executable=found;self.hub.settings['lively_executable']=found;settings_store.save(self.hub.settings)
        self.lively_info.config(text='Lively executable connected.')

    def install_lively(self):
        result=lively.install()
        self.executable=result
        return 'Installation finished. Open Lively to finish setup.' if result else 'Installer finished. Open Lively and use Locate Lively.exe to connect it.'

    def lively_action(self,action):
        executable=lively.find_executable(self.executable)
        if not executable and action in ('open','set'):
            from core.dependencies import enabled
            if enabled(self.hub):
                from rt_dependencies import ensure
                ensure(self.hub,'lively',lambda:self.lively_action(action))
                return
        monitor=None if self.monitor.get()=='Primary' else int(self.monitor.get())
        self.task(lambda:lively.command(executable,action,self.video,monitor))

    def on_shown(self):
        self.refresh_favorites()
        self.executable=lively.find_executable(self.hub.settings.get('lively_executable') or self.executable)
        self.lively_info.config(text='Lively executable connected.' if self.executable else 'Optional: install or locate Lively for animated desktop wallpapers.')
        def ready(result):
            if self.closed:return
            if isinstance(result,Exception):self.current_info.config(text=str(result));return
            names=[Path(m['image']).name or 'Solid color' for m in result['monitors']]
            self.current_info.config(text='Current Windows pictures: '+', '.join(names))
        run_bg(self.hub,wallpaper.current,ready)

    def close(self):
        self.closed=True
