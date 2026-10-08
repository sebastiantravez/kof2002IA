"""Pruebas de regresion de la defensa (sin el juego): el sistema defensivo debe
seguir teniendo prioridad ante amenazas reales, con o sin la ofensiva estrategica.

Uso: python -m unittest discover tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kof_ai.brain import RuleBrain  # noqa: E402
from kof_ai.defense_log import DefenseLogger  # noqa: E402
from kof_ai.game_state import Fighter, GameState  # noqa: E402

IORI = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["characters"]["Iori"]
THREAT_SITUATIONS = {"rival ataca", "presion del rival", "rival cae hacia mi", "rival ataca desde el aire",
                     "me golpearon", "castigar"}


class Feed:
    live = True

    def __init__(self):
        self.s = None

    def read(self):
        return self.s


def st(f, mx=400, rx=440, ml=102, rl=102, ratk=False, rcr=False, rh=0, mh=0):
    return GameState(f, Fighter(mx, 100, 220, mh, ml),
                     Fighter(rx, 140, 220, rh, rl, attacking=ratk, crouching=rcr))


class DefenseRegression:
    """Mismas pruebas para la configuracion defensiva y para la ofensiva estrategica."""
    profile = IORI

    def brain(self, states, **overrides):
        feed = Feed()
        brain = RuleBrain(feed, {**self.profile, **overrides})
        for s in states:
            feed.s = s
            brain.state()
        return brain

    def situation(self, brain):
        return brain._options_for(brain.state())[0]

    def test_rival_attacking_close_is_defended(self):
        b = self.brain([st(f, ratk=(f >= 10)) for f in range(0, 14)])
        self.assertEqual(self.situation(b), "rival ataca")

    def test_pressure_keeps_guard_after_short_attack(self):
        b = self.brain([st(f, ratk=(5 <= f < 15)) for f in range(0, 21)])
        self.assertEqual(self.situation(b), "presion del rival")

    def test_short_attack_not_punished(self):
        b = self.brain([st(f, ratk=(5 <= f < 12)) for f in range(0, 15)])
        self.assertFalse(b.can_punish_now())

    def test_long_attack_is_punished(self):
        b = self.brain([st(f, ratk=(5 <= f < 40)) for f in range(0, 43)])
        self.assertTrue(b.can_punish_now())
        self.assertIn(self.situation(b), {"castigar", "castigo tras bloqueo", "castigo a golpe fallado"})

    def test_jump_in_triggers_anti_air_situation(self):
        heights = [0] * 5 + [60, 70, 65, 55, 45]
        b = self.brain([st(f, rh=h) for f, h in enumerate(heights)])
        self.assertEqual(self.situation(b), "rival cae hacia mi")

    def test_recently_hit_is_recovery(self):
        b = self.brain([st(f, ml=102 if f < 5 else 90) for f in range(0, 8)])
        self.assertEqual(self.situation(b), "me golpearon")

    def test_corner_never_retreats_into_wall(self):
        b = self.brain([st(f, mx=40, rx=90) for f in range(0, 80)])
        names = [o.name for o in b._options_for(b.state())[1]]
        self.assertNotIn("backdash", names)
        self.assertNotIn("retroceder", names)

    def test_threat_beats_any_neutral_logic(self):
        """Con amenaza real nunca se elige una situacion de neutral."""
        b = self.brain([st(f, ratk=(f >= 30)) for f in range(0, 33)])
        self.assertIn(self.situation(b), THREAT_SITUATIONS)

    def test_reaction_delay(self):
        b = self.brain([st(f, ratk=(f >= 50)) for f in range(0, 56)], reaction_frames=10)
        self.assertFalse(b.state().rival.attacking)


class DefensiveOnly(DefenseRegression, unittest.TestCase):
    profile = {**IORI, "offense": "off"}


class StrategicOffense(DefenseRegression, unittest.TestCase):
    profile = {**IORI, "offense": "strategic"}


class DefenseLoggerRegression(unittest.TestCase):
    def test_classification(self):
        path = tempfile.mktemp(suffix=".csv")
        log = DefenseLogger(path, lambda: ("rival ataca", "guardia"))
        seq = [(st(f, rcr=(f < 10), ratk=(10 <= f < 25), ml=102 if f < 15 else 95), {"left"}) for f in range(30)]
        seq += [(st(f, ml=95, ratk=(40 <= f < 55), rh=(30 if 35 <= f < 60 else 0)), {"left"})
                for f in range(30, 90)]
        for s, k in seq:
            log.observe(s, k)
        log.close()
        self.assertEqual(log.threats[("bajo", "golpeado")], 1)
        self.assertEqual(log.threats[("aereo", "evitado")], 1)
        self.assertEqual(log.reasons["guardia alta contra ataque bajo"], 1)

    def test_offense_metrics(self):
        path = tempfile.mktemp(suffix=".csv")
        info = {"v": ("NEUTRAL:POKE", "poke", 1)}
        log = DefenseLogger(path, lambda: info["v"])
        for f in range(0, 30):                       # poke que no hace danio -> fallido
            log.observe(st(f, mx=400, rx=500), {"right", "C"} if f < 5 else set())
        info["v"] = ("NEUTRAL:PRESSURE", "golpe bajo 2B", 2)
        for f in range(30, 100):                     # 2B que hace danio
            log.observe(st(f, rl=102 if f < 40 else 95), set())
        info["v"] = ("rival ataca", "guardia", 3)
        for f in range(100, 200):                    # ataque rival evitado y luego danio nuestro
            log.observe(st(f, rl=95 if f < 170 else 90, ratk=(110 <= f < 120)), {"left"})
        log.close()
        m = log.metrics()
        self.assertEqual(log.attacks["fallidos"], 1)
        self.assertEqual(log.attacks["con danio"], 1)
        self.assertEqual(m["danio_hecho"], 12)
        self.assertEqual(log.counters["defensas"], 1)
        self.assertEqual(log.counters["con danio"], 1)
        self.assertGreater(m["quieto_pct"], 50)
        self.assertIn("POKE", m["tiempo_por_estado_pct"])
        self.assertIn("DEFEND", m["tiempo_por_estado_pct"])


if __name__ == "__main__":
    unittest.main()
