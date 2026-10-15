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
        b = brain_after([st(f, mx=300, rx=420, ratk=(5 <= f < 12)) for f in range(0, 15)])
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

    def test_choices_are_varied_and_not_all_guard(self):
        b = brain_after([st(f, mx=400, rx=440) for f in range(0, 100)])
        names = Counter(b.decide()[1].name for _ in range(300))
        self.assertGreater(len(names), 4)
        self.assertLess(names.get("guardia corta", 0), 120)


if __name__ == "__main__":
    unittest.main()


class CalmPressure(unittest.TestCase):
    """pressure_needs_calm: sin presion cercana mientras el rival esta activo."""

    def names(self, calm, rival_attacks):
        profile = {**STRATEGIC, "pressure_needs_calm": calm}
        # rival pegado (d=30); atacando hace poco o pasivo desde hace mucho
        states = [st(f, mx=400, rx=430, ratk=(rival_attacks and f % 40 < 6)) for f in range(0, 400)]
        b = brain_after(states, profile)
        sit, opts = b._options_for(b.state())
        return sit, {o.name for o in opts}

    def test_active_rival_gets_no_pressure(self):
        sit, names = self.names(calm=True, rival_attacks=True)
        self.assertFalse([n for n in names if n.startswith("combo")])

    def test_passive_rival_still_gets_pressure(self):
        sit, names = self.names(calm=True, rival_attacks=False)
        self.assertEqual(sit, "NEUTRAL:PRESSURE")
        self.assertTrue([n for n in names if n.startswith("combo")])

    def test_off_by_default(self):
        sit, names = self.names(calm=False, rival_attacks=True)
        self.assertTrue(sit != "NEUTRAL:PRESSURE" or [n for n in names if n.startswith("combo")])
