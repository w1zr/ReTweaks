"""Round audio slider with explicit pointer capture and user-only callbacks."""
import tkinter as tk

class VolumeSlider(tk.Canvas):
    def __init__(self,parent,variable,colors,command,on_drag=lambda active:None):
        super().__init__(parent,height=30,width=220,bg=colors['PANEL'],highlightthickness=0,bd=0,takefocus=True,cursor='hand2')
        self.variable=variable;self.colors=colors;self.command=command;self.on_drag=on_drag;self.dragging=False
        self.trace=variable.trace_add('write',lambda *args:self.draw())
        self.bind('<Configure>',lambda e:self.draw())
        self.bind('<ButtonPress-1>',self.press);self.bind('<B1-Motion>',self.move);self.bind('<ButtonRelease-1>',self.release)
        self.bind('<KeyPress>',self.key);self.bind('<FocusIn>',lambda e:self.draw());self.bind('<FocusOut>',lambda e:self.draw())
        self.bind('<Destroy>',self.dispose)
        self.draw()

    def draw(self):
        self.delete('all');g=self.colors;self.configure(bg=g['PANEL'])
        width=max(25,self.winfo_width());x=12+(width-24)*max(0,min(100,float(self.variable.get())))/100
        self.create_line(12,15,width-12,15,fill=g['LINE'],width=5,capstyle='round')
        if x>12:self.create_line(12,15,x,15,fill=g['ACC'],width=5,capstyle='round')
        self.create_oval(x-8,7,x+8,23,fill=g['FG'],outline=g['PANEL'],width=2)
        if self.focus_get() is self:self.create_oval(x-11,4,x+11,26,outline=g['ACC'])

    def choose(self,value):
        value=round(max(0,min(100,float(value))))
        if value!=round(float(self.variable.get())):
            self.variable.set(value);self.command(value)

    def move(self,event):
        if self.dragging:self.choose((event.x-12)*100/max(1,self.winfo_width()-24))
        return 'break'

    def press(self,event):
        self.focus_set();self.dragging=True;self.on_drag(True);self.grab_set();return self.move(event)

    def release(self,event):
        if self.dragging:
            self.move(event);self.dragging=False;self.on_drag(False)
            if self.grab_current() is self:self.grab_release()
        return 'break'

    def key(self,event):
        value=float(self.variable.get())
        if event.keysym in ('Left','Down'):value-=1
        elif event.keysym in ('Right','Up'):value+=1
        elif event.keysym=='Home':value=0
        elif event.keysym=='End':value=100
        elif event.keysym=='Prior':value+=10
        elif event.keysym=='Next':value-=10
        else:return
        self.choose(value);return 'break'

    def dispose(self,event):
        if event.widget is self:
            self.on_drag(False)
            self.variable.trace_remove('write',self.trace)
