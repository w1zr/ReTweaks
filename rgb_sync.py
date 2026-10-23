"""One animation clock and color for all selected RGB controllers."""
import colorsys
import threading
import time
import rgb_service

def rainbow_period(speed):
    """Full spectrum duration: 120 seconds at Slow, 8 seconds at Fast."""
    return 120 * (8 / 120) ** (max(0, min(100, float(speed))) / 100)

def frame_color(elapsed,speed):
    from openrgb.utils import RGBColor
    period=rainbow_period(speed)
    return RGBColor(*(round(c*255) for c in colorsys.hsv_to_rgb((elapsed/period)%1,1,1)))

class RainbowSync:
    def __init__(self,service,keys,speed,status,scope="Fans + RAM"):
        self.service,self.keys,self.speed,self.status=service,keys,speed,status
        self.stop_event=threading.Event();self.client=None;self.devices=[];self.thread=None;self.origin=0;self.phase_anchor=0;self.clock_lock=threading.Lock();self.scope=scope
        self.writer=rgb_service.LightingWriter()
        self.brightness=100      # RETWEAKS: 10-100 %, applied to every frame
    def color(self,now=None):
        from openrgb.utils import RGBColor
        now=time.monotonic() if now is None else now
        with self.clock_lock:
            period=rainbow_period(self.speed)
            hue=(self.phase_anchor+(now-self.origin)/period)%1
        return RGBColor(*(round(c*255) for c in colorsys.hsv_to_rgb(hue,1,max(0,min(100,self.brightness))/100)))
    def set_speed(self,speed):
        now=time.monotonic()
        with self.clock_lock:
            period=rainbow_period(self.speed)
            self.phase_anchor=(self.phase_anchor+(now-self.origin)/period)%1
            self.origin=now;self.speed=max(0,min(100,speed))
    def prepare(self):
        from openrgb.utils import ModeColors
        self.service.start()
        if self.stop_event.is_set():return
        self.client=rgb_service.connect();plan=[]
        for key in self.keys:
            matches=rgb_service.find(self.client.devices,key)
            if len(matches)!=1:raise ValueError('A synchronized lighting device is unavailable.')
            d=matches[0]
            mode=next((m for name in ('direct','static') for m in d.modes if m.name.lower()==name and m.color_mode==ModeColors.PER_LED),None)
            if mode is None:raise ValueError(d.name+' does not support synchronized live colors.')
            plan.append((d,mode))
        # Validate all controllers before touching their modes.
        color=self.color()
        import copy
        originals=[(d,copy.deepcopy(d.modes[d.active_mode]),copy.deepcopy(d.colors)) for d,_ in plan]
        try:
            for d,mode in plan:
                if self.stop_event.is_set():return
                d._set_device_colors([color]*len(d.leds),fast=True)
                if d.active_mode!=mode.id:d.set_mode(mode.name)
                d._set_device_colors([color]*len(d.leds),fast=True)
        except Exception:
            for d,old,colors in originals:
                try:d._set_device_colors(colors,fast=True);d.set_mode(old);d._set_device_colors(colors)
                except Exception:pass
            raise
        self.devices=[d for d,_ in plan]
    def start(self):
        self.origin=time.monotonic()
        try:self.writer.acquire();self.prepare()
        except Exception:
            self.stop();raise
        self.thread=threading.Thread(target=self.run,daemon=True,name='RETWEAKS synchronized Rainbow');self.thread.start()
    def run(self):
        while not self.stop_event.is_set():
            try:
                # Calculate once per frame so device latency cannot change hue.
                color=self.color()
                for device in self.devices:
                    if self.stop_event.is_set():return
                    device._set_device_colors([color]*len(device.leds),fast=True)
                if self.stop_event.wait(.1):return
            except Exception:
                if self.stop_event.is_set():return
                self.status('Rainbow paused after a connection error. Last color kept; press Apply to resume.')
                self.stop();return
    def stop(self):
        self.stop_event.set()
        if self.client:
            try:self.client.disconnect()
            except Exception:pass
        if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=3)
        if self.thread and self.thread.is_alive() and self.thread is not threading.current_thread():
            raise RuntimeError('Previous lighting effect is still stopping. Try Apply again shortly.')
        self.writer.release()
