from __future__ import annotations

from .bounded import read_file, read_stream, resilient_run

from datetime import datetime, timezone
import hashlib
import threading
from urllib.request import Request, urlopen

from goblin_eye.repository import Database

from .base import AdapterCapability, ImportResult


OFFICIAL_FOREVER_PAGES = (
    "https://worldofwarcraft.blizzard.com/en-gb/news/24302093",
    "https://worldofwarcraft.blizzard.com/en-us/news/24302070",
    "https://worldofwarcraft.blizzard.com/en-us/news/24304160/the-world-of-warcraft-forever-beta-now-live",
    "https://worldofwarcraft.blizzard.com/en-us/news/24303862/world-of-warcraft-forever-whats-next-panel-recap",
    "https://worldofwarcraft.blizzard.com/en-gb/news/24304071/world-of-warcraft-forever-found-photos-panel-recap",
    "https://worldofwarcraft.blizzard.com/en-gb/news/24307383/get-to-know-the-world-of-warcraft-forever-legacy-system",
)


class BlizzardResearchAdapter:
    capability = AdapterCapability(
        key="blizzard_forever_research",
        display_name="Official Blizzard Forever research",
        status="ready",
        input_types=("public official pages",),
        supplies=("launch schedule", "rulesets", "content roadmap", "Legacy system", "world changes"),
        needs=(),
        documentation_url="https://worldofwarcraft.blizzard.com/en-gb/forever",
        notes="Caches official pages verbatim for agent inspection; no claims are generated from them.",
    )

    def sync(self, database: Database) -> ImportResult:
        retrieved = datetime.now(timezone.utc).isoformat()
        documents: list[tuple[str, bytes, str | None, str | None]] = []
        for url in OFFICIAL_FOREVER_PAGES:
            request = Request(url, headers={"User-Agent": "Goblin-Eye/0.1 local research"})
            with urlopen(request, timeout=30) as response:
                documents.append((url, read_stream(response), response.headers.get("Content-Type"), response.headers.get("Cache-Control")))
        with database.transaction() as connection:
            connection.execute(
                """INSERT INTO sources(source_key, name, source_type, url, trust_rank, enabled,
                notes, last_success_at, last_error) VALUES ('blizzard-official', 'Blizzard Entertainment',
                'official_publication', 'https://worldofwarcraft.blizzard.com/en-gb/forever', 2, 1,
                'Official Forever announcements cached verbatim', ?, NULL)
                ON CONFLICT(source_key) DO UPDATE SET last_success_at=excluded.last_success_at,
                last_error=NULL, notes=excluded.notes""", (retrieved,)
            )
            source_id = connection.execute("SELECT id FROM sources WHERE source_key='blizzard-official'").fetchone()["id"]
            for url, body, content_type, cache_control in documents:
                connection.execute(
                    """INSERT OR IGNORE INTO source_documents(source_id, url, retrieved_at,
                    content_type, cache_control, sha256, body) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (source_id, url, retrieved, content_type, cache_control, hashlib.sha256(body).hexdigest(), body),
                )
            connection.execute(
                """INSERT INTO imports(adapter_key, source_id, started_at, completed_at, status,
                file_name, record_count) VALUES (?, ?, ?, ?, 'complete', NULL, ?)""",
                (self.capability.key, source_id, retrieved, datetime.now(timezone.utc).isoformat(), len(documents)),
            )
        return ImportResult(self.capability.key, "blizzard-official", len(documents), len(documents))


class BlizzardResearchWatcher:
    def __init__(self, database: Database, refresh_minutes: int = 30):
        self.database = database
        self.refresh_seconds = max(60, refresh_minutes * 60)
        self.adapter = BlizzardResearchAdapter()
        self._stop = threading.Event()
        self._thread = None

    def scan_once(self):
        from .static_watcher import record_error
        try:
            return self.adapter.sync(self.database)
        except Exception as exc:
            record_error(self.database, "blizzard-official", "Blizzard Entertainment",
                         "official_publication", self.adapter.capability.documentation_url, 2, exc)
            return None

    @resilient_run
    def _run(self):
        while not self._stop.is_set():
            self.scan_once()
            self._stop.wait(self.refresh_seconds)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="blizzard-research-watcher", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
