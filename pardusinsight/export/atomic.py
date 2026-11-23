"""Atomik dosya yazımı: yarım kalmış rapor dosyası oluşmasını önler."""
from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from typing import IO, Iterator


@contextmanager
def atomic_write(path: str, newline: str = "") -> Iterator[IO[str]]:
    """Aynı dizinde geçici dosyaya yazar, başarılıysa hedefin yerine koyar.

    Hata olursa geçici dosya silinir ve hedef dosya (varsa) değişmeden kalır.
    Dosya izinleri gizlilik için yalnızca sahibine açıktır (0600).
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".pardusinsight-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
