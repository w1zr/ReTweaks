"""RGB: changing RAM colour colours EVERY stick (owner report 2026-10-22: "If I try and change the RAM colors, it
only changes one of them"). Two identical sticks (same name, no serial/location, as many kits report) + a fan hub.
All hardware writes are mocked."""
import os, sys, tempfile, time
TMP = tempfile.mkdtemp(prefix="rt_rgbram_")
os.environ["APPDATA"] = TMP; os.environ["LOCALAPPDATA"] = TMP
from types import SimpleNamespace
from unittest.mock import Mock, patch
import retweaks as app, hubplus, automation, rgb_service
from openrgb.utils import DeviceType, ModeColors


class Hotkeys:
    def __init__(self, *a): self.thread = Mock()
    def update(self, *a): pass
    def close(self): pass


def pump(hub, cond):
    end = time.monotonic() + 3
    while not cond() and time.monotonic() < end:
        hub.update(); time.sleep(.02)
    assert cond(), "worker did not finish"


automation.Hotkeys = Hotkeys
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
hub = app.Hub(show_intro=False, enable_ai=False)
hub.update()
rgb = hub.rgb_lighting; rgb.tried = True; rgb.retry_at = time.monotonic() + 3600
hub.sidebar_nav.buttons["RGB lighting"].command(); hub.update()
modes = lambda: [SimpleNamespace(name='Static', color_mode=ModeColors.PER_LED)]
dev = lambda i, name, kind: SimpleNamespace(id=i, name=name, type=kind, leds=[1], modes=modes(), active_mode=0,
                                            set_mode=Mock(), set_color=Mock(), zones=[])
devices = [dev(0, "Fan Hub", DeviceType.COOLER), dev(1, "Corsair Vengeance RGB", DeviceType.DRAM),
           dev(2, "Corsair Vengeance RGB", DeviceType.DRAM)]
client = Mock(); client.devices = devices
with patch('rgb_service.server_available', return_value=True), patch('openrgb.OpenRGBClient', return_value=client):
    rgb.connect(); pump(hub, lambda: not rgb.busy)
# identical twins get distinct keys, and each key finds exactly its own stick
k1 = rgb_service.identity(devices[1], devices); k2 = rgb_service.identity(devices[2], devices)
assert k1 != k2 and rgb_service.find(devices, k1) == [devices[1]] and rgb_service.find(devices, k2) == [devices[2]]
assert rgb_service.identity(devices[0], devices) == rgb_service.identity(devices[0])     # unique devices unchanged
rgb.choose_group('RAM'); hub.update()
assert rgb.quick_target.values[0] == "All RAM sticks (2)" and rgb.quick_target.get() == "All RAM sticks (2)", \
    rgb.quick_target.values
assert "RAM stick 1 · Corsair Vengeance RGB" in rgb.quick_target.values
assert "RAM stick 2 · Corsair Vengeance RGB" in rgb.quick_target.values
write = lambda d, z, c: d.set_color(c)
with patch.object(rgb.service, 'start'), patch('rgb_service.connect', return_value=client), \
        patch('rgb_service.write_solid', side_effect=write):
    rgb.preset('Red', '#ff0000'); rgb.quick_apply_color(); pump(hub, lambda: not rgb.busy)
assert devices[1].set_color.called and devices[2].set_color.called, "both sticks must change"
assert not devices[0].set_color.called                          # RAM only, not the fan hub
for d in devices: d.set_color.reset_mock()
rgb.quick_target.set("RAM stick 2 · Corsair Vengeance RGB"); rgb.show_target()
with patch.object(rgb.service, 'start'), patch('rgb_service.connect', return_value=client), \
        patch('rgb_service.write_solid', side_effect=write):
    rgb.preset('Blue', '#0000ff'); rgb.quick_apply_color(); pump(hub, lambda: not rgb.busy)
assert devices[2].set_color.called and not devices[1].set_color.called, "single stick choice hits only that stick"
print("PASS: RGB RAM — identical sticks get their own keys, 'All RAM sticks' (default) colours every stick, "
      "each stick can still be chosen alone, fans untouched.")
hub.destroy()
