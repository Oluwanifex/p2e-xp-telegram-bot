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


if __name__ == '__main__':
    unittest.main()
