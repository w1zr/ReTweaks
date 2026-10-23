"""Official driver downloads inside RETWEAKS (owner request 2026-10-22: "make some drivers downloadable").

Only the makers' own servers, over HTTPS; every redirect hop is checked against the vendor's host list. Nothing is
downloaded or run without the user saying yes (the Drivers page asks twice: before downloading, and before
running the vendor's own installer). RETWEAKS never installs a graphics driver silently: the vendor installer does
the install with its own screens.

Sources (checked 2026-10-22):
- NVIDIA: the lookup the nvidia.com driver page uses.
  Product list: https://www.nvidia.com/Download/API/lookupValueSearch.aspx?TypeID=3 (XML; LookupValue@ParentID =
  series id "psid", Value = product id "pfid"); series list TypeID=2 (notebook series have "Notebook" in the name).
  Latest driver: https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/AjaxDriverService.php
  ?func=DriverManualLookup&psid=..&pfid=..&osID=..&languageCode=1033&beta=0&isWHQL=1&dltype=-1&dch=1&upCRD=0&qnf=0
  &sort1=0&numberOfResults=1 -> JSON {"Success": "1", "IDS": [{"downloadInfo": {"Version", "ReleaseDateTime",
  "DownloadURL", "DownloadURLFileSize", ...}}]}; DownloadURL is on *.download.nvidia.com. osID 57 = Windows 10
  64-bit, 135 = Windows 11. (Endpoint and fields as used by NVIDIA-update scripts and Chromium's infra; not an
  officially documented API, so a changed response is reported, never guessed around.)
- AMD: the "Download Windows Drivers" (auto-detect, minimal setup) link on
  https://www.amd.com/en/support/download/drivers.html, e.g.
  https://drivers.amd.com/drivers/installer/26.20/whql/amd-software-adrenalin-edition-26.10.1-minimalsetup-261018_web.exe
  (found on that page 2026-10-22). Fetched with a Referer from amd.com, as browsers send.
- Intel: Intel Driver & Support Assistant, "Download now" on https://www.intel.com/content/www/us/en/support/detect.html
  -> https://dsadata.intel.com/installer.
- Windows Update: optional drivers through the Windows Update Agent (Microsoft.Update.Session COM API).
Downloads are checked with Windows' Authenticode signature check (Get-AuthenticodeSignature): Valid and signed by
the vendor, or the installer can't be run from RETWEAKS.
"""
import html
import json
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/126.0 Safari/537.36 RETWEAKS-Drivers")

HOSTS = {
    "NVIDIA": ("nvidia.com", "geforce.com"),
    "AMD": ("amd.com",),
    "Intel": ("intel.com",),
}
SIGNERS = {"NVIDIA": "NVIDIA Corporation", "AMD": "Advanced Micro Devices", "Intel": "Intel Corporation"}

NVIDIA_LOOKUP = "https://www.nvidia.com/Download/API/lookupValueSearch.aspx"
NVIDIA_SERVICE = "https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/AjaxDriverService.php"
NVIDIA_PAGE = "https://www.nvidia.com/en-us/drivers/"
AMD_PAGE = "https://www.amd.com/en/support/download/drivers.html"
AMD_LINK = re.compile(r"https://drivers\.amd\.com/drivers/installer/[0-9.]+/whql/"
                      r"amd-software-adrenalin-edition-([0-9][0-9.]*)-minimalsetup-(\d+)_web\.exe")
INTEL_PAGE = "https://www.intel.com/content/www/us/en/support/detect.html"
INTEL_URL = "https://dsadata.intel.com/installer"
OS_WIN10_64, OS_WIN11 = "57", "135"


class DriverError(Exception):
    """A plain-language reason shown on the page."""


# ------------------------------------------------------------------ official-host checks
def official(url, vendor):
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    host = (p.hostname or "").lower()
    return p.scheme == "https" and any(host == d or host.endswith("." + d) for d in HOSTS.get(vendor, ()))


def _opener(vendor):
    class Guard(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not official(newurl, vendor):
                raise DriverError(f"{vendor}'s server redirected to an address that isn't {vendor}'s "
                                  f"({urlsplit(newurl).hostname}); nothing was downloaded.")
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    return build_opener(Guard())


def http_get(url, vendor, headers=None, timeout=15, method="GET"):
    """(final_url, headers, body bytes) from an official host; raises DriverError."""
    if not official(url, vendor):
        raise DriverError(f"Refused: {url} isn't an official {vendor} address.")
    req = Request(url, method=method, headers={"User-Agent": AGENT, **(headers or {})})
    try:
        with _opener(vendor).open(req, timeout=timeout) as r:
            return r.geturl(), dict(r.headers), (r.read() if method == "GET" else b"")
    except DriverError:
        raise
    except Exception as e:
        raise DriverError(f"Couldn't reach {vendor} ({type(e).__name__}: {e}). Check your internet connection.")


# ------------------------------------------------------------------ which GPUs this PC has
def detect_gpus(adapters=None, info_gpu=""):
    """[{'name', 'vendor'}] for real NVIDIA / AMD / Intel GPUs (DXGI first, then the PC scan's GPU text)."""
    from core import gpu_dxgi
    if adapters is None:
        try:
            adapters = gpu_dxgi.list_adapters()
        except Exception:
            adapters = []
    out = []
    for a in adapters or []:
        v = a.get("vendor") or gpu_dxgi.vendor_from_name(a.get("name", ""))
        if v in SIGNERS:
            out.append({"name": a.get("name", ""), "vendor": v})
    if not out:
        for part in str(info_gpu or "").split(","):
            name = part.strip()
            v = gpu_dxgi.vendor_from_name(name)
            if v in SIGNERS and not gpu_dxgi.is_virtual(name):
                out.append({"name": name, "vendor": v})
    seen, unique = set(), []
    for g in out:
        if g["name"].lower() not in seen:
            seen.add(g["name"].lower())
            unique.append(g)
    return unique


# ------------------------------------------------------------------ NVIDIA
def _lookup_values(xml_bytes):
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        raise DriverError("NVIDIA's product list came back in an unexpected format.")
    rows = []
    for lv in root.iter("LookupValue"):
        rows.append({"name": (lv.findtext("Name") or "").strip(), "value": (lv.findtext("Value") or "").strip(),
                     "parent": lv.get("ParentID", "")})
    return rows


def _norm(name):
    n = name.lower().replace("nvidia", "").replace("(r)", "").replace("(tm)", "")
    n = re.sub(r"\b(laptop gpu|laptop|notebook|graphics)\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


def nvidia_product(gpu_name, products, series):
    """(psid, pfid, product name) for the GPU, or None. Laptop GPUs match notebook series only."""
    want = _norm(gpu_name)
    laptop = bool(re.search(r"laptop|notebook|mobile|max-q", gpu_name, re.I))
    notebook_series = {s["value"] for s in series if "notebook" in s["name"].lower()}
    hits = [p for p in products if _norm(p["name"]) == want
            and ((p["parent"] in notebook_series) == laptop)]
    if not hits:
        return None
    p = hits[0]
    return p["parent"], p["value"], p["name"]


def nvidia_offer(gpu_name, windows_build, get=http_get):
    _, _, x3 = get(f"{NVIDIA_LOOKUP}?TypeID=3", "NVIDIA")
    _, _, x2 = get(f"{NVIDIA_LOOKUP}?TypeID=2", "NVIDIA")
    match = nvidia_product(gpu_name, _lookup_values(x3), _lookup_values(x2))
    if not match:
        raise DriverError(f"NVIDIA's driver list has no exact match for \"{gpu_name}\". Use NVIDIA's driver "
                          f"page instead.")
    psid, pfid, product = match
    os_id = OS_WIN11 if (windows_build or 0) >= 22000 else OS_WIN10_64
    q = urlencode({"func": "DriverManualLookup", "psid": psid, "pfid": pfid, "osID": os_id, "languageCode": 1033,
                   "beta": 0, "isWHQL": 1, "dltype": -1, "dch": 1, "upCRD": 0, "qnf": 0, "sort1": 0,
                   "numberOfResults": 1})
    _, _, body = get(f"{NVIDIA_SERVICE}?{q}", "NVIDIA")
    return parse_nvidia(body, product)


def parse_nvidia(body, product):
    try:
        data = json.loads(body)
        info = data["IDS"][0]["downloadInfo"]
        ok = str(data.get("Success")) == "1"
    except (ValueError, KeyError, IndexError, TypeError):
        raise DriverError("NVIDIA's driver lookup answered in an unexpected format, so no driver is offered.")
    url = unquote(str(info.get("DownloadURL", "")))
    version = str(info.get("Version", "")).strip()
    if not ok or not version or not official(url, "NVIDIA") or not url.lower().endswith(".exe"):
        raise DriverError("NVIDIA's driver lookup didn't return an official download for this GPU.")
    return {"vendor": "NVIDIA", "title": f"NVIDIA Game Ready driver {version}", "product": product,
            "version": version, "date": unquote(str(info.get("ReleaseDateTime", ""))).strip(),
            "size_text": unquote(str(info.get("DownloadURLFileSize", ""))).strip(), "url": url,
            "headers": {}, "source": "NVIDIA driver lookup (nvidia.com)",
            "note": "WHQL Game Ready driver for your GPU and Windows version. NVIDIA's installer does the install."}


# ------------------------------------------------------------------ AMD
def amd_offer(get=http_get):
    _, _, body = get(AMD_PAGE, "AMD")
    m = AMD_LINK.search(html.unescape(body.decode("utf-8", "replace")))
    if not m:
        raise DriverError("AMD's driver page didn't show its Windows auto-detect installer link right now. "
                          "Use AMD's driver page instead.")
    return {"vendor": "AMD", "title": f"AMD Software: Adrenalin Edition {m.group(1)} (auto-detect installer)",
            "product": "AMD Radeon graphics and Ryzen chipset", "version": m.group(1), "date": "",
            "size_text": "", "url": m.group(0), "headers": {"Referer": "https://www.amd.com/"},
            "source": "amd.com driver page",
            "note": "AMD's own installer detects your Radeon GPU / Ryzen chipset and downloads the matching driver."}


# ------------------------------------------------------------------ Intel
def intel_offer():
    return {"vendor": "Intel", "title": "Intel Driver & Support Assistant", "product":
            "Intel graphics, chipset, Wi-Fi, Bluetooth and Ethernet", "version": "latest", "date": "",
            "size_text": "", "url": INTEL_URL, "headers": {}, "source": "intel.com support (detect page)",
            "note": "Intel's own tool scans this PC and installs matching Intel drivers."}


# ------------------------------------------------------------------ download + verify
def probe(offer, get=http_get):
    """Fill in the real file size and final address (HEAD request) before asking to download."""
    try:
        final, headers, _ = get(offer["url"], offer["vendor"], headers=offer.get("headers"), method="HEAD")
    except DriverError:
        return offer
    size = headers.get("Content-Length") or headers.get("content-length")
    if size and str(size).isdigit():
        offer = dict(offer, size_bytes=int(size), size_text=offer.get("size_text") or f"{int(size) / 1e6:.0f} MB")
    return dict(offer, final_url=final)


def downloads_dir():
    return Path(os.getenv("LOCALAPPDATA") or Path.home()) / "RETWEAKS" / "Drivers"


def _file_name(offer, final_url, headers):
    cd = headers.get("Content-Disposition") or headers.get("content-disposition") or ""
    m = re.search(r'filename="?([^";]+)', cd)
    name = m.group(1) if m else os.path.basename(urlsplit(final_url).path)
    name = re.sub(r"[^\w.\-]+", "_", name or "")
    if not name.lower().endswith(".exe"):
        name = re.sub(r"\W+", "_", offer["title"]).strip("_") + ".exe"
    return name


def download(offer, progress=None, cancel=None, folder=None, opener=None, chunk=256 * 1024):
    """Stream the installer to %LOCALAPPDATA%\\RETWEAKS\\Drivers. progress(done, total|None). Returns the path.
    Cancel (threading.Event) removes the partial file."""
    vendor = offer["vendor"]
    if not official(offer["url"], vendor):
        raise DriverError("Refused: not an official download address.")
    folder = Path(folder or downloads_dir())
    folder.mkdir(parents=True, exist_ok=True)
    req = Request(offer["url"], headers={"User-Agent": AGENT, **(offer.get("headers") or {})})
    try:
        r = (opener or _opener(vendor)).open(req, timeout=30)
    except DriverError:
        raise
    except Exception as e:
        raise DriverError(f"Download didn't start ({type(e).__name__}: {e}).")
    with r:
        final = r.geturl()
        if not official(final, vendor):
            raise DriverError("The download moved to a non-official address; stopped.")
        headers = dict(r.headers)
        total = headers.get("Content-Length") or headers.get("content-length")
        total = int(total) if total and str(total).isdigit() else None
        path = folder / _file_name(offer, final, headers)
        part = path.with_name(path.name + ".part")
        done = 0
        try:
            with open(part, "wb") as f:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise DriverError("Download cancelled.")
                    data = r.read(chunk)
                    if not data:
                        break
                    f.write(data)
                    done += len(data)
                    if progress:
                        progress(done, total)
        except BaseException:
            try:
                part.unlink()
            except OSError:
                pass
            raise
    if total is not None and done != total:
        try:
            part.unlink()
        except OSError:
            pass
        raise DriverError(f"Download incomplete ({done:,} of {total:,} bytes); try again.")
    os.replace(part, path)
    return path


def verify_signature(path, vendor, run_ps=None):
    """(ok, message) from Windows' Authenticode check: Valid + signed by the vendor."""
    if run_ps is None:
        from core.winutil import run_powershell as run_ps
    p = str(path).replace("'", "''")
    out = run_ps(f"$s = Get-AuthenticodeSignature -LiteralPath '{p}'\n"
                 "\"$($s.Status)|$($s.SignerCertificate.Subject)\"", timeout=60) or ""
    status, _, subject = out.strip().partition("|")
    want = SIGNERS[vendor]
    if status.strip() == "Valid" and want.lower() in subject.lower():
        org = re.search(r"O=\"?([^,\"]+)", subject)
        return True, f"Signature valid · signed by {org.group(1) if org else want}"
    if status.strip() == "Valid":
        return False, f"Signed, but not by {want} ({subject.strip()[:80]}). Not run."
    return False, f"Windows reports the signature as \"{status.strip() or 'unknown'}\". Not run."


def run_installer(path, launcher=None):
    """Start the vendor's installer (its own windows take over). Returns (ok, message)."""
    try:
        if launcher is not None:
            launcher(str(path))
        elif hasattr(os, "startfile"):
            os.startfile(str(path))  # noqa: S606 - the user confirmed; vendor-signed installer
        else:
            raise OSError("Installers can only be run on Windows.")
        return True, "Installer started. Follow its steps; a restart may be needed."
    except OSError as e:
        return False, f"Couldn't start the installer: {e}"


# ------------------------------------------------------------------ Windows Update drivers
WU_SEARCH = r"""
$s = New-Object -ComObject Microsoft.Update.Session
$r = $s.CreateUpdateSearcher().Search("IsInstalled=0 and Type='Driver'")
$out = @()
foreach ($u in $r.Updates) {
  $out += [pscustomobject]@{ id = $u.Identity.UpdateID; title = $u.Title; maker = $u.DriverManufacturer;
    cls = $u.DriverClass; date = "$($u.DriverVerDate)"; size = [int64]$u.MaxDownloadSize }
}
ConvertTo-Json -InputObject @($out) -Compress
"""

WU_INSTALL = r"""
$ids = '__IDS__' -split ','
$s = New-Object -ComObject Microsoft.Update.Session
$r = $s.CreateUpdateSearcher().Search("IsInstalled=0 and Type='Driver'")
$coll = New-Object -ComObject Microsoft.Update.UpdateColl
foreach ($u in $r.Updates) { if ($ids -contains $u.Identity.UpdateID) { if (-not $u.EulaAccepted) { $u.AcceptEula() }; [void]$coll.Add($u) } }
$res = @()
if ($coll.Count -gt 0) {
  $d = $s.CreateUpdateDownloader(); $d.Updates = $coll; [void]$d.Download()
  $i = $s.CreateUpdateInstaller(); $i.Updates = $coll; $ir = $i.Install()
  for ($k = 0; $k -lt $coll.Count; $k++) {
    $res += [pscustomobject]@{ id = $coll.Item($k).Identity.UpdateID; title = $coll.Item($k).Title;
      code = [int]$ir.GetUpdateResult($k).ResultCode; reboot = [bool]$ir.RebootRequired }
  }
}
ConvertTo-Json -InputObject @($res) -Compress
"""
WU_CODES = {2: "Installed", 3: "Installed with errors", 4: "Failed", 5: "Cancelled"}


def _json_list(out):
    lines = [x for x in (out or "").strip().splitlines() if x.strip()]
    if not lines:      # the script always prints at least "[]", so silence means it failed
        raise DriverError("Windows Update didn't answer. Its service may be turned off or busy; try again, or "
                          "use Windows Update in Settings.")
    try:
        data = json.loads(lines[-1])
    except ValueError:
        raise DriverError("Windows Update returned something unexpected.")
    return data if isinstance(data, list) else [data]


def wu_search(run_ps=None):
    if run_ps is None:
        from core.winutil import run_powershell as run_ps
    rows = _json_list(run_ps(WU_SEARCH, timeout=300))
    return [{"id": str(r.get("id", "")), "title": str(r.get("title", "")), "maker": str(r.get("maker") or ""),
             "cls": str(r.get("cls") or ""), "date": str(r.get("date") or "")[:10],
             "size": int(r.get("size") or 0)} for r in rows if r.get("id")]


def wu_install(ids, run_ps=None):
    """Download + install the chosen Windows Update drivers. [{'id','title','result','reboot'}]."""
    ids = [i for i in ids if re.fullmatch(r"[0-9a-fA-F-]{36}", str(i))]
    if not ids:
        raise DriverError("No drivers selected.")
    if run_ps is None:
        from core.winutil import run_powershell as run_ps
    rows = _json_list(run_ps(WU_INSTALL.replace("__IDS__", ",".join(ids)), timeout=3600))
    return [{"id": str(r.get("id")), "title": str(r.get("title")), "result": WU_CODES.get(int(r.get("code", 0)),
             f"Result code {r.get('code')}"), "reboot": bool(r.get("reboot"))} for r in rows]


class Job:
    """One background task with a cancel flag; results go to a queue the Tk side polls."""

    def __init__(self, queue_put, kind, target, *args):
        self.cancel = threading.Event()
        self.kind = kind
        self.started = time.monotonic()

        def run():
            try:
                queue_put((kind, "done", target(self, *args)))
            except DriverError as e:
                queue_put((kind, "error", str(e)))
            except Exception as e:  # never kill the page
                queue_put((kind, "error", f"{type(e).__name__}: {e}"))
        threading.Thread(target=run, daemon=True, name=f"RetweaksDriver-{kind}").start()
