"""Pruebas de regresion de la defensa (sin el juego): el sistema defensivo debe
seguir teniendo prioridad ante amenazas reales, con o sin la ofensiva estrategica.

Uso: python -m unittest discover tests
"""
import json
from dataclasses import replace
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

    def test_chip_damage_with_guard_is_a_block(self):
        path = tempfile.mktemp(suffix=".csv")
        log = DefenseLogger(path, lambda: ("rival ataca", "guardia", 1))
        # rival a la derecha: atras = left. Ataque largo; pierde 1 de vida con guardia (raspado)
        for f in range(0, 60):
            log.observe(st(f, ml=102 if f < 15 else 101, ratk=(5 <= f < 30)), {"left"})
        # otro ataque: pierde 1 SIN guardia -> golpe
        for f in range(60, 120):
            log.observe(st(f, ml=101 if f < 75 else 100, ratk=(65 <= f < 90)), set())
        log.close()
        self.assertEqual(log.chip_blocks, 1)
        self.assertEqual(log.threats[("de pie/overhead", "evitado")], 1)
        self.assertEqual(log.threats[("de pie/overhead", "golpeado")], 1)
        self.assertEqual(log.taken, 2)

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


class ChipDamageInBrain(unittest.TestCase):
    """Perder 1 punto con guardia puesta es raspado (bloqueo), no un golpe."""

    def run_states(self, keys):
        feed = Feed()
        brain = RuleBrain(feed, {**IORI, "combat_mode": "DEFENSE_ONLY"})
        brain.held_keys = lambda: keys
        for f in range(0, 30):
            feed.s = st(f, ml=102 if f < 20 else 101, ratk=(10 <= f < 25))
            brain.state()
        return brain

    def test_chip_while_guarding_is_not_a_hit(self):
        b = self.run_states({"left"})            # rival a la derecha: atras = left
        self.assertEqual(b.chip_total, 1)
        self.assertEqual(b.taken_total, 0)
        self.assertFalse(b._recently_hit(b.state()))

    def test_same_damage_without_guard_is_a_hit(self):
        b = self.run_states(set())
        self.assertEqual(b.taken_total, 1)
        self.assertTrue(b._recently_hit(b.state()))

    def test_holding_forward_is_not_guard(self):
        b = self.run_states({"right"})
        self.assertEqual(b.taken_total, 1)


class PreventiveGuardHeight(unittest.TestCase):
    """Guardia preventiva: agachada sin ataque (no camina hacia atras), de pie ante saltos
    y ataques de pie, agachada ante ataques agachados."""

    def brain(self, states, preventive=True):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "DEFENSE_ONLY", "preventive_guard": preventive})
        for s in states:
            feed.s = s
            b.state()
        return b

    def test_idle_rival_crouch_guard(self):
        self.assertTrue(self.brain([st(f) for f in range(10)]).guard_low())

    def test_standing_attack_stand_guard(self):
        self.assertFalse(self.brain([st(f, ratk=(f >= 5)) for f in range(10)]).guard_low())

    def test_crouching_attack_low_guard(self):
        self.assertTrue(self.brain([st(f, rcr=(f >= 3), ratk=(f >= 5)) for f in range(10)]).guard_low())

    def test_airborne_stand_guard(self):
        self.assertFalse(self.brain([st(f, rh=(30 if f >= 5 else 0)) for f in range(10)]).guard_low())

    def test_original_unchanged(self):
        self.assertFalse(self.brain([st(f) for f in range(10)], preventive=False).guard_low())


class ComboRearm(unittest.TestCase):
    """combo_rearm_frames: no empezar un combo si el rival recibio un golpe hace poco."""

    def brain(self, rearm, hit_frame):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "DEFENSE_ONLY", "preventive_guard": False,
                             "combo_rearm_frames": rearm})
        for f in range(0, 200):
            feed.s = st(f, mx=400, rx=430, rl=102 if f < hit_frame else 90)
            b.state()
        return b

    def names(self, b):
        return [o.name for o in b._options_for(b.state())[1]]

    def test_recent_hit_waits(self):
        names = self.names(self.brain(120, hit_frame=150))      # golpe hace 50 frames
        self.assertFalse([n for n in names if n.startswith("combo")])
        self.assertIn("esperar que el rival se levante", names)

    def test_old_hit_allows_combos(self):
        names = self.names(self.brain(120, hit_frame=50))       # golpe hace 150 frames
        self.assertTrue([n for n in names if n.startswith("combo")])

    def test_default_off(self):
        names = self.names(self.brain(0, hit_frame=190))
        self.assertTrue([n for n in names if n.startswith("combo")])


class PrematurePunish(unittest.TestCase):
    """Auditoria externa, hallazgo 1: con el rival TODAVIA atacando (bit de ataque encendido
    mas de BLOCK_FRAMES) la IA elegia 'castigar'. El bit de ataque cubre toda la animacion
    (golpe activo y recuperacion): no es una senal de vulnerabilidad."""

    def brain(self, **extra):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "DEFENSE_ONLY", **extra})
        for f in range(0, 46):
            feed.s = st(f, ratk=(f >= 5))       # el rival ataca desde el frame 5 y sigue atacando
            b.state()
        return b

    def test_no_punish_while_rival_still_attacking(self):
        b = self.brain()
        self.assertFalse(b.can_punish_now())
        self.assertNotEqual(b._options_for(b.state())[0], "castigar")

    def test_legacy_reproduces_the_bug(self):
        b = self.brain(legacy_punish=True)      # comportamiento anterior, solo para comparar
        self.assertTrue(b.can_punish_now())
        self.assertEqual(b._options_for(b.state())[0], "castigar")


class SafeDefenseUnderThreat(unittest.TestCase):
    """Auditoria externa, hallazgo 2: con amenaza activa la defensa elegia al azar reversals,
    rodadas o backdash. Ahora solo guardia; los escapes quedan fuera hasta tener condiciones
    comprobables (legacy_escapes los reproduce para comparar)."""

    def options(self, states, **extra):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "DEFENSE_ONLY", **extra})
        for s in states:
            feed.s = s
            b.state()
        return b._options_for(b.state())

    CASES = {
        "rival ataca": [st(f, ratk=(f >= 10)) for f in range(0, 14)],
        "presion del rival": [st(f, ratk=(5 <= f < 15)) for f in range(0, 21)],
        "me golpearon": [st(f, ml=102 if f < 5 else 90) for f in range(0, 8)],
        "rival cae hacia mi": [st(f, rh=h) for f, h in enumerate([0] * 5 + [60, 70, 65, 55, 45])],
        "rival ataca desde el aire": [st(f, rh=40, ratk=(f >= 4)) for f in range(0, 8)],
    }

    def test_only_guard_under_threat(self):
        for expected, states in self.CASES.items():
            sit, opts = self.options(states)
            self.assertEqual(sit, expected)
            self.assertEqual({o.name for o in opts}, {"guardia"}, f"{sit}: {[o.name for o in opts]}")

    def test_legacy_restores_escapes(self):
        sit, opts = self.options(self.CASES["rival ataca"], legacy_escapes=True)
        self.assertIn("reversal", [o.name for o in opts])


class CornerEscape(unittest.TestCase):
    """corner_escape: solo en un hueco de la presion, acorralado, sin bloquear ni estar golpeado."""

    def brain(self, states, **extra):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "DEFENSE_ONLY", "corner_escape": "roll", **extra})
        for s in states:
            feed.s = s
            b.state()
        return b

    def options(self, b):
        return b._options_for(b.state())

    def cornered(self, f, **kw):
        return st(f, mx=40, rx=90, **kw)       # Iori pegado a la pared izquierda, rival a 50

    def test_escapes_in_the_gap(self):
        # el rival ataco (frames 5-15) y ahora esta quieto: hueco de la presion
        b = self.brain([self.cornered(f, ratk=(5 <= f < 15)) for f in range(0, 20)])
        sit, opts = self.options(b)
        self.assertEqual(sit, "salida de esquina")
        self.assertEqual(opts[0].notation, "AB")

    def test_not_while_rival_attacks(self):
        b = self.brain([self.cornered(f, ratk=(f >= 5)) for f in range(0, 12)])
        self.assertNotEqual(self.options(b)[0], "salida de esquina")

    def test_not_in_open_field(self):
        b = self.brain([st(f, mx=400, rx=450, ratk=(5 <= f < 15)) for f in range(0, 20)])
        self.assertNotEqual(self.options(b)[0], "salida de esquina")

    def test_not_while_blocking(self):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "DEFENSE_ONLY", "corner_escape": "roll"})
        for f in range(0, 20):
            s = self.cornered(f, ratk=(5 <= f < 15))
            feed.s = replace(s, me=replace(s.me, state_id=30))      # bloqueando (27-37)
            b.state()
        self.assertNotEqual(self.options(b)[0], "salida de esquina")

    def test_cooldown_and_off_by_default(self):
        b = self.brain([self.cornered(f, ratk=(5 <= f < 15)) for f in range(0, 20)])
        self.options(b)                          # usa la salida
        self.assertNotEqual(self.options(b)[0], "salida de esquina")   # enfriamiento
        off = self.brain([self.cornered(f, ratk=(5 <= f < 15)) for f in range(0, 20)], corner_escape="none")
        self.assertNotEqual(self.options(off)[0], "salida de esquina")


class MoveTable(unittest.TestCase):
    def test_move_rows(self):
        path = tempfile.mktemp(suffix=".csv")
        log = DefenseLogger(path, lambda: ("rival ataca", "guardia", 1))
        seq = []
        for f in range(0, 40):               # movimiento 89 de 20 frames, sin pegar
            s = st(f, ratk=(5 <= f < 25))
            if 5 <= f < 25:
                s = replace(s, rival=replace(s.rival, state_id=89))
            seq.append(s)
        for s in seq:
            log.observe(s, {"left"})
        log.close()
        rows = [r.split(",") for r in Path(path).read_text(encoding="utf-8").splitlines() if ",movimiento," in r]
        self.assertEqual(len(rows), 1)
        self.assertIn("estado 89 dura 20 f", ",".join(rows[0]))


class GuardCancel(unittest.TestCase):
    """guard_cancel: solo bloqueando, con barra, tras N bloqueos recientes y con enfriamiento."""

    def feed(self, frames_blocking, stocks=3, **extra):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "DEFENSE_ONLY", "guard_cancel": "roll_b", **extra})
        for f in range(0, 60):
            s = st(f, mx=400, rx=440, ratk=(f % 20 < 8))
            blocking = f in frames_blocking
            feed.s = replace(s, me=replace(s.me, state_id=30 if blocking else 23, stocks=stocks))
            b.state()
        return b

    def test_second_block_triggers(self):
        b = self.feed(set(range(10, 16)) | set(range(50, 60)))     # dos bloqueos; el segundo en curso
        self.assertTrue(b.guard_cancel_ready())
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "cancelar guardia")
        self.assertEqual(opts[0].notation, "4AB")

    def test_single_block_does_not(self):
        b = self.feed(set(range(50, 59)))                           # un solo bloqueo, en curso
        self.assertFalse(b.guard_cancel_ready())

    def test_needs_a_stock(self):
        b = self.feed(set(range(10, 16)) | set(range(30, 36)) | set(range(50, 59)), stocks=0)
        self.assertFalse(b.guard_cancel_ready())

    def test_off_by_default(self):
        b = self.feed(set(range(10, 16)) | set(range(30, 36)) | set(range(50, 59)), guard_cancel="none")
        self.assertFalse(b.guard_cancel_ready())


class GuardCancelChain(unittest.TestCase):
    """Medido en FBNeo: bajo una cadena el bloqueo es continuo (estados 27-37 sin salir)."""

    def test_chained_blocks_count(self):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "DEFENSE_ONLY", "guard_cancel": "roll_b"})
        # Iori en bloqueo continuo desde el frame 10; el rival ataca en 10-18 y otra vez en 28-36
        for f in range(0, 40):
            s = st(f, mx=400, rx=440, ratk=(10 <= f < 18 or 28 <= f < 36))
            blocking = f >= 12
            feed.s = replace(s, me=replace(s.me, state_id=(27 + f % 5) if blocking else 23, stocks=3))
            b.state()
        self.assertTrue(b.guard_cancel_ready())


class NeverBlowback(unittest.TestCase):
    """Regla del usuario: nada de C+D (empuje) al bloquear, ni por configuracion."""

    def test_atk_variants_are_not_available(self):
        for mode in ("atk", "atk_d"):
            feed = Feed()
            b = RuleBrain(feed, {**IORI, "combat_mode": "DEFENSE_ONLY", "guard_cancel": mode})
            for f in range(0, 40):
                s = st(f, mx=400, rx=440, ratk=(10 <= f < 18 or 28 <= f < 36))
                feed.s = replace(s, me=replace(s.me, state_id=(27 + f % 5) if f >= 12 else 23, stocks=3))
                b.state()
            self.assertIsNone(b._guard_cancel_option(b.state()))
        from kof_ai import brain
        self.assertFalse([m for m in brain.GUARD_CANCEL_MOVES.values() if "CD" in m])


class ThrowEscape(unittest.TestCase):
    """Soltar agarres: atras + el boton del agarre, tras una espera, mantenido (medido con una
    persona el 2026-10-15: ni C+D ni el boton al instante sueltan)."""

    def thrown_by(self, rival_state, **overrides):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, **overrides})
        for f in range(0, 10):
            s = st(f, mx=400, rx=430)
            feed.s = replace(s, me=replace(s.me, state_id=168 if f >= 6 else 0),
                             rival=replace(s.rival, state_id=rival_state if f >= 6 else 1))
            b.state()
        return b, b._options_for(b.state())

    def test_profile_is_matching_with_back_and_delay(self):
        b, (situation, options) = self.thrown_by(229)
        self.assertEqual(situation, "me agarran")
        self.assertEqual(options[0].notation, "5[6]4C[5]")
        b, (_, options) = self.thrown_by(232)
        self.assertEqual(options[0].notation, "5[6]4D[5]")

    def test_delay_and_hold_come_from_profile(self):
        _, (_, options) = self.thrown_by(232, throw_escape_delay=0, throw_escape_hold=3)
        self.assertEqual(options[0].notation, "4D[3]")

    def test_never_blowback(self):
        for rival_state in (229, 230, 231, 232):
            _, (_, options) = self.thrown_by(rival_state)
            self.assertNotIn("CD", options[0].notation)

    def test_rival_throw_state_triggers_escape_even_if_my_state_is_unknown(self):
        # Pelea 2026-10-15: agarrado en guardia agachada, mi estado nunca fue 168
        feed = Feed()
        b = RuleBrain(feed, IORI)
        for f in range(0, 10):
            s = st(f, mx=400, rx=430)
            feed.s = replace(s, me=replace(s.me, state_id=23), rival=replace(s.rival, state_id=232 if f >= 6 else 1))
            b.state()
        self.assertTrue(b.being_thrown())
        situation, options = b._options_for(b.state())
        self.assertEqual(situation, "me agarran")
        self.assertEqual(options[0].notation, "5[6]4D[5]")


class GuardHeightByRivalMove(unittest.TestCase):
    """Kim 137 (Haki Kyaku, abajo-abajo+D) es bajo aunque Kim este de pie y atacando: guardia abajo."""

    def guard_low_with(self, rival_state, rival_char=6):
        feed = Feed()
        b = RuleBrain(feed, IORI)
        for f in range(0, 12):
            s = st(f, mx=400, rx=460, ratk=(f >= 4))
            feed.s = replace(s, rival=replace(s.rival, state_id=rival_state if f >= 6 else 98, character_id=rival_char))
            b.state()
        return b.guard_low()

    def test_haki_kyaku_is_blocked_low(self):
        self.assertTrue(self.guard_low_with(137))

    def test_standing_c_is_blocked_high(self):
        self.assertFalse(self.guard_low_with(98))

    def test_other_character_same_state_id_is_not_assumed_low(self):
        self.assertFalse(self.guard_low_with(137, rival_char=0))   # Kyo: 137 no esta medido
