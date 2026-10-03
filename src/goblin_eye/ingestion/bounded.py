"""Bounded reads and watcher failure isolation shared by ingestion adapters."""
from pathlib import Path
import logging
import time

MAX_SOURCE_BYTES = 64 * 1024 * 1024
WATCHERS = []

def read_stream(handle, limit=MAX_SOURCE_BYTES):
    chunks, size = [], 0
    deadline = time.monotonic() + 60
    while True:
        block = handle.read(min(65536, limit + 1 - size))
        if not block:
            break
        chunks.append(block)
        size += len(block)
        if size > limit or time.monotonic() > deadline:
            raise ValueError('Source exceeds byte or elapsed read budget')
    return b''.join(chunks)

def read_file(path: Path, limit=MAX_SOURCE_BYTES):
    before = path.stat()
    if before.st_size > limit:
        raise ValueError('Source exceeds supported size')
    with path.open('rb') as handle:
        body = read_stream(handle, limit)
    after = path.stat()
    if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
        raise ValueError('Source changed during read; retry after save completes')
    return body

def resilient_run(method):
    """Even a failed error-log write must not permanently kill a watcher."""
    def run(self):
        if self not in WATCHERS:
            WATCHERS.append(self)
        delay = 1
        while not self._stop.is_set():
            try:
                method(self)
                return
            except Exception:
                logging.exception('Watcher interrupted; retrying')
                if self._stop.wait(delay):
                    return
                delay = min(delay * 2, 60)
    return run
