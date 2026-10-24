import io
from pathlib import Path
import threading
import time
import zipfile

import pytest

from core import file_transfers as t


class Response(io.BytesIO):
    def __init__(self, data, length=None):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data) if length is None else length)}


def service():
    stored = {}

    def open_request(req, timeout):
        assert req.full_url.startswith('https://')
        if req.get_method() == 'POST':
            data = bytearray()
            while block := req.data.read(8192):
                data.extend(block)
            assert len(data) == int(req.headers['Content-length'])
            boundary = req.data.boundary.encode()
            marker = b'Content-Type: application/octet-stream\r\n\r\n'
            stored['body'] = bytes(data).split(marker, 1)[1].rsplit(b'\r\n--' + boundary, 1)[0]
            assert stored['body'].startswith(t.MAGIC)
            return Response(b'https://litter.catbox.moe/abcdef.zip\n')
        assert req.full_url == 'https://litter.catbox.moe/abcdef.zip'
        return Response(stored['body'])
    return stored, open_request


def test_file_and_folder_roundtrip(tmp_path):
    folder = tmp_path / 'Folder'
    (folder / 'empty').mkdir(parents=True)
    (folder / 'hello.txt').write_text('private file content')
    (folder / 'Unicode.txt').write_text('café', encoding='utf-8')
    file = tmp_path / 'single.bin'
    file.write_bytes(bytes(range(256)))
    stored, opener = service()
    result = t.send([folder, file], opener=opener, temp_dir=tmp_path)
    assert b'private file content' not in stored['body']
    assert b'hello.txt' not in stored['body']
    output = tmp_path / 'received.zip'
    assert t.receive(result['code'], output, opener=opener) == output
    with zipfile.ZipFile(output) as z:
        assert z.read('Folder/hello.txt') == b'private file content'
        assert z.read('single.bin') == file.read_bytes()
        assert 'Folder/empty/' in z.namelist()
        assert z.read('Folder/Unicode.txt').decode() == 'café'
    assert not list(tmp_path.glob('*retweaks-transfer-*'))


@pytest.mark.parametrize('code', ['https://evil.example/file', 'RTF1.x.y.z', 'RTF1...0', ''])
def test_reject_invalid_codes(code):
    with pytest.raises(t.TransferError):
        t.parse_code(code)


def test_expiry_and_key_validation():
    code = t.make_code('abcdef.zip', b'x' * 32, 2_000_000_000)
    url, key, expiry = t.parse_code(code, now=1_900_000_000)
    assert key == b'x' * 32 and expiry == 2_000_000_000
    assert url == 'https://litter.catbox.moe/abcdef.zip'
    with pytest.raises(t.TransferError, match='expired'):
        t.parse_code(code, now=2_000_000_001)
    with pytest.raises(t.TransferError):
        t.make_code('../evil.zip', b'x' * 32, expiry)


def test_rejects_size_duplicates_and_empty_selection(tmp_path, monkeypatch):
    a = tmp_path / 'a'; a.write_bytes(b'123456')
    monkeypatch.setattr(t, 'MAX_BYTES', 5)
    with pytest.raises(t.TransferError, match='exceeds'):
        t.collect_entries([a])
    with pytest.raises(t.TransferError, match='distinct'):
        t.collect_entries([a, a])
    with pytest.raises(t.TransferError, match='Choose'):
        t.collect_entries([])


def test_tampering_and_wrong_key_preserve_existing_destination(tmp_path):
    source = tmp_path / 'hello.txt'; source.write_text('secret')
    stored, opener = service()
    result = t.send([source], opener=opener, temp_dir=tmp_path)
    output = tmp_path / 'existing.zip'; output.write_bytes(b'keep me')
    wrong = t.make_code('abcdef.zip', b'k' * 32, result['expires'])
    with pytest.raises(t.TransferError, match='incorrect|damaged'):
        t.receive(wrong, output, opener=opener)
    assert output.read_bytes() == b'keep me'
    stored['body'] = stored['body'][:-1] + bytes([stored['body'][-1] ^ 1])
    with pytest.raises(t.TransferError, match='incorrect|damaged'):
        t.receive(result['code'], output, opener=opener)
    assert output.read_bytes() == b'keep me'
    assert not list(tmp_path.glob('.retweaks-transfer-*'))


def test_cancel_prevents_network_and_cleans_temporary_files(tmp_path):
    source = tmp_path / 'a'; source.write_text('hello')
    cancel = threading.Event(); cancel.set()
    with pytest.raises(t.Cancelled):
        t.send([source], cancel=cancel, temp_dir=tmp_path,
               opener=lambda *a, **kw: pytest.fail('Cancelled upload reached network'))
    assert not list(tmp_path.glob('retweaks-transfer-*'))


def test_cancel_during_receive_preserves_destination(tmp_path):
    source = tmp_path / 'a'; source.write_bytes(b'hello' * 100)
    stored, opener = service()
    result = t.send([source], opener=opener, temp_dir=tmp_path)
    destination = tmp_path / 'keep.zip'; destination.write_bytes(b'previous')
    cancel = threading.Event()
    with pytest.raises(t.Cancelled):
        t.receive(result['code'], destination, cancel=cancel, opener=opener,
                  progress=lambda message: cancel.set())
    assert destination.read_bytes() == b'previous'
    assert not list(tmp_path.glob('.retweaks-transfer-*'))


def test_download_bounds_and_incomplete_content(tmp_path, monkeypatch):
    code = t.make_code('abcdef.zip', b'x' * 32, int(time.time()) + 3600)
    destination = tmp_path / 'out.zip'
    monkeypatch.setattr(t, 'MAX_BYTES', 8)
    for payload, length in [(b'a' * 9, 0), (b'a', 9), (b'a', 7)]:
        with pytest.raises(t.TransferError):
            t.receive(code, destination, opener=lambda *a, **kw: Response(payload, length))
        assert not destination.exists()


def test_bad_upload_response_never_becomes_share_code(tmp_path):
    source = tmp_path / 'a'; source.write_text('a')
    with pytest.raises(t.TransferError):
        t.send([source], temp_dir=tmp_path,
               opener=lambda *a, **kw: Response(b'https://evil.example/a.zip'))


def test_links_are_rejected(tmp_path, monkeypatch):
    target = tmp_path / 'data'; target.write_text('private')
    original = Path.lstat
    class LinkStat:
        st_mode = 0o120777
        st_file_attributes = 0
    monkeypatch.setattr(Path, 'lstat', lambda self: LinkStat() if self == target else original(self))
    with pytest.raises(t.TransferError, match='Links'):
        t.collect_entries([target])
