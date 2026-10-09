"""Notacion de movimientos (kof_ai/motions.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kof_ai.motions import Step, parse  # noqa: E402


class ParseTests(unittest.TestCase):
    def test_existing_notation_unchanged(self):
        self.assertEqual(parse("236A", 2, 3), [Step(2, "", 2), Step(3, "", 2), Step(6, "A", 3), Step(5, "", 1)])
        self.assertEqual(parse("2[40]8A", 2, 3), [Step(2, "", 40), Step(8, "A", 3), Step(5, "", 1)])
        self.assertEqual(parse("4CD", 2, 3)[0], Step(4, "CD", 3))

    def test_held_buttons(self):
        self.assertEqual(parse("6C[4] 5[2] B[1]", 2, 3),
                         [Step(6, "C", 4), Step(5, "", 2), Step(5, "B", 1), Step(5, "", 1)])
