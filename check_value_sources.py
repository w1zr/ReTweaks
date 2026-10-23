"""Independent pricing-source checks: no network, credentials or live AI."""
import json
from unittest.mock import patch, Mock
from value_sources import jawa_sources, source_page, gather, query_name, search_variants, expanded_jawa, EvidenceText
from pc_value import parse_estimate, ask

products = [
    {'name': 'Example CPU', 'price': 12000, 'category': {'id': 1}, 'condition': 'used', 'status': 'available', 'url': '/product/1/cpu', 'quantity_available': 1},
    {'name': 'New Example CPU', 'price': 18000, 'category': {'id': 1}, 'condition': 'bnib', 'status': 'available', 'url': '/product/2/cpu'},
    {'name': 'Complete PC', 'price': 150000, 'category': {'id': 28}, 'condition': 'used', 'status': 'available', 'url': '/product/3/pc'},
    {'name': 'Sold CPU', 'price': 10000, 'category': {'id': 1}, 'condition': 'used', 'status': 'sold', 'url': '/product/4/cpu'},
    {'name': 'Bad URL', 'price': 10000, 'category': {'id': 1}, 'condition': 'used', 'status': 'available', 'url': '//untrusted.example/cpu'},
]
fixture = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps({'props': {'pageProps': {'dehydratedState': {'queries': [{'state': {'data': {'products': products}}}]}}}}) + '</script>'
with patch('value_sources.fetch', return_value=fixture) as fetch:
    rows = jawa_sources('CPU', 'Example CPU')
    assert len(rows) == 2 and rows[0]['market'] == 'used' and rows[1]['market'] == 'new'
    assert json.loads(rows[0]['text'])['price'] == 120 and 'asking price' in rows[0]['text']
    assert 'categoryIds=1' in fetch.call_args.args[0] and 'name=Example+CPU' in fetch.call_args.args[0]
assert query_name('Example CPU, quantity 2') == 'Example CPU'
assert '32GB DDR4' in search_variants('RAM', 'Corsair CMK16 16 GB DDR4 3200 MT/s, quantity 2')
assert search_variants('GPU', 'NVIDIA GeForce RTX 4070, quantity 1')[0] == 'RTX 4070'
assert len(search_variants('Storage', 'Samsung 980 PRO 931 GiB detected NVMe SSD, quantity 1; Crucial MX500 465 GiB detected SSD, quantity 1')) >= 3
with patch('value_sources.jawa_sources', side_effect=[[], rows]) as retry:
    assert expanded_jawa('RAM', 'Corsair CMK16 16 GB DDR4 3200 MT/s, quantity 2') == rows
    assert retry.call_count == 2
with patch('value_sources.fetch', return_value='Robot check ' + 'x' * 200):
    try:
        source_page('CPU', 'CPU', 'new', 'https://example.com', 'example.com', 'US')
        raise AssertionError('Blocked source accepted')
    except ValueError:
        pass
request = {'country': 'United States', 'currency': 'USD', 'components': {'CPU': 'Example CPU'}}
with patch('value_sources.source_page', side_effect=OSError('Blocked')), patch('value_sources.jawa_sources', return_value=rows):
    assert len(gather(request)) == 2
with patch('value_sources.source_page', side_effect=OSError('Blocked')), patch('value_sources.jawa_sources', return_value=[]):
    try:
        gather(request)
        raise AssertionError('Fabricated empty-source valuation')
    except OSError:
        pass
    assert gather({**request, 'allow_estimates': True}) == []
chunks = [{'web': {'uri': r['uri'], 'title': r['title']}, 'component_id': 'CPU', 'market': r['market']} for r in rows]
quote = {'low': 100, 'high': 130, 'sources': [0]}
answer = {'text': json.dumps({'currency': 'USD', 'items': [{'id': 'CPU', 'new': quote, 'used': quote}]}),
          'grounding': {'groundingChunks': chunks}, 'source_mode': 'public_pages'}
result = parse_estimate(answer, request['components'], 'USD')
assert result['rows'][0]['new'] is None and result['rows'][0]['used'] is not None
# Regression: a $600 Kingston source cannot substantiate a $215 G.SKILL basis.
ram_quote = {'currency': 'USD', 'items': [{'id': 'RAM', 'new': {'low': 200, 'high': 250, 'sources': ['source-016'], 'method': 'comparable', 'basis': 'Derived from G.SKILL 16 GB DDR5 at $215, scaled for two sticks.'},
              'used': {'low': 120, 'high': 160, 'sources': ['source-016'], 'method': 'estimate', 'basis': 'Low-confidence AI estimate of used 32GB RAM.'}}]}
ram_answer = {'allow_estimates': True, 'source_mode': 'public_pages', 'text': json.dumps(ram_quote), 'grounding': {'groundingChunks': [{'source_id': 'source-016', 'component_id': 'RAM', 'market': 'new', 'web': {'uri': 'https://www.jawa.gg/product/1/kingston', 'title': 'Kingston FURY Beast 32GB DDR5 6000', 'listing': {'price': 600, 'currency': 'USD'}}}]}}
ram = parse_estimate(ram_answer, {'RAM': 'Kingston 16GB DDR5 5600, quantity 2'}, 'USD')['rows'][0]
assert ram['new']['method'] == 'estimate' and not ram['new']['sources']
assert ram['used']['method'] == 'estimate' and not ram['used']['sources']
assert 'citation was removed' in ram['new']['basis']
ram_quote['items'][0]['new'].update(low=600, high=600, method='listing', basis='Kingston asking price is $600 for the full 32GB kit.')
direct = parse_estimate({**ram_answer, 'text': json.dumps(ram_quote)}, {'RAM': 'Kingston 32GB kit'}, 'USD')['rows'][0]['new']
assert direct['method'] == 'comparable' and direct['sources'] == [0]
ram_quote['items'][0]['new']['sources'] = [16]
assert parse_estimate({**ram_answer, 'text': json.dumps(ram_quote)}, {'RAM': 'Kingston 32GB kit'}, 'USD')['rows'][0]['new'] is None
initial = {'ok': True, 'allow_estimates': True, 'source_mode': 'public_pages', 'grounding': {}, 'text': json.dumps({'currency': 'USD', 'items': [{'id': 'CPU', 'new': {'low': 100, 'high': 180, 'sources': [], 'method': 'estimate', 'basis': 'Unverified estimate'}, 'used': None}]})}
filled = {'ok': True, 'text': json.dumps({'currency': 'USD', 'items': [{'id': 'CPU', 'used': {'low': 40, 'high': 80, 'basis': 'Age and working-condition assumptions'}}]})}
processes = [Mock(), Mock()]
for process, reply in zip(processes, (initial, filled)):
    process.communicate.return_value = (json.dumps(reply), '')
with patch('value_sources.gather', return_value=[]), patch('pc_value.subprocess.Popen', side_effect=processes) as create:
    answer = ask({**request, 'task': 'estimate', 'condition': 'Good — fully working'})
    complete = parse_estimate(answer, request['components'], 'USD')
    assert complete['rows'][0]['new']['low'] == 100
    assert complete['rows'][0]['used']['method'] == 'estimate' and not complete['rows'][0]['used']['sources']
    followup = json.loads(processes[1].communicate.call_args.args[0])
    assert followup['missing_markets'] == {'CPU': ['used']} and followup['task'] == 'fill_estimates'
print('PASS: independent public sources, category/condition filtering, price units, retailer-block fallback, no invented empty prices and per-market source validation.')
