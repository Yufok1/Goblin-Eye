"""Freshness stays scoped to a market, source, and observation type."""
from datetime import datetime, timezone


def _state(observed_at, observed_date, imported_at, count, stale_hours):
    age = None
    if observed_at:
        stamp = datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
        age = max(0, (datetime.now(timezone.utc) - stamp).total_seconds() / 3600)
    status = ('stale' if age > stale_hours else 'recent') if age is not None else ('date_only' if observed_date else 'missing')
    return dict(observed_at=observed_at, observed_date=observed_date, imported_at=imported_at,
                evidence_count=count, has_evidence=bool(count), status=status,
                timestamp_precision='instant' if observed_at else ('date' if observed_date else 'unknown'),
                age_hours=round(age, 2) if age is not None else None,
                is_stale=age > stale_hours if age is not None else None)


def evidence_freshness(connection, local_market, stale_hours):
    prices = {}
    for row in connection.execute("""SELECT m.market_key,s.source_key,
            MAX(CASE WHEN h.granularity IN ('scan','source_table') THEN h.observed_at END) observed_at,
            MAX(p.observed_date) observed_date,MAX(h.retrieved_at) imported_at,
            COUNT(DISTINCT h.id) count
            FROM market_captures h JOIN markets m ON m.id=h.market_id
            JOIN sources s ON s.id=h.source_id JOIN market_price_points p ON p.capture_id=h.id
            WHERE p.minimum_copper IS NOT NULL OR p.median_copper IS NOT NULL
            GROUP BY m.market_key,s.source_key"""):
        prices[(row['market_key'], row['source_key'])] = _state(
            row['observed_at'], row['observed_date'], row['imported_at'], row['count'], stale_hours)
    # Old daily tables remain visible without assigning them an intraday time.
    for row in connection.execute("""SELECT m.market_key,s.source_key,MAX(po.observed_date) observed_date,
            MAX(po.imported_at) imported_at,COUNT(*) count
            FROM price_observations po JOIN markets m ON m.id=po.market_id
            JOIN sources s ON s.id=po.source_id
            WHERE po.current_min_unit_copper IS NOT NULL OR po.daily_min_unit_copper IS NOT NULL
            GROUP BY m.market_key,s.source_key"""):
        key = (row['market_key'], row['source_key'])
        prices.setdefault(key, _state(None, row['observed_date'], row['imported_at'], row['count'], stale_hours))
    listing_scans = []
    for row in connection.execute("""SELECT s.source_key,MAX(sn.captured_at) observed_at,
            MAX(sn.imported_at) imported_at,COUNT(*) count,
            MAX(CASE WHEN EXISTS(SELECT 1 FROM auction_rows a WHERE a.snapshot_id=sn.id AND a.buyout_copper>0)
                OR EXISTS(SELECT 1 FROM listings l WHERE l.snapshot_id=sn.id AND l.buyout_copper>0)
                THEN sn.captured_at END) price_at
            FROM snapshots sn JOIN markets m ON m.id=sn.market_id JOIN sources s ON s.id=sn.source_id
            WHERE m.market_key=? GROUP BY s.source_key""", (local_market,)):
        listing_scans.append(dict(market_key=local_market, source_key=row['source_key'],
            **_state(row['observed_at'], None, row['imported_at'], row['count'], stale_hours)))
        if row['price_at']:
            prices[(local_market, row['source_key'])] = _state(row['price_at'], None, row['imported_at'], row['count'], stale_hours)
    local_prices = []
    for source in ('local-auctionator', 'local-ahledger'):
        local_prices.append(dict(market_key=local_market, source_key=source,
            **prices.get((local_market, source), _state(None, None, None, 0, stale_hours))))
    if not listing_scans:
        listing_scans.append(dict(market_key=local_market, source_key='local-ahledger',
            **_state(None, None, None, 0, stale_hours)))
    references = [dict(market_key=market, source_key=source, **value)
                  for (market, source), value in prices.items() if market != local_market]
    characters = []
    for row in connection.execute("""SELECT name,character_key,captured_at,imported_at FROM character_snapshots
            WHERE id IN (SELECT MAX(id) FROM character_snapshots GROUP BY character_key)
            ORDER BY id DESC LIMIT 101"""):
        characters.append(dict(name=row['name'], character_key=row['character_key'],
            **_state(row['captured_at'], None, row['imported_at'], 1, stale_hours)))
    return dict(local_prices=local_prices, local_listing_scans=listing_scans,
                public_references=references, characters=characters[:100], characters_truncated=len(characters)>100,
                interpretation='Import time never establishes observation freshness. Date-only prices have unknown intraday age. Public reference markets cannot establish local pricing readiness.')
