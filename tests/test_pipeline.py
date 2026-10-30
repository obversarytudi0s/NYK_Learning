import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from knicks_history.pipeline import archive, build, normalize, digest, season_label

FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures' / 'league-demo.json'


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.raw = FIXTURE.read_bytes()
        self.payload = json.loads(self.raw)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'demo'

    def tearDown(self):
        self.temp.cleanup()

    def records(self, payload=None):
        return normalize(payload or self.payload, '2024-25', 'Regular Season', digest(self.raw))

    def ingest(self, payload=None):
        raw = json.dumps(payload).encode() if payload is not None else self.raw
        return archive(self.root, raw, '2024-25', 'Regular Season', True, {'input': 'test'})

    def test_filter_and_join_opponents(self):
        rows = self.records()
        self.assertEqual(len(rows), 2)
        self.assertEqual([r['point_margin'] for r in rows], [10, -6])

    def test_preserves_leading_zero(self):
        self.assertEqual(self.records()[0]['game_id'], '0022400001')

    def test_null_is_not_zero(self):
        self.assertIsNone(self.records()[1]['reb'])
        self.assertIsNone(self.records()[0]['stl'])

    def test_duplicate_rejected(self):
        self.payload['resultSets'][0]['rowSet'].append(self.payload['resultSets'][0]['rowSet'][0])
        with self.assertRaises(ValueError):
            self.records()

    def test_missing_header_rejected(self):
        self.payload['resultSets'][0]['headers'][0] = 'TEAM_BROKEN'
        with self.assertRaises(ValueError):
            self.records()

    def test_wrong_row_width_rejected(self):
        self.payload['resultSets'][0]['rowSet'][0].append(0)
        with self.assertRaises(ValueError):
            self.records()

    def test_bad_score_rejected(self):
        self.payload['resultSets'][0]['rowSet'][0][5] = 120
        with self.assertRaises(ValueError):
            self.records()

    def test_numeric_id_rejected(self):
        self.payload['resultSets'][0]['rowSet'][0][1] = 22400001
        with self.assertRaises(ValueError):
            self.records()

    def test_wrong_season_rejected(self):
        with self.assertRaises(ValueError):
            normalize(self.payload, '2021-22', 'Regular Season', digest(self.raw))

    def test_empty_requires_explicit_opt_in(self):
        self.payload['resultSets'][0]['rowSet'] = []
        with self.assertRaises(ValueError):
            self.ingest(self.payload)
        self.assertEqual(json.loads(next((self.root / 'runs').glob('*.json')).read_text())['status'], 'rejected')

    def test_replay_same_rows(self):
        self.ingest()
        one = build(self.root)
        self.ingest()
        two = build(self.root)
        self.assertEqual((one / 'team_games.csv').read_bytes(), (two / 'team_games.csv').read_bytes())
        with sqlite3.connect(two / 'knicks.sqlite') as con:
            self.assertEqual(con.execute('SELECT count(*) FROM team_games').fetchone()[0], 2)
            self.assertEqual(con.execute('SELECT wins, losses FROM season_summary').fetchone(), (1, 1))

    def test_correction_replaces_partition(self):
        self.ingest()
        changed = copy.deepcopy(self.payload)
        changed['resultSets'][0]['rowSet'][0][5] = 112
        changed['resultSets'][0]['rowSet'][0][10] = 22
        self.ingest(changed)
        release = build(self.root)
        with sqlite3.connect(release / 'knicks.sqlite') as con:
            self.assertEqual(con.execute("SELECT pts FROM team_games WHERE game_id='0022400001'").fetchone()[0], 112)
            self.assertEqual(con.execute('SELECT count(*) FROM team_games').fetchone()[0], 2)

    def test_no_mixed_modes(self):
        self.ingest()
        with self.assertRaises(ValueError):
            archive(self.root, self.raw, '2024-25', 'Regular Season', False, {})

    def test_checksum_detects_tampering(self):
        m = self.ingest()
        (self.root / m['raw_file']).write_text('{}')
        with self.assertRaises(ValueError):
            build(self.root)

    def test_failed_build_preserves_current(self):
        self.ingest()
        release = build(self.root)
        old = (self.root / 'CURRENT').read_text()
        with patch('knicks_history.pipeline.csv_write', side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError):
                build(self.root)
        self.assertEqual((self.root / 'CURRENT').read_text(), old)
        self.assertEqual(release.name, old.strip())

    def test_missing_opponent_is_null(self):
        self.payload['resultSets'][0]['rowSet'].pop(1)
        self.assertIsNone(self.records()[0]['opponent_pts'])

    def test_season_century_boundary(self):
        self.assertEqual(season_label(1999), '1999-00')

    def test_synthetic_label_required(self):
        with self.assertRaises(ValueError):
            archive(self.root, self.raw, '2024-25', 'Regular Season', False, {})

    def test_bad_expected_count_blocks_promotion(self):
        self.ingest()
        release = build(self.root)
        expected = self.root / 'expected.csv'
        expected.write_text('season,season_type,expected_games,source\n2024-25,Regular Season,82,test\n')
        with self.assertRaises(ValueError):
            build(self.root, expected)
        self.assertEqual((self.root / 'CURRENT').read_text().strip(), release.name)

    def test_parquet_round_trip(self):
        try:
            import polars as pl
        except ImportError:
            self.skipTest('Install columnar extra to run Parquet check')
        self.ingest()
        release = build(self.root, parquet=True)
        frame = pl.read_parquet(release / 'team_games.parquet')
        self.assertEqual(frame.height, 2)
        self.assertEqual(frame.schema['game_id'], pl.String)
        self.assertEqual(frame['reb'].null_count(), 1)


if __name__ == '__main__':
    unittest.main()
