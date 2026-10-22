"""CI check on GitHub's Windows runner: calls the real Windows display functions RETWEAKS uses
(QueryDisplayConfig names/native size + EnumDisplaySettings modes) and reports what Windows returned
as build annotations. A runner has no real monitor, so this proves the calls work, not specific values."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import display  # noqa: E402

cfg = display.display_config()
print(f"::notice::QueryDisplayConfig returned {len(cfg)} display(s): {cfg}")
for d in display.list_displays():
    print(f"::notice::{d['device']}: name={d.get('name')!r} current={d['width']}x{d['height']} "
          f"native={display.native_size(d)} rotated={d.get('rotated')} modes={len(d.get('modes') or [])} "
          f"stretch choices={display.stretch_choices(d)[:3]}")
