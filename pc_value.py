"""Photo-assisted PC valuation. No prices are supplied from model memory."""
import base64
import datetime as dt
import io
import json
import math
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, ttk, simpledialog
from pathlib import Path
from urllib.parse import urlsplit
import webbrowser
import re
from collections import Counter
from component_inventory import normalize_ram, normalize_components, specifications, matches_capacity, exact_model_match

KINDS = ('CPU', 'GPU', 'Motherboard', 'RAM', 'Storage', 'Power supply', 'Case', 'Cooling', 'Other')
COUNTRIES = ('United States', 'United Kingdom', 'Canada', 'Australia', 'Germany', 'France', 'India', 'Japan', 'Brazil', 'Mexico', 'New Zealand', 'South Africa', 'Singapore')
CURRENCIES = ('USD', 'GBP', 'CAD', 'AUD', 'EUR', 'INR', 'JPY', 'BRL', 'MXN', 'NZD', 'ZAR', 'SGD', 'CHF', 'CNY', 'KRW')

def detected_components(info):
    """Allowlisted model/capacity fields only; never serials or user data."""
    from drivers import physical_gpu
    info = info if isinstance(info, dict) else {}
    raw = info.get('raw') if isinstance(info.get('raw'), dict) else {}
    def text(value):
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            return ''
        value = re.sub(r'[\x00-\x1f\x7f]', ' ', str(value)).strip()
        if value.lower() in ('', '?', '0', 'none', 'n/a') or re.search(r'(?i)unknown|not available|to be filled|default string|system product name|system manufacturer', value):
            return ''
        return value[:220]
    def rows(value):
        return [r for r in (value if isinstance(value, list) else [value]) if isinstance(r, dict)]
    def capacity(value):
        try:
            n = float(value)
            return f'{n:g} GB' if math.isfinite(n) and n > 0 else ''
        except (ValueError, TypeError):
            return ''
    def grouped(names):
        return '; '.join(f'{name}, quantity {count}' for name, count in Counter(names).items())
    result = {}
    cpu = text(raw.get('cpu')) or text(info.get('cpu'))
    if cpu:
        result['CPU'] = cpu + ', quantity 1'
    board = text(raw.get('board')) or text(info.get('board'))
    if board:
        result['Motherboard'] = board + ', quantity 1'
    gpus = rows(raw.get('gpus'))
    gpu_names = [text(r.get('name')) for r in gpus if text(r.get('name')) and physical_gpu(r['name'], r.get('pnp', ''))]
    if not gpus:
        gpu_names = [n.strip() for n in text(info.get('gpu')).split(', ') if physical_gpu(n.strip())]
    # Integrated graphics are included in CPU replacement value, not a second card.
    gpu_names = [n for n in gpu_names if not re.search(r'(?i)\b(?:UHD|HD Graphics|Iris|Vega|integrated)\b|Radeon\s*(?:\(TM\)\s*)?(?:Graphics|\d{3}M(?:\s+Graphics)?)\s*$', n)
                 and not ('intel' in n.lower() and 'graphics' in n.lower() and 'arc' not in n.lower())]
    if gpu_names:
        result['GPU'] = grouped(gpu_names)
    modules = []
    for module in rows(raw.get('ram_modules')):
        gb = capacity(module.get('gb'))
        if not gb:
            continue
        speed = text(module.get('speed')) or text(module.get('rated'))
        name = ' '.join(filter(None, (text(module.get('maker')), text(module.get('part')), gb, text(module.get('type')), (speed + ' MT/s') if speed else '')))
        modules.append(name)
    if modules:
        result['RAM'] = normalize_ram(grouped(modules))
    else:
        gb = capacity(raw.get('ram') or info.get('ram'))
        if gb:
            result['RAM'] = gb + ' total RAM (module models and quantities need confirmation)'
    disks = []
    for disk in rows(raw.get('disks')):
        name = text(disk.get('name'))
        if not name:
            continue
        size = capacity(disk.get('gb')).replace('GB', 'GiB detected')
        disks.append(' '.join(filter(None, (name, size, text(disk.get('kind'))))))
    if disks:
        result['Storage'] = grouped(disks)
    return result

def safe_url(value):
    try:
        u = urlsplit(value)
        return u.scheme == 'https' and bool(u.hostname) and not u.username and not u.password and u.port in (None, 443)
    except (ValueError, TypeError):
        return False

def decode_object(text):
    if not isinstance(text, str) or len(text) > 200000:
        raise ValueError('Invalid AI response.')
    data = json.loads(text[text.find('{'):text.rfind('}') + 1])
    if not isinstance(data, dict):
        raise ValueError('Invalid AI response.')
    return data

def parse_estimate(answer, components, currency):
    """Accept numbers only with indices backed by retrieved source records."""
    data = decode_object(answer.get('text'))
    if data.get('currency') != currency:
        raise ValueError('The price response used a different currency. Please retry.')
    metadata = answer.get('grounding') or {}
    chunks = metadata.get('groundingChunks') or []
    sources = []
    source_ids = {chunk['source_id']: i for i, chunk in enumerate(chunks) if isinstance(chunk, dict) and isinstance(chunk.get('source_id'), str)}
    for chunk in chunks:
        web = chunk.get('web', {}) if isinstance(chunk, dict) else {}
        sources.append(web if safe_url(web.get('uri')) else None)
    allow_estimates = answer.get('allow_estimates') is True
    if not any(sources) and not allow_estimates:
        raise ValueError('No current price sources were available. No estimate was shown. Please retry.')
    results = []
    items = data.get('items')
    if not isinstance(items, list):
        raise ValueError('Missing component prices. Please retry.')
    for kind, name in components.items():
        candidates = [r for r in items if isinstance(r, dict) and r.get('id') == kind]
        item = candidates[0] if len(candidates) == 1 else {}
        row = {'id': kind, 'name': name, 'note': str(item.get('note', ''))[:1200]}
        spec = specifications({kind:name})[kind]
        if spec.get('kind') == 'RAM' and spec.get('total_gb'):
            row['note'] = f'Both ranges cover {spec["total_gb"]:g} GB total RAM.'
            if spec.get('modules') and spec.get('module_gb'):
                row['note'] += f' Installed layout: {spec["modules"]} × {spec["module_gb"]:g} GB modules; the per-module capacity is not the total being priced.'
        elif spec.get('kind') == 'Storage' and spec.get('unit_gb'):
            row['note'] = f'This row prices this drive only: {spec["unit_gb"]:g} GB per drive, quantity {spec["quantity"]}. Other drives have separate rows; their capacities are not added to choose a replacement.'
        for market in ('new', 'used'):
            quote = item.get(market)
            row[market] = None
            if not isinstance(quote, dict):
                continue
            lo, hi = quote.get('low'), quote.get('high')
            refs = quote.get('sources', [])
            method = str(quote.get('method', 'listing')).strip().lower().replace('ai_estimate', 'estimate')
            if method not in ('listing', 'comparable', 'estimate'):
                continue
            if not isinstance(refs, list):
                continue
            refs = [source_ids.get(i) if isinstance(i, str) else i if not source_ids else None for i in refs]
            refs = list(dict.fromkeys(i for i in refs if type(i) is int and 0 <= i < len(sources) and sources[i]))
            if answer.get('source_mode') == 'public_pages':
                refs = [i for i in refs if (chunks[i].get('component_id') == kind and (chunks[i].get('market') == market or method != 'listing')) or chunks[i].get('market') == 'fx']
                refs = [i for i in refs if chunks[i].get('market') == 'fx' or matches_capacity(kind, name, sources[i])]
                if method != 'estimate' and not any(chunks[i].get('component_id') == kind and (chunks[i].get('market') == market or method == 'comparable') for i in refs):
                    continue
            if method == 'estimate' and (not allow_estimates or not str(quote.get('basis', '')).strip()):
                continue
            if (not refs and method != 'estimate') or type(lo) not in (int, float) or type(hi) not in (int, float):
                continue
            if not math.isfinite(lo) or not math.isfinite(hi) or not 0 < lo <= hi < 1e9:
                continue
            basis = str(quote.get('basis', ''))[:1800]
            if method == 'listing' and spec.get('kind') in ('RAM','Storage'):
                if any(sources[i].get('listing') and not exact_model_match(name, str(sources[i].get('title', ''))) for i in refs):
                    method = 'comparable'
                    basis = 'Same-capacity comparison, not an exact-model listing. Brand or model differs from the installed component. ' + basis
            # Never attach an unrelated dollar amount as proof of the AI range.
            mismatch = False
            for i in refs:
                listing = sources[i].get('listing') or {}
                price = listing.get('price')
                if type(price) not in (int, float) or listing.get('currency') != currency:
                    continue
                if not lo - .51 <= price <= hi + .51:
                    mentioned = any(abs(float(n.replace(',', '')) - price) < .51 for n in re.findall(r'\d+(?:,\d{3})*(?:\.\d+)?', basis))
                    if not mentioned:
                        mismatch = True
                    elif method == 'listing':
                        method = 'comparable'
            if mismatch and allow_estimates:
                method = 'estimate'
                basis = 'LOW-CONFIDENCE AI ESTIMATE — not verified current pricing. The supplied explanation did not match the referenced listing price, so that citation was removed. Review this range as an unsourced estimate.'
            elif mismatch:
                continue
            if method == 'estimate':
                refs = []
            row[market] = {'low': lo, 'high': hi, 'sources': refs, 'basis': basis, 'method': method}
        results.append(row)
    return {'rows': results, 'sources': sources, 'notes': str(data.get('notes', ''))[:3000],
            'queries': metadata.get('webSearchQueries', []), 'search_entry': (metadata.get('searchEntryPoint') or {}).get('renderedContent', ''),
            'checked': dt.datetime.now().astimezone().isoformat(timespec='seconds'), 'currency': currency,
            'model': answer.get('model', '')}

def ask(data, owner=None):
    if data.get('task') == 'estimate':
        from value_sources import gather
        data = {**data, 'allow_estimates': True}
        data['inventory_specs'] = specifications(data['components'])
        data = {**data, 'sources': gather(data)}
        if owner and owner.closed:
            raise OSError('Valuation cancelled.')
    exe = Path(__file__).with_name('ai') / 'ValueAI.exe'
    process = subprocess.Popen([str(exe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, encoding='utf-8', creationflags=0x08000000)
    if owner:
        owner.process = process
        if owner.closed:
            process.terminate()
    try:
        stdout, _ = process.communicate(json.dumps(data, ensure_ascii=True) + '\n', timeout=230)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise OSError('AI request timed out. Please retry.')
    finally:
        if owner:
            owner.process = None
    answer = json.loads(stdout or '{}')
    if not answer.get('ok'):
        raise OSError(answer.get('error', 'AI is unavailable. Please retry.'))
    if data.get('task') == 'estimate':
        parsed = parse_estimate(answer, data['components'], data['currency'])
        missing = {row['id']: [m for m in ('new', 'used') if not row[m]] for row in parsed['rows'] if not row['new'] or not row['used']}
        if missing:
            fallback = ask({'task': 'fill_estimates', 'country': data['country'], 'currency': data['currency'], 'condition': data['condition'],
                            'components': {k: data['components'][k] for k in missing}, 'missing_markets': missing,
                            'inventory_specs': {k: data['inventory_specs'][k] for k in missing},
                            'existing_ranges': parsed['rows'], 'fx_sources': [s for s in data['sources'] if s.get('market') == 'fx']}, owner)
            repaired = decode_object(fallback['text'])
            if repaired.get('currency') != data['currency']:
                raise ValueError('Fallback estimates used a different currency. Please retry.')
            original = decode_object(answer['text'])
            original_items = {r['id']: r for r in original['items'] if isinstance(r, dict) and r.get('id') in data['components']}
            for item in repaired.get('items', []):
                if not isinstance(item, dict) or item.get('id') not in missing:
                    continue
                key = item['id']
                target = original_items.setdefault(key, {'id': key})
                for market in missing[key]:
                    quote = item.get(market)
                    if isinstance(quote, dict):
                        target[market] = {**quote, 'method': 'estimate', 'sources': [],
                                          'basis': 'LOW-CONFIDENCE AI ESTIMATE — not verified current pricing. ' + str(quote.get('basis', 'Assumptions need review.'))}
            original['items'] = list(original_items.values())
            original['notes'] = str(original.get('notes', '')) + ' Missing listing prices were completed with explicitly labeled low-confidence AI estimates where the component could be recognized.'
            answer['text'] = json.dumps(original)
    return answer

class PCValuePage:
    def __init__(self, hub, tab, g, enabled=True):
        self.hub, self.g, self.enabled = hub, g, enabled
        self.busy = self.closed = False
        self.process = None
        self.photo = None
        self.result = None
        self.revision = 0
        self.preview_image = None
        body = hub.page(tab, 'PC Value Checker', 'Upload a photo, confirm your parts, then check current replacement and resale price ranges.')
        settings = hub.box(body, '1. Choose your market', 'Country controls the market searched. Currency controls every displayed price. Include quantities and capacities in the component names.')
        self.country = tk.StringVar(value='United States')
        self.currency = tk.StringVar(value='USD')
        self.condition = tk.StringVar(value='Good — fully working')
        for title, var, values, state in [('Country', self.country, COUNTRIES, 'normal'), ('Currency', self.currency, CURRENCIES, 'readonly'),
                                         ('Condition', self.condition, ('Like new', 'Good — fully working', 'Fair — working with wear', 'Faulty / for parts'), 'readonly')]:
            hub.label(settings, title)
            widget = g['RSelect'](settings,values,width=360,command=var.set)
            widget.set(var.get());widget.pack(anchor='w',padx=16,pady=6)
            var.trace_add('write',lambda *args,selector=widget,variable=var:selector.set(variable.get()))
            if state=='normal':
                def custom_country(variable=var):
                    value=simpledialog.askstring('Country','Enter your country or market:',initialvalue=variable.get(),parent=hub)
                    if value and value.strip():variable.set(value.strip()[:120])
                hub.action(settings,'Enter another country',custom_country)
            var.trace_add('write', self.invalidate)
        photos = hub.box(body, '2. Add a computer photo (optional)', 'Choose a JPG, PNG or WebP photo. Analyze photo sends only that image to the existing Gemini connection. Hidden parts and unreadable labels must be entered manually.')
        self.photo_label = hub.label(photos, 'No photo selected.')
        hub.action(photos, 'Choose photo…', self.choose_photo)
        hub.action(photos, 'Analyze photo with AI', self.analyze)
        hub.action(photos, 'Remove photo', self.remove_photo)
        parts = hub.box(body, '3. List or confirm components', 'Use this PC’s existing hardware scan, enter parts manually, or review photo suggestions. Confirm exact models, capacities and quantities. Unknown parts are excluded from the estimate.')
        hub.action(parts, 'Use this PC’s components', self.use_this_pc)
        hub.label(parts, 'Fills CPU, separate graphics cards, motherboard, RAM and physical drives from RETWEAKS’s scan. Power supply, case, cooling and Other stay as entered. No data is sent until you check value.', color=g['MUTED'])
        self.confirmed = tk.BooleanVar(value=False)
        self.parts = {}
        component_grid=tk.Frame(parts,bg=g['PANEL']);component_grid.pack(fill='x',padx=10,pady=8)
        fields=[]
        for kind in KINDS:
            field=tk.Frame(component_grid,bg=g['PANEL']);fields.append(field)
            hub.label(field,kind)
            var=tk.StringVar();entry=g['REntry'](field,var)
            entry.pack(fill='x',padx=12,pady=(0,12))
            var.trace_add('write',self.edit_parts);self.parts[kind]=var
        def arrange(event=None):
            columns=2 if component_grid.winfo_width()>740 else 1
            for column in range(2):component_grid.columnconfigure(column,weight=1 if column<columns else 0,uniform='components')
            for index,field in enumerate(fields):field.grid(row=index//columns,column=index%columns,sticky='ew')
        component_grid.bind('<Configure>',arrange);arrange()
        self.confirm = g['RCheck'](parts,'I have reviewed these components and quantities.',self.confirmed,outer=g['PANEL'])
        self.confirm.pack(anchor='w',padx=16,pady=12)
        hub.action(parts, 'Check current value', self.estimate)
        self.status = hub.label(body, 'Ready. No photo or component details have been sent.', color=g['MUTED'])
        self.results = tk.Frame(body, bg=g['BG'])
        self.results.pack(fill='x')
        hub.action(body, 'Save valuation report…', self.save)
        hub.bind('<Destroy>', self.destroy, add='+')

    def invalidate(self, *_):
        self.revision += 1
        self.result = None
        if hasattr(self, 'results'):
            for child in self.results.winfo_children():
                child.destroy()

    def edit_parts(self, *_):
        self.confirmed.set(False)
        self.invalidate()

    def use_this_pc(self):
        if self.busy:
            self.status.config(text='Wait for the current request to finish before importing components.')
            return
        values = detected_components(getattr(self.hub, 'info', None))
        if not values:
            self.status.config(text='Hardware details are not available yet. Let RETWEAKS finish its startup scan, then click Use this PC’s components again.')
            return
        for kind in ('CPU', 'GPU', 'Motherboard', 'RAM', 'Storage'):
            self.parts[kind].set(values.get(kind, ''))
        self.status.config(text='Loaded this PC’s detected components locally. Review models, capacities and quantities, then confirm the list. Add any missing PSU, case or cooling manually. Integrated graphics are included with the CPU.')

    def remove_photo(self):
        if self.busy:
            return
        self.photo = self.preview_image = None
        self.photo_label.config(text='No photo selected.', image='')

    def choose_photo(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self.hub, title='Choose a computer photo', filetypes=[('Computer photos', '*.jpg *.jpeg *.png *.webp')])
        if not path:
            return
        try:
            from PIL import Image, ImageOps, ImageTk
            if Path(path).stat().st_size > 20 * 1024 * 1024:
                raise ValueError('Choose a photo smaller than 20 MB.')
            with Image.open(path) as image:
                if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 40000000:
                    raise ValueError('Choose a JPG, PNG or WebP photo under 40 megapixels.')
                image = ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((1600, 1600))
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=88)
                self.photo = base64.b64encode(output.getvalue()).decode('ascii')
                image.thumbnail((360, 200))
                self.preview_image = ImageTk.PhotoImage(image)
            self.photo_label.config(image=self.preview_image, text=Path(path).name, compound='top')
            self.status.config(text='Photo selected locally. Click Analyze photo to send it to AI.')
        except Exception as exc:
            self.status.config(text='Could not load photo: ' + str(exc)[:240])

    def run(self, task, request):
        if self.busy:
            self.status.config(text='A request is already running.')
            return
        if not self.enabled:
            self.status.config(text='AI is disabled in this session.')
            return
        self.busy = True
        revision = self.revision
        self.status.config(text='Analyzing photo…' if task == 'photo' else 'Reading current retail and resale sources, then analyzing prices… This can take a minute.')
        def worker():
            try:
                answer = ask(request, self)
                result = decode_object(answer['text']) if task == 'photo' else parse_estimate(answer, request['components'], request['currency'])
                event = {'task': task, 'result': result, 'request': request if task != 'photo' else {}, 'revision': revision}
            except Exception as exc:
                event = {'error': str(exc)[:500], 'revision': revision}
            if not self.closed:
                self.hub.q.put(('pc_value', event))
        threading.Thread(target=worker, daemon=True).start()

    def analyze(self):
        if not self.photo:
            self.status.config(text='Choose a computer photo first, or enter components manually.')
            return
        if any(v.get().strip() for v in self.parts.values()):
            from tkinter import messagebox
            if not messagebox.askyesno('Replace component list?', 'Photo analysis will replace the current component list with unconfirmed suggestions.', parent=self.hub):
                return
        self.run('photo', {'task': 'photo', 'image': self.photo})

    def estimate(self):
        if self.busy:
            self.status.config(text='A request is already running.')
            return
        components = {k: v.get().strip()[:350] for k, v in self.parts.items() if v.get().strip()}
        if not components or not self.confirmed.get():
            self.status.config(text='Enter at least one component and confirm the reviewed list.')
            return
        if not self.country.get().strip():
            self.status.config(text='Choose or enter a country.')
            return
        self.invalidate()
        self.run('estimate', {'task': 'estimate', 'country': self.country.get().strip()[:100], 'currency': self.currency.get(),
                              'condition': self.condition.get(), 'components': normalize_components(components)})

    def event(self, event):
        self.busy = False
        if event['revision'] != self.revision:
            self.status.config(text='Inputs changed during the request. Review the current inputs and try again.')
            return
        if 'error' in event:
            self.status.config(text=event['error'])
            return
        result = event['result']
        if event['task'] == 'photo':
            items = result.get('components')
            if not isinstance(items, dict):
                self.status.config(text='The photo response had no component list. Try another photo or enter parts manually.')
                return
            for kind, var in self.parts.items():
                value = items.get(kind, '')
                var.set(value[:350] if isinstance(value, str) else '')
            self.status.config(text='Unconfirmed photo suggestions. ' + str(result.get('notes', ''))[:1600])
        else:
            self.result = {**result, 'market': event['request']['country'], 'condition': event['request']['condition']}
            self.render()
            self.status.config(text='Estimate checked ' + result['checked'] + '. Review coverage and sources below.')

    def money(self, value):
        return f'{self.result["currency"]} {value:,.0f}'

    def range_text(self, quote):
        return self.money(quote['low']) + ' – ' + self.money(quote['high'])

    def render(self):
        for child in self.results.winfo_children():
            child.destroy()
        r = self.result
        body = self.hub.box(self.results, 'Estimated PC value · ' + r['market'],
                            'Totals can include exact listings, comparable parts and low-confidence AI estimates. AI fallback estimates are not verified current prices; review the breakdown below. Used resale is a parts-based estimate. Taxes, shipping and selling fees are excluded unless stated.')
        for market, label in [('new', 'New replacement'), ('used', 'Used resale (parts basis)')]:
            quotes = [row[market] for row in r['rows'] if row[market]]
            total = {'low': sum(q['low'] for q in quotes), 'high': sum(q['high'] for q in quotes)}
            coverage = f'{len(quotes)}/{len(r["rows"])} listed components priced'
            counts = Counter(q.get('method', 'listing') for q in quotes)
            coverage += f' · {counts["listing"]} listing-based, {counts["comparable"]} comparable, {counts["estimate"]} AI estimates'
            text = self.range_text(total) if quotes else 'Unavailable'
            self.hub.label(body, label + ': ' + text + (' (includes estimates)' if counts['estimate'] else ''), 17)
            self.hub.label(body, coverage + (' — partial subtotal; missing prices excluded' if len(quotes) != len(r['rows']) else '') + '.', color=self.g['MUTED'])
        self.hub.label(body, r['notes'])
        for row in r['rows']:
            box = self.hub.box(self.results, row['id'] + ' · ' + row['name'], row['note'])
            for market, label in [('new', 'New'), ('used', 'Used')]:
                quote = row[market]
                method_label = {'listing': 'listing-based', 'comparable': 'comparable / derived estimate', 'estimate': 'LOW-CONFIDENCE AI ESTIMATE · not verified current pricing'}
                self.hub.label(box, label + ': ' + (self.range_text(quote) + ' · ' + method_label[quote.get('method', 'listing')] if quote else 'Model details needed to estimate this part'))
                if quote:
                    self.hub.label(box, quote['basis'], color=self.g['MUTED'])
                    for i in quote['sources']:
                        source = r['sources'][i]
                        listing = source.get('listing') or {}
                        if type(listing.get('price')) in (int, float):
                            actual = f'{listing.get("currency", "")} {listing["price"]:,.2f}'
                            self.hub.label(box, f'At check time, referenced listing asked {actual} per listing. ' + ('This is comparison evidence; the estimated range is not this seller’s price.' if quote.get('method') == 'comparable' else 'Check listing quantity and condition.'), color=self.g['MUTED'])
                        self.hub.action(box, f'[{i + 1}] ' + str(source.get('title') or source['uri'])[:100], lambda u=source['uri']: webbrowser.open(u))
                    if quote.get('method') == 'estimate':
                        self.hub.label(box, 'No verified listing supports this range. It is an AI estimate, not a linked seller’s asking price.', color=self.g['MUTED'])
        if r['queries']:
            box = self.hub.box(self.results, 'Search queries', '\n'.join(str(q) for q in r['queries']))
            for query in r['queries'][:12]:
                from urllib.parse import quote_plus
                self.hub.action(box, str(query)[:90], lambda q=str(query): webbrowser.open('https://www.google.com/search?q=' + quote_plus(q)))

    def save(self):
        if not self.result:
            self.status.config(text='Check current value before saving a report.')
            return
        path = filedialog.asksaveasfilename(parent=self.hub, title='Save valuation report', defaultextension='.json', filetypes=[('JSON report', '*.json')])
        if path:
            try:
                Path(path).write_text(json.dumps(self.result, indent=2, ensure_ascii=False), encoding='utf-8')
                self.status.config(text='Valuation report saved with component ranges, sources and check time.')
            except OSError as exc:
                self.status.config(text='Could not save report: ' + str(exc)[:240])

    def destroy(self, event):
        if event.widget is self.hub:
            self.closed = True
            if self.process is not None:
                try:
                    self.process.terminate()
                except OSError:
                    pass
