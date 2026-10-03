"""Refresh installed static catalogs on startup and whenever their files change."""
import logging
import threading

from .bounded import resilient_run
from .discovery import discover_addon_paths


def record_error(database, source_key, name, source_type, url, rank, exc):
    with database.transaction() as connection:
        connection.execute("""INSERT INTO sources(source_key,name,source_type,url,trust_rank,last_error)
            VALUES (?,?,?,?,?,?) ON CONFLICT(source_key) DO UPDATE SET last_error=excluded.last_error""",
            (source_key, name, source_type, url, rank, str(exc)))


class StaticAddonWatcher:
    def __init__(self, database, paths=(), interval=60):
        self.database, self.paths, self.interval = database, paths, max(10, interval)
        self._signatures = {}
        self._stop = threading.Event()
        self._thread = None

    def scan_once(self):
        results = []
        for path in discover_addon_paths(self.addon, self.marker, self.paths):
            try:
                watched = [path / name for name in self.files]
                signature = tuple((str(file), file.stat().st_mtime_ns, file.stat().st_size) for file in watched)
                if self._signatures.get(str(path)) == signature:
                    continue
                result = self.adapter.import_file(self.database, path)
                # An update during parsing must be checked again next time.
                after = tuple((str(file), file.stat().st_mtime_ns, file.stat().st_size) for file in watched)
                if after == signature:
                    self._signatures[str(path)] = signature
                results.append(result)
            except Exception as exc:
                logging.exception("Static addon import failed: %s", path)
                record_error(self.database, self.source_key, self.adapter.capability.display_name,
                             self.source_type, self.adapter.capability.documentation_url, self.rank, exc)
        return results

    @resilient_run
    def _run(self):
        while not self._stop.is_set():
            self.scan_once()
            self._stop.wait(self.interval)

    def start(self):
        self._thread = threading.Thread(target=self._run, name=f"{self.addon.lower()}-watcher", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)


class QuestieDbWatcher(StaticAddonWatcher):
    addon, marker = "QuestieDB", "QuestieDB_Forever.toc"
    files = (marker,)
    source_key, source_type, rank = "questiedb-forever", "bundled_world_database", 5

    def __init__(self, *args, **kwargs):
        from .questiedb import QuestieDbAdapter
        super().__init__(*args, **kwargs)
        self.adapter = QuestieDbAdapter()


class MapzerothWatcher(StaticAddonWatcher):
    addon, marker = "Mapzeroth", "Mapzeroth.toc"
    source_key, source_type, rank = "mapzeroth-forever", "bundled_travel_database", 5

    def __init__(self, *args, **kwargs):
        from .mapzeroth import MapzerothAdapter, FILES
        super().__init__(*args, **kwargs)
        self.adapter, self.files = MapzerothAdapter(), FILES
