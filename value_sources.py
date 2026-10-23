"""Public retail and resale evidence, independent of Gemini Search quotas."""
import concurrent.futures
import datetime as dt
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlencode
from driver_sources import fetch
from component_inventory import kind_of, specifications, matches_capacity

MARKETS = {
    'United States': ('com', [('newegg.com', 'https://www.newegg.com/p/pl?', 'd'), ('bestbuy.com', 'https://www.bestbuy.com/site/searchpage.jsp?', 'st')]),
    'Canada': ('ca', [('newegg.ca', 'https://www.newegg.ca/p/pl?', 'd')]),
    'United Kingdom': ('co.uk', [('scan.co.uk', 'https://www.scan.co.uk/search?', 'q')]),
    'Australia': ('com.au', [('pccasegear.com', 'https://www.pccasegear.com/search?', 'query')]),
    'Germany': ('de', [('alternate.de', 'https://www.alternate.de/listing.xhtml?', 'q')]),
    'France': ('fr', [('ldlc.com', 'https://www.ldlc.com/recherche/', None)]),
    'India': ('com', [('mdcomputers.in', 'https://mdcomputers.in/index.php?route=product/search&', 'search')]),
    'Japan': ('com', [('amazon.co.jp', 'https://www.amazon.co.jp/s?', 'k')]),
    'Brazil': ('com', [('amazon.com.br', 'https://www.amazon.com.br/s?', 'k')]),
    'Mexico': ('com', [('amazon.com.mx', 'https://www.amazon.com.mx/s?', 'k')]),
    'New Zealand': ('com.au', [('pbtech.co.nz', 'https://www.pbtech.co.nz/search?', 'sf')]),
    'South Africa': ('com', [('wootware.co.za', 'https://www.wootware.co.za/catalogsearch/result/?', 'q')]),
    'Singapore': ('com.sg', [('amazon.sg', 'https://www.amazon.sg/s?', 'k')]),
}
JAWA_CATEGORIES = {'CPU': 1, 'GPU': 6, 'Motherboard': 3, 'RAM': 4, 'Storage': 5, 'Power supply': 8, 'Case': 7, 'Cooling': 2, 'Other': 43}


def jawa_sources(kind, model):
    """Read category-filtered public listing data; avoid whole-PC price matches."""
    url = 'https://www.jawa.gg/search?' + urlencode({'name': model, 'categoryIds': JAWA_CATEGORIES[kind_of(kind)]})
    raw = fetch(url, ('jawa.gg',), 1800000)
    match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw, re.S)
    if not match:
        return []
    props = json.loads(match.group(1))['props']['pageProps']
    result = []
    for query in props.get('dehydratedState', {}).get('queries', []):
        data = query.get('state', {}).get('data', {})
        if not isinstance(data, dict):
            continue
        for product in data.get('products', [])[:20]:
            if (product.get('category') or {}).get('id') != JAWA_CATEGORIES[kind_of(kind)]:
                continue
            condition = product.get('condition')
            if condition not in ('used', 'bnib', 'open_box', 'open-box'):
                continue
            price = product.get('price')
            path = product.get('url', '')
            if type(price) not in (int, float) or not 0 < price < 1e10 or not path.startswith('/product/'):
                continue
            if product.get('status') != 'available' or product.get('is_sold_out'):
                continue
            facts = {'name': product.get('name'), 'price': price / 100, 'currency': 'USD', 'condition': condition,
                     'status': 'available', 'price_type': 'asking price, not a completed sale',
                     'updated_at': product.get('updated_at'), 'quantity_available': product.get('quantity_available'),
                     'description': str(product.get('description', ''))[:1200]}
            result.append({'component_id': kind, 'market': 'new' if condition == 'bnib' else 'used', 'country': 'United States',
                           'title': str(product.get('name', ''))[:200], 'uri': 'https://www.jawa.gg' + path,
                           'checked': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
                           'text': json.dumps(facts), 'listing': {'price': price / 100, 'currency': 'USD', 'condition': condition},
                           'basis': 'Public US marketplace asking price; not a sold-price record. Listed amount is per listing; check quantity and whether it is a bundle.'})
    return result

class EvidenceText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.structured = False
        self.parts = []
        self.structured_parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.skip += 1
        if tag == 'script' and dict(attrs).get('type', '').lower() == 'application/ld+json':
            self.structured = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.skip = max(0, self.skip - 1)
        if tag == 'script':
            self.structured = False

    def handle_data(self, data):
        if self.structured:
            self.structured_parts.append(data)
        elif not self.skip and data.strip():
            self.parts.append(data.strip())


def query_name(name):
    return re.sub(r'(?i)\b(?:quantity|qty)\s*[:=]?\s*\d+', '', name).strip(' ,;')[:240]


def search_variants(kind, name):
    """Retry imported SMBIOS names as individual models, then broader comparables."""
    result = []
    kind = kind_of(kind)
    for part in name.split(';'):
        clean = query_name(part)
        clean = re.sub(r'(?i)\b\d+(?:\.\d+)?\s*GiB detected\b|\b(?:NVIDIA|GeForce|AuthenticAMD|GenuineIntel)\b|\(R\)|\(TM\)|[®™]', ' ', clean)
        clean = re.sub(r'\s+', ' ', clean).strip(' ,;()')
        if clean and clean not in result:
            result.append(clean)
    primary = result[0] if result else query_name(name)
    if kind == 'RAM':
        match = re.search(r'(?i)\b(?:LP)?DDR[345]\b', name)
        broad = match.group(0) if match else 'RAM'
        total = specifications({'RAM':name})['RAM'].get('total_gb')
        if total:
            broad = f'{total:g}GB ' + broad
    elif kind == 'Storage':
        broad = 'NVMe SSD' if 'nvme' in name.lower() else 'SSD' if 'ssd' in name.lower() else 'hard drive'
    elif kind == 'Power supply':
        match = re.search(r'(?i)\b\d{3,4}\s*W\b', name)
        broad = match.group(0) if match else 'power supply'
    else:
        broad = ' '.join(primary.split()[:3])
    if broad and broad not in result:
        result.append(broad)
    return result[:4]


def expanded_jawa(kind, name):
    result = []
    seen = set()
    for query in search_variants(kind, name):
        try:
            rows = jawa_sources(kind, query)
        except Exception:
            continue
        for row in rows[:12]:
            if row['uri'] not in seen:
                result.append(row)
                seen.add(row['uri'])
        if len(result) >= 12 and {r['market'] for r in result} == {'new', 'used'}:
            break
    return result


def source_page(kind, model, market, url, domain, country):
    parser = EvidenceText()
    parser.feed(fetch(url, (domain,), 1800000))
    text = ' '.join(parser.parts)
    if len(text) < 100 or re.search(r'(?i)(pardon our interruption|verify you are human|access denied|robot check|checking your browser)', text[:1800]):
        raise ValueError('Source blocked automated reading.')
    # Keep listing names, prices, condition, sale dates and surrounding context.
    contexts = []
    for match in list(re.finditer(r'(?i)(?:US\s*\$|C\s*\$|AU\s*\$|[$£€¥₹]|\b(?:USD|CAD|AUD|EUR|GBP|price|sold|out of stock|in stock)\b)', text))[:70]:
        contexts.append(text[max(0, match.start() - 250):match.start() + 350])
    structured = ' '.join(parser.structured_parts)
    evidence = (structured[:12000] + '\n' + '\n'.join(contexts)[:18000] + '\n' + text[:2000]).strip()[:26000]
    return {'component_id': kind, 'market': market, 'country': country, 'title': domain + ' · ' + model + ' · ' + market,
            'uri': url, 'checked': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'text': evidence,
            'basis': 'Current search listings; confirm exact model, quantity, condition, listing currency, availability and sold versus asking status in the text.'}


def gather(request):
    country = request['country']
    suffix, shops = MARKETS.get(country, ('com', []))
    work = []
    for kind, name in request['components'].items():
        model = search_variants(kind, name)[0]
        for domain, base, key in shops:
            if key:
                url = base + urlencode({key: model})
            else:
                from urllib.parse import quote
                url = base + quote(model) + '/'
            work.append((kind, model, 'new', url, domain, country))
        domain = 'ebay.' + suffix
        # Sold/completed evidence for resale, excluding new condition listings.
        for market, params in [('used', {'LH_Sold': '1', 'LH_Complete': '1', 'LH_ItemCondition': '3000'}),
                               ('new', {'LH_BIN': '1', 'LH_ItemCondition': '1000'})]:
            url = 'https://www.' + domain + '/sch/i.html?' + urlencode({'_nkw': model, **params})
            work.append((kind, model, market, url, domain, country))
    def one(args):
        try:
            return source_page(*args)
        except Exception:
            return None
    sources = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        # Marketplace fallback uses ordinary public pages, not Gemini's Search tool.
        fallback = {kind: pool.submit(expanded_jawa, kind, name) for kind, name in request['components'].items()}
        for row in pool.map(one, work):
            if row:
                sources.append(row)
        for future in fallback.values():
            try:
                sources.extend(future.result())
            except Exception:
                pass
    # Add a dated conversion source only when requested, never a memorized FX rate.
    if sources and request.get('currency', 'USD') != 'USD':
        currency = request['currency']
        url = 'https://api.frankfurter.dev/v1/latest?' + urlencode({'base': 'USD', 'symbols': currency})
        try:
            fx = json.loads(fetch(url, ('frankfurter.dev',), 20000))
            if isinstance(fx.get('rates', {}).get(currency), (int, float)):
                sources.append({'component_id': '*', 'market': 'fx', 'country': 'Global', 'title': 'Dated USD / ' + currency + ' reference rate',
                                'uri': url, 'checked': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'text': json.dumps(fx)})
        except Exception:
            pass
    # Capacity is checked in code, not delegated to the model's judgment.
    sources = [row for row in sources if row.get('market') == 'fx' or matches_capacity(row['component_id'], request['components'][row['component_id']], row)]
    if not sources and not request.get('allow_estimates'):
        raise OSError('No matching retail or resale sources could be read. Please retry.')
    # Bound the ordinary AI request across large builds without dropping a component.
    limit = min(12000, 100000 // max(1, len(sources)))
    for index, row in enumerate(sources):
        row['source_id'] = f'source-{index:03d}'
        row['text'] = row['text'][:limit]
    return sources
