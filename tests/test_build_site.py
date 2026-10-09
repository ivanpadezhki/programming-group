import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))

import build_site as b  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'people'


class HeaderTests(unittest.TestCase):
    def test_plain_block(self):
        h = b.parse_header(['---', 'objectives: [2.1, 2.2]', 'week: 1', '---', 'x = 1'])
        self.assertEqual(b.parse_ids(h['objectives']), ['2.1', '2.2'])
        self.assertEqual(h['week'], '1')

    def test_r_comment_block(self):
        h = b.parse_header(['# ---', '# objectives: [3.1, 3.2]', '# ---', 'x <- 1'])
        self.assertEqual(b.parse_ids(h['objectives']), ['3.1', '3.2'])

    def test_matlab_comment_block(self):
        h = b.parse_header(['% ---', '% objectives: 3.1, 3.2', '% attempted: [3.3]', '% ---'])
        self.assertEqual(b.parse_ids(h['objectives']), ['3.1', '3.2'])
        self.assertEqual(b.parse_ids(h['attempted']), ['3.3'])

    def test_missing_or_unclosed_block(self):
        self.assertIsNone(b.parse_header(['x = 1']))
        self.assertIsNone(b.parse_header(['---', 'objectives: [1.1]']))


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.modules, self.objectives, self.config = b.load_spine()
        self.ids = {o['id'] for o in self.objectives}
        self.warnings = []
        self.people = b.load_people(FIXTURES, self.ids, self.warnings)
        self.by_module = b.compute(self.people, self.modules, self.objectives, self.config)
        self.by_slug = {p['slug']: p for p in self.people}

    def test_counts_do_not_depend_on_language(self):
        ana, ben, carla = (self.by_slug[s] for s in ('ana', 'ben', 'carla'))
        self.assertEqual(ana['modules'][2]['done'], 3)
        self.assertEqual(ben['modules'][2]['done'], 3)
        self.assertEqual(carla['modules'][2]['done'], 3)
        self.assertEqual(ana['modules'][2]['total'], 8)

    def test_status_and_current_module(self):
        ana = self.by_slug['ana']
        self.assertEqual(b.status(ana, '2.1'), 'Done')
        self.assertEqual(b.status(ana, '2.4'), 'Attempted')
        self.assertEqual(b.status(ana, '2.8'), 'Not started')
        self.assertEqual(ana['current'], 2)

    def test_warnings_for_bad_files(self):
        text = ' '.join(m for _, m in self.warnings)
        self.assertIn('unknown objective ID 9.9', text)
        self.assertIn('no header block', text)

    def test_fence_survives_backticks(self):
        out = b.fence('print("```")', 'python')
        self.assertTrue(out.startswith('````python'))


if __name__ == '__main__':
    unittest.main()
