"""Windows check for the Browser (v1.5): loads the Edge engine, opens a real tab in a Qt window,
shows a page and reads its title back. Run: python tools/browser_smoke.py  (exit code 0 = works)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


def main():
    from core import browser_engine as be
    eng = be.load()
    print("Edge WebView2 runtime:", eng.version)
    if "--load-only" in sys.argv:
        return 0
    app = QApplication(sys.argv)
    from ui.widgets.edge_view import EdgeView, EnvironmentHolder
    env = EnvironmentHolder(eng, tempfile.mkdtemp(prefix="rytweaks_browser_"))
    result = {"code": 1}
    views = []

    def check(private):
        v = EdgeView(eng, env, private=private)
        v.resize(800, 600)
        v.show()
        views.append(v)

        def ready():
            v.wv.NavigateToString("<html><head><title>RYTWEAKS OK</title></head><body>ok</body></html>")

        def title(t):
            print(("private" if private else "normal"), "tab title:", t)
            if t == "RYTWEAKS OK":
                done(private)

        v.ready.connect(ready)
        v.titleChanged.connect(title)
        v.failed.connect(lambda m: (print("FAILED:", m), app.exit(1)))
        v.start()

    seen = set()

    def done(private):
        seen.add(private)
        if seen == {False, True}:
            result["code"] = 0
            app.exit(0)

    check(False)
    check(True)
    QTimer.singleShot(60000, lambda: (print("TIMEOUT"), app.exit(2)))
    code = app.exec()
    for v in views:
        v.close_engine()
    return result["code"] if code == 0 else code


if __name__ == "__main__":
    sys.exit(main())
