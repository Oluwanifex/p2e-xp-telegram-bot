import unittest

from bot import format_status


class BotTests(unittest.TestCase):
    def test_format_status(self):
        text = format_status({
            'xp': 1234, 'level': 3, 'energy': 42, 'maxEnergy': 100, 'food': 7,
            'wood': 1, 'coal': 2, 'stone': 3, 'sand': 4, 'glass': 5,
            'plank': 6, 'earth': 7, 'currentQuestId': 'q1_stone',
            'completedQuests': 0,
        }, True)
        self.assertIn('XP: 1,234', text)
        self.assertIn('Optimizer: running', text)
        self.assertIn('q1_stone', text)

    def test_error_status(self):
        self.assertEqual(format_status({'error': 'boom'}, True), 'Optimizer error: boom')

    def test_progress_fields_are_reported(self):
        text = format_status({
            'xp': 99, 'level': 2, 'energy': 8, 'maxEnergy': 100, 'food': 3,
            'wood': 10, 'coal': 11, 'stone': 12, 'sand': 13, 'glass': 14,
            'plank': 15, 'earth': 16, 'currentQuestId': 'q4_sand',
            'completedQuests': 3,
        }, True)
        self.assertIn('Energy: 8/100', text)
        self.assertIn('Sand 13', text)
        self.assertIn('Quest: q4_sand', text)


if __name__ == '__main__':
    unittest.main()
