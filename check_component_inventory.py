"""Global inventory regression cases, independent of any user's hardware."""
from component_inventory import normalize_components, specifications, matches_capacity, capacity_gb, exact_model_match
from pc_value import parse_estimate
import json

for name,total in [('16 GB DDR5, quantity 2',32),('32GB (2 x 16GB) DDR5',32),('2x16GB DDR4',32),('8GB DDR4, quantity 4',32),('16GB DDR4, quantity 1; 8GB DDR4, quantity 2',32),('64GB total RAM',64),('32GB (2x16GB) DDR5, quantity 2',64),('32GB DDR5',32)]:
    result=normalize_components({'RAM':name})
    assert specifications(result)['RAM']['total_gb']==total,(name,result)
    assert normalize_components(result)==result
assert 'modules' not in specifications({'RAM':'32GB DDR5'})['RAM']
assert capacity_gb('2 x 1TB SSD bundle') == 2000
assert capacity_gb('1TB x 2 SSD bundle') == 2000
assert exact_model_match('Samsung 980 PRO 1TB, quantity 1','Samsung 980 PRO 1TB SSD')
assert not exact_model_match('Samsung 980 PRO 1TB','Samsung 980 1TB SSD')
assert not exact_model_match('WD SN770 1TB','Samsung 980 1TB SSD')

parts=normalize_components({'Storage':'Samsung SSD 980 PRO 931 GiB detected NVMe SSD, quantity 1; WD SN770 931 GiB detected NVMe SSD, quantity 1','RAM':'Kingston KF560C36-16 16 GB DDR5 5600 MT/s, quantity 2'})
assert set(parts)=={'Storage 1','Storage 2','RAM'}
assert all(specifications(parts)[key]['unit_gb']==1000 for key in ('Storage 1','Storage 2'))
assert 'Samsung' in parts['Storage 1'] and 'WD' in parts['Storage 2']
assert all('2 TB' not in parts[key] for key in ('Storage 1','Storage 2'))
assert len(normalize_components({'Storage':'Samsung 1TB SSD, quantity 2'}))==2
assert capacity_gb('2 TB')==2000 and capacity_gb('931 GiB detected')==1000

def source(title):return {'title':title,'listing':{'price':100,'currency':'USD'},'uri':'https://www.jawa.gg/product/1/item'}
assert matches_capacity('RAM',parts['RAM'],source('Kingston 32GB (2x16GB) DDR5 5600'))
assert not matches_capacity('RAM',parts['RAM'],source('Kingston 16GB DDR5 5600'))
assert not matches_capacity('RAM',parts['RAM'],source('32GB DDR4 3200'))
assert matches_capacity('Storage 1',parts['Storage 1'],source('Samsung 980 PRO 1TB NVMe SSD'))
assert not matches_capacity('Storage 1',parts['Storage 1'],source('Samsung 980 PRO 2TB NVMe SSD'))
assert not matches_capacity('Storage 1',parts['Storage 1'],source('Samsung SSD with no capacity'))
assert not matches_capacity('RAM',parts['RAM'],{'title':'32GB DDR5 search results'})

answer={'allow_estimates':True,'source_mode':'public_pages','grounding':{'groundingChunks':[{'source_id':'wrong-ssd','component_id':'Storage 1','market':'new','web':source('Samsung 2TB NVMe SSD')},{'source_id':'wrong-ram','component_id':'RAM','market':'new','web':source('Kingston 16GB DDR5')} ]},'text':json.dumps({'currency':'USD','items':[{'id':'Storage 1','new':{'low':100,'high':100,'sources':['wrong-ssd'],'method':'listing'}},{'id':'RAM','new':{'low':100,'high':100,'sources':['wrong-ram'],'method':'listing'}}]})}
r=parse_estimate(answer,parts,'USD')
assert all(row['new'] is None for row in r['rows'])
assert '32 GB total' in next(row['note'] for row in r['rows'] if row['id']=='RAM')
print('PASS: mixed/identical drives remain separate, physical capacities stay per drive, RAM totals/kits/modules agree and wrong-capacity or wrong-generation citations are rejected.')
