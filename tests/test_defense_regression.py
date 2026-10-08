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

from kof_ai.brain import Option, RuleBrain  # noqa: E402
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
        if self.profile.get("combat_mode") != "DEFENSE_ONLY":
            self.skipTest("castigo original solo en DEFENSE_ONLY; ver SafePunish")
        b = self.brain([st(f, ratk=(5 <= f < 40)) for f in range(0, 43)])
        self.assertTrue(b.can_punish_now())
        self.assertEqual(self.situation(b), "castigar")

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
    profile = {**IORI, "combat_mode": "DEFENSE_ONLY"}


class DefenseWithPunish(DefenseRegression, unittest.TestCase):
    profile = {**IORI, "combat_mode": "DEFENSE_WITH_PUNISH"}


class BalancedExperimental(DefenseRegression, unittest.TestCase):
    profile = {**IORI, "combat_mode": "BALANCED_EXPERIMENTAL"}


class SafePunish(unittest.TestCase):
    """DEFENSE_WITH_PUNISH: castigo solo con oportunidad comprobada."""
    profile = {**IORI, "combat_mode": "DEFENSE_WITH_PUNISH", "punish_confirm_frames": 4}

    def run_states(self, states, guarded=True):
        feed = Feed()
        brain = RuleBrain(feed, self.profile)
        for s in states:
            feed.s = s
            brain.state()
            if guarded and s.rival.attacking:   # el bot estaba en guardia durante el ataque
                brain._last_choice = Option(1, "guardia", "G[12]")
        return brain

    def situation(self, brain):
        return brain._options_for(brain.state())[0]

    def test_waits_confirmation_then_short_hit(self):
        b = self.run_states([st(f, ratk=(5 <= f < 40)) for f in range(0, 42)])   # 2 f despues: aun no
        self.assertFalse(b.can_punish_now())
        self.assertEqual(self.situation(b), "presion del rival")
        b = self.run_states([st(f, ratk=(5 <= f < 40)) for f in range(0, 45)])   # 5 f despues: si
        self.assertTrue(b.can_punish_now())
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "castigo seguro")
        self.assertTrue(all(o.notation in ("2B", "C") for o in opts))      # golpe corto, sin combos

    def test_no_punish_while_rival_still_attacking(self):
        # Ataque largo con el bit encendido (recuperacion o varias partes): seguir cubierto.
        b = self.run_states([st(f, ratk=(f >= 5)) for f in range(0, 45)])
        self.assertFalse(b.can_punish_now())
        self.assertEqual(self.situation(b), "presion del rival")

    def test_no_punish_if_rival_restarts(self):
        # Termina en 40 y vuelve a atacar en 43 (cadena): no castigar.
        b = self.run_states([st(f, ratk=(5 <= f < 40 or f >= 43)) for f in range(0, 46)])
        self.assertFalse(b.can_punish_now())
        self.assertIn(self.situation(b), {"rival ataca", "presion del rival"})

    def test_no_punish_without_guard_or_if_hit(self):
        b = self.run_states([st(f, ratk=(5 <= f < 40)) for f in range(0, 45)], guarded=False)
        self.assertFalse(b.can_punish_now())
        b = self.run_states([st(f, ratk=(5 <= f < 40), ml=102 if f < 20 else 95) for f in range(0, 45)])
        self.assertFalse(b.can_punish_now())

    def test_short_attack_not_punished(self):
        b = self.run_states([st(f, ratk=(5 <= f < 12)) for f in range(0, 20)])
        self.assertFalse(b.can_punish_now())

    def test_out_of_short_range_not_punished(self):
        b = self.run_states([st(f, rx=470, ratk=(5 <= f < 40)) for f in range(0, 45)])   # d=70
        self.assertFalse(b.can_punish_now())

    def test_no_strategic_neutral(self):
        b = self.run_states([st(f, mx=200, rx=450) for f in range(0, 30)])
        self.assertEqual(self.situation(b), "rival lejos")


class ArbiterPriority(unittest.TestCase):
    def test_defense_wins_hard_threat(self):
        from kof_ai.arbiter import CombatActionArbiter, Proposal
        a = CombatActionArbiter("BALANCED_EXPERIMENTAL")
        d = Proposal("rival ataca", ["guardia"])
        self.assertEqual(a.select(d, Proposal("castigo seguro", ["2B"]), Proposal("NEUTRAL:POKE", ["poke"]))[0],
                         "rival ataca")

    def test_punish_beats_pressure_and_attack_only_in_neutral(self):
        from kof_ai.arbiter import CombatActionArbiter, Proposal
        a = CombatActionArbiter("BALANCED_EXPERIMENTAL")
        self.assertEqual(a.select(Proposal("presion del rival", []), Proposal("castigo seguro", []))[0],
                         "castigo seguro")
        self.assertEqual(a.select(Proposal("presion del rival", []), None, Proposal("NEUTRAL:POKE", []))[0],
                         "presion del rival")
        self.assertEqual(a.select(Proposal("media distancia", []), None, Proposal("NEUTRAL:POKE", []))[0],
                         "NEUTRAL:POKE")

    def test_defense_only_ignores_offense(self):
        from kof_ai.arbiter import CombatActionArbiter, Proposal
        a = CombatActionArbiter("DEFENSE_ONLY")
        self.assertEqual(a.select(Proposal("media distancia", []), Proposal("castigo seguro", []),
                                  Proposal("NEUTRAL:POKE", []))[0], "media distancia")


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


class PreventiveGuardDefense(DefenseRegression, unittest.TestCase):
    """Con guardia preventiva, la defensa ante amenazas tiene que seguir igual."""
    profile = {**IORI, "combat_mode": "DEFENSE_ONLY", "preventive_guard": True}


class PreventiveGuard(unittest.TestCase):
    def brain(self, states, preventive=True):
        feed = Feed()
        brain = RuleBrain(feed, {**IORI, "combat_mode": "DEFENSE_ONLY", "preventive_guard": preventive})
        for s in states:
            feed.s = s
            brain.state()
        return brain

    def test_close_without_threat_has_no_long_actions(self):
        b = self.brain([st(f, mx=400, rx=430) for f in range(0, 80)])   # d=30, sin amenaza
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "pegado al rival")
        names = [o.name for o in opts]
        self.assertFalse([n for n in names if n.startswith(("combo", "salto", "hop", "roll", "overhead", "reversal"))])
        self.assertIn("guardia", names)

    def test_off_keeps_original_options(self):
        b = self.brain([st(f, mx=400, rx=430) for f in range(0, 80)], preventive=False)
        names = [o.name for o in b._options_for(b.state())[1]]
        self.assertTrue([n for n in names if n.startswith("combo")])

    def test_waiting_for_airborne_rival_becomes_guard(self):
        heights = [0] * 70 + [20, 40, 60, 80]          # subiendo: aun no "cae hacia mi"
        b = self.brain([st(f, rh=h) for f, h in enumerate(heights)])
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "rival en el aire, esperando")
        self.assertNotIn("esperar", [o.name for o in opts])
        self.assertTrue(all(not o.notation.startswith("5[") for o in opts))

    def test_punish_keeps_combos(self):
        b = self.brain([st(f, ratk=(5 <= f < 40)) for f in range(0, 43)])
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "castigar")
        self.assertTrue([o for o in opts if o.name.startswith("castigo")])
