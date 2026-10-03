"""Personal auction workspace: local scans, one label, explicit reset boundary."""
from datetime import datetime, timezone
import hashlib
import json

MARKET_KEY = 'wow-forever'
MARKET_NAME = 'WoW Forever'
LOCAL_SOURCES = ('local-auctionator', 'local-ahledger')


def policy(connection):
    row = connection.execute('SELECT * FROM auction_policy WHERE id=1').fetchone()
    return dict(row) if row else None


def reject_external_auctions(database):
    # This workspace restriction must not depend on whether a reset was recorded.
    raise ValueError('Generic auction imports and bulk history recovery remain disabled. Use local addon scans or the approved AHledger Forever public feed.')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def market_profile(c):
    return dict(c.execute("SELECT * FROM local_market_profile WHERE id=1").fetchone())


def _merge_identity(profile, values):
    for key, value in values.items():
        if not value or value == 'unknown':
            continue
        if profile[key] != 'unknown' and profile[key].casefold() != value.casefold():
            raise ValueError(f"Local {key} conflicts with this database's market profile. Use a separate database for another market; existing evidence was retained.")
        profile[key] = value
    return profile


def _save_profile(c, profile):
    c.execute('UPDATE local_market_profile SET faction=?,ruleset=?,region=?,realm=? WHERE id=1',
              tuple(profile[key] for key in ('faction','ruleset','region','realm')))


def configure_market(database, settings):
    with database.transaction() as c:
        profile = market_profile(c)
        values = {key: getattr(settings, 'local_' + key) for key in ('faction','ruleset','region','realm')}
        _save_profile(c, _merge_identity(profile, values))


def local_market(c, source_id, retrieved_at, build=None, *, faction='unknown', region='unknown', realm='unknown'):
    profile = market_profile(c)
    if profile['legacy_unverified']:
        raise ValueError('This database contains legacy local-market assumptions. Keep it for historical research and use a new database for neutral market imports; no evidence was deleted.')
    # Only explicit source fields identify the market; realm names do not establish a ruleset.
    profile = _merge_identity(profile, dict(faction=faction.lower(), region=region.lower(), realm=realm))
    _save_profile(c, profile)
    c.execute("""INSERT INTO markets(market_key,name,region,ruleset,faction,is_verified,source_id,
        retrieved_at,game_build,confidence,evidence_kind)
        VALUES (?,?,?,?,?,0,?,?,?,0.9,'observed')
        ON CONFLICT(market_key) DO UPDATE SET retrieved_at=excluded.retrieved_at,
        region=excluded.region,faction=excluded.faction,ruleset=excluded.ruleset,
        is_verified=0,game_build=COALESCE(excluded.game_build,markets.game_build)""",
        (MARKET_KEY,MARKET_NAME,profile['region'],profile['ruleset'],profile['faction'],source_id,retrieved_at,build))
    return c.execute('SELECT id FROM markets WHERE market_key=?',(MARKET_KEY,)).fetchone()[0]


def context(database):
    with database.transaction() as c:
        p = policy(c)
        profile = market_profile(c)
        peers = [dict(r) for r in c.execute("SELECT market_key,name,faction,ruleset,region FROM markets WHERE market_key LIKE 'forever.%' ORDER BY market_key")]
    candidate = f"forever.{profile['ruleset']}.{profile['faction']}.{profile['region']}"
    preferred = candidate if any(m['market_key'] == candidate for m in peers) else None
    return dict(name=MARKET_NAME,market_key=MARKET_KEY,
        auction_sources='Local addon scans and separately identified public community markets',
        public_markets=peers,
        public_feed=dict(source_key='ahledger',preferred_reference=preferred,
                         role='Separate reference market; never substitute public quotes for local availability'),
        faction=profile['faction'],ruleset=profile['ruleset'],region=profile['region'],realm=profile['realm'],
        legacy_market_requires_review=bool(profile['legacy_unverified']),
        reset_at=p['reset_at'] if p else None,
        generic_auction_imports_enabled=False,
        reset_boundary_status='recorded' if p else 'missing',
        reset_boundary_warning=None if p else 'No reset cutoff is stored. Historical reset filtering is unavailable.',
        identity_basis='Explicit local configuration and source-reported scan fields; unknown values are not inferred',
        instructions='Use wow-forever for this database only. Each database holds one local market profile. Do not infer faction, ruleset or region from a realm name. Public markets retain their own source and identity. Compare only explicitly identified markets, preserve capture timestamps and explain transfer assumptions. Asking prices do not establish completed sales.')


def restore_static_identity_selection(c):
    c.execute("""UPDATE evidence_assertions AS current SET selected=(id=(
        SELECT candidate.id FROM evidence_assertions candidate JOIN sources s ON s.id=candidate.source_id
        WHERE candidate.entity_type=current.entity_type AND candidate.entity_key=current.entity_key
        ORDER BY s.trust_rank,candidate.retrieved_at DESC,candidate.confidence DESC,candidate.id DESC LIMIT 1))
        WHERE entity_type='item_identity'""")


def reset_auctions(database, auctionator_paths=(), *, clear_characters=False):
    """Delete auction evidence, retaining static research and characters. No game files written."""
    from goblin_eye.ingestion.auctionator import discover_auctionator_files, parse_auctionator_file
    now = datetime.now(timezone.utc).isoformat()
    baselines = []
    # Only hashes are retained: unchanged SavedVariables entries must not resurrect old prices.
    for path in discover_auctionator_files(auctionator_paths):
        capture = parse_auctionator_file(path)
        for market, items in capture.markets.items():
            baselines.extend((str(path.resolve()),market,str(k),digest(v)) for k,v in items.items() if isinstance(v,dict))
    with database.transaction() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('PRAGMA secure_delete=ON')
        counts = {t:c.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                  for t in ('snapshots','listings','auction_rows','price_observations','market_captures','market_price_points')}
        for table in ('market_price_points','market_captures','auction_rows','listings','snapshots','price_observations'):
            c.execute(f'DELETE FROM {table}')
        # Public tooltip documents also contain quotes, even though item identities were extracted from them.
        c.execute("DELETE FROM source_documents WHERE source_id IN (SELECT id FROM sources WHERE source_key IN ('ahledger','local-auctionator','local-ahledger'))")
        # Normalized static item observations survive; embedded raw quotes do not.
        unwanted = "SELECT id FROM evidence_assertions WHERE entity_type IN ('markets','snapshots','listings','item_identity')"
        c.execute(f'DELETE FROM assertion_conflicts WHERE left_id IN ({unwanted}) OR right_id IN ({unwanted})')
        c.execute(f'DELETE FROM evidence_assertions WHERE id IN ({unwanted})')
        c.execute("DELETE FROM fact_conflicts WHERE entity_type IN ('markets','snapshots','listings','item_identity')")
        restore_static_identity_selection(c)
        c.execute('DELETE FROM markets')
        c.execute("DELETE FROM imports WHERE source_id IN (SELECT id FROM sources WHERE source_key IN ('ahledger','local-auctionator','local-ahledger')) OR adapter_key='snapshot_csv'")
        c.execute("DELETE FROM watched_files WHERE adapter_key LIKE 'auctionator%' OR adapter_key LIKE 'ahledger%'")
        c.execute("UPDATE sources SET notes='Auction cache cleared; configured public syncing resumes on next refresh.',last_success_at=NULL,last_error=NULL WHERE source_key='ahledger'")
        c.execute("UPDATE sources SET last_success_at=NULL,last_error=NULL WHERE source_key IN ('local-auctionator','local-ahledger')")
        c.execute("INSERT OR IGNORE INTO sources(source_key,name,source_type,trust_rank) VALUES ('local-ahledger','Local AHledger scans','local_addon',1)")
        profile = market_profile(c)
        c.execute("INSERT OR REPLACE INTO auction_policy(id,reset_at,faction,ruleset) VALUES (1,?,?,?)",(now,profile['faction'],profile['ruleset']))
        c.execute('UPDATE local_market_profile SET legacy_unverified=0 WHERE id=1')
        c.execute('DELETE FROM auction_reset_baselines')
        c.executemany('INSERT INTO auction_reset_baselines VALUES (?,?,?,?)',baselines)
        if clear_characters:
            counts['companion_entries'] = c.execute('SELECT count(*) FROM companion_entries').fetchone()[0]
            c.execute('DELETE FROM companion_status_events')
            c.execute('DELETE FROM companion_entries')
            counts['character_snapshots'] = c.execute('SELECT count(*) FROM character_snapshots').fetchone()[0]
            counts['character_item_observations'] = c.execute('SELECT count(*) FROM character_item_observations').fetchone()[0]
            c.execute('DELETE FROM character_inventory_observations')
            c.execute('DELETE FROM character_item_observations')
            c.execute('DELETE FROM character_snapshots')
            c.execute("DELETE FROM imports WHERE source_id IN (SELECT id FROM sources WHERE source_key='local-alts-forever')")
        source_id=c.execute("SELECT id FROM sources WHERE source_key='local-ahledger'").fetchone()[0]
        local_market(c,source_id,now)
    return dict(reset_at=now,deleted=counts,market_key=MARKET_KEY,waiting_for='A new local addon scan saved after the reset')


def reset_personal_data(database, auctionator_paths=()):
    """Explicit no-backup reset, including local character export files.

    The caller pauses auction workers/configuration before entering maintenance.
    Only files under this database's characters directory may be removed.
    """
    folder = database.path.resolve().parent / 'characters'
    if folder.is_symlink() or (folder.exists() and folder.resolve() != folder):
        raise ValueError('Character export directory must not redirect outside the database directory')
    exports = list(folder.rglob('*')) if folder.exists() else []
    for path in exports:
        if path.is_symlink() or not path.resolve().is_relative_to(folder):
            raise ValueError('Character export path escapes the local character directory')
    result = reset_auctions(database, auctionator_paths, clear_characters=True)
    removed = 0
    for path in exports:
        if path.is_file():
            path.unlink()
            removed += 1
    # Remove freed SQLite pages rather than keeping deleted rows in the DB file.
    with database.transaction() as c:
        checkpoint = c.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        if checkpoint[0]:
            raise ValueError('Reset committed, but a database reader prevents checkpointing. Close clients and retry maintenance.')
        c.execute('VACUUM')
        checkpoint = c.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        if checkpoint[0]:
            raise ValueError('Reset committed, but final checkpoint is busy. Close clients and retry maintenance.')
    result.update(character_exports_removed=removed, backup_created=False,
                  waiting_for='Auction imports are paused. Enable them explicitly when ready for new evidence.')
    return result
