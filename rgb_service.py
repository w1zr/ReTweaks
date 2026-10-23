"""Local OpenRGB engine startup and bounded SDK connection checks.

From base app v1.5 (GPL-3.0, by the base app's author), added to RETWEAKS 2026-10-22. OpenRGB 1.1 portable is bundled
in ai/openrgb (GPL-2.0, unmodified official release; see ai/openrgb/SOURCE.txt)."""
from pathlib import Path
import socket
import subprocess
import sys
import time
import tempfile
import os

class LightingWriter:
    """Cross-process ownership of lighting writes; discovery remains read-only."""
    def __init__(self):self.file=None
    def acquire(self):
        if self.file:return
        handle=open(Path(tempfile.gettempdir())/'RETWEAKS-lighting-writer.lock','a+b')
        try:
            if os.fstat(handle.fileno()).st_size==0:handle.write(b'0');handle.flush()
            handle.seek(0)
            try:
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            except ImportError:            # not Windows (tests): same non-blocking exclusive lock via fcntl
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except Exception:
            handle.close()
            raise RuntimeError('Another RETWEAKS lighting effect is active. Quit the other RETWEAKS copy from its tray icon first.')
        self.file=handle
    def release(self):
        if self.file:
            self.file.close();self.file=None
    def __enter__(self):self.acquire();return self
    def __exit__(self,*args):self.release()

ENGINE=Path(__file__).resolve().parent/'ai'/'openrgb'/'OpenRGB Windows 64-bit'/'OpenRGB.exe'

def server_available():
    try:
        with socket.create_connection(('127.0.0.1',6742),timeout=.5):return True
    except OSError:return False

class RGBService:
    def __init__(self):self.process=None;self.closed=False
    def start(self):
        if self.closed:raise RuntimeError('RETWEAKS is closing.')
        if server_available():return
        if not self.process or self.process.poll() is not None:
            if not ENGINE.is_file():raise RuntimeError('The bundled RGB engine (OpenRGB) is missing from this build. Use a complete RETWEAKS build.')
            self.process=subprocess.Popen([str(ENGINE),'--gui','--startminimized','--noautoconnect','--server','--server-host','127.0.0.1','--server-port','6742'],cwd=str(ENGINE.parent),creationflags=0x08000000,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+40
        while time.monotonic()<deadline and not self.closed:
            if server_available():return
            if self.process.poll() is not None:raise RuntimeError('OpenRGB stopped during startup. Open its setup window to inspect hardware detection.')
            time.sleep(.5)
        raise RuntimeError('OpenRGB has not finished starting. Check its tray icon, then reconnect.')
    def close(self):
        self.closed=True
        if self.process and self.process.poll() is None:self.process.terminate()

def connect():
    if not server_available():raise ConnectionError('Waiting for the automatic RGB service to start.')
    from openrgb import OpenRGBClient
    # Device colors/modes use protocol 3; avoid optional plugin enumeration,
    # which can stall otherwise-compatible servers during their startup scan.
    return OpenRGBClient('127.0.0.1',6742,name='RETWEAKS',protocol_version=3)

def solid_mode(device,zone=False):
    from openrgb.utils import ModeColors
    supported=(ModeColors.PER_LED,) if zone else (ModeColors.PER_LED,ModeColors.MODE_SPECIFIC)
    names=('static','solid','solid color','direct')
    return next((mode for name in names for mode in device.modes if mode.name.lower()==name and mode.color_mode in supported),None)

def _base_identity(device):
    meta=getattr(device,'metadata',None)
    return (device.type.name,device.name,getattr(meta,'serial',''),getattr(meta,'location',''))

def identity(device,devices=None):
    """Stable key for an OpenRGB device. Identical RAM sticks / fan hubs can report the same name, serial and
    location; with the full device list the key also carries the device's position among those twins (in
    OpenRGB's detection order), so each stick is addressed on its own (owner report 2026-10-22)."""
    base=_base_identity(device)
    if devices is None:return base
    twins=[d for d in devices if _base_identity(d)==base]
    if len(twins)<2:return base
    position=next((i for i,d in enumerate(twins) if d is device or getattr(d,'id',None)==getattr(device,'id',object())),0)
    return base+(position,)

def find(devices,key):
    """Devices in `devices` matching an identity() key (exactly one when the hardware didn't change)."""
    return [d for d in devices if identity(d,devices)==key]

def fan_zones(device):
    return [z for z in getattr(device,'zones',[]) if any(k in z.name.upper() for k in ('JRGB','JRAINBOW','JCORSAIR','ARGB','HEADER','FAN'))]

def effect_mode(device,effect):
    if effect in ('Solid','Solid color'):return solid_mode(device)
    aliases={'Rainbow':('rainbow','rainbow wave','rainbowwave'),'Breathing':('breathing','breath'),'Color cycle':('spectrum','color shift','colorshift')}
    names=aliases.get(effect,(effect.lower(),))
    return next((m for name in names for m in device.modes if m.name.lower()==name),None)

def scale_color(color,brightness):
    """RETWEAKS: colour at a brightness percentage (10-100). Used for solid colours and the software Rainbow."""
    from openrgb.utils import RGBColor
    k=max(0.0,min(100.0,float(brightness)))/100
    return RGBColor(round(color.red*k),round(color.green*k),round(color.blue*k))

def write_effect(device,effect,color,speed=50,brightness=None):
    if effect in ('Solid','Solid color'):return write_solid(device,None,color)
    import copy
    from openrgb.utils import ModeFlags,ModeColors
    mode=effect_mode(device,effect)
    if mode is None:raise ValueError('The selected lighting effect is not supported by this device.')
    configured=copy.deepcopy(mode);old=copy.deepcopy(device.modes[device.active_mode]);colors=copy.deepcopy(device.colors)
    uses_color='rainbow' not in effect.lower()
    if ModeFlags.HAS_SPEED in configured.flags and configured.speed_min is not None and configured.speed_max is not None:
        configured.speed=round(configured.speed_min+(configured.speed_max-configured.speed_min)*max(0,min(100,speed))/100)
    # RETWEAKS: hardware brightness when the mode has it (OpenRGB HAS_BRIGHTNESS)
    if brightness is not None and ModeFlags.HAS_BRIGHTNESS in configured.flags and getattr(configured,'brightness_min',None) is not None and getattr(configured,'brightness_max',None) is not None:
        configured.brightness=round(configured.brightness_min+(configured.brightness_max-configured.brightness_min)*max(0,min(100,brightness))/100)
    if uses_color and configured.color_mode==ModeColors.MODE_SPECIFIC:configured.colors=[color]*max(1,configured.colors_min or 1)
    try:
        if uses_color and configured.color_mode==ModeColors.PER_LED:device._set_device_colors([color]*len(device.leds),fast=True)
        device.set_mode(configured)
        if uses_color and configured.color_mode==ModeColors.PER_LED:device._set_device_colors([color]*len(device.leds))
        device.update()
        actual=device.modes[device.active_mode]
        if actual.id!=configured.id:raise ValueError('The controller did not confirm the lighting effect.')
        if ModeFlags.HAS_SPEED in configured.flags and actual.speed!=configured.speed:raise ValueError('The controller did not confirm the effect speed.')
    except Exception:
        try:device._set_device_colors(colors,fast=True);device.set_mode(old);device._set_device_colors(colors)
        except Exception:pass
        raise

def write_solid(device,zones,color):
    """Preserve non-target colors and avoid restarting an already-active mode."""
    import copy
    from openrgb.utils import ModeColors
    mode=solid_mode(device,zone=zones is not None)
    if mode is None:raise ValueError('This controller does not report a supported solid-color mode.')
    original_mode=device.active_mode
    original_settings=copy.deepcopy(device.modes[original_mode])
    original=copy.deepcopy(device.colors)
    target_ids={led.id for zone in zones for led in zone.leds} if zones is not None else set(range(len(device.leds)))
    if not target_ids:raise ValueError('Fan lighting has no configured LEDs. Complete the one-time setup in Advanced settings.')
    desired=[color if index in target_ids else old for index,old in enumerate(original)]
    try:
        if mode.color_mode==ModeColors.PER_LED:
            # Seed the server's complete color buffer before a mode transition.
            # This prevents mode activation from flushing black defaults first.
            device._set_device_colors(desired,fast=True)
            if device.active_mode!=mode.id:device.set_mode(mode.name)
            device._set_device_colors(desired)
        else:
            configured=copy.deepcopy(mode)
            configured.colors=[color]*max(1,configured.colors_min or 1)
            device.set_mode(configured)
        device.update()
        if device.active_mode!=mode.id:raise ValueError('The lighting controller did not confirm the color mode.')
        if mode.color_mode==ModeColors.PER_LED:
            if len(device.colors)!=len(desired) or any(device.colors[i]!=desired[i] for i in range(len(desired))):raise ValueError('The lighting controller did not confirm all requested colors.')
        else:
            actual=device.modes[device.active_mode].colors
            if not actual or any(c!=color for c in actual):raise ValueError('The lighting controller did not confirm the requested color.')
    except Exception:
        try:
            device._set_device_colors(original,fast=True)
            device.set_mode(original_settings)
            device._set_device_colors(original)
        except Exception:pass
        raise
