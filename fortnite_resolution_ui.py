"""Fortnite-only video resolution controls, shared by Presets and Display."""
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from core import fortnite_resolution as fr
from rt_pages.common import card, label, button_row, run_bg


class FortniteResolutionPanel:
    def __init__(self, hub, parent, g):
        self.hub, self.g, self.busy = hub, g, False
        self.path = None
        body = card(parent, g, 'Fortnite-only stretched resolution')
        label(body, 'Sets Fortnite\'s own resolution and Fullscreen mode. Windows and other apps keep their normal '
              'desktop resolution. Close Fortnite before applying.\n\n'
              'Fullscreen is required; Windowed Fullscreen uses the desktop size. Fortnite resets its settings file '
              'when it starts, so the file is made read-only (Restore unlocks it). Your graphics card must offer '
              'the size, and its scaling must be set to Full-screen to stretch instead of showing black bars. '
              'Start the game afterward to check the result.', g, 10, g['MUTED'])
        row = button_row(body, g)
        self.choices = g['RSelect'](row, ['1440 × 1080 (4:3)', '1280 × 960 (4:3)',
                                       '1720 × 1080', 'Custom'], width=230, command=self.choose)
        self.choices.pack(side='left', padx=(0, 8))
        self.width, self.height = tk.StringVar(value='1440'), tk.StringVar(value='1080')
        g['REntry'](row, self.width, width_px=85).pack(side='left')
        tk.Label(row, text=' × ', bg=row.cget('bg'), fg=g['MUTED'], font=(g['UI'], 10)).pack(side='left')
        g['REntry'](row, self.height, width_px=85).pack(side='left')
        row = button_row(body, g)
        self.apply_button = g['RButton'](row, 'Apply to Fortnite only', self.apply, kind='primary')
        self.apply_button.pack(side='left', padx=(0, 6))
        self.restore_button = g['RButton'](row, 'Restore previous resolution', self.restore)
        self.restore_button.pack(side='left', padx=(0, 6))
        self.file_button = g['RButton'](row, 'Choose Fortnite settings file', self.pick)
        self.file_button.pack(side='left')
        self.lock = tk.BooleanVar(value=bool(hub.settings.get('fortnite_resolution_lock', True)))
        g['RCheck'](body, 'Lock the settings file (read-only) so Fortnite can\'t reset the resolution', self.lock,
                    self.lock_changed).pack(anchor='w', padx=16, pady=(0, 4))
        self.status = label(body, 'Looking for Fortnite\'s settings file…', g, 9, g['MUTED'], pady=(0, 12))
        self.found = None
        self.detect()

    def detect(self):
        """Find GameUserSettings.ini in the background (read-only; nothing is changed)."""
        def done(result):
            if self.busy or self.path:
                return
            if isinstance(result, Exception) or not result:
                self.found = None
                self.status.config(text='Fortnite\'s settings file wasn\'t found. Start Fortnite once and close it, '
                                        'or use Choose Fortnite settings file.')
                return
            self.found = result
            self.status.config(text='Found Fortnite settings: ' + str(Path(result)))
        run_bg(self.hub, fr.find_file, done)

    def lock_changed(self):
        self.hub.settings['fortnite_resolution_lock'] = bool(self.lock.get())
        save = getattr(self.hub, 'save_settings', None)
        if callable(save):
            save()

    def mode_note(self, w, h):
        """Read-only check of the graphics card's modes; never changes the display."""
        try:
            offered, shown = fr.mode_check(w, h)
        except Exception:
            return ''
        if offered is None:
            return ''
        if offered:
            return (f'\n\nYour graphics card offers {w} × {h}. If you see black bars, set the scaling to '
                    'Full-screen (NVIDIA Control Panel → Adjust desktop size and position, or AMD/Intel display '
                    'settings).')
        return (f'\n\nYour graphics card does not offer {w} × {h} on this monitor yet, so Fortnite can\'t use it in '
                'Fullscreen. Add it as a custom resolution in your graphics driver first (NVIDIA Control Panel → '
                'Change resolution → Customize), and set scaling to Full-screen.')

    def choose(self, text):
        if text != 'Custom':
            self.width.set(text.split(' × ')[0])
            self.height.set(text.split(' × ')[1].split(' ')[0])

    def pick(self):
        path = filedialog.askopenfilename(parent=self.hub, title='Choose Fortnite GameUserSettings.ini',
                                         filetypes=[('Fortnite settings', 'GameUserSettings.ini')])
        if path:
            self.path = path
            self.status.config(text='Selected ' + str(Path(path)))

    def target(self):
        return self.path or self.found or fr.find_file()

    def apply(self):
        if self.busy:
            return
        path, w, h = self.target(), self.width.get(), self.height.get()
        try:
            changes = fr.preview(path, w, h)
        except Exception as exc:
            self.status.config(text=str(exc))
            return
        if not changes:
            self.status.config(text='Fortnite already has these video settings. Windows desktop resolution is unchanged.')
            return
        lock = bool(self.lock.get())
        lines = '\n'.join(f'{key}: {old} → {new}' for key, old, new in changes)
        locked = ('\n\nThe file will be made read-only so Fortnite can\'t reset it. Restore unlocks it.' if lock
                  else '')
        if not messagebox.askyesno('Fortnite-only resolution',
                'Save these changes to Fortnite only?\n\n' + lines + locked +
                '\n\nA backup is saved first. Windows desktop resolution will not change. '
                'Start Fortnite afterward and check Fullscreen and resolution in Video settings.' +
                self.mode_note(w.strip(), h.strip()), parent=self.hub):
            return
        self._run('Apply Fortnite-only resolution', lambda: fr.apply(path, w, h, lock=lock))

    def restore(self):
        if self.busy:
            return
        path = self.target()
        if not path:
            self.status.config(text='Choose Fortnite\'s GameUserSettings.ini first.')
            return
        if messagebox.askyesno('Restore Fortnite resolution', 'Restore the Fortnite video settings from before '
                'the first application of this profile? Other game settings and Windows desktop resolution are kept.',
                parent=self.hub):
            self._run('Restore Fortnite-only resolution', lambda: fr.restore(path))

    def _run(self, action, function):
        self.busy = True
        for button in (self.apply_button, self.restore_button, self.file_button):
            button.set_enabled(False)
        self.status.config(text='Saving Fortnite settings…')
        def done(result):
            self.busy = False
            for button in (self.apply_button, self.restore_button, self.file_button):
                button.set_enabled(True)
            failed = isinstance(result, Exception)
            self.status.config(text=str(result), fg=self.g.get('RED') if failed else self.g['MUTED'])
            self.hub.log_action('Fortnite resolution', action, 'Failed' if failed else 'Saved',
                                str(result) if failed else '')
        run_bg(self.hub, function, done)
