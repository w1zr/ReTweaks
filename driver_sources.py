"""Current official driver evidence. Public vendor pages/metadata; no paid search API."""
import concurrent.futures
import datetime
import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urlencode,urljoin,urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
from drivers import allowed_url,clean

AGENT='Mozilla/5.0 (compatible; RETWEAKS Driver Links)'
def fetch(url,domains,limit=400000):
    class Redirect(HTTPRedirectHandler):
        def redirect_request(self,request,fp,code,msg,headers,newurl):
            if not allowed_url(newurl,domains):raise ValueError('Non-vendor redirect')
            return super().redirect_request(request,fp,code,msg,headers,newurl)
    if not allowed_url(url,domains):raise ValueError('Unsupported source')
    if re.search(r'\.(exe|msi|zip|cab|7z|rar)(?:[?#]|$)',url,re.I):raise ValueError('Installer files are opened only by the user')
    with build_opener(Redirect()).open(Request(url,headers={'User-Agent':AGENT}),timeout=8) as response:
        kind=response.headers.get('Content-Type','').lower()
        if any(k in kind for k in ('application/octet-stream','application/x-msdownload','application/zip')):raise ValueError('Not a web document')
        return response.read(limit).decode('utf-8','replace')

class PageText(HTMLParser):
    def __init__(self,url,domains):super().__init__(convert_charrefs=True);self.url=url;self.domains=domains;self.skip=0;self.parts=[];self.links=[];self.current=None
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','svg'):self.skip+=1
        if tag=='a' and not self.skip:
            target=urljoin(self.url,dict(attrs).get('href',''))
            if allowed_url(target,self.domains):self.current=[target,'']
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','svg'):self.skip=max(0,self.skip-1)
        if tag=='a' and self.current:
            if len(self.links)<100:self.links.append({'url':self.current[0],'label':clean(self.current[1],140)})
            self.current=None
    def handle_data(self,data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())
            if self.current:self.current[1]+=' '+data

def page(row,url):
    parser=PageText(url,row['domains']);parser.feed(fetch(url,row['domains']))
    text=' '.join(parser.parts)
    # Keep download/release contexts before broad navigation text.
    contexts=[]
    for match in list(re.finditer(r'(?i)(driver version|revision|release date|adrenalin|WHQL|version[: ]+[0-9]|windows 11|windows 10)',text))[:30]:contexts.append(text[max(0,match.start()-80):match.start()+250])
    return {'component_id':row['id'],'url':url,'text':(' '.join(contexts)+' '+text[:1500])[:7000], 'links':sorted(parser.links,key=lambda link:not bool(re.search(r'(?i)(download|drivers/details|driverResults|\.exe|\.msi)',link['url'])))[:25]}

def search(row,os_name):
    category="BIOS firmware support" if row["kind"]=="BIOS" else "Windows chipset driver" if row["kind"]=="CPU / chipset" else "Windows driver"
    query=f'{row["name"]} {category} site:{row["domains"][0]}'
    url='https://www.bing.com/search?'+urlencode({'format':'rss','q':query})
    root=ET.fromstring(fetch(url,('bing.com',),400000));results=[]
    for item in root.findall('./channel/item'):
        link=item.findtext('link') or ''
        if link.startswith('http://'):link='https://'+link[7:]
        if allowed_url(link,row['domains']):results.append({'component_id':row['id'],'url':link,'text':clean((item.findtext('title') or '')+' '+(item.findtext('description') or ''),900),'links':[]})
    return results[:4]

def nvidia(row,info):
    if '32' in str((info.get('raw') or {}).get('os_arch','')):return None
    os_name=str(info.get('os','')).lower()
    if 'windows 11' not in os_name and 'windows 10' not in os_name:return None
    source=fetch('https://www.nvidia.com/en-us/drivers/',('nvidia.com',),1500000)
    names=json.loads(re.search(r'var nvProducts\s*=\s*(\[.*?\]);',source,re.S).group(1))
    blocks=re.findall(r"'(\{[^']+\})'",re.search(r'var nvProductsJson\s*=\s*(\[.*?\]);',source,re.S).group(1))
    def normal(name):return re.sub('[^a-z0-9]','',name.lower().replace('nvidia','').replace('(r)','').replace('(tm)',''))
    matches=[i for i,name in enumerate(names) if normal(name.split('|')[-1])==normal(row['name'])]
    if len(matches)!=1 or len(names)!=len(blocks):return None
    ids=json.loads(blocks[matches[0]])
    query={'func':'DriverManualLookup','psid':ids['pst'],'pfid':ids['d2'],'osID':135 if 'windows 11' in os_name else 57,'languageCode':1033,'isWHQL':0,'beta':'null','dltype':-1,'dch':1,'upCRD':0,'qnf':0,'ctk':'null','sort1':0,'numberOfResults':3}
    url='https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/AjaxDriverService.php?'+urlencode(query)
    data=json.loads(fetch(url,('geforce.com',),600000))
    releases=[]
    for item in data.get('IDS',[]):
        details=item.get('downloadInfo') or {}
        if str(details.get('Success'))!='1' or str(details.get('IsBeta'))!='0' or str(details.get('IsWHQL'))!='1':continue
        link=details.get('DetailsURL','');download=details.get('DownloadURL','')
        if not allowed_url(link,row['domains']):continue
        date=datetime.datetime.strptime(details['ReleaseDateTime'],'%a %b %d, %Y').strftime('%Y-%m-%d')
        if date>datetime.date.today().isoformat():continue
        releases.append({'component_id':row['id'],'url':link,'download':download if allowed_url(download,row['domains']) else '', 'version':clean(details.get('Version'),80),'date':date,'name':row['name'],'verified':True,'note':'Latest stable WHQL release returned by NVIDIA for this exact GPU and Windows version.'})
    return max(releases,key=lambda r:r['date']) if releases else None

def amd_product(row):
    match=re.search(r'(?i)radeon\s+(RX\s+([5679])\d{3}(?:\s*(?:XT|XTX))?)\s*$',row['name'])
    if not match:return None
    model=re.sub(r'\s+','-',match.group(1).strip().lower());series=match.group(2)+'000'
    return f'https://www.amd.com/en/support/downloads/drivers.html/graphics/radeon-rx/radeon-rx-{series}-series/amd-radeon-{model}.html'

def gather(info,rows):
    def one(row):
        evidence=[];facts=[]
        if row['vendor_key']=='nvidia' and row['kind']=='Graphics':
            try:
                release=nvidia(row,info)
                if release:
                    facts.append(release)
                    return [{'component_id':row['id'],'url':release['url'],'text':json.dumps(release),'links':[{'url':release['download'],'label':'Official driver download'}] if release['download'] else []}],facts
            except (OSError,ValueError,KeyError,AttributeError,TypeError):pass
        target=amd_product(row) if row['vendor_key']=='amd' and row['kind']=='Graphics' else None
        try:evidence.append(page(row,target or row['url']))
        except Exception:
            if target:
                try:evidence.append(page(row,row['url']))
                except Exception:pass
        try:
            results=search(row,info.get('os',''))
            for item in results:
                if item['url'] not in [s['url'] for s in evidence]:evidence.append(item)
            for item in results[:1]:
                if item['url']!=row['url']:
                    try:evidence.append(page(row,item['url']))
                    except Exception:pass
        except Exception:pass
        return evidence[:5],facts
    evidence=[];facts=[];remaining=42000;per_row=max(1500,42000//max(1,min(20,len(rows))))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        # Preserve priority: graphics and motherboard, then the detected devices.
        for sources,releases in pool.map(one,rows[:20]):
            facts.extend(releases)
            source_budget=per_row//max(1,len(sources))
            for source in sources:
                source['text']=source['text'][:max(0,min(source_budget,remaining))];remaining-=len(source['text'])
                source['links']=source['links'][:10]
                if source['text']:evidence.append(source)
    return evidence,facts
