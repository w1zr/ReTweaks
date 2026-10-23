"""Daily Tools UI: local utilities, explicit file actions and background work."""
import ctypes
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog,messagebox
from PIL import Image,ImageOps,ImageTk,ImageGrab
import daily_toolkit as kit

IMAGE_TYPES=[('Images','*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.ico *.gif'),('All files','*.*')]

class DailyToolsPage:
    def __init__(self,hub,tab,g):
        self.hub=hub;self.g=g;self.windows={};self.events=queue.Queue();self.closed=False
        self.awake=tk.BooleanVar(value=False);self.top=tk.BooleanVar(value=False)
        body=hub.page(tab,'Daily Tools','Useful everyday tools. Files stay on your computer; no sign-in or AI connection is needed.')
        options=tk.Frame(body,bg=g['BG']);options.pack(fill='x',padx=16,pady=10)
        g['RCheck'](options,'Keep RETWEAKS on top',self.top,command=self.on_top).pack(side='left',padx=(0,20))
        g['RCheck'](options,'Keep PC awake while RETWEAKS is open',self.awake,command=self.keep_awake).pack(side='left')
        self.power_status=hub.label(body,'Normal sleep settings are active.',9,g['MUTED'])
        grid=tk.Frame(body,bg=g['BG']);grid.pack(fill='x')
        tools=[('OCR','Image to text','Extract text from a photo or screenshot, or paste an image. Edit the result, copy it, or save a text file.',self.ocr),
               ('IMG','Image converter & resizer','Convert batches to PNG, JPEG, WebP, BMP or ICO. Resize while preserving proportions and keep your originals.',self.converter),
               ('PDF','Images to PDF','Combine images into a PDF in the order you choose. Reorder pages before exporting.',self.pdf),
               ('TXT','Text toolbox','Clean up pasted text, remove duplicate lines, format JSON, or encode and decode URLs and Base64.',self.text_tool),
               ('SHA','File checksum','Calculate a SHA-256 fingerprint and compare it with a publisher-provided checksum.',self.checksum),
               ('HEX','Image color picker','Open an image and click a pixel to get its HEX and RGB colors for a design or theme.',self.color)]
        for i,(tag,title,description,command) in enumerate(tools):
            grid.columnconfigure(i%2,weight=1,uniform='daily')
            card=g['Card'](grid);card.grid(row=i//2,column=i%2,sticky='nsew',padx=(0,10),pady=6)
            hub.label(card.body,tag,12,g['ACC']);hub.label(card.body,title,16)
            label=hub.label(card.body,description,10,g['MUTED']);card.wrap(label,margin=32)
            g['RButton'](card.body,'Open tool',command).pack(anchor='w',padx=16,pady=(4,16))
        hub.label(body,'Image exports use new files and leave originals unchanged. Animated images export the first frame. JPEG/BMP and PDF use a white background for transparency. OCR accuracy depends on image quality and installed Windows languages.',9,g['MUTED'])
        hub.bind('<Destroy>',self.destroy,add='+');self.job=hub.after(100,self.poll)
    def on_top(self):self.hub.attributes('-topmost',self.top.get())
    def keep_awake(self):
        flags=0x80000003 if self.awake.get() else 0x80000000
        if not ctypes.windll.kernel32.SetThreadExecutionState(flags):
            self.awake.set(False);self.power_status.config(text='Windows could not change the sleep request.');return
        self.power_status.config(text='Keeping the PC and display awake while RETWEAKS is open. Closing RETWEAKS restores normal sleep behavior.' if self.awake.get() else 'Normal sleep settings are active.')
    def window(self,key,title):
        old=self.windows.get(key)
        if old and old['window'].winfo_exists():old['window'].lift();return None
        win=tk.Toplevel(self.hub);win.title(title+' - RETWEAKS');win.geometry('920x730');win.minsize(720,560);win.configure(bg=self.g['BG']);win.transient(self.hub)
        self.hub.label(win,title,20)
        state={'window':win,'busy':False,'closed':False,'cancel':threading.Event()};self.windows[key]=state
        def close():state['closed']=True;state['cancel'].set();win.destroy()
        win.protocol('WM_DELETE_WINDOW',close)
        return state
    def label(self,parent,text):
        label=self.hub.label(parent,text,10,self.g['MUTED'])
        def wrap(event):
            width=max(200,event.width)
            if int(label.cget('wraplength'))!=width:label.config(wraplength=width)
        label.bind('<Configure>',wrap)
        return label
    def row(self,parent):
        row=tk.Frame(parent,bg=self.g['BG']);row.pack(fill='x',padx=16,pady=6);return row
    def button(self,parent,title,command):
        button=self.g['RButton'](parent,title,command);button.pack(side='left',padx=(0,8));return button
    def text_box(self,parent):
        frame=tk.Frame(parent,bg=self.g['PANEL']);frame.pack(fill='both',expand=True,padx=16,pady=8)
        text=tk.Text(frame,wrap='word',undo=True,bg=self.g['PANEL'],fg=self.g['FG'],insertbackground=self.g['ACC'],font=(self.g['UI'],11),relief='flat',padx=12,pady=12)
        scroll=tk.Scrollbar(frame,command=text.yview);scroll.pack(side='right',fill='y');text.config(yscrollcommand=scroll.set);text.pack(side='left',fill='both',expand=True)
        return text
    def replace(self,text,value):text.replace('1.0','end-1c',value)
    def copy(self,value):self.hub.clipboard_clear();self.hub.clipboard_append(value);self.hub.update_idletasks()
    def save_text(self,state,text):
        path=filedialog.asksaveasfilename(parent=state['window'],title='Save text',defaultextension='.txt',filetypes=[('Text file','*.txt')])
        if path:
            try:Path(path).write_text(text.get('1.0','end-1c'),encoding='utf-8')
            except OSError as exc:messagebox.showerror('Could not save text',str(exc),parent=state['window'])
    def background(self,state,work,done,status,buttons=()):
        if state['busy']:return
        state['busy']=True;status.config(text='Working...')
        for button in buttons:button.set_enabled(False)
        def run():
            try:result=work();error=None
            except Exception as exc:result=None;error=str(exc)
            self.events.put((state,result,error,done,status,buttons))
        threading.Thread(target=run,daemon=True).start()
    def poll(self):
        if self.closed:return
        try:
            while True:
                state,result,error,done,status,buttons=self.events.get_nowait();state['busy']=False
                if state['closed'] or not state['window'].winfo_exists():continue
                for button in buttons:button.set_enabled(True)
                if error:status.config(text=error)
                else:
                    status.config(text='Finished.');done(result)
        except queue.Empty:pass
        self.job=self.hub.after(100,self.poll)
    def ocr(self):
        state=self.window('ocr','Image to text')
        if not state:return
        win=state['window'];self.label(win,'Choose a clear image or paste an image from your clipboard. Recognition runs locally using Windows OCR.')
        row=self.row(win);status=self.label(win,'Choose an image to begin.');text=self.text_box(win)
        def recognize(source):
            def done(result):
                self.replace(text,result['text']);status.config(text='Recognized using '+result['language']+'. Review the text for mistakes.' if result['text'].strip() else 'No text found. Try a clearer, larger image.')
            self.background(state,lambda:kit.extract_text(source),done,status,buttons)
        def choose():
            if state['busy']:return
            path=filedialog.askopenfilename(parent=win,filetypes=IMAGE_TYPES)
            if path:recognize(path)
        def paste():
            if state['busy']:return
            try:
                image=ImageGrab.grabclipboard()
                if isinstance(image,list) and image:recognize(image[0])
                elif isinstance(image,Image.Image):recognize(image)
                else:status.config(text='The clipboard does not contain an image. Copy a screenshot or choose an image file.')
            except Exception as exc:status.config(text=str(exc))
        buttons=[self.button(row,'Choose image',choose),self.button(row,'Paste image',paste)]
        row=self.row(win);self.button(row,'Copy text',lambda:self.copy(text.get('1.0','end-1c')));self.button(row,'Save TXT',lambda:self.save_text(state,text))
        state['text']=text
    def converter(self):
        state=self.window('converter','Image converter & resizer')
        if not state:return
        win=state['window'];paths=[]
        self.label(win,'Select images and an output folder. Width/height are maximum bounds; proportions are preserved and smaller images are not enlarged. Use 0 for no limit. ICO exports are square with transparent padding, up to 256 pixels. Exports omit source EXIF/GPS metadata.')
        row=self.row(win);chosen=self.label(win,'No images selected.');status=self.label(win,'Ready.');output=self.text_box(win)
        def choose():
            if state['busy']:return
            selected=filedialog.askopenfilenames(parent=win,filetypes=IMAGE_TYPES)
            if selected:paths[:]=selected;chosen.config(text=f'{len(paths)} images selected.')
        choose_button=self.button(row,'Choose images',choose)
        format=self.g['RSelect'](row,list(kit.FORMATS),width=150);format.pack(side='left',padx=8)
        dims=self.row(win);self.label(dims,'Max width');width=tk.StringVar(value='0');self.g['REntry'](dims,width,width_px=110).pack(side='left',padx=5)
        self.label(dims,'Max height');height=tk.StringVar(value='0');self.g['REntry'](dims,height,width_px=110).pack(side='left',padx=5)
        # Labels in a horizontal control row must use pack(side=left).
        for child in dims.winfo_children():
            if isinstance(child,tk.Label):child.pack_configure(side='left',fill='none',padx=4)
        def start():
            if state['busy']:return
            if not paths:status.config(text='Choose at least one image first.');return
            try:bounds=kit.bounds_from(width.get(),height.get())
            except ValueError as exc:status.config(text=str(exc));return
            folder=filedialog.askdirectory(parent=win,title='Choose folder for new image files')
            if not folder:return
            selected=tuple(paths);fmt=format.get()
            def work():
                results=[]
                for path in selected:
                    if state['cancel'].is_set():break
                    try:results.append('Saved: '+str(kit.convert_image(path,folder,fmt,bounds)))
                    except Exception as exc:results.append('Failed: '+Path(path).name+' - '+str(exc))
                return '\n'.join(results)
            self.background(state,work,lambda result:self.replace(output,result),status,[choose_button,start_button])
        start_button=self.button(self.row(win),'Convert to new files',start)
        state.update(paths=paths,width=width,height=height,format=format,output=output)
    def pdf(self):
        state=self.window('pdf','Images to PDF')
        if not state:return
        win=state['window'];paths=[]
        self.label(win,'Choose up to 50 images. Each image becomes one page; export follows the order below. Larger images are limited to 2400 pixels on their longest side.')
        row=self.row(win)
        list_frame=tk.Frame(win,bg=self.g['PANEL']);list_frame.pack(fill='both',expand=True,padx=16,pady=8)
        box=tk.Listbox(list_frame,bg=self.g['PANEL'],fg=self.g['FG'],selectbackground=self.g['ACC2'],font=(self.g['UI'],11),exportselection=False);box.pack(side='left',fill='both',expand=True)
        scroll=tk.Scrollbar(list_frame,command=box.yview);scroll.pack(side='right',fill='y');box.config(yscrollcommand=scroll.set)
        status=self.label(win,'Choose images to begin.')
        def refresh():
            box.delete(0,'end')
            for i,path in enumerate(paths):box.insert('end',f'{i+1}. {Path(path).name}')
        def add():
            if state['busy']:return
            selected=filedialog.askopenfilenames(parent=win,filetypes=IMAGE_TYPES)
            if len(paths)+len(selected)>50:status.config(text='Use at most 50 images per PDF.');return
            paths.extend(selected);refresh()
        def move(step):
            if state['busy'] or not box.curselection():return
            i=box.curselection()[0];j=i+step
            if 0<=j<len(paths):paths[i],paths[j]=paths[j],paths[i];refresh();box.selection_set(j)
        def remove():
            if not state['busy'] and box.curselection():paths.pop(box.curselection()[0]);refresh()
        add_button=self.button(row,'Add images',add);self.button(row,'Move up',lambda:move(-1));self.button(row,'Move down',lambda:move(1));self.button(row,'Remove selected',remove)
        def export():
            if state['busy']:return
            if not paths:status.config(text='Choose images first.');return
            folder=filedialog.askdirectory(parent=win,title='Save PDF in folder')
            if folder:
                selected=tuple(paths)
                self.background(state,lambda:kit.images_to_pdf(selected,folder),lambda path:status.config(text='Saved: '+str(path)),status,[add_button,export_button])
        export_button=self.button(self.row(win),'Create PDF',export);state['paths']=paths
    def text_tool(self):
        state=self.window('text','Text toolbox')
        if not state:return
        win=state['window'];self.label(win,'Paste or type text below. Transformations stay local. Undo restores previous text. Base64 is an encoding, not encryption.')
        row=self.row(win);action=self.g['RSelect'](row,kit.TEXT_ACTIONS,width=240);action.pack(side='left',padx=(0,8))
        status=self.label(win,'Ready.');text=self.text_box(win)
        def apply():
            try:
                value=text.get('1.0','end-1c')
                if len(value)>2000000:raise ValueError('Use less than 2 million characters for an interactive text transformation.')
                result=kit.transform_text(value,action.get());text.edit_separator();self.replace(text,result);text.edit_separator();status.config(text='Applied '+action.get()+'.')
            except Exception as exc:status.config(text=str(exc))
        def undo():
            try:text.edit_undo()
            except tk.TclError:pass
        self.button(row,'Apply',apply);self.button(row,'Undo',undo)
        row=self.row(win);self.button(row,'Copy text',lambda:self.copy(text.get('1.0','end-1c')));self.button(row,'Save TXT',lambda:self.save_text(state,text))
        state.update(text=text,apply=apply,action=action)
    def checksum(self):
        state=self.window('checksum','File checksum')
        if not state:return
        win=state['window'];self.label(win,'Compute a SHA-256 fingerprint. A matching checksum confirms that bytes match the provided value; it does not prove a file is safe.')
        row=self.row(win);status=self.label(win,'Choose a file to calculate its SHA-256.');text=self.text_box(win);state['digest']=None
        self.label(win,'Optional expected SHA-256 (64 hexadecimal characters):');expected=tk.StringVar();entry=self.g['REntry'](win,expected,width_px=600);entry.pack(fill='x',padx=16,pady=6)
        def choose():
            if state['busy']:return
            path=filedialog.askopenfilename(parent=win)
            if not path:return
            def done(digest):state['digest']=digest;self.replace(text,Path(path).name+'\n\n'+digest)
            state['digest']=None;self.background(state,lambda:kit.sha256_file(path),done,status,[choose_button])
        def compare():
            value=expected.get().strip().lower()
            if not state['digest']:status.config(text='Calculate a file checksum first.');return
            if len(value)!=64 or any(c not in '0123456789abcdef' for c in value):status.config(text='Enter exactly 64 hexadecimal characters.');return
            status.config(text='MATCH - the checksums are identical.' if value==state['digest'] else 'DOES NOT MATCH - this file has different contents.')
        choose_button=self.button(row,'Choose file',choose);self.button(row,'Compare',compare);self.button(row,'Copy SHA-256',lambda:self.copy(state['digest'] or ''))
    def color(self):
        state=self.window('color','Image color picker')
        if not state:return
        win=state['window'];self.label(win,'Choose an image, then click its preview to sample a pixel. Transparent pixels are displayed against white.')
        row=self.row(win);value=tk.StringVar(value='No color selected');self.label(win,'HEX and RGB:');field=self.g['REntry'](win,value);field.entry.configure(state='readonly',readonlybackground=self.g['PANEL2']);field.pack(fill='x',padx=16,pady=8)
        preview=tk.Label(win,bg=self.g['PANEL']);preview.pack(expand=True,pady=10)
        status=self.label(win,'Choose an image to begin.')
        def choose():
            path=filedialog.askopenfilename(parent=win,filetypes=IMAGE_TYPES)
            if not path:return
            try:
                with Image.open(path) as original:image=kit.opaque(ImageOps.exif_transpose(original))
                state['image']=image;display=image.copy();display.thumbnail((780,440),Image.Resampling.LANCZOS);state['preview']=display;state['photo']=ImageTk.PhotoImage(display,master=win);preview.config(image=state['photo']);status.config(text='Click the preview. Color is sampled from the corresponding original image pixel.')
            except Exception as exc:status.config(text=str(exc))
        def sample(event):
            image=state.get('image')
            if image is None:return
            display=state['preview']
            x=event.x-(preview.winfo_width()-display.width)//2;y=event.y-(preview.winfo_height()-display.height)//2
            if 0<=x<display.width and 0<=y<display.height:
                rgb=image.getpixel((min(image.width-1,int(x*image.width/display.width)),min(image.height-1,int(y*image.height/display.height))));hex='#%02X%02X%02X'%rgb;state['hex']=hex;value.set(hex+'    RGB '+str(rgb));status.config(text=hex)
        preview.bind('<Button-1>',sample);self.button(row,'Choose image',choose);self.button(row,'Copy HEX',lambda:self.copy(state.get('hex','')))
    def destroy(self,event):
        if event.widget is not self.hub:return
        self.closed=True
        if self.awake.get():ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        for state in self.windows.values():state['closed']=True;state['cancel'].set()
        try:self.hub.after_cancel(self.job)
        except tk.TclError:pass
