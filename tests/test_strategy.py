"""Pruebas de la ofensiva estrategica (kof_ai/strategy.py) sin el juego."""
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_defense_regression import IORI, Feed, st  # noqa: E402

from kof_ai.brain import RuleBrain  # noqa: E402

STRATEGIC = {**IORI, "combat_mode": "BALANCED_EXPERIMENTAL"}


def brain_after(states, profile=STRATEGIC):
    feed = Feed()
    brain = RuleBrain(feed, profile)
    for s in states:
        feed.s = s
        brain.state()
    return brain


class StrategyTests(unittest.TestCase):
    def test_far_without_threat_approaches(self):
        b = brain_after([st(f, mx=200, rx=450) for f in range(0, 30)])
        self.assertEqual(b._options_for(b.state())[0], "NEUTRAL:APPROACH")

    def test_poke_range(self):
        b = brain_after([st(f, mx=400, rx=500) for f in range(0, 30)])
        self.assertEqual(b._options_for(b.state())[0], "NEUTRAL:POKE")

    def test_close_without_threat_is_pressure_not_guard_only(self):
        b = brain_after([st(f, mx=400, rx=440) for f in range(0, 200)])
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "NEUTRAL:PRESSURE")
        guard = sum(o.weight for o in opts if o.notation.startswith("G["))
        self.assertLess(guard, sum(o.weight for o in opts) * 0.25)

    def test_passivity_raises_useful_actions(self):
        b = brain_after([st(f, mx=400, rx=500) for f in range(0, 30)])
        calm = {o.name: o.weight for o in b._options_for(b.state())[1]}
        b2 = brain_after([st(f, mx=400, rx=500) for f in range(0, 400)])   # ~6 s sin nada util
        bored = {o.name: o.weight for o in b2._options_for(b2.state())[1]}
        self.assertGreater(b2.strategy.passivity_score(b2.state().frame), 5)
        self.assertGreater(bored["poke"], calm["poke"])

    def test_hysteresis_keeps_mode_briefly(self):
        b = brain_after([st(f, mx=200, rx=450) for f in range(0, 30)])      # APPROACH
        b._options_for(b.state())
        feed = b._reader
        feed.s = st(31, mx=400, rx=500)                                     # ahora a distancia de poke
        b.state()
        self.assertEqual(b._options_for(b.state())[0], "NEUTRAL:APPROACH")  # aun no pasaron 20 frames
        for f in range(32, 60):
            feed.s = st(f, mx=400, rx=500)
            b.state()
        self.assertEqual(b._options_for(b.state())[0], "NEUTRAL:POKE")

    def test_whiff_from_far_is_punished(self):
        # el rival ataca a 120 de distancia (nunca se acerca) y termina: golpe fallado
        b = brain_after([st(f, mx=300, rx=420, ratk=(5 <= f < 12)) for f in range(0, 17)])
        self.assertTrue(b.can_punish_now())
        self.assertEqual(b._options_for(b.state())[0], "castigo a golpe fallado")
        # el mismo ataque a 150: fuera de alcance, no se castiga
        far = brain_after([st(f, mx=300, rx=450, ratk=(5 <= f < 12)) for f in range(0, 15)])
        self.assertFalse(far.can_punish_now())

    def test_whiff_punish_needs_strategy(self):
        b = brain_after([st(f, mx=300, rx=420, ratk=(5 <= f < 12)) for f in range(0, 15)],
                        {**IORI, "combat_mode": "DEFENSE_ONLY"})
        self.assertFalse(b.can_punish_now())

    def test_offense_off_keeps_old_neutral(self):
        b = brain_after([st(f, mx=200, rx=450) for f in range(0, 30)], {**IORI, "combat_mode": "DEFENSE_ONLY"})
        self.assertEqual(b._options_for(b.state())[0], "rival lejos")

    def test_corner_neutral_can_pressure_without_retreat(self):
        b = brain_after([st(f, mx=40, rx=80) for f in range(80)])
        situation, options = b._options_for(b.state())
        self.assertEqual(situation, "NEUTRAL:PRESSURE")
        self.assertIn("golpe bajo 2B", [o.name for o in options])
        self.assertNotIn("backdash", [o.name for o in options])
        self.assertFalse(any(o.name.startswith("retroceder") for o in options))

    def test_corner_under_attack_still_defends(self):
        b = brain_after([st(f, mx=40, rx=80, ratk=f >= 30) for f in range(80)])
        situation, options = b._options_for(b.state())
        self.assertEqual(situation, "rival ataca")
        self.assertEqual([o.name for o in options], ["guardia"])

    def test_outside_light_range_approaches_instead_of_combos(self):
        b = brain_after([st(f, mx=400, rx=465) for f in range(80)])
        situation, options = b._options_for(b.state())
        self.assertEqual(situation, "NEUTRAL:APPROACH")
        self.assertFalse(any("combo" in o.name for o in options))

    def test_neutral_pressure_avoids_unconfirmed_long_combos(self):
        b = brain_after([st(f, mx=400, rx=435) for f in range(80)])
        situation, options = b._options_for(b.state())
        self.assertEqual(situation, "NEUTRAL:PRESSURE")
        self.assertTrue(any(o.name == "golpe cercano C" for o in options))
        self.assertFalse(any(">" in o.notation for o in options))
        self.assertFalse(any(o.name.startswith("combo: ") for o in options))

    def test_choices_are_varied_and_not_all_guard(self):
        b = brain_after([st(f, mx=400, rx=440) for f in range(0, 100)])
        names = Counter(b.decide()[1].name for _ in range(300))
        self.assertGreater(len(names), 4)
        self.assertLess(names.get("guardia corta", 0), 120)

    def test_whiff_waits_confirmation_and_never_runs_blindly_into_2b(self):
        early = brain_after([st(f, mx=300, rx=420, ratk=5 <= f < 12) for f in range(15)])
        self.assertFalse(early.can_punish_now())
        b = brain_after([st(f, mx=300, rx=420, ratk=5 <= f < 12) for f in range(17)])
        _, options = b._options_for(b.state())
        self.assertTrue(all(o.interruptible and o.notation == "6[5]" for o in options))

    def test_whiff_in_normal_range_attacks_without_running(self):
        b = brain_after([st(f, mx=300, rx=400, ratk=5 <= f < 12) for f in range(17)])
        situation, options = b._options_for(b.state())
        self.assertEqual(situation, "castigo a golpe fallado")
        self.assertEqual({o.notation for o in options}, {IORI["poke"], "2D"})

    def test_new_attack_cancels_whiff_opportunity(self):
        b = brain_after([st(f, mx=300, rx=400, ratk=5 <= f < 12 or f >= 16) for f in range(18)])
        self.assertFalse(b.can_punish_now())
        self.assertEqual(b._options_for(b.state())[0], "rival ataca")

    def test_punish_combo_only_after_guarded_long_attack_and_in_range(self):
        for distance in (35, 50):
            b = brain_after([st(f, rx=400 + distance, ratk=5 <= f < 40) for f in range(45)])
            self.assertNotEqual(b._options_for(b.state())[0], "castigo seguro")
            b._guarded_attack = True
            situation, options = b._options_for(b.state())
            self.assertEqual(situation, "castigo seguro")
            self.assertEqual(any(o.notation == "C>623C" for o in options), distance == 35)

    def test_hysteresis_cannot_keep_short_attacks_out_of_range(self):
        b = brain_after([st(f, rx=435) for f in range(80)])
        b._options_for(b.state())
        b._reader.s = st(81, rx=500)
        b.state()
        _, options = b._options_for(b.state())
        self.assertFalse(any(o.notation in {"2B", "C", "6C", "6D", "2B>2A"} for o in options))


if __name__ == "__main__":
    unittest.main()
