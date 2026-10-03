"""Immutable source observations and explicit, descriptive price references."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from statistics import median
from goblin_eye.validation import integer, text, timestamp

def record_capture(c, source_id, market_id, identity, observed_at, retrieved_at, granularity,
                   points, document_id=None, game_build=None, period='unknown', recovered=False, limitations=()):
    c.execute('''INSERT OR IGNORE INTO market_captures(source_id,market_id,document_id,identity,observed_at,
        retrieved_at,granularity,game_build,economic_period,recovered,limitations_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (source_id,market_id,document_id,identity,observed_at,retrieved_at,
        granularity,game_build,period,int(recovered),json.dumps(list(limitations))))
    capture = c.execute('SELECT id FROM market_captures WHERE source_id=? AND market_id=? AND identity=?',
                        (source_id,market_id,identity)).fetchone()[0]
    c.executemany('''INSERT OR IGNORE INTO market_price_points VALUES (?,?,?,?,?,?,?,?)''',
        ((capture,str(p['item_key']),p.get('item_id'),p['observed_date'],p.get('minimum_copper'),
          p.get('median_copper'),p.get('available_quantity'),json.dumps(p,sort_keys=True)) for p in points))
    return capture

def parse_price_table(body: bytes, expected_market: str | None = None):
    lines = body.decode('utf-8').splitlines()
    header = lines[0].split('|') if lines else []
    if len(header) != 4 or header[0] != 'AHL1':
        raise ValueError('Unsupported AHledger price table header')
    market = header[1].replace('/', '.')
    if expected_market and market != expected_market:
        raise ValueError('Price table market mismatch')
    epoch = int(header[2]); integer(epoch, 'source timestamp', 1)
    observed = datetime.fromtimestamp(epoch,timezone.utc).isoformat()
    rows = [line.split(':') for line in lines[1:] if line]
    if len(rows) != int(header[3]):
        raise ValueError('Price table count mismatch')
    seen = set()
    for row in rows:
        if len(row) != 8:
            raise ValueError('Unsupported AHledger price row')
        item_id = int(row[0]); integer(item_id,'item_id',1)
        if item_id in seen: raise ValueError('Duplicate price-table item')
        seen.add(item_id)
        for value in row[1:]:
            if value: integer(int(value), 'price-table value')
    return market, observed, rows

def public_capture(c, source_id, market_id, document_id, body, retrieved_at, recovered=False, period="unknown"):
    market, observed, rows = parse_price_table(body)
    expected = c.execute('SELECT market_key FROM markets WHERE id=?',(market_id,)).fetchone()[0]
    if market != expected: raise ValueError('Cached table does not match target market')
    points = []
    for row in rows:
        values = [int(v) if v else None for v in row]
        points.append(dict(item_key=row[0],item_id=values[0],observed_date=observed[:10],provider_market=market,
            minimum_copper=values[2],median_copper=values[1],available_quantity=values[3],
            provider_median_7d=values[4],provider_median_30d=values[5],provider_low_30d=values[6],provider_high_30d=values[7]))
    return record_capture(c,source_id,market_id,hashlib.sha256(body).hexdigest(),observed,retrieved_at,
                          'source_table',points,document_id,period=period,recovered=recovered,
                          limitations=['AHledger Forever community reference; not a personal scan or completed sale. Public markets remain separate; correspondence to the local economy is not assumed. Provider rolling metrics retain provider semantics.'])

def recover_history(database):
    from goblin_eye.auction_policy import reject_external_auctions
    reject_external_auctions(database)
    report = {'public_documents':0,'legacy_points':0,'errors':[]}
    with database.transaction() as c:
        before = c.execute('SELECT count(*) FROM market_captures').fetchone()[0]
        docs = c.execute("SELECT id,source_id,body,retrieved_at FROM source_documents WHERE url LIKE 'https://api.ahledger.com/v1/pricetable/%' ORDER BY id").fetchall()
        for doc in docs:
            try:
                key, _, _ = parse_price_table(bytes(doc['body']))
                market = c.execute('SELECT id FROM markets WHERE market_key=?',(key,)).fetchone()
                if not market: raise ValueError('Cached market not indexed')
                public_capture(c,doc['source_id'],market[0],doc['id'],bytes(doc['body']),doc['retrieved_at'],True,period='Forever beta')
                report['public_documents'] += 1
            except (ValueError, OverflowError, UnicodeError) as exc:
                report['errors'].append({'document_id':doc['id'],'error':str(exc)})
        # Keep legacy daily state, explicitly excluding it from precise price estimates.
        for row in c.execute('SELECT * FROM price_observations').fetchall():
            p = dict(row)
            point = dict(item_key=p['item_key'],item_id=p['item_id'],observed_date=p['observed_date'],
                         minimum_copper=p['current_min_unit_copper'],median_copper=p['median_unit_copper'],
                         available_quantity=p['available_quantity'],legacy_record=p)
            record_capture(c,p['source_id'],p['market_id'],'legacy:'+str(p['id']),None,p['imported_at'],
                           'legacy_daily',[point],recovered=True,limitations=['Legacy daily state. Original intraday history and per-item observation time unavailable.'])
            report['legacy_points'] += 1
        report['new_captures'] = c.execute('SELECT count(*) FROM market_captures').fetchone()[0] - before
    return report

class MarketHistory:
    def __init__(self, database): self.database = database

    def coverage(self, market_key='wow-forever', source_key=None, item_id=None):
        text(market_key, 'market_key')
        if source_key is not None: text(source_key, 'source_key')
        if item_id is not None: integer(item_id, 'item_id', 1)
        with self.database.transaction() as c:
            captures = c.execute('''SELECT s.source_key,h.economic_period,h.granularity,
                h.game_build,count(*) capture_count,min(h.observed_at) first_observed_at,
                max(h.observed_at) last_observed_at,min(h.retrieved_at) first_retrieved_at,
                max(h.retrieved_at) last_retrieved_at
                FROM market_captures h JOIN markets m ON m.id=h.market_id JOIN sources s ON s.id=h.source_id
                WHERE m.market_key=? AND (? IS NULL OR s.source_key=?) AND (? IS NULL OR EXISTS
                    (SELECT 1 FROM market_price_points p WHERE p.capture_id=h.id AND p.item_id=?))
                GROUP BY s.source_key,h.economic_period,h.granularity,h.game_build
                ORDER BY s.source_key,h.economic_period,h.granularity,h.game_build''',
                (market_key,source_key,source_key,item_id,item_id)).fetchall()
            scans = c.execute('''SELECT s.source_key,h.economic_period,'listing_scan' granularity,
                h.game_build,count(*) capture_count,min(h.captured_at) first_observed_at,
                max(h.captured_at) last_observed_at,min(h.imported_at) first_retrieved_at,
                max(h.imported_at) last_retrieved_at
                FROM snapshots h JOIN markets m ON m.id=h.market_id JOIN sources s ON s.id=h.source_id
                WHERE m.market_key=? AND s.source_key='local-ahledger' AND (? IS NULL OR s.source_key=?)
                AND (? IS NULL OR EXISTS(SELECT 1 FROM auction_rows a WHERE a.snapshot_id=h.id AND a.item_id=?))
                GROUP BY s.source_key,h.economic_period,h.game_build ORDER BY h.economic_period,h.game_build''',
                (market_key,source_key,source_key,item_id,item_id)).fetchall()
        records = [dict(r) for r in captures] + [dict(r) for r in scans]
        return dict(market_key=market_key, item_id=item_id, source_key=source_key, records=records,
            available_periods=sorted({r['economic_period'] for r in records}),
            queried_at=datetime.now(timezone.utc).isoformat(),
            interpretation='Counts are retained captures, not sales. Item-filtered coverage includes only captures containing that item. Daily records have unknown intraday observation time; retrieval time does not repair that. period selects an exact economic/content phase, not a daily/hourly time bucket. start/end require a timezone, e.g. 2026-09-28T00:00:00Z.')

    def _check_period(self, period, market_key, source_key=None):
        if period is None: return
        text(period, 'period')
        available = self.coverage(market_key, source_key)['available_periods']
        if available and period not in available:
            raise ValueError(f'Unknown economic period {period!r}; available labels: {available}. '
                'period is an exact content-phase filter, not daily/hourly aggregation. '
                'Omit it for unfiltered history, or choose a label from get_history_coverage.')

    def scans(self, market_key, limit=50, offset=0):
        text(market_key,'market_key'); integer(limit,'limit',1,500); integer(offset,'offset')
        with self.database.transaction() as c:
            total=c.execute('SELECT count(*) FROM snapshots s JOIN markets m ON m.id=s.market_id WHERE m.market_key=?',(market_key,)).fetchone()[0]
            rows=c.execute('''SELECT s.*,m.market_key,so.source_key,
                (SELECT count(*) FROM auction_rows a WHERE a.snapshot_id=s.id) auction_row_count,
                (SELECT count(*) FROM listings l WHERE l.snapshot_id=s.id) legacy_listing_count
                FROM snapshots s JOIN markets m ON m.id=s.market_id JOIN sources so ON so.id=s.source_id
                WHERE m.market_key=? ORDER BY s.captured_at DESC,s.id DESC LIMIT ? OFFSET ?''',(market_key,limit,offset)).fetchall()
        return dict(market_key=market_key,records=[dict(r) for r in rows],total=total,limit=limit,offset=offset)

    def points(self,item_id,market_key,limit=100,offset=0,start=None,end=None,item_key=None,period=None,source_key=None):
        integer(item_id,'item_id',1);text(market_key,'market_key');integer(limit,'limit',1,500);integer(offset,'offset')
        self._check_period(period,market_key,source_key)
        where=['p.item_id=?','m.market_key=?']; args=[item_id,market_key]
        for value,column in ((item_key,'p.item_key'),(period,'h.economic_period'),(source_key,'s.source_key')):
            if value is not None: text(value,column);where.append(column+'=?');args.append(value)
        for value,op in ((start,'>='),(end,'<=')):
            if value is not None:
                value=timestamp(value)
                where.append(f"COALESCE(h.observed_at,p.observed_date||'T00:00:00+00:00'){op}?");args.append(value)
        if start and end and timestamp(start)>timestamp(end): raise ValueError('start must precede end')
        base=''' FROM market_price_points p JOIN market_captures h ON h.id=p.capture_id
             JOIN markets m ON m.id=h.market_id JOIN sources s ON s.id=h.source_id WHERE '''+' AND '.join(where)
        with self.database.transaction() as c:
            total=c.execute('SELECT count(*)'+base,args).fetchone()[0]
            rows=c.execute('''SELECT p.*,h.observed_at,h.retrieved_at,h.granularity,h.game_build,h.economic_period,
                h.recovered,h.document_id,h.limitations_json,s.source_key,m.market_key'''+base+
                " ORDER BY COALESCE(h.observed_at,p.observed_date) DESC,h.id DESC LIMIT ? OFFSET ?",(*args,limit,offset)).fetchall()
        records=[]
        for row in rows:
            r=dict(row);r['metrics']=json.loads(r.pop('payload_json'));r['limitations']=json.loads(r.pop('limitations_json'));records.append(r)
        return dict(item_id=item_id,market_key=market_key,records=records,total=total,limit=limit,offset=offset,
                    limitations=['Dates on daily aggregates do not establish intraday timing. Sources and variants remain separate.'])

    def reference(self,item_id,market_key,start,end,source_key,period,item_key=None,minimum_samples=3):
        integer(minimum_samples,'minimum_samples',2,500)
        text(source_key,'source_key');text(period,'period');timestamp(start);timestamp(end)
        if source_key == 'local-ahledger':
            if item_key not in (None,str(item_id)):
                raise ValueError('Local scans have base item IDs only')
            series=self.local_series(item_id,market_key,start,end,500,period)
            records=[r for r in series['records'] if r['minimum_copper'] is not None]
            values=[r['minimum_copper'] for r in records]
            sufficient=len(values)>=minimum_samples and not series['truncated'] and len({r['game_build'] for r in records})==1 and len({r['observed_at'] for r in records})==len(records)
            return dict(status='ok' if sufficient else 'insufficient_evidence',method='median of per-scan observed unit minima',
                reference_copper=median(values) if sufficient else None,sample_count=len(values),
                observed_range_copper=[min(values),max(values)] if values else None,
                snapshot_ids=[r['snapshot_id'] for r in records],market_key=market_key,item_id=item_id,
                start=start,end=end,source_key=source_key,economic_period=period,
                limitations=series['limitations']+['Equal weight per saved scan. A reference is not a sale prediction. No cross-build pooling.'])
        page=self.points(item_id,market_key,500,0,start,end,item_key,period,source_key)
        records=[r for r in page['records'] if r['granularity']=='source_table' and r['minimum_copper'] is not None and r['minimum_copper']>0]
        identities={(r['item_key'],r['game_build']) for r in records}
        values=[r['minimum_copper'] for r in records]
        sufficient=len(values)>=minimum_samples and page['total']<=500 and len(identities)==1 and len({r['observed_at'] for r in records})==len(records)
        return dict(status='ok' if sufficient else 'insufficient_evidence',item_id=item_id,market_key=market_key,
                    source_key=source_key,economic_period=period,start=start,end=end,sample_count=len(values),
                    method='median of distinct source-table observed unit minima; equal weight per source observation',
                    reference_copper=median(values) if sufficient else None,
                    observed_range_copper=[min(values),max(values)] if values else None,
                    capture_ids=[r['capture_id'] for r in records],newest_observation=records[0]['observed_at'] if records else None,
                    limitations=['Descriptive asking-price reference, not sale value, liquidity or a confidence interval.',
                        'Requires one item variant/build and at least the requested number of observations. Windows over 500 points must be narrowed.',
                        'Only source-stamped public tables qualify for this method; daily captures are excluded. Observation spacing may be uneven.'])

    def local_series(self,item_id,market_key,start=None,end=None,limit=100,period=None):
        integer(item_id,'item_id',1);text(market_key,'market_key');integer(limit,'limit',1,500)
        self._check_period(period,market_key,'local-ahledger')
        where=['m.market_key=?',"so.source_key='local-ahledger'"];args=[market_key]
        if period is not None: text(period,'period');where.append('s.economic_period=?');args.append(period)
        for value,op in ((start,'>='),(end,'<=')):
            if value: where.append('s.captured_at'+op+'?');args.append(timestamp(value))
        if start and end and timestamp(start)>timestamp(end): raise ValueError('start must precede end')
        with self.database.transaction() as c:
            scans=c.execute('''SELECT s.* FROM snapshots s JOIN markets m ON m.id=s.market_id
                JOIN sources so ON so.id=s.source_id WHERE '''+' AND '.join(where)+
                ' ORDER BY s.captured_at DESC,s.id DESC LIMIT ?',(*args,limit+1)).fetchall()
            records=[]
            for scan in scans[:limit]:
                rows=c.execute('''SELECT quantity,buyout_copper FROM auction_rows WHERE snapshot_id=? AND item_id=?
                    ORDER BY 1.0*buyout_copper/quantity,ordinal''',(scan['id'],item_id)).fetchall()
                buyouts=[r for r in rows if r['buyout_copper']>0]
                units=sum(r['quantity'] for r in buyouts)
                cumulative=0;weighted=None
                for r in buyouts:
                    cumulative+=r['quantity']
                    if cumulative*2>=units:
                        weighted=r['buyout_copper']/r['quantity'];break
                records.append(dict(snapshot_id=scan['id'],observed_at=scan['captured_at'],game_build=scan['game_build'],
                    economic_period=scan['economic_period'],listing_count=len(rows),listed_units=sum(r['quantity'] for r in rows),buyout_units=units,
                    bid_only_listings=len(rows)-len(buyouts),minimum_copper=buyouts[0]['buyout_copper']/buyouts[0]['quantity'] if buyouts else None,
                    quantity_weighted_median_copper=weighted,is_complete=bool(scan['is_complete']),
                    absence='not_observed' if not rows else None))
        return dict(item_id=item_id,market_key=market_key,records=records,truncated=len(scans)>limit,
                    limitations=['Listed supply is not sales or liquidity. Missing rows do not prove zero supply.',
                        'Completeness and economic period are unverified. Gear variants and persistent auction IDs unavailable.',
                        'Quantity-weighted median is the first unit-price level reaching half the buyout units.'])

    def compare(self,item_id,market_key,before_id,after_id):
        integer(before_id,'before_id',1);integer(after_id,'after_id',1)
        from goblin_eye.item_graph import ItemGraph
        graph=ItemGraph(self.database)
        before=graph.market_depth(item_id,market_key,1,0,before_id)
        after=graph.market_depth(item_id,market_key,1,0,after_id)
        if not before['snapshot'] or not after['snapshot']: raise ValueError('Both snapshots must exist in the selected market')
        if before['snapshot']['economic_period']!=after['snapshot']['economic_period']: raise ValueError('Choose snapshots from the same economic period')
        if before['snapshot']['game_build']!=after['snapshot']['game_build']: raise ValueError('Choose snapshots from the same build')
        if before['snapshot']['captured_at']>=after['snapshot']['captured_at']: raise ValueError('Before must precede after')
        keys=('listing_count','listed_units','buyout_units','bid_only_listings')
        return dict(before_snapshot=before['snapshot'],after_snapshot=after['snapshot'],
            before=before['totals'],after=after['totals'],
            observed_net_changes={k:after['totals'][k]-before['totals'][k] for k in keys},
            limitations=['Net differences between observed scans; not matched auction events, sales, or measured consumption. Completeness unverified.'])
