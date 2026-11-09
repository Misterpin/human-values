import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Study


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.study = Study(db_path=Path(self.temp.name) / 'answers.sqlite3')

    def tearDown(self):
        self.temp.cleanup()

    def trial(self, mode='rating', **kwargs):
        return self.study.make_trial(dict(participant='TEST', value_id='HV001', mode=mode,
            definition_id='dataset', formulation_id='canonical', criterion='association',
            context_id='unspecified', **kwargs))

    def answer(self, trial, answer, participant='TEST'):
        return self.study.answer(dict(trial_id=trial['id'], participant=participant,
            answer=answer, elapsed_ms=1000, presentation='participant'))

    def test_taxonomy_and_pilot(self):
        catalog = self.study.catalog()
        self.assertEqual(len(catalog['groups']), 7)
        self.assertEqual(len(self.study.values), 100)
        for vid, value in self.study.values.items():
            self.assertEqual(len(self.study.images(value)), 5 if int(vid[2:]) <= 20 else 0)
            self.assertTrue(value['definitions'][0]['text'])

    def test_four_modes_and_export(self):
        for mode in ('rating', 'ranking', 'pair', 'bws'):
            t = self.trial(mode)
            a = {'rating': 4, 'ranking': [i['id'] for i in t['images']], 'pair': 'tie',
                 'bws': {'best': t['options'][0]['id'], 'worst': t['options'][1]['id']} if t['options'] else None}[mode]
            self.answer(t, a)
        rows = self.study.export('TEST')
        self.assertEqual(len(rows), 4)
        self.assertEqual({r['mode'] for r in rows}, {'rating','ranking','pair','bws'})
        self.assertTrue(all(len(i['sha256']) == 64 for r in rows for i in r['images']))

    def test_rejects_invalid_answers_and_participant(self):
        t = self.trial()
        for a in (0, 6, True, '5', None):
            with self.assertRaises(ValueError): self.answer(t, a)
        with self.assertRaises(ValueError): self.answer(t, 3, 'OTHER')
        t = self.trial('ranking')
        with self.assertRaises(ValueError): self.answer(t, [t['images'][0]['id']] * 5)
        t = self.trial('bws')
        with self.assertRaises(ValueError): self.answer(t, {'best':t['options'][0]['id'], 'worst':t['options'][0]['id']})

    def test_empty_value_rejected(self):
        data = dict(participant='TEST',value_id='HV021',mode='rating',definition_id='dataset',
                    formulation_id='canonical',criterion='association',context_id='unspecified')
        with self.assertRaisesRegex(ValueError, 'сейчас 0'): self.study.make_trial(data)

    def test_retries_do_not_duplicate_answers(self):
        t = self.trial()
        a = self.answer(t, 4)
        b = self.answer(t, 4)
        self.assertEqual(a['id'], b['id'])
        self.assertTrue(b['already_saved'])
        with self.assertRaises(ValueError): self.answer(t, 5)
        self.assertEqual(len(self.study.export()), 1)

    def test_rating_and_pair_coverage(self):
        for mode, count in [('rating', 5), ('pair', 10)]:
            seen = set()
            for _ in range(count):
                t = self.trial(mode)
                key = tuple(sorted(i['id'] for i in t['images']))
                self.assertNotIn(key, seen)
                self.assertFalse(t['cycle_complete'])
                seen.add(key)
                self.answer(t, 3 if mode == 'rating' else 'tie')
            self.assertTrue(self.trial(mode)['cycle_complete'])

    def test_snapshot_persists_after_reopening(self):
        t = self.trial()
        self.answer(t, 2)
        reopened = Study(db_path=self.study.db_path)
        row = reopened.export()[0]
        for key in ('definition', 'formulation', 'images', 'config_version', 'context'):
            self.assertEqual(row[key], t[key])

    def test_configured_interpretations(self):
        self.study.values['HV001']['bws_option_sets'] = [{'options': [
            {'id': str(n), 'concept': f'Понятие {n}', 'explanation': f'Объяснение {n}'} for n in range(4)]}]
        t = self.trial('bws')
        self.assertEqual(t['options_source'], 'configured')
        self.assertEqual({o['id'] for o in t['options']}, {'0', '1', '2', '3'})


if __name__ == '__main__':
    unittest.main()
