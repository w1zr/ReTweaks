"""In-app driver downloads (core/driver_download.py + driver_download_ui.py). Network, PowerShell and COM are
faked; the samples follow the response formats documented in the module docstring."""
import io
import os
import sys
import tempfile
import threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tk_harness import FakeHub, g, pump
from core import driver_download as dd
import driver_download_ui as ui

fails = []


def ok(cond, what):
    print(("PASS " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


# ------------------------------------------------------------------ samples
TYPE2 = b"""<?xml version="1.0"?><LookupValueSearch><LookupValues>
<LookupValue ParentID="1"><Name>GeForce RTX 40 Series</Name><Value>127</Value></LookupValue>
<LookupValue ParentID="1"><Name>GeForce RTX 40 Series (Notebooks)</Name><Value>129</Value></LookupValue>
</LookupValues></LookupValueSearch>"""
TYPE3 = b"""<?xml version="1.0"?><LookupValueSearch><LookupValues>
<LookupValue ParentID="127"><Name>NVIDIA GeForce RTX 4060 Ti</Name><Value>1022</Value></LookupValue>
<LookupValue ParentID="127"><Name>NVIDIA GeForce RTX 4060</Name><Value>1023</Value></LookupValue>
<LookupValue ParentID="129"><Name>NVIDIA GeForce RTX 4060 Laptop GPU</Name><Value>1004</Value></LookupValue>
</LookupValues></LookupValueSearch>"""
NV_JSON = (b'{"Success":"1","IDS":[{"downloadInfo":{"Version":"531.79","ReleaseDateTime":"Tue May 02, 2023",'
           b'"DownloadURL":"https://us.download.nvidia.com/Windows/531.79/531.79-desktop-win10-win11-64bit-'
           b'international-dch-whql.exe","DownloadURLFileSize":"895.77 MB","IsWHQL":"1","IsBeta":"0",'
           b'"OSName":"Windows%2011","LanguageName":"English%20(US)"}}]}')
AMD_HTML = (b'<a class="btn" href="https://drivers.amd.com/drivers/installer/26.20/whql/amd-software-adrenalin-'
            b'edition-26.10.1-minimalsetup-261018_web.exe">Download Windows Drivers</a>')
seen = []


def fake_get(url, vendor, headers=None, timeout=15, method="GET"):
    seen.append((url, vendor, method, headers))
    if "TypeID=3" in url:
        return url, {}, TYPE3
    if "TypeID=2" in url:
        return url, {}, TYPE2
    if "AjaxDriverService" in url:
        return url, {}, NV_JSON
    if url == dd.AMD_PAGE:
        return url, {}, AMD_HTML
    if method == "HEAD":
        return url, {"Content-Length": "939282432"}, b""
    raise AssertionError(url)


# ------------------------------------------------------------------ lookups
o = dd.nvidia_offer("NVIDIA GeForce RTX 4060", 22631, get=fake_get)
ok(o["version"] == "531.79" and o["url"].startswith("https://us.download.nvidia.com/"), "NVIDIA lookup parsed")
ajax = [u for u, *_ in seen if "AjaxDriverService" in u][0]
ok("pfid=1023" in ajax and "psid=127" in ajax and "osID=135" in ajax, "RTX 4060 -> desktop pfid 1023, Win11 os 135")
seen.clear()
dd.nvidia_offer("NVIDIA GeForce RTX 4060 Laptop GPU", 19045, get=fake_get)
ajax = [u for u, *_ in seen if "AjaxDriverService" in u][0]
ok("pfid=1004" in ajax and "psid=129" in ajax and "osID=57" in ajax, "laptop GPU -> notebook series, Win10 os 57")
try:
    dd.nvidia_offer("NVIDIA GeForce RTX 9999", 22631, get=fake_get)
    ok(False, "unknown GPU refused")
except dd.DriverError as e:
    ok("no exact match" in str(e), "unknown GPU refused, no guess")
for bad in (b'{"Success":"0","IDS":[]}', b"<html>", b'{"Success":"1","IDS":[{"downloadInfo":{"Version":"1",'
            b'"DownloadURL":"https://evil.example.com/x.exe"}}]}'):
    try:
        dd.parse_nvidia(bad, "x")
        ok(False, f"bad NVIDIA answer refused {bad[:20]}")
    except dd.DriverError:
        ok(True, f"bad NVIDIA answer refused {bad[:20]}")
a = dd.amd_offer(get=fake_get)
ok(a["version"] == "26.10.1" and a["url"].endswith("minimalsetup-261018_web.exe") and a["headers"].get("Referer"),
   "AMD link scraped from the driver page")
try:
    dd.amd_offer(get=lambda *a, **k: ("", {}, b"<html>no link</html>"))
    ok(False, "AMD page without link")
except dd.DriverError:
    ok(True, "AMD page without link -> honest error")
ok(dd.intel_offer()["url"] == "https://dsadata.intel.com/installer", "Intel DSA official URL")
p = dd.probe(dict(o), get=fake_get)
ok(p["size_bytes"] == 939282432, "HEAD probe fills real size")

# ------------------------------------------------------------------ host checks
ok(dd.official("https://downloadmirror.intel.com/x.exe", "Intel"), "intel subdomain allowed")
ok(not dd.official("http://us.download.nvidia.com/x.exe", "NVIDIA"), "plain http refused")
ok(not dd.official("https://nvidia.com.evil.io/x.exe", "NVIDIA"), "look-alike host refused")
ok(not dd.official("https://drivers.amd.com/x.exe", "NVIDIA"), "other vendor's host refused")
try:
    dd.http_get("https://example.com/", "AMD")
    ok(False, "http_get refuses foreign host")
except dd.DriverError:
    ok(True, "http_get refuses foreign host")


# ------------------------------------------------------------------ download / cancel / signature
class Resp(io.BytesIO):
    def __init__(self, data, url, total=True):
        super().__init__(data)
        self.url = url
        self.headers = {"Content-Length": str(len(data))} if total else {}

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class Opener:
    def __init__(self, data, url, total=True):
        self.data, self.url, self.total = data, url, total

    def open(self, req, timeout=30):
        return Resp(self.data, self.url, self.total)


tmp = tempfile.mkdtemp()
data = os.urandom(300_000)
prog = []
path = dd.download(o, progress=lambda d, t: prog.append((d, t)), folder=tmp, opener=Opener(data, o["url"]),
                   chunk=65536)
ok(path.read_bytes() == data and path.name.endswith(".exe") and not list(path.parent.glob("*.part")),
   "download saved, no .part left")
ok(prog[-1] == (len(data), len(data)) and len(prog) == 5, "real progress reported")
ev = threading.Event()
ev.set()
try:
    dd.download(dict(o, url=o["url"].replace("531.79-", "x-")), cancel=ev, folder=tmp, opener=Opener(data, o["url"]))
    ok(False, "cancel")
except dd.DriverError as e:
    ok("cancelled" in str(e) and not list(__import__("pathlib").Path(tmp).glob("*.part")), "cancel removes partial file")
try:
    dd.download(o, folder=tmp, opener=Opener(data, "https://evil.example.com/a.exe"))
    ok(False, "final url check")
except dd.DriverError:
    ok(True, "download that lands off the vendor's host is refused")

ok(dd.verify_signature(path, "NVIDIA", run_ps=lambda s, timeout=0: 'Valid|CN="NVIDIA Corporation", O="NVIDIA '
                       'Corporation", L=Santa Clara')[0], "Valid NVIDIA signature accepted")
ok(not dd.verify_signature(path, "NVIDIA", run_ps=lambda s, timeout=0: "HashMismatch|CN=NVIDIA Corporation")[0],
   "HashMismatch blocked")
ok(not dd.verify_signature(path, "AMD", run_ps=lambda s, timeout=0: "Valid|CN=Someone Else")[0], "wrong signer blocked")
ok(not dd.verify_signature(path, "Intel", run_ps=lambda s, timeout=0: "")[0], "no answer blocked")

# ------------------------------------------------------------------ Windows Update
WU_ID = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
scripts = []


def fake_ps(script, timeout=0):
    scripts.append(script)
    if "UpdateColl" in script:
        return ('[{"id":"%s","title":"Realtek - Audio - 6.0.9600.1","code":2,"reboot":true}]' % WU_ID)
    return ('{"id":"%s","title":"Realtek - Audio - 6.0.9600.1","maker":"Realtek","cls":"MEDIA",'
            '"date":"2024-05-01T00:00:00","size":12000000}' % WU_ID)


rows = dd.wu_search(run_ps=fake_ps)
ok(len(rows) == 1 and rows[0]["date"] == "2024-05-01" and rows[0]["size"] == 12000000, "WU single result parsed")
ok("IsInstalled=0 and Type='Driver'" in scripts[0], "WU search criteria")
res = dd.wu_install([WU_ID, "bad id; Remove-Item C:\\"], run_ps=fake_ps)
ok(res == [{"id": WU_ID, "title": "Realtek - Audio - 6.0.9600.1", "result": "Installed", "reboot": True}],
   "WU install result + reboot flag")
ok("Remove-Item" not in scripts[-1], "only GUIDs reach PowerShell")
ok(dd.wu_search(run_ps=lambda s, timeout=0: "[]") == [], "WU nothing found -> empty list")
try:
    dd.wu_search(run_ps=lambda s, timeout=0: "")
    ok(False, "WU silence is an error")
except dd.DriverError:
    ok(True, "WU silence is an error, never 'nothing found'")

# ------------------------------------------------------------------ vendor matching
ok([x["vendor"] for x in dd.detect_gpus([{"name": "NVIDIA GeForce RTX 4060", "vendor": "NVIDIA"},
                                           {"name": "Microsoft Basic Render Driver", "vendor": "Microsoft"}])]
   == ["NVIDIA"], "DXGI adapters -> NVIDIA only")
ok([x["vendor"] for x in dd.detect_gpus([], "AMD Radeon RX 7800 XT, Intel(R) UHD Graphics 770")] == ["AMD", "Intel"],
   "fallback to PC-scan GPU text")


# ------------------------------------------------------------------ UI flow
class FakeApi:
    DriverError = dd.DriverError
    Job = dd.Job

    def __init__(self):
        self.sig = (True, "Signature valid · signed by NVIDIA Corporation")
        self.downloads = []
        self.ran = []
        self.block = None

    def detect_gpus(self, info_gpu=""):
        return [{"name": "NVIDIA GeForce RTX 4060", "vendor": "NVIDIA"}]

    def nvidia_offer(self, gpu, build):
        return dict(o, size_bytes=None)

    def amd_offer(self):
        raise AssertionError("AMD must not be looked up on this PC")

    def intel_offer(self):
        return dd.intel_offer()

    def probe(self, offer):
        return dict(offer, size_bytes=4096)

    def download(self, offer, progress=None, cancel=None):
        self.downloads.append(offer["url"])
        progress(2048, 4096)
        if self.block:
            self.block.wait(3)
            if cancel.is_set():
                raise dd.DriverError("Download cancelled.")
        progress(4096, 4096)
        return os.path.join(tmp, "driver.exe")

    def verify_signature(self, path, vendor):
        return self.sig

    def run_installer(self, path):
        self.ran.append(path)
        return True, "Installer started."

    def wu_search(self):
        return rows

    def wu_install(self, ids):
        return [{"id": ids[0], "title": rows[0]["title"], "result": "Installed", "reboot": True}]


hub = FakeHub()
hub.info = {"gpu": "NVIDIA GeForce RTX 4060", "cpu": "Intel(R) Core(TM) i7-14700F"}
api = FakeApi()
answers = []
asked = []


def ask(parent, title, text):
    asked.append((title, text))
    return answers.pop(0) if answers else False


page = ui.DriverDownloads(hub, hub, g(), api=api, ask=ask, windows_build=22631)
page.open()
pump(hub, lambda: page.rows["NVIDIA"]["check"].enabled)
ok(page.rows["NVIDIA"]["check"].enabled and page.rows["Intel"]["check"].enabled, "NVIDIA GPU + Intel CPU offered")
ok(not page.rows["AMD"]["check"].enabled and "No AMD" in page.rows["AMD"]["status"].cget("text"),
   "AMD absent hardware stays hidden")
page.check("NVIDIA")
pump(hub, lambda: "NVIDIA" in page.offers)
st = page.rows["NVIDIA"]["status"].cget("text")
ok("531.79" in st and "us.download.nvidia.com" in st and "MB" in st, "offer shows version, size and URL")
answers[:] = [False]
page.download("NVIDIA")
ok(not api.downloads and "Download driver" == asked[-1][0] and "531.79" in asked[-1][1], "no = nothing downloaded")
api.sig = (False, "Windows reports the signature as \"NotSigned\". Not run.")
answers[:] = [True]
page.download("NVIDIA")
pump(hub, lambda: not page.jobs)
ok(api.downloads and not page.rows["NVIDIA"]["run"].enabled and "blocked" in page.rows["NVIDIA"]["status"].cget("text"),
   "signature failure blocks Run installer")
page.run("NVIDIA")
ok(not api.ran, "no run without a verified file")
api.sig = (True, "Signature valid · signed by NVIDIA Corporation")
answers[:] = [True]
page.download("NVIDIA")
pump(hub, lambda: not page.jobs)
ok(page.rows["NVIDIA"]["run"].enabled, "verified download enables Run installer")
answers[:] = [False]
page.run("NVIDIA")
ok(not api.ran and asked[-1][0] == "Run installer", "run asks first; no = not run")
answers[:] = [True]
page.run("NVIDIA")
ok(api.ran, "run after yes")
before_runs, before_prompts = len(api.ran), len(asked)
answers[:] = [True]
page.install("NVIDIA")
pump(hub, lambda: not page.jobs)
ok(len(api.ran) == before_runs + 1 and len(asked) == before_prompts + 1
   and asked[-1][0] == 'Install driver', 'combined install asks once, verifies, then launches setup')
api.sig = (False, 'Wrong publisher')
before_runs = len(api.ran)
answers[:] = [True]
page.install("NVIDIA")
pump(hub, lambda: not page.jobs)
ok(len(api.ran) == before_runs and not page.run_after_download,
   'combined install never launches an unverified installer')
api.sig = (True, 'Signature valid · signed by NVIDIA Corporation')
before_downloads = len(api.downloads)
answers[:] = [False]
page.install("NVIDIA")
pump(hub, lambda: not page.jobs)
ok(len(api.downloads) == before_downloads, 'declining combined install downloads nothing')
api.block = threading.Event()
answers[:] = [True]
page.download("NVIDIA")
pump(hub, lambda: page.rows["NVIDIA"]["cancel"].enabled, 2)
page.cancel("NVIDIA")
api.block.set()
pump(hub, lambda: not page.jobs)
ok("cancelled" in page.rows["NVIDIA"]["status"].cget("text"), "cancel from the page")
page.wu_search()
pump(hub, lambda: not page.jobs)
ok(len(page.wu_vars) == 1 and "1 driver" in page.wu_status.cget("text"), "WU list shown")
page.wu_vars[WU_ID].set(True)
page._wu_sel()
answers[:] = [True]
page.wu_install()
pump(hub, lambda: "Restart" in page.wu_status.cget("text"), 5)
ok("Installed: Realtek" in page.wu_status.cget("text") and "Restart" in page.wu_status.cget("text"),
   "WU per-driver result + restart note")
ok(any(l[0] == "Drivers" for l in hub.logs), "actions logged")
pump(hub, lambda: not page.jobs, 3)
# Refine from a present-device scan: unrelated vendors disappear, including after rescan.
page.set_components([{'kind':'Graphics','name':'Intel Iris Xe','vendor_key':'intel'}])
pump(hub,lambda:True)
ok(page.rows['Intel']['frame'].winfo_manager()=='pack', 'Intel-only PC shows Intel installer')
ok(not page.rows['AMD']['frame'].winfo_manager() and not page.rows['NVIDIA']['frame'].winfo_manager(),
   'Intel-only PC hides NVIDIA and AMD installers entirely')
page.set_components([{'kind':'CPU / chipset','name':'AMD Ryzen','vendor_key':'asus','device_vendor':'amd'},
                     {'kind':'Network','name':'Intel Wi-Fi','vendor_key':'dell','device_vendor':'intel'}])
ok(page.rows['AMD']['frame'].winfo_manager()=='pack' and page.rows['Intel']['frame'].winfo_manager()=='pack',
   'actual AMD CPU and Intel network adapter both match, even with OEM support URLs')
page.set_components([])
ok(all(not r['frame'].winfo_manager() for r in page.rows.values()),'rescan without matching hardware hides all vendor installers')
page.destroy()
hub.destroy()
print("ALL PASS" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
