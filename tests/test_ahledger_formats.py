from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from goblin_eye.history import MarketHistory, parse_price_table
from goblin_eye.ingestion.ahledger import AHLedgerPublicApiAdapter, Download
from goblin_eye.repository import Database

ROOT = Path(__file__).resolve().parents[1]
MARKET = 'forever.pvp.horde.us'
BASE_ROW = '2589:20:18:3420:22:21:18:25'


def table(row):
    return ('AHL1|forever/pvp/horde/us|1791374689|1\n' + row + '\n').encode()


class AHLedgerFormatTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db = Database(Path(temporary.name) / 'test.db')
        self.db.migrate(ROOT / 'migrations')

    def sync(self, row):
        def download(path):
            if path == '/v1/markets':
                body = json.dumps({'markets': [{'id': MARKET, 'game': 'forever',
                    'ruleset': 'pvp', 'faction': 'horde', 'region': 'us', 'label': 'PvP Horde'}]}).encode()
            elif path.startswith('/v1/pricetable/'):
                body = table(row)
            elif path.startswith('/v1/tooltip/'):
                body = json.dumps({'items': [{'id': 2589, 'name': 'Linen Cloth'}]}).encode()
            else:
                self.fail('Unexpected download: ' + path)
            return Download('https://api.ahledger.com' + path, body, 'text/plain', None)
        with patch('goblin_eye.ingestion.ahledger._download', side_effect=download):
            return AHLedgerPublicApiAdapter().sync(self.db)

    def test_legacy_and_current_tables_keep_price_positions(self):
        for suffix, expected in [('', None), (':3600', 360.0), (':4', 0.4), (':0', 0.0), (':', None)]:
            with self.subTest(suffix=suffix):
                self.sync(BASE_ROW + suffix)
        points = MarketHistory(self.db).points(2589, MARKET)['records']
        self.assertEqual(len(points), 5)
        self.assertEqual(sorted(p['metrics']['provider_estimated_units_sold_per_day']
                                for p in points if p['metrics']['provider_estimated_units_sold_per_day'] is not None),
                         [0.0, 0.4, 360.0])
        self.assertEqual(sum(p['metrics']['provider_estimated_units_sold_per_day'] is None for p in points), 2)
        for point in points:
            self.assertEqual(point['source_key'], 'ahledger')
            self.assertEqual(point['market_key'], MARKET)
            self.assertEqual((point['minimum_copper'], point['median_copper'], point['available_quantity']), (18, 20, 3420))
            self.assertEqual(point['metrics']['provider_high_30d'], 25)
            self.assertIn('not confirmed sales', ' '.join(point['limitations']))
        with self.db.transaction() as c:
            observation = c.execute('SELECT * FROM price_observations').fetchone()
            self.assertEqual((observation['current_min_unit_copper'], observation['available_quantity'],
                              observation['high_30d_copper']), (18, 3420, 25))
            self.assertEqual(c.execute("SELECT last_error FROM sources WHERE source_key='ahledger'").fetchone()[0], None)

    def test_unknown_prices_and_estimate_remain_unknown(self):
        self.sync('2589::::::::')
        point = MarketHistory(self.db).points(2589, MARKET)['records'][0]
        self.assertIsNone(point['minimum_copper'])
        self.assertIsNone(point['available_quantity'])
        self.assertIsNone(point['metrics']['provider_estimated_units_sold_per_day'])

    def test_bad_width_and_estimates_are_rejected(self):
        for row in [BASE_ROW.rsplit(':', 1)[0], BASE_ROW + ':4:5',
                    BASE_ROW + ':-1', BASE_ROW + ':0.4', BASE_ROW + ':wat']:
            with self.subTest(row=row), self.assertRaises(ValueError):
                parse_price_table(table(row), MARKET)

    def test_existing_format_guards_remain(self):
        for body in [table(BASE_ROW).replace(b'AHL1', b'AHL2'),
                     table(BASE_ROW).replace(b'|1\n', b'|2\n'),
                     table(BASE_ROW).replace(b'|1\n', b'|2\n') + (BASE_ROW + '\n').encode()]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_price_table(body, MARKET)
        with self.assertRaisesRegex(ValueError, 'market mismatch'):
            parse_price_table(table(BASE_ROW), 'forever.normal.alliance.us')

    def test_malformed_sync_preserves_previous_evidence(self):
        self.sync(BASE_ROW)
        with self.db.transaction() as c:
            c.execute("UPDATE sources SET last_error='previous error' WHERE source_key='ahledger'")
            before = c.execute('SELECT count(*) FROM source_documents').fetchone()[0]
        with self.assertRaises(ValueError):
            self.sync(BASE_ROW + ':4:5')
        with self.db.transaction() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM source_documents').fetchone()[0], before)
            self.assertEqual(c.execute('SELECT count(*) FROM price_observations').fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT last_error FROM sources WHERE source_key='ahledger'").fetchone()[0], 'previous error')


if __name__ == '__main__':
    unittest.main()
