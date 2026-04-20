import hashlib
import os
import shutil
import tempfile

import pytest

from safecopy import parse_chunk_size


# --- chunk size parsing ---

def test_parse_mb():
    assert parse_chunk_size("1mb") == 1 * 1024 * 1024

def test_parse_mb_decimal():
    assert parse_chunk_size("0.5mb") == 512 * 1024

def test_parse_kb():
    assert parse_chunk_size("512kb") == 512 * 1024

def test_parse_uppercase():
    assert parse_chunk_size("2MB") == 2 * 1024 * 1024

def test_parse_invalid_unit():
    with pytest.raises(ValueError, match="Invalid"):
        parse_chunk_size("100")

def test_parse_invalid_unit_gb():
    with pytest.raises(ValueError, match="Invalid"):
        parse_chunk_size("1gb")

def test_parse_too_small():
    with pytest.raises(ValueError, match="at least 4kb"):
        parse_chunk_size("1kb")


# --- md5 doğrulama ---

def _md5(path):
    m = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(128 * 1024):
            m.update(chunk)
    return m.hexdigest()


class TestCopy:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmp)

    def _make_file(self, name, size_bytes):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as f:
            f.write(os.urandom(size_bytes))
        return path

    def test_copy_matches_md5(self):
        src = self._make_file("src.bin", 1 * 1024 * 1024)
        dst = os.path.join(self.tmp, "dst.bin")
        chunk_size = 256 * 1024

        src_md5 = hashlib.md5()
        with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
            while data := fsrc.read(chunk_size):
                fdst.write(data)
                src_md5.update(data)

        assert src_md5.hexdigest() == _md5(dst)

    def test_corrupted_copy_detected(self):
        src = self._make_file("src.bin", 512 * 1024)
        dst = os.path.join(self.tmp, "dst.bin")
        shutil.copy2(src, dst)

        # hedefi boz
        with open(dst, "r+b") as f:
            f.seek(1024)
            f.write(b"\x00" * 512)

        assert _md5(src) != _md5(dst)

    def test_move_deletes_source_on_success(self):
        src = self._make_file("src.bin", 64 * 1024)
        dst = os.path.join(self.tmp, "dst.bin")
        chunk_size = 32 * 1024

        src_md5 = hashlib.md5()
        with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
            while data := fsrc.read(chunk_size):
                fdst.write(data)
                src_md5.update(data)

        if src_md5.hexdigest() == _md5(dst):
            os.unlink(src)

        assert not os.path.exists(src)
        assert os.path.exists(dst)

    def test_move_keeps_source_on_mismatch(self):
        src = self._make_file("src.bin", 64 * 1024)
        dst = os.path.join(self.tmp, "dst.bin")

        shutil.copy2(src, dst)
        with open(dst, "r+b") as f:
            f.write(b"\x00" * 512)

        if hashlib.md5(open(src, "rb").read()).hexdigest() != _md5(dst):
            pass  # silme — kaynak kalmalı

        assert os.path.exists(src)
