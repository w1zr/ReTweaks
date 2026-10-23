"""RETWEAKS' own tray menu: opened by a right-click on the tray icon (queued from pystray's thread),
themed with the current colours, rounded, keyboard + mouse, Open / Settings / Quit, closes on Esc."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["APPDATA"] = tempfile.mkdtemp(); os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
import retweaks as app, hubplus, rt_shell, rt_traymenu
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
hub = app.Hub(show_intro=False, enable_ai=False)
hub.settings["check_updates"] = False
shell = rt_shell.Shell(hub, vars(app), [])
hub.update()
pump = lambda n=20: [hub.update() or time.sleep(0.01) for _ in range(n)]
# right-click arrives from the tray thread as a queued action
shell.tray.actions.put(("menu", 900, 700)); pump(30)
m = rt_traymenu.TrayMenu.current
assert m is not None and m.win.winfo_exists()
labels = [r[0] for r in m.rows if r]
assert labels == ["Open RETWEAKS", "Settings", "Quit RETWEAKS"], labels
# themed: drawn with the theme's colours, rounded outline polygon
items = m.cv.find_all()
assert any(m.cv.type(i) == "polygon" and m.cv.itemcget(i, "fill") == hub._g["PANEL"] for i in items)
# placed with its bottom-right corner at the cursor (like the Windows menu)
x, y = m.win.winfo_rootx(), m.win.winfo_rooty()
assert abs((x + m.w) - 900) <= 2 and abs((y + m.h) - 700) <= 2, (x, y)
# keyboard: Down twice -> Settings; Esc closes
m._step(1); m._step(1); assert m.rows[m.hover][0] == "Settings"
m.close(); pump(); assert rt_traymenu.TrayMenu.current is None
# Settings opens the window on the Settings page
hub.withdraw(); pump()
shell.tray.show_menu(900, 700); pump()
m = rt_traymenu.TrayMenu.current
m._choose(1); pump(400)
assert hub.state() != "withdrawn" and hub.cur_tab == hub.rt_tabs["Settings"], (hub.state(), hub.cur_tab)
# a second right-click replaces the open menu (never two)
shell.tray.show_menu(500, 500); first = rt_traymenu.TrayMenu.current
shell.tray.show_menu(600, 600); pump()
assert first.closed and rt_traymenu.TrayMenu.current is not first
rt_traymenu.TrayMenu.current.close()
# theme change -> next menu uses the new colours
hub.apply_theme("Ocean"); pump()
shell.tray.show_menu(900, 700); pump()
m = rt_traymenu.TrayMenu.current
assert m.panel == hub._g["PANEL"]
# Quit from the menu closes the app
quit_called = []
orig = rt_shell.quit_app
rt_shell.quit_app = lambda h: quit_called.append(h)
m.rows[3] = (m.rows[3][0], lambda: rt_shell.quit_app(hub))
m._choose(3); pump()
assert quit_called and m.closed
rt_shell.quit_app = orig
print("PASS: tray menu — opened from the tray thread, themed + rounded, placed at the cursor, keyboard, Settings, "
      "single menu, follows theme changes, Quit.")
hub.destroy()
