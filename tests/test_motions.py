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


class CheckpointCombo(unittest.TestCase):
    """'|': punto de control sin pausa para combos grabados al frame."""

    def run_combo(self, notation, hit_at):
        from kof_ai.combo import play_combo

        class Clock:
            frame = 0
            def wait_frames(self, n, should_stop=None):
                for _ in range(n):
                    Clock.frame += 1
                    if should_stop and should_stop():
                        return False
                return True

        class Keys:
            presses = []
            def set_state(self, keys):
                if keys:
                    Keys.presses.append((Clock.frame, tuple(sorted(keys))))
            def release_all(self):
                pass

        life = lambda: 100 - (10 if hit_at is not None and Clock.frame >= hit_at else 0)
        result = play_combo(Keys(), Clock(), notation, True, life, 2, 3)
        return result, Keys.presses

    def test_hit_continues_without_delay(self):
        (connected, damage, done), presses = self.run_combo("6C[3] | 5[2] 6D[2]", hit_at=2)
        self.assertEqual((connected, damage, done), (1, 10, True))   # la parte final no vuelve a pegar aqui
        frames_of_d = [f for f, k in presses if "D" in k]
        self.assertEqual(frames_of_d, [5])      # 3 (C) + 2 (neutro): sin pausa extra

    def test_no_hit_stops_at_checkpoint(self):
        (connected, damage, done), presses = self.run_combo("6C[3] | 5[2] 6D[2]", hit_at=None)
        self.assertEqual(connected, 0)
        self.assertFalse([k for _, k in presses if "D" in k])

    def test_late_hit_within_grace(self):
        _, presses = self.run_combo("6C[3] | 5[2] 6D[2]", hit_at=5)
        self.assertTrue([k for _, k in presses if "D" in k])   # siguio el combo
