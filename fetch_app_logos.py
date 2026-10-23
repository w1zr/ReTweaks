"""Developer-only asset refresh. No icon network requests occur in the application."""
from pathlib import Path
import urllib.request,urllib.parse,re,html,io,json,concurrent.futures
from PIL import Image
from app_catalog import CATALOG
OUT=Path(__file__).parent/'assets/apps'
SLUGS={k:k for k in ('chrome discord steam spotify nvidia logitech firefox edge brave opera vivaldi librewolf thunderbird zoom slack telegram signal element anydesk audacity handbrake libreoffice onlyoffice notion obsidian joplin calibre anki todoist bitwarden keepassxc tailscale wireguard treesize vscode git github python dotnet docker postman syncthing putty gimp blender qbittorrent').split()}
SLUGS.update(drive='google-drive',epic='epic-games',capcut='cap-cut',teams='microsoft-teams',teamviewer='team-viewer',protonvpn='proton-vpn',sevenzip='7zip',etcher='balena-etcher',node='nodejs')
CURATED=json.loads((OUT/'sources.json').read_text(encoding='utf-8')) if (OUT/'sources.json').is_file() else {}
REV='b409eb0d1fa960277f8510d3ae3a19093b910ca4'
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 RETWEAKS asset preparation'}),timeout=18) as response:return response.read(5000000)
def one(row):
    key,name,_,_,site=row;candidates=[CURATED[key]['url']] if isinstance(CURATED.get(key),dict) else []
    if key in SLUGS:candidates.append(f'https://raw.githubusercontent.com/homarr-labs/dashboard-icons/{REV}/png/{SLUGS[key]}.png')
    # Prefer vendor artwork; indexed favicons provide a second source for sites
    # that block automated page requests. Preserve native dimensions in metadata.
    if not candidates:
        try:
            page=get(site).decode('utf-8',errors='replace')
            tags=re.findall(r'<link\b[^>]+>',page,re.I)
            for tag in sorted(tags,key=lambda t:'apple-touch' not in t):
                if re.search(r'rel=[\"\'][^\"\']*icon',tag,re.I):
                    match=re.search(r'href=[\"\']([^\"\']+)',tag,re.I)
                    if match and '.svg' not in match[1]:candidates.append(urllib.parse.urljoin(site,html.unescape(match[1])))
        except Exception:pass
    candidates.append('https://www.google.com/s2/favicons?sz=256&domain_url='+urllib.parse.quote(site,safe=''))
    candidates.append(urllib.parse.urljoin(site,'/favicon.ico'))
    best=None
    for url in dict.fromkeys(candidates):
        try:
            data=get(url);vector=b'<svg' in data[:1000]
            if vector:
                import resvg_py
                svg=data.decode('utf-8').replace('width="85.741mm" height="12.889mm"','width="1024" height="154"')
                data=resvg_py.svg_to_bytes(svg_string=svg,width=256)
            source=Image.open(io.BytesIO(data))
            if source.format=='ICO':source=source.ico.getimage(max(source.ico.sizes(),key=lambda size:size[0]*size[1]))
            image=source.convert('RGBA');size=image.size
            if best is None or min(size)>min(best[2]):best=(image,url,size)
            if min(size)>=128:break
        except Exception:pass
    if best is None:raise RuntimeError('No artwork for '+key)
    image,url,size=best;image.thumbnail((256,256),Image.Resampling.LANCZOS)
    canvas=Image.new('RGBA',(256,256));canvas.alpha_composite(image,((256-image.width)//2,(256-image.height)//2));canvas.save(OUT/(key+'.png'),optimize=True)
    print(key+': '+str(size),flush=True)
    return key,{'url':url,'native_size':size,'canvas_size':[256,256]}
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:results=dict(pool.map(one,CATALOG))
    (OUT/'sources.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
if __name__=='__main__':main()
