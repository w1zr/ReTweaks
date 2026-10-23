"""Valuation evidence validation and UI lifecycle; no network or private photo."""
import copy
import json
import base64
import io
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
from pc_value import parse_estimate, safe_url, detected_components

hardware = {'cpu': 'AMD Ryzen 7 7700', 'gpu': 'NVIDIA GeForce RTX 4070', 'ram': '32', 'username': 'PRIVATE-USER',
            'raw': {'board': 'ASUS B650-PLUS', 'serial': 'PRIVATE-SERIAL',
                    'gpus': [{'name': 'NVIDIA GeForce RTX 4070', 'pnp': 'PCI\\'}, {'name': 'AMD Radeon(TM) Graphics', 'pnp': 'PCI\\'},
                             {'name': 'Virtual Display', 'pnp': 'OTHER'}],
                    'ram_modules': [{'maker': 'Corsair', 'part': 'CMK16', 'gb': 16, 'type': 'DDR5', 'speed': '6000', 'serial': 'PRIVATE-RAM'}] * 2,
                    'disks': [{'name': 'Samsung SSD 980 PRO', 'kind': 'NVMe SSD', 'gb': 931, 'serial': 'PRIVATE-DISK'}],
                    'volumes': [{'label': 'PRIVATE-VOLUME', 'gb': 931}]}}
detected = detected_components(hardware)
assert detected['GPU'] == 'NVIDIA GeForce RTX 4070, quantity 1'
assert detected['RAM'].startswith('32 GB total (2 × 16 GB modules)')
assert 'Samsung SSD 980 PRO 931 GiB detected NVMe SSD, quantity 1' == detected['Storage']
assert 'PRIVATE' not in str(detected) and 'Power supply' not in detected
assert detected_components(None) == {} and detected_components({'cpu': '?', 'gpu': 'Unknown', 'ram': '0'}) == {}
assert 'GPU' not in detected_components({'cpu': 'Example CPU', 'gpu': 'Intel UHD Graphics 770'})
assert '32 GB total RAM' in detected_components({'ram': '32'})['RAM']

parts = {'CPU': 'Example CPU', 'GPU': 'Example GPU'}
data = {'currency': 'USD', 'items': [
    {'id': 'CPU', 'new': {'low': 100, 'high': 140, 'sources': [0], 'basis': 'Retail offers'},
     'used': {'low': 60, 'high': 90, 'sources': [1], 'basis': 'Sold comparisons'}},
    {'id': 'GPU', 'new': {'low': 200, 'high': 300, 'sources': [99]}, 'used': None}]}
answer = {'text': json.dumps(data), 'grounding': {'groundingChunks': [
    {'web': {'uri': 'https://retailer.example/product', 'title': 'Retail'}},
    {'web': {'uri': 'https://market.example/sold', 'title': 'Sold'}}]}}
r = parse_estimate(answer, parts, 'USD')
assert r['rows'][0]['new']['low'] == 100 and r['rows'][1]['new'] is None
for lo, hi, refs in [(float('nan'), 140, [0]), (140, 100, [0]), (-1, 10, [0]), (1, 2, [True]), (1, 2, []), (True, 2, [0])]:
    bad = copy.deepcopy(data)
    bad['items'][0]['new'] = {'low': lo, 'high': hi, 'sources': refs}
    assert parse_estimate({**answer, 'text': json.dumps(bad)}, parts, 'USD')['rows'][0]['new'] is None
for changed in [{**answer, 'grounding': {}}, {**answer, 'text': json.dumps({**data, 'currency': 'EUR'})}]:
    try:
        parse_estimate(changed, parts, 'USD')
        raise AssertionError('Unsupported valuation accepted')
    except ValueError:
        pass
assert not safe_url('javascript:alert(1)') and not safe_url('https://user:password@example.com')
assert not safe_url('https://example.com:1234') and safe_url('https://example.com/price')
fallback = {'text': json.dumps({'currency': 'USD', 'items': [{'id': 'CPU', 'new': {'low': 80, 'high': 160, 'sources': [], 'method': 'estimate', 'basis': 'Low-confidence AI estimate; no exact current listing.'}, 'used': {'low': 35, 'high': 85, 'sources': [], 'method': 'estimate', 'basis': 'Low-confidence AI estimate; working condition assumed.'}}]}), 'allow_estimates': True, 'source_mode': 'public_pages', 'grounding': {}}
estimated = parse_estimate(fallback, {'CPU': 'Example CPU'}, 'USD')
assert estimated['rows'][0]['new']['method'] == 'estimate' and not estimated['rows'][0]['new']['sources']
try:
    parse_estimate({**fallback, 'allow_estimates': False}, {'CPU': 'Example CPU'}, 'USD')
    raise AssertionError('Unsourced estimates silently enabled')
except ValueError:
    pass

import retweaks as app
import hubplus
import automation
class Hotkeys:
    def __init__(self, *args): self.thread = Mock()
    def update(self, *args): pass
    def close(self): pass
automation.Hotkeys = Hotkeys
app.Hub._load_info = lambda self: None
hubplus.write_json = lambda *args: None
hubplus.install(vars(app))
hub = app.Hub(show_intro=False, enable_ai=False)
hub.withdraw()
try:
    page = hub.pc_value
    hub.info = hardware
    page.parts['Power supply'].set('My manually entered PSU')
    page.confirmed.set(True)
    with patch('pc_value.ask') as network:
        page.use_this_pc()
        network.assert_not_called()
    assert page.parts['CPU'].get() == 'AMD Ryzen 7 7700, quantity 1'
    assert page.parts['RAM'].get() == detected['RAM'] and not page.confirmed.get()
    assert page.parts['Power supply'].get() == 'My manually entered PSU'
    assert page.country.get() == 'United States' and page.currency.get() == 'USD'
    imported = page.parts['CPU'].get()
    page.busy = True
    hub.info = {'cpu': 'Do not import while request is running'}
    page.use_this_pc()
    assert page.parts['CPU'].get() == imported
    page.busy = False
    hub.info = None
    page.use_this_pc()
    assert page.parts['CPU'].get() == imported and 'not available yet' in page.status.cget('text')
    for var in page.parts.values():
        var.set('')
    from PIL import Image
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
        assert Path(directory).resolve().parent == Path(__file__).resolve().parent
        photo = Path(directory) / 'computer.jpg'
        exif = Image.Exif()
        exif[315] = 'PRIVATE PHOTO METADATA'
        Image.new('RGB', (2000, 1000), '#202020').save(photo, exif=exif)
        with patch('pc_value.filedialog.askopenfilename', return_value=str(photo)):
            page.choose_photo()
        with Image.open(io.BytesIO(base64.b64decode(page.photo))) as prepared:
            assert prepared.size == (1600, 800) and not prepared.getexif()
        page.remove_photo()
        assert page.photo is None
    page.parts['CPU'].set('Example CPU')
    page.confirmed.set(True)
    page.parts['CPU'].set('Another CPU')
    assert not page.confirmed.get()
    page.confirmed.set(True)
    with patch.object(page, 'run') as run:
        page.estimate()
        request = run.call_args.args[1]
        assert 'image' not in request and request['components'] == {'CPU': 'Another CPU'}
    page.event({'revision': page.revision - 1, 'result': {}, 'task': 'photo'})
    assert 'Inputs changed' in page.status.cget('text')
    page.event({'revision': page.revision, 'task': 'estimate', 'result': r,
                'request': {'country': 'United States', 'condition': 'Good'}})
    assert page.result and page.results.winfo_children()
    page.currency.set('EUR')
    assert page.result is None and not page.results.winfo_children()
    page.event({'revision': page.revision, 'task': 'photo', 'result': {'components': {'CPU': 'Photo suggestion'}, 'notes': 'Read labels'}, 'request': {}})
    assert page.parts['CPU'].get() == 'Photo suggestion' and not page.confirmed.get()
    assert page.parts['GPU'].get() == ''
    hub.update()
finally:
    hub.destroy()
print('PASS: grounded price validation, missing prices, currency mismatch, unsafe links, confirmation reset, stale results, photo suggestions and result invalidation.')
