"""Windows wallpaper pictures through the documented IDesktopWallpaper interface."""
import ctypes
import json
import os
from pathlib import Path
import sys
import uuid

POSITIONS = {'Fill': 4, 'Fit': 3, 'Stretch': 2, 'Center': 0, 'Tile': 1, 'Span': 5}
PRESETS = {
    'Ocean glow': ('#071426', '#143955', '#26b5cd'),
    'Purple dusk': ('#100d27', '#35204b', '#9566d9'),
    'Forest light': ('#071711', '#1c3b30', '#68ba8d'),
    'Carbon': ('#050608', '#1a1c23', '#626b7c'),
    'Ember horizon': ('#170e14', '#4e2525', '#df8c55'),
    'Midnight blue': ('#080c1d', '#132446', '#577ccb'),
}


class WallpaperError(Exception):
    pass


def data_dir():
    return Path(os.environ.get('APPDATA', Path.home())) / 'RETWEAKS' / 'Wallpapers'


class Desktop:
    """Each instance is created and released on its calling thread."""
    def __init__(self):
        if sys.platform != 'win32':
            raise WallpaperError('Windows wallpaper controls require Windows 8 or newer.')
        self.dll = ctypes.WinDLL('ole32')
        self.dll.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.dll.CoInitializeEx.restype = ctypes.c_long
        self.dll.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                             ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        self.dll.CoCreateInstance.restype = ctypes.c_long
        self.dll.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        self.pointer = ctypes.c_void_p()
        hr = self.dll.CoInitializeEx(None, 2)
        self.uninitialize = hr in (0, 1)
        if hr < 0 and hr & 0xffffffff != 0x80010106:
            raise WallpaperError(f'Windows could not initialize wallpaper controls (0x{hr & 0xffffffff:08x}).')
        clsid = (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID('C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD').bytes_le)
        iid = (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID('B92B56A9-8B55-4E14-9A89-0199BBB6F93B').bytes_le)
        try:
            result = self.dll.CoCreateInstance(ctypes.byref(clsid), None, 23, ctypes.byref(iid), ctypes.byref(self.pointer))
            if result < 0:
                raise OSError(f'COM error 0x{result & 0xffffffff:08x}')
        except OSError as exc:
            self.close()
            raise WallpaperError('Windows wallpaper controls are unavailable: ' + str(exc)) from None

    def call(self, index, types=(), args=()):
        table = ctypes.cast(self.pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        method = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(table[index])
        result = method(self.pointer, *args)
        if result < 0:
            raise WallpaperError(f'Windows refused the wallpaper operation (0x{result & 0xffffffff:08x}).')
        return result

    def string(self, index, types=(), args=()):
        result = ctypes.c_void_p()
        self.call(index, (*types, ctypes.POINTER(ctypes.c_void_p)), (*args, ctypes.byref(result)))
        try:
            return ctypes.wstring_at(result) if result.value else ''
        finally:
            if result.value:
                self.dll.CoTaskMemFree(result)

    def snapshot(self):
        count, position = ctypes.c_uint32(), ctypes.c_int()
        self.call(6, (ctypes.POINTER(ctypes.c_uint32),), (ctypes.byref(count),))
        self.call(11, (ctypes.POINTER(ctypes.c_int),), (ctypes.byref(position),))
        monitors = []
        for index in range(count.value):
            monitor = self.string(5, (ctypes.c_uint32,), (index,))
            image = self.string(4, (ctypes.c_wchar_p,), (monitor,))
            monitors.append({'monitor': monitor, 'image': image})
        return {'position': position.value, 'monitors': monitors}

    def set_position(self, value):
        self.call(10, (ctypes.c_int,), (value,))

    def set_image(self, path, monitor=None):
        self.call(3, (ctypes.c_wchar_p, ctypes.c_wchar_p), (monitor, path))

    def restore(self, snapshot):
        self.set_position(snapshot['position'])
        for monitor in snapshot['monitors']:
            self.set_image(monitor['image'], monitor['monitor'])

    def close(self):
        if self.pointer.value:
            table = ctypes.cast(self.pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])(self.pointer)
            self.pointer = ctypes.c_void_p()
        if self.uninitialize:
            self.dll.CoUninitialize()
            self.uninitialize = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def current(factory=Desktop):
    with factory() as desktop:
        return desktop.snapshot()


def prepare_image(source, folder=None):
    """Keep an independent wallpaper copy; EXIF orientation and first frame handled."""
    from PIL import Image, ImageOps
    import hashlib
    source = Path(source)
    folder = Path(folder) if folder else data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as original:
        if original.width * original.height > 80_000_000:
            raise WallpaperError('Choose an image smaller than 80 megapixels.')
        image = ImageOps.exif_transpose(original).convert('RGB')
        hasher = hashlib.sha256(f'{image.width}x{image.height}'.encode())
        for y in range(0,image.height,256):
            hasher.update(image.crop((0,y,image.width,min(y+256,image.height))).tobytes())
        digest = hasher.hexdigest()[:24]
        output = folder / (digest + '.jpg')
        if not output.exists():
            temporary = folder / (digest + '.tmp')
            image.save(temporary, format='JPEG', quality=95)
            os.replace(temporary, output)
    return output


def preset_image(name, folder=None):
    """Generate deterministic, local gradient artwork without network downloads."""
    from PIL import Image
    import math
    if name not in PRESETS:
        raise WallpaperError('Choose an available wallpaper preset.')
    folder = Path(folder) if folder else data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / ('preset-' + name.lower().replace(' ', '-') + '.jpg')
    if output.exists():
        return output
    colors = [tuple(int(color[i:i+2], 16) for i in (1,3,5)) for color in PRESETS[name]]
    image = Image.new('RGB', (480,270))
    pixels=[]
    for y in range(270):
        v=y/269
        for x in range(480):
            glow=math.exp(-((x/480-.72)**2*9+(v-.35)**2*14))*.6
            wave=.5+.5*math.sin(x/125+v*4)
            base=[colors[0][i]*(1-v)+colors[1][i]*v for i in range(3)]
            pixels.append(tuple(round(c*(1-glow)+colors[2][i]*glow+wave*2) for i,c in enumerate(base)))
    image.putdata(pixels)
    image=image.resize((1920,1080),Image.Resampling.LANCZOS)
    temporary=output.with_suffix('.tmp')
    image.save(temporary,format='JPEG',quality=95)
    os.replace(temporary,output)
    return output


def apply_picture(source, position='Fill', folder=None, factory=Desktop):
    if position not in POSITIONS:
        raise WallpaperError('Choose a supported picture fit.')
    folder = Path(folder) if folder else data_dir()
    image = prepare_image(source, folder)
    with factory() as desktop:
        previous = desktop.snapshot()
        backup = folder / 'previous-picture.json'
        temporary = backup.with_suffix('.tmp')
        temporary.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, backup)
        try:
            desktop.set_position(POSITIONS[position])
            desktop.set_image(str(image))
            result = desktop.snapshot()
            if result['position'] != POSITIONS[position] or any(
                    os.path.normcase(m['image']) != os.path.normcase(str(image)) for m in result['monitors']):
                raise WallpaperError('Windows did not confirm the selected wallpaper. A policy or another wallpaper app may control it.')
        except Exception:
            desktop.restore(previous)
            raise
    return image


def restore_picture(folder=None, factory=Desktop):
    folder = Path(folder) if folder else data_dir()
    backup = folder / 'previous-picture.json'
    if not backup.exists():
        raise WallpaperError('No previous picture has been saved yet. Apply a picture from this page first.')
    saved = json.loads(backup.read_text(encoding='utf-8'))
    if saved.get('position') not in POSITIONS.values() or not isinstance(saved.get('monitors'), list):
        raise WallpaperError('The previous-picture backup is invalid.')
    for monitor in saved['monitors']:
        if monitor['image'] and not Path(monitor['image']).is_file():
            raise WallpaperError('A previous wallpaper file is missing. Choose another picture instead.')
    with factory() as desktop:
        desktop.restore(saved)
        result = desktop.snapshot()
        found = {m['monitor']: os.path.normcase(m['image']) for m in result['monitors']}
        if result['position'] != saved['position'] or any(found.get(m['monitor']) != os.path.normcase(m['image']) for m in saved['monitors']):
            raise WallpaperError('Windows did not confirm the restored picture.')
    return result
