# core/browser_newtab.py
"""The RETWEAKS start page shown in new tabs (v1.5): the chip logo, the RETWEAKS name, a search box
that uses the chosen search engine, and bookmark tiles. Colors come from the current theme.

The page is a local file served to the Edge engine under https://retweaks.newtab/ (a WebView2
virtual host mapped to a folder in %LOCALAPPDATA%\\RETWEAKS\\Browser\\newtab). Nothing is fetched
from the internet to draw it.
"""

import html
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from core import browser_data as bd
from core.version import BRAND

HOST = bd.NEWTAB_HOST
URL = bd.NEWTAB_URL

LOGO_SVG = """<svg viewBox="0 0 120 120" width="76" height="76" aria-hidden="true">
<rect x="26" y="26" width="68" height="68" rx="14" fill="none" stroke="{c}" stroke-width="5"/>
<g stroke="{c}" stroke-width="4" stroke-linecap="round" opacity="0.6">
<line x1="42" y1="12" x2="42" y2="22"/><line x1="60" y1="12" x2="60" y2="22"/><line x1="78" y1="12" x2="78" y2="22"/>
<line x1="42" y1="98" x2="42" y2="108"/><line x1="60" y1="98" x2="60" y2="108"/><line x1="78" y1="98" x2="78" y2="108"/>
<line x1="12" y1="42" x2="22" y2="42"/><line x1="12" y1="60" x2="22" y2="60"/><line x1="12" y1="78" x2="22" y2="78"/>
<line x1="98" y1="42" x2="108" y2="42"/><line x1="98" y1="60" x2="108" y2="60"/><line x1="98" y1="78" x2="108" y2="78"/>
</g>
<path d="M 48 78 L 48 42 L 62 42 Q 72 42 72 52 Q 72 61 62 61 L 48 61 M 60 61 L 73 78" fill="none" stroke="{c}"
 stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/></svg>"""


def _search_template(engine, custom):
    if engine == bd.CUSTOM and bd.valid_custom_search(custom)[0]:
        return custom.strip().replace("%s", "{q}")
    return bd.SEARCH_ENGINES.get(engine, bd.SEARCH_ENGINES[bd.DEFAULT_ENGINE])


def render(theme, engine=bd.DEFAULT_ENGINE, custom="", bookmarks=(), private=False):
    """Full HTML of the start page. Every user-provided value is escaped."""
    t = theme
    name = "your search engine" if engine == bd.CUSTOM else engine
    tiles = []
    for b in list(bookmarks)[-12:][::-1]:
        url = b.get("url", "")
        if not url.lower().startswith(("http://", "https://")):
            continue
        host = urlsplit(url).netloc.replace("www.", "")
        title = b.get("title") or host
        tiles.append(f'<a class="tile" href="{html.escape(url, quote=True)}" title="{html.escape(url, quote=True)}">'
                     f'<span class="letter">{html.escape((host[:1] or "?").upper())}</span>'
                     f'<span class="t">{html.escape(title[:40])}</span><span class="h">{html.escape(host[:40])}</span></a>')
    tiles_html = ("<div class='tiles'>" + "".join(tiles) + "</div>") if tiles else \
        "<p class='hint'>Bookmark pages with ☆ (Ctrl+D) and they show up here.</p>"
    template = json.dumps(_search_template(engine, custom)).replace("</", "<\\/")
    # Galaxy theme: the same kind of static starfield as the rest of the app
    stars = ""
    if t.get("stars"):
        import random
        rnd = random.Random(7)
        dots = ", ".join(f"radial-gradient({rnd.choice([1, 1, 1.5, 2])}px {rnd.choice([1, 1, 1.5, 2])}px at "
                         f"{rnd.randint(0, 100)}% {rnd.randint(0, 100)}%, rgba(255,255,255,{rnd.choice([.35, .5, .7, .9])}), transparent)"
                         for _ in range(90))
        stars = f"body {{ background-image: {dots}; background-attachment: fixed; }}"
    private_note = ("<p class='private'>Private tab: no history, cookies or cache are kept after it closes.</p>"
                    if private else "")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>New tab</title>
<meta name="color-scheme" content="{'light' if t.get('light') else 'dark'}">
<style>
  :root {{ --bg:{t['bg']}; --card:{t['card']}; --hover:{t['card_hover']}; --input:{t['input']};
          --border:{t['border']}; --text:{t['text']}; --sub:{t['subtext']}; --muted:{t['muted']};
          --accent:{t['accent']}; }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin:0; height:100%; background:var(--bg); color:var(--text);
               font-family:'Segoe UI Variable Text','Segoe UI',sans-serif; }}
  main {{ min-height:100%; display:flex; flex-direction:column; align-items:center; padding:12vh 24px 40px; }}
  .brand {{ display:flex; align-items:center; gap:16px; margin-bottom:28px; }}
  .word {{ font-size:34px; font-weight:700; letter-spacing:2px; }}
  form {{ width:min(640px, 100%); }}
  input {{ width:100%; padding:15px 22px; font-size:16px; color:var(--text); background:var(--input);
          border:1px solid var(--border); border-radius:28px; outline:none; }}
  input:focus {{ border-color:var(--accent); }}
  .engine {{ color:var(--muted); font-size:12px; margin:10px 0 0; text-align:center; }}
  .tiles {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 170px)); justify-content:center; gap:12px;
           width:min(820px, 100%); margin-top:40px; }}
  .tile {{ display:flex; flex-direction:column; gap:6px; padding:14px; background:var(--card);
          border:1px solid var(--border); border-radius:12px; color:var(--text); text-decoration:none;
          transition: background .12s; min-width:0; }}
  .tile:hover {{ background:var(--hover); }}
  .letter {{ width:30px; height:30px; border-radius:8px; background:var(--input); display:flex;
            align-items:center; justify-content:center; font-weight:700; color:var(--sub); }}
  .t {{ font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .h {{ font-size:11px; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .hint, .private {{ color:var(--muted); font-size:13px; margin-top:40px; }}
  .private {{ margin-top:14px; }}
  {stars}
</style></head>
<body><main>
  <div class="brand">{LOGO_SVG.format(c=html.escape(t.get('logo', t['text'])))}<span class="word">{BRAND}</span></div>
  <form id="f" autocomplete="off">
    <input id="q" type="search" placeholder="Search with {html.escape(name)} or type an address" autofocus>
  </form>
  <p class="engine">Search engine: {html.escape(name)} · change it in the ••• menu</p>
  {private_note}
  {tiles_html}
</main>
<script>
  const template = {template};
  const looksLikeAddress = s => /^(https?:\\/\\/)?(localhost|(\\d{{1,3}}\\.){{3}}\\d{{1,3}}|([a-z0-9-]+\\.)+[a-z]{{2,63}})(:\\d{{1,5}})?(\\/\\S*)?$/i.test(s);
  document.getElementById('f').addEventListener('submit', e => {{
    e.preventDefault();
    const s = document.getElementById('q').value.trim();
    if (!s) return;
    if (/^https?:\\/\\//i.test(s)) {{ location.href = s; return; }}
    if (!/\\s/.test(s) && looksLikeAddress(s)) {{ location.href = 'https://' + s; return; }}
    location.href = template.split('{{q}}').join(encodeURIComponent(s).replace(/%20/g, '+'));
  }});
</script>
</body></html>"""


def write(folder, theme, engine=bd.DEFAULT_ENGINE, custom="", bookmarks=()):
    """Writes index.html (normal tabs) and private.html into `folder`. Returns the folder."""
    Path(folder).mkdir(parents=True, exist_ok=True)
    for fname, private in (("index.html", False), ("private.html", True)):
        p = Path(folder) / fname
        tmp = p.with_suffix(".tmp")
        tmp.write_text(render(theme, engine, custom, bookmarks, private), encoding="utf-8")
        os.replace(tmp, p)
    return str(folder)
