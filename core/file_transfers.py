"""Encrypted, temporary internet transfers through Litterbox's public API.

Codes carry a random AES-256 key. Only ciphertext goes to the provider; codes
are never saved in settings or logs. Downloads remain ZIPs and are not executed.
"""
import base64
import io
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAX_BYTES = 1_000_000_000
MAX_ITEMS = 10000
CHUNK = 256 * 1024
MAGIC = b'RTFILE1\0'
API = 'https://litterbox.catbox.moe/resources/internals/api.php'
HOST = 'litter.catbox.moe'
LIFETIMES = {'1 hour': '1h', '12 hours': '12h', '24 hours': '24h', '72 hours': '72h'}


class TransferError(Exception):
    pass


class Cancelled(TransferError):
    pass


def _check(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled('Transfer cancelled.')


def _notify(progress, text):
    if progress:
        progress(text)


def _regular(path):
    st = path.lstat()
    if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & 0x400:
        raise TransferError('Links and junctions cannot be shared. Select the original file or folder.')
    if not stat.S_ISDIR(st.st_mode) and not stat.S_ISREG(st.st_mode):
        raise TransferError('Only regular files and folders can be shared.')
    return st


def collect_entries(paths, cancel=None):
    """Preserve top-level folder names, empty directories and Unicode filenames."""
    roots, entries, names, total = [], [], set(), 0
    for value in paths:
        path = Path(os.path.abspath(value))
        _regular(path)
        if not path.name or path.name.casefold() in names:
            raise TransferError('Selections must have distinct top-level names.')
        names.add(path.name.casefold())
        roots.append(path)
    if not roots:
        raise TransferError('Choose at least one file or folder.')

    def visit(path, relative):
        nonlocal total
        _check(cancel)
        st = _regular(path)
        if len(entries) >= MAX_ITEMS:
            raise TransferError('Choose fewer than 10,000 files and folders per transfer.')
        if any(c in relative for c in ('\\', ':')) or any(p in ('', '..', '.') for p in relative.split('/')):
            raise TransferError('A selected filename is not supported on Windows.')
        is_dir = stat.S_ISDIR(st.st_mode)
        entries.append((path, relative + ('/' if is_dir else ''), st.st_size if not is_dir else 0))
        if is_dir:
            for child in sorted(path.iterdir(), key=lambda p: p.name.casefold()):
                visit(child, relative + '/' + child.name)
        else:
            total += st.st_size
            if total > MAX_BYTES:
                raise TransferError('The selection exceeds 1 GB. Split it into smaller transfers.')

    for root in roots:
        visit(root, root.name)
    return entries, total


def create_archive(paths, output, cancel=None, progress=None):
    _notify(progress, 'Checking selected files and folders…')
    entries, total = collect_entries(paths, cancel)
    processed = 0
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for path, name, size in entries:
            _check(cancel)
            if name.endswith('/'):
                archive.writestr(name, b'')
                continue
            _regular(path)
            with path.open('rb') as src, archive.open(name, 'w') as dst:
                while True:
                    _check(cancel)
                    block = src.read(CHUNK)
                    if not block:
                        break
                    processed += len(block)
                    if processed > MAX_BYTES:
                        raise TransferError('The selection grew past the 1 GB limit.')
                    dst.write(block)
                    _notify(progress, f'Preparing ZIP: {processed / 1_000_000:.1f} / {total / 1_000_000:.1f} MB')
    if Path(output).stat().st_size + len(MAGIC) + 28 > MAX_BYTES:
        raise TransferError('The encrypted ZIP exceeds 1 GB. Choose fewer files.')


def encrypt_archive(source, output, key, cancel=None, progress=None):
    nonce = secrets.token_bytes(12)
    enc = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    enc.authenticate_additional_data(MAGIC)
    _notify(progress, 'Encrypting the ZIP before upload…')
    with Path(source).open('rb') as src, Path(output).open('wb') as dst:
        dst.write(MAGIC + nonce)
        while True:
            _check(cancel)
            block = src.read(CHUNK)
            if not block:
                break
            dst.write(enc.update(block))
        dst.write(enc.finalize())
        dst.write(enc.tag)


def decrypt_archive(source, output, key, cancel=None):
    size = Path(source).stat().st_size
    if not len(MAGIC) + 28 <= size <= MAX_BYTES:
        raise TransferError('This is not a valid ReTweaks transfer.')
    with Path(source).open('rb') as src, Path(output).open('wb') as dst:
        if src.read(len(MAGIC)) != MAGIC:
            raise TransferError('This is not a ReTweaks transfer, or the service returned an error page.')
        nonce = src.read(12)
        src.seek(-16, 2)
        tag = src.read(16)
        src.seek(len(MAGIC) + 12)
        dec = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        dec.authenticate_additional_data(MAGIC)
        remaining = size - len(MAGIC) - 28
        try:
            while remaining:
                _check(cancel)
                block = src.read(min(CHUNK, remaining))
                if not block:
                    raise TransferError('The transfer download is incomplete.')
                remaining -= len(block)
                dst.write(dec.update(block))
            dst.write(dec.finalize())
        except InvalidTag:
            raise TransferError('The share code is incorrect or the transfer is damaged.') from None
    # Authenticate before any downloaded bytes become a user-visible ZIP.
    if not zipfile.is_zipfile(output):
        raise TransferError('The transfer did not contain a ZIP archive.')


def make_code(filename, key, expires):
    if not re.fullmatch(r'[a-zA-Z0-9]{4,32}\.zip', filename) or len(key) != 32:
        raise TransferError('The service returned an unexpected transfer address.')
    return f'RTF1.{filename[:-4]}.{base64.urlsafe_b64encode(key).decode().rstrip("=")}.{int(expires)}'


def parse_code(code, now=None):
    code = code.strip()
    match = re.fullmatch(r'RTF1\.([a-zA-Z0-9]{4,32})\.([a-zA-Z0-9_-]{43})\.([0-9]{10,11})', code)
    if not match:
        raise TransferError('Paste the complete ReTweaks share code beginning RTF1.')
    file_id, encoded, expires = match.groups()
    key = base64.b64decode(encoded + '=', altchars=b'-_', validate=True)
    if len(key) != 32:
        raise TransferError('The share code is invalid.')
    if int(expires) <= (time.time() if now is None else now):
        raise TransferError('This share code has expired. Ask the sender to upload again.')
    return f'https://{HOST}/{file_id}.zip', key, int(expires)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TransferError('The transfer service redirected the request. Please try again later.')


def _open(request, timeout=45):
    try:
        return urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            raise TransferError('The transfer expired or was removed by the hosting service.') from None
        if exc.code == 413:
            raise TransferError('The hosting service rejected the file size. Choose a smaller selection.') from None
        if exc.code == 429:
            raise TransferError('The hosting service is busy. Wait a little and try again.') from None
        raise TransferError(f'The hosting service returned HTTP {exc.code}. Please try again later.') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TransferError('Could not reach the transfer service. Check your connection and try again.') from None


class Multipart:
    """Stream the encrypted payload without loading large files into RAM."""
    def __init__(self, source, lifetime, cancel=None, progress=None):
        self.cancel, self.progress = cancel, progress
        self.boundary = 'ReTweaks' + secrets.token_hex(16)
        self.file = Path(source).open('rb')
        self.size = Path(source).stat().st_size
        self.sent = 0
        prefix = ''.join(f'--{self.boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
                         for name, value in [('reqtype', 'fileupload'), ('time', lifetime)])
        prefix += (f'--{self.boundary}\r\nContent-Disposition: form-data; name="fileToUpload"; '
                   'filename="retweaks.zip"\r\nContent-Type: application/octet-stream\r\n\r\n')
        self.prefix = io.BytesIO(prefix.encode())
        suffix = f'\r\n--{self.boundary}--\r\n'.encode()
        self.suffix = io.BytesIO(suffix)
        self.length = len(prefix.encode()) + self.size + len(suffix)

    def read(self, n=CHUNK):
        _check(self.cancel)
        n = CHUNK if n < 0 else min(n, CHUNK)
        chunk = self.prefix.read(n)
        if chunk:
            return chunk
        chunk = self.file.read(n)
        if chunk:
            self.sent += len(chunk)
            _notify(self.progress, f'Uploading: {self.sent / 1_000_000:.1f} / {self.size / 1_000_000:.1f} MB')
            return chunk
        return self.suffix.read(n)

    def close(self):
        self.file.close()


def send(paths, lifetime='72h', cancel=None, progress=None, opener=None, temp_dir=None):
    if lifetime not in LIFETIMES.values():
        raise TransferError('Choose an available expiry time.')
    opener = opener or _open
    with tempfile.TemporaryDirectory(prefix='retweaks-transfer-', dir=temp_dir) as work:
        archive, payload = Path(work) / 'selection.zip', Path(work) / 'payload.bin'
        create_archive(paths, archive, cancel, progress)
        key = secrets.token_bytes(32)
        encrypt_archive(archive, payload, key, cancel, progress)
        _check(cancel)
        # Start expiry conservatively before upload, never promise extra retention.
        expires = int(time.time()) + int(lifetime[:-1]) * 3600
        body = Multipart(payload, lifetime, cancel, progress)
        try:
            request = urllib.request.Request(API, data=body, headers={
                'Content-Type': 'multipart/form-data; boundary=' + body.boundary,
                'Content-Length': str(body.length), 'User-Agent': 'ReTweaks File Transfers/1.0'}, method='POST')
            with opener(request, timeout=90) as response:
                result = response.read(4097)
            if len(result) > 4096:
                raise TransferError('The service returned an unexpected response.')
            address = urllib.parse.urlparse(result.decode('utf-8').strip())
            if address.scheme != 'https' or address.netloc != HOST or address.query or address.fragment:
                raise TransferError('Upload failed: the service did not return a valid download address.')
            code = make_code(address.path.lstrip('/'), key, expires)
            # Return a code even if cancellation arrived after the server committed the upload.
            return {'code': code, 'expires': expires, 'bytes': body.size}
        finally:
            body.close()


def receive(code, destination, cancel=None, progress=None, opener=None):
    url, key, expires = parse_code(code)
    destination = Path(destination)
    opener = opener or _open
    if not destination.parent.is_dir():
        raise TransferError('Choose an existing destination folder.')
    # Work beside the destination, so final replace is atomic and other files stay intact.
    with tempfile.TemporaryDirectory(prefix='.retweaks-transfer-', dir=destination.parent) as work:
        payload, archive = Path(work) / 'payload.bin', Path(work) / 'received.zip'
        _check(cancel)
        request = urllib.request.Request(url, headers={'User-Agent': 'ReTweaks File Transfers/1.0'})
        with opener(request, timeout=45) as response, payload.open('wb') as dst:
            length = int(response.headers.get('Content-Length') or 0)
            if length > MAX_BYTES:
                raise TransferError('This download exceeds the 1 GB limit.')
            count = 0
            while True:
                _check(cancel)
                block = response.read(CHUNK)
                if not block:
                    break
                count += len(block)
                if count > MAX_BYTES:
                    raise TransferError('This download exceeds the 1 GB limit.')
                dst.write(block)
                _notify(progress, f'Downloading: {count / 1_000_000:.1f} MB' +
                        (f' / {length / 1_000_000:.1f} MB' if length else ''))
            if length and count != length:
                raise TransferError('The transfer download is incomplete. Please try again.')
        _notify(progress, 'Checking and decrypting the transfer…')
        decrypt_archive(payload, archive, key, cancel)
        _check(cancel)
        os.replace(archive, destination)
        return destination
