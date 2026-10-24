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
        # golpe corto o combo CON confirmacion ('>'): nunca una parte larga sin confirmar
        for o in opts:
            self.assertTrue(o.notation == "2B" or o.notation.startswith("C>"), o.notation)

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


class ConfirmedPunishCombos(unittest.TestCase):
    """Castigo seguro de cerca = combo corto con confirmacion (C>623C): seguro si lo bloquean."""

    def test_close_safe_punish_offers_confirmed_combo(self):
        from kof_ai.combo import is_combo
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "BALANCED_EXPERIMENTAL"})   # el modo de las peleas
        for f in range(0, 45):
            feed.s = st(f, mx=400, rx=430, ratk=(5 <= f < 40))
            b.state()
            if 5 <= f < 40:
                b._last_choice = Option(1, "guardia", "G[12]")
        self.assertTrue(b.can_punish_now())
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "castigo seguro")
        names = {o.name: o.notation for o in opts}
        self.assertEqual(names["castigo seguro: C Oniyaki"], "C>623C")
        self.assertTrue(is_combo(names["castigo seguro: C Oniyaki"]))
        self.assertNotIn("castigo seguro: C", names)      # el C suelto ya no se propone

    def test_whiff_punish_never_runs_in(self):
        from kof_ai.brain import RuleBrain as RB
        feed = Feed()
        b = RB(feed, {**IORI, "combat_mode": "BALANCED_EXPERIMENTAL"})
        for f in range(0, 15):
            feed.s = st(f, mx=300, rx=420, ratk=(5 <= f < 12))
            b.state()
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "castigo a golpe fallado")
        self.assertFalse([o for o in opts if "correr" in o.name])


class NoWalkingIntoTheCorner(unittest.TestCase):
    """Pelea 2026-10-15: acorralado el 58% del tiempo. Con el rival en el aire alto o lejos la guardia
    es agachada (no camina atras) y cerca de la pared no se propone 'retroceder un paso'."""

    def brain(self, states):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "BALANCED_EXPERIMENTAL"})
        for s in states:
            feed.s = s
            b.state()
        return b

    def test_rival_high_in_the_air_guards_crouching(self):
        b = self.brain([st(f, mx=400, rx=460, rh=90) for f in range(0, 10)])
        self.assertTrue(b.guard_low())

    def test_rival_descending_close_guards_standing(self):
        b = self.brain([st(f, mx=400, rx=440, rh=40) for f in range(0, 10)])
        self.assertFalse(b.guard_low())

    def test_no_step_back_near_the_wall(self):
        # pared izquierda en x=32: Iori a 90 de ella mirando a la derecha
        near = self.brain([st(f, mx=120, rx=250, rh=90) for f in range(0, 10)])
        sit, opts = near._options_for(near.state())
        self.assertEqual(sit, "rival en el aire, esperando")
        self.assertFalse([o for o in opts if o.name == "retroceder un paso"])
        far = self.brain([st(f, mx=400, rx=530, rh=90) for f in range(0, 10)])
        _, opts = far._options_for(far.state())
        self.assertTrue([o for o in opts if o.name == "retroceder un paso"])

    def test_profile_rolls_out_of_the_corner(self):
        self.assertIn(IORI.get("corner_escape"), ("roll", "mix"))


class KnockedDown(unittest.TestCase):
    """Derribado (72/73/78): solo levantarse cubierto; ni rodadas, ni castigos, ni ataque."""

    def brain(self, my_state, mode="BALANCED_EXPERIMENTAL", **extra):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": mode, **extra})
        for f in range(0, 50):
            s = st(f, mx=60, rx=100, ratk=(5 <= f < 40))     # acorralado a la izquierda, presion y hueco
            feed.s = replace(s, me=replace(s.me, state_id=my_state if f >= 20 else 0))
            b.state()
            if 5 <= f < 40:
                b._last_choice = Option(1, "guardia", "G[12]")
        return b

    def test_down_means_guarded_wakeup_only(self):
        for state_id in (72, 73, 78):
            b = self.brain(state_id)
            sit, opts = b._options_for(b.state())
            self.assertEqual(sit, "derribado", state_id)
            self.assertEqual([o.notation for o in opts], ["G[6]"])
            self.assertFalse(b.can_punish_now())

    def test_no_corner_roll_while_down(self):
        b = self.brain(72, corner_escape="roll")
        self.assertIsNone(b._corner_option(b.state()))

    def test_standing_in_the_same_spot_still_escapes(self):
        b = self.brain(0, mode="GUARD_ONLY_TEST", corner_escape="roll")
        sit, _ = b._options_for(b.state())
        self.assertEqual(sit, "salida de esquina")


class MeasuredRanges(unittest.TestCase):
    """Castigo seguro a 31-45: C>623C si, 2B no (el 2B de Iori no llega mas alla de ~30)."""

    def punish_at(self, rx):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "BALANCED_EXPERIMENTAL"})
        for f in range(0, 45):
            feed.s = st(f, mx=400, rx=rx, ratk=(5 <= f < 40))
            b.state()
            if 5 <= f < 40:
                b._last_choice = Option(1, "guardia", "G[12]")
        self.assertTrue(b.can_punish_now())
        return {o.name for o in b._options_for(b.state())[1]}

    def test_mid_close_uses_confirmed_c_not_2b(self):
        names = self.punish_at(438)      # d = 38
        self.assertIn("castigo seguro: C Oniyaki", names)
        self.assertNotIn("castigo seguro: 2B", names)

    def test_point_blank_offers_2b_too(self):
        self.assertIn("castigo seguro: 2B", self.punish_at(425))   # d = 25


class CrossupAndAirGuard(unittest.TestCase):
    def brain(self, states):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "BALANCED_EXPERIMENTAL"})
        for s in states:
            feed.s = s
            b.state()
        return b

    def test_air_attack_is_blocked_standing_at_any_height(self):
        b = self.brain([st(f, mx=400, rx=440, rh=82, ratk=(f >= 8)) for f in range(0, 10)])
        self.assertFalse(b.guard_low())

    def test_air_without_attack_high_stays_crouched(self):
        b = self.brain([st(f, mx=400, rx=440, rh=82) for f in range(0, 10)])
        self.assertTrue(b.guard_low())

    def test_crossup_blocks_towards_landing_side(self):
        # Kim viene por el aire desde la derecha, pegada, moviendose a la izquierda: va a caer detras
        b = self.brain([st(f, mx=400, rx=430 - 6 * f, rh=40) for f in range(0, 4)])   # rx: 430..412
        self.assertTrue(b.state().facing_right)            # por posicion aun esta a la derecha
        self.assertFalse(b.guard_facing_right())           # pero se cubre hacia la izquierda (donde cae)

    def test_no_crossup_prediction_when_far(self):
        b = self.brain([st(f, mx=400, rx=480 - 6 * f, rh=40) for f in range(0, 4)])
        self.assertTrue(b.guard_facing_right())

    def test_houou_kyaku_slide_is_blocked_low(self):
        feed = Feed()
        b = RuleBrain(feed, IORI)
        for f in range(0, 12):
            s = st(f, mx=400, rx=460, ratk=(f >= 4))
            feed.s = replace(s, rival=replace(s.rival, state_id=146 if f >= 6 else 144, character_id=6))
            b.state()
        self.assertTrue(b.guard_low())


class CornerOverhead(unittest.TestCase):
    """Acorralado y el rival cae encima (d <= 20): anti-aire 623A, porque cubrir no vale ahi."""

    def brain(self, mx, rx, heights):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "BALANCED_EXPERIMENTAL"})
        for f, h in enumerate(heights):
            feed.s = st(f, mx=mx, rx=rx, rh=h, ratk=(h > 0))
            b.state()
        return b

    def test_corner_overhead_uses_anti_air(self):
        b = self.brain(40, 42, [100, 95, 90, 83, 73])       # pared izquierda en 32; Kim cae encima
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "rival encima (esquina)")
        self.assertEqual({o.name for o in opts}, {"anti-aire en la esquina", "guardia"})
        self.assertEqual(max(opts, key=lambda o: o.weight).name, "guardia")     # medido: cubrir gana ahi

    def test_open_field_overhead_stays_guarded(self):
        b = self.brain(400, 402, [100, 95, 90, 83, 73])
        sit, _ = b._options_for(b.state())
        self.assertNotEqual(sit, "rival encima (esquina)")

    def test_corner_but_rival_far_is_not_overhead(self):
        b = self.brain(40, 100, [100, 95, 90, 83, 73])
        sit, _ = b._options_for(b.state())
        self.assertNotEqual(sit, "rival encima (esquina)")


class GameFacing(unittest.TestCase):
    """+0x31 del juego manda sobre la posicion (levantarse de espaldas en la esquina, cruces)."""

    def test_raw_facing_overrides_position(self):
        s = st(0, mx=40, rx=60)
        self.assertTrue(s.facing_right)
        s2 = replace(s, me=replace(s.me, facing_right_raw=0))
        self.assertFalse(s2.facing_right)                 # el juego lo tiene mirando a la pared
        self.assertTrue(replace(s, me=replace(s.me, facing_right_raw=1)).facing_right)

    def test_unknown_falls_back_to_position(self):
        self.assertFalse(st(0, mx=500, rx=400).facing_right)

    def test_sparse_parse_with_and_without_facing(self):
        from kof_ai.lockstep import _fighter_from_sparse
        old = "00af00480000000000dc0015000000660000"[:26]       # 13 bytes
        self.assertEqual(_fighter_from_sparse(old).facing_right_raw, -1)
        new = old + "01"
        self.assertEqual(_fighter_from_sparse(new).facing_right_raw, 1)


class MoreKimThrowsAndOverhead(unittest.TestCase):
    def thrown_by(self, rival_state):
        feed = Feed()
        b = RuleBrain(feed, IORI)
        for f in range(0, 10):
            s = st(f, mx=400, rx=430)
            feed.s = replace(s, me=replace(s.me, state_id=23), rival=replace(s.rival, state_id=rival_state if f >= 6 else 1))
            b.state()
        return b._options_for(b.state())

    def test_248_and_249_are_throws_250_is_not(self):
        for rs in (248, 249):
            sit, opts = self.thrown_by(rs)
            self.assertEqual(sit, "me agarran", rs)
        self.assertNotEqual(self.thrown_by(250)[0], "me agarran")   # remate de la patada 214+K: cubrir agachado
        self.assertIn("4C", self.thrown_by(248)[1][0].notation)
        self.assertIn("4D", self.thrown_by(249)[1][0].notation)

    def test_kim_arc_kick_is_blocked_standing(self):
        feed = Feed()
        b = RuleBrain(feed, IORI)
        for f in range(0, 12):
            s = st(f, mx=400, rx=440, ratk=(f >= 4), rcr=(f < 4))
            feed.s = replace(s, rival=replace(s.rival, state_id=89 if f >= 6 else 115, character_id=6))
            b.state()
        self.assertFalse(b.guard_low())


class CornerMixAndGuardWorn(unittest.TestCase):
    def cornered_brain(self, mode="mix", blocks=0):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "DEFENSE_ONLY", "corner_escape": mode})
        for f in range(0, 60):
            feed.s = st(f, mx=40, rx=90, ratk=(5 <= f < 40))
            b.state()
        for k in range(blocks):
            b._block_starts.append(50 + k)
        return b

    def test_mix_never_rolls_twice_in_a_row(self):
        import random
        random.seed(1)
        for _ in range(30):
            b = self.cornered_brain()
            b._last_corner_move, b._last_corner_escape = "roll", b.state().frame - 200
            opt = b._corner_option(b.state())
            self.assertFalse(opt is not None and "roll" in opt.name)

    def test_mix_can_roll_after_the_repeat_window(self):
        import random
        random.seed(2)
        seen = set()
        for _ in range(40):
            b = self.cornered_brain()
            b._last_corner_move, b._last_corner_escape = "roll", b.state().frame - 400
            opt = b._corner_option(b.state())
            seen.add(opt.name if opt else "stay")
        self.assertIn("salida de esquina: roll", seen)
        self.assertTrue(len(seen) >= 2)

    def test_guard_worn_responds_instead_of_guarding(self):
        b = self.cornered_brain(blocks=4)                 # rival a 50: ni 2B (<=30) ni C (<=45)
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "guardia desgastada: responder")
        self.assertFalse([o for o in opts if o.name == "guardia"])
        self.assertFalse([o for o in opts if "CD" in o.notation])
        self.assertFalse([o for o in opts if o.name == "golpe bajo 2B"])   # a 50 el 2B no llega

    def test_few_blocks_keep_guarding(self):
        b = self.cornered_brain(blocks=2)
        sit, _ = b._options_for(b.state())
        self.assertNotEqual(sit, "guardia desgastada: responder")


class AggressiveStyle(unittest.TestCase):
    def brain(self, states, style="aggressive"):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "BALANCED_EXPERIMENTAL", "style": style, "preventive_guard": False})
        for s in states:
            feed.s = s
            b.state()
        return b

    def test_running_rival_gets_hit(self):
        states = [replace(st(f, mx=400, rx=560 - 12 * f), rival=replace(st(f).rival, x=560 - 12 * f, character_id=6, state_id=95))
                  for f in range(0, 6)]
        b = self.brain(states)
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "rival corre hacia mi")
        self.assertTrue([o for o in opts if "carrera" in o.name])
        # estilo defensivo: no
        sit2, _ = self.brain(states, style="defensive")._options_for(b.state())
        self.assertNotEqual(sit2, "rival corre hacia mi")

    def test_pressure_gap_is_contested(self):
        # la defensa propone pegar en el hueco; el arbitro agresivo puede preferir el ataque (RUSH)
        b = self.brain([st(f, mx=400, rx=440, ratk=(5 <= f < 30)) for f in range(0, 40)])
        sit, opts = b._defense_options(b.state(), allow_punish=False)
        self.assertEqual(sit, "presion del rival")
        self.assertTrue([o for o in opts if o.name == "golpe bajo 2B"])

    def test_defensive_pressure_gap_only_guards(self):
        b = self.brain([st(f, mx=400, rx=440, ratk=(5 <= f < 30)) for f in range(0, 40)], style="defensive")
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "presion del rival")
        self.assertEqual({o.name for o in opts}, {"guardia"})


class KimSankuuParts(unittest.TestCase):
    def test_250_is_an_overhead_blocked_standing(self):
        feed = Feed()
        b = RuleBrain(feed, IORI)
        for f in range(0, 12):
            s = st(f, mx=400, rx=460, ratk=(f >= 2))
            feed.s = replace(s, rival=replace(s.rival, state_id=250 if f >= 6 else 247, character_id=6))
            b.state()
        self.assertFalse(b.guard_low())

    def test_235_blocked_crouching_and_247_standing(self):
        for state_id, low in ((235, True), (247, False)):
            feed = Feed()
            b = RuleBrain(feed, IORI)
            for f in range(0, 12):
                s = st(f, mx=400, rx=460, ratk=(f >= 2))
                feed.s = replace(s, rival=replace(s.rival, state_id=state_id if f >= 6 else 97, character_id=6))
                b.state()
            self.assertEqual(b.guard_low(), low, state_id)


class RecoveryPunish(unittest.TestCase):
    def brain(self, rival_state, my_state=0, rx=430):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "BALANCED_EXPERIMENTAL"})
        for f in range(0, 12):
            s = st(f, mx=400, rx=rx, ratk=True)                   # el bit de ataque sigue encendido
            feed.s = replace(s, me=replace(s.me, state_id=my_state),
                             rival=replace(s.rival, state_id=rival_state if f >= 6 else 250, character_id=6))
            b.state()
        return b

    def test_kim_landing_after_blocked_kick_is_punished(self):
        sit, opts = self.brain(251)._options_for(self.brain(251).state())
        self.assertEqual(sit, "castigo a recuperacion")
        self.assertEqual(opts[0].notation, "C>623C")

    def test_not_while_still_in_blockstun(self):
        b = self.brain(251, my_state=30)
        self.assertNotEqual(b._options_for(b.state())[0], "castigo a recuperacion")

    def test_not_out_of_range(self):
        b = self.brain(251, rx=470)
        self.assertNotEqual(b._options_for(b.state())[0], "castigo a recuperacion")


class KimGuardTableFromTwelveFights(unittest.TestCase):
    def guard_low_vs(self, rival_state):
        feed = Feed()
        b = RuleBrain(feed, IORI)
        for f in range(0, 12):
            s = st(f, mx=400, rx=455, ratk=(f >= 2))
            feed.s = replace(s, rival=replace(s.rival, state_id=rival_state if f >= 6 else 1, character_id=6))
            b.state()
        return b.guard_low()

    def test_136_low(self):
        self.assertTrue(self.guard_low_vs(136))

    def test_129_and_224_standing(self):
        self.assertFalse(self.guard_low_vs(129))
        self.assertFalse(self.guard_low_vs(224))


class PunishMistakes(unittest.TestCase):
    """Pedido del usuario: castigar el fallo EN CURSO (Kim atada a un poder que no pego) y el aterrizaje."""

    def brain(self, states, rival_state=98):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "BALANCED_EXPERIMENTAL", "punish_whiff_now": True})
        for s in states:
            feed.s = replace(s, rival=replace(s.rival, state_id=rival_state, character_id=6))
            b.state()
        return b

    def test_whiffing_special_is_punished_before_it_ends(self):
        b = self.brain([st(f, mx=400, rx=440, ratk=(f >= 4)) for f in range(0, 18)])   # 14 frames atacando sin pegar
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "castigo a fallo")
        self.assertEqual(opts[0].notation, "C>623C")

    def test_not_in_the_first_frames(self):
        b = self.brain([st(f, mx=400, rx=440, ratk=(f >= 4)) for f in range(0, 9)])
        self.assertNotEqual(b._options_for(b.state())[0], "castigo a fallo")

    def test_multipart_kick_is_not_a_whiff(self):
        b = self.brain([st(f, mx=400, rx=440, ratk=(f >= 4)) for f in range(0, 18)], rival_state=235)
        self.assertNotEqual(b._options_for(b.state())[0], "castigo a fallo")

    def test_far_whiff_uses_sweep(self):
        b = self.brain([st(f, mx=400, rx=480, ratk=(f >= 4)) for f in range(0, 18)])
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "castigo a fallo")
        self.assertEqual(opts[0].notation, "2D")

    def test_landing_after_missed_air_attack(self):
        states = [st(f, mx=400, rx=440, rh=(60 - 6 * f if f < 10 else 0), ratk=(3 <= f < 9)) for f in range(0, 12)]
        b = self.brain(states, rival_state=1)
        self.assertEqual(b._options_for(b.state())[0], "castigo a fallo")


class CornerFiftyFifty(unittest.TestCase):
    def test_cornered_without_attack_guard_is_not_dominant(self):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "DEFENSE_ONLY", "corner_escape": "none"})
        for f in range(0, 80):
            feed.s = st(f, mx=40, rx=80)        # acorralado a la izquierda, rival a 40 sin atacar
            b.state()
        sit, opts = b._defense_options(b.state(), allow_punish=False)
        self.assertEqual(sit, "acorralado")
        names = {o.name: o.weight for o in opts}
        self.assertIn("castigo seguro: C Oniyaki", names)
        guard = names["guardia"]
        self.assertGreater(sum(w for n, w in names.items() if n != "guardia"), guard)   # salir/pegar > cubrir

    def test_corner_mix_can_counter(self):
        import random
        random.seed(3)
        seen = set()
        for _ in range(60):
            feed = Feed()
            b = RuleBrain(feed, {**IORI, "combat_mode": "DEFENSE_ONLY", "corner_escape": "mix"})
            for f in range(0, 60):
                feed.s = st(f, mx=40, rx=80, ratk=(5 <= f < 40))
                b.state()
            opt = b._corner_option(b.state())
            seen.add(opt.name if opt else "stay")
        self.assertIn("salida de esquina: counter", seen)


class WhiffNowOffByDefault(unittest.TestCase):
    def test_off_by_default(self):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "BALANCED_EXPERIMENTAL"})
        for f in range(0, 18):
            s = st(f, mx=400, rx=440, ratk=(f >= 4))
            feed.s = replace(s, rival=replace(s.rival, state_id=98, character_id=6))
            b.state()
        self.assertNotEqual(b._options_for(b.state())[0], "castigo a fallo")   # 0 de 12 medido: apagado


class LeaveTheCorner(unittest.TestCase):
    def test_preventive_guard_keeps_corner_exits(self):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "BALANCED_EXPERIMENTAL", "preventive_guard": True, "corner_escape": "none"})
        for f in range(0, 120):
            feed.s = st(f, mx=40, rx=100)       # acorralado, Kim quieta a 60
            b.state()
        sit, opts = b._options_for(b.state())
        self.assertEqual(sit, "acorralado")
        names = {o.name: o.weight for o in opts}
        self.assertIn("roll adelante (salir de la esquina)", names)
        self.assertIn("salto adelante", names)
        self.assertGreater(names["roll adelante (salir de la esquina)"], names["guardia"])


class RollUnderTheKick(unittest.TestCase):
    def brain(self, my_state, rival_state=246):
        feed = Feed()
        b = RuleBrain(feed, {**IORI, "combat_mode": "BALANCED_EXPERIMENTAL", "roll_under_kick": True})
        for f in range(0, 12):
            s = st(f, mx=400, rx=460, ratk=True)
            feed.s = replace(s, me=replace(s.me, state_id=my_state), rival=replace(s.rival, state_id=rival_state if f >= 6 else 235, character_id=6))
            b.state()
        return b

    def test_free_iori_rolls_under_followup(self):
        for rs in (246, 247):
            b = self.brain(0, rs)
            sit, opts = b._options_for(b.state())
            self.assertEqual(sit, "rodar bajo la patada", rs)
            self.assertEqual(max(opts, key=lambda o: o.weight).notation, "AB")

    def test_still_in_blockstun_keeps_guarding(self):
        b = self.brain(30)
        self.assertNotEqual(b._options_for(b.state())[0], "rodar bajo la patada")


class KimDMEnderIsLow(unittest.TestCase):
    def test_167_blocked_crouching(self):
        feed = Feed()
        b = RuleBrain(feed, IORI)
        for f in range(0, 12):
            s = st(f, mx=400, rx=460, ratk=True)
            feed.s = replace(s, rival=replace(s.rival, state_id=167 if f >= 6 else 146, character_id=6))
            b.state()
        self.assertTrue(b.guard_low())

    def test_dm_startup_142_already_crouching(self):
        feed = Feed()
        b = RuleBrain(feed, IORI)
        for f in range(0, 10):
            s = st(f, mx=400, rx=460, ratk=(f >= 6))
            feed.s = replace(s, rival=replace(s.rival, state_id=142 if f >= 6 else 1, character_id=6))
            b.state()
        self.assertTrue(b.guard_low())
