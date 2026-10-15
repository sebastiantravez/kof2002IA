"""Ofensiva estrategica (DEFENSIVE OFFENSE AI V2): decide que hacer en NEUTRAL, es
decir, cuando no hay ninguna amenaza real. La defensa (kof_ai/brain.py) sigue
teniendo prioridad: este modulo solo se consulta despues de descartar amenazas.

Todo sale de informacion observable en la RAM; nada de inputs futuros del rival.
Las puntuaciones son heuristicas (no probabilidades): pesos relativos que el
aprendizaje (kof_ai/learning.py) corrige con el resultado real de cada accion.
"""
from collections import deque
from dataclasses import dataclass

WINDOW_FRAMES = 30 * 60          # el modelo del rival mira los ultimos 30 s de juego
MIN_DWELL_FRAMES = 20            # histeresis: minimo en un modo antes de cambiar
POKE_MIN, POKE_MAX = 60, 130     # distancias donde llegan los pokes (2C/2D/D de Iori)
PASSIVE_RIVAL_FRAMES = 90        # rival sin atacar este tiempo: esta pasivo
CALM_PRESSURE_RANGE = 60         # presion cercana: distancia a la que aplica pressure_needs_calm
BAIT_COOLDOWN_FRAMES = 300       # tras un amague, no volver a amagar en 5 s (medido: 24% del tiempo en BAIT sin pegar)

# Riesgo si la accion falla o la bloquean (heuristico, por tipo de accion):
# 0 = seguro, 1 = algo de recuperacion, 2 = muy castigable.
RISK = {"poke": 0, "golpe bajo 2B": 0, "combo corto 2B": 0, "agarre C": 1, "agarre D": 1,
        "overhead": 1, "barrida 2D": 1, "especial de lejos": 1, "hop adelante": 2, "roll adelante": 1}


@dataclass(frozen=True)
class Mode:
    name: str        # nombre del modo (tambien es la "situacion" que ve el aprendizaje)
    reason: str      # motivo legible


class OpponentModel:
    """Tendencias del rival en los ultimos WINDOW_FRAMES frames observados."""

    def __init__(self):
        self.jumps = deque()
        self.attacks = deque()
        self.lows = deque()
        self.whiffs = deque()          # ataques que terminaron sin pegarme y lejos
        self.our_attempts = deque()    # nuestros ataques de cerca (frame, hizo danio?)
        self.last_attack_frame = -10_000

    def _trim(self, frame):
        for q in (self.jumps, self.attacks, self.lows, self.whiffs, self.our_attempts):
            while q and frame - (q[0][0] if isinstance(q[0], tuple) else q[0]) > WINDOW_FRAMES:
                q.popleft()

    def observe(self, prev, state, attack_low, attack_ended_without_hit):
        f = state.frame
        if state.rival.airborne and not prev.rival.airborne:
            self.jumps.append(f)
        if state.rival.attacking and not prev.rival.attacking:
            self.attacks.append(f)
            self.last_attack_frame = f
            if attack_low:
                self.lows.append(f)
        if attack_ended_without_hit and state.distance > 90:
            self.whiffs.append(f)
        self._trim(f)

    def record_our_attack(self, frame, did_damage):
        self.our_attempts.append((frame, did_damage))

    # Tasas por minuto de juego / proporciones
    def per_minute(self, q):
        return len(q) * 3600 / WINDOW_FRAMES

    @property
    def jump_rate(self):
        return self.per_minute(self.jumps)

    @property
    def aggression(self):
        return self.per_minute(self.attacks)

    @property
    def low_ratio(self):
        return len(self.lows) / max(len(self.attacks), 1)

    @property
    def whiff_rate(self):
        return self.per_minute(self.whiffs)

    @property
    def blocks_a_lot(self):
        """Nuestros ataques de cerca casi nunca hacen danio: el rival se cubre."""
        if len(self.our_attempts) < 5:
            return False
        return sum(1 for _, dmg in self.our_attempts if dmg) / len(self.our_attempts) < 0.25

    def rival_passive(self, frame):
        return frame - self.last_attack_frame > PASSIVE_RIVAL_FRAMES

    def summary(self):
        return (f"saltos/min {self.jump_rate:.1f}, ataques/min {self.aggression:.1f}, "
                f"bajos {100 * self.low_ratio:.0f}%, fallos/min {self.whiff_rate:.1f}, "
                f"se cubre mucho: {'si' if self.blocks_a_lot else 'no'}")


class Strategy:
    def __init__(self, pressure_needs_calm=False):
        # Medido contra una persona (2026-10-14): los ataques de presion iniciados pegado al
        # rival mientras el rival TAMBIEN atacaba entraron 8 de 8 (el 2B rival gana a un golpe
        # lento). Con este interruptor la presion cercana solo sale si el rival esta pasivo.
        self.pressure_needs_calm = pressure_needs_calm
        self.model = OpponentModel()
        self.mode = Mode("NEUTRAL", "inicio")
        self.mode_since = 0
        self.last_bait_end = -10_000
        self.last_useful_frame = 0

    # ---- pasividad ----

    def passivity_score(self, frame):
        """Segundos en neutral sin una accion util (acercarse, poke, presion, castigo)."""
        return max(0.0, (frame - self.last_useful_frame) / 60)

    def mark_useful(self, frame):
        self.last_useful_frame = frame

    # ---- eleccion de modo con histeresis ----

    def choose_mode(self, state, my_life_lead):
        d, f = state.distance, state.frame
        m = self.model
        passive = self.passivity_score(f)
        rival_passive = m.rival_passive(f)
        if d > 180:
            new = Mode("APPROACH", "rival lejos: acercarse")
            if m.aggression > 25 and passive < 2 and not rival_passive:
                new = Mode("BAIT", "rival agresivo: provocar que ataque desde lejos")
        elif d > 75:
            if state.back_to_wall:
                new = Mode("APPROACH", "acorralado: ganar espacio")
            elif my_life_lead > 25 and m.aggression > 20 and passive < 3:
                new = Mode("RETREAT", "voy ganando y el rival presiona: recuperar distancia")
            elif m.whiff_rate > 3 and passive < 3 and f - self.last_bait_end > BAIT_COOLDOWN_FRAMES:
                new = Mode("BAIT", "el rival falla golpes: provocarlo")
            elif POKE_MIN <= d <= POKE_MAX:
                new = Mode("POKE", "distancia de poke")
            else:
                new = Mode("APPROACH", "ajustar distancia al alcance de los normales")
        else:
            if m.aggression > 30 and my_life_lead < -25 and not rival_passive:
                new = Mode("RETREAT", "rival agresivo y voy perdiendo: reposicionar")
            else:
                new = Mode("PRESSURE", "cerca y sin amenaza: presion controlada")
        # histeresis: no cambiar de modo cada frame (las amenazas no pasan por aqui)
        if new.name != self.mode.name and f - self.mode_since < MIN_DWELL_FRAMES:
            return self.mode
        if new.name != self.mode.name:
            if self.mode.name == "BAIT":
                self.last_bait_end = f
            self.mode, self.mode_since = new, f
        return self.mode

    # ---- opciones por modo ----

    def options(self, state, moves, option_cls, combos_in_range, my_life_lead, attacks_ready=True):
        mode = self.choose_mode(state, my_life_lead)
        d = state.distance
        m = self.model
        O = option_cls
        passive = min(self.passivity_score(state.frame), 5)
        push = 1 + 0.3 * passive          # sube aproximacion/poke/presion si estoy pasivo
        blocks = 1.8 if m.blocks_a_lot else 1.0
        cornered_rival = 1.5 if state.rival_cornered else 1.0
        lows = m.low_ratio > 0.4          # el rival ataca mucho por abajo

        if mode.name == "APPROACH":
            opts = [O(30 * push, "acercarse (pasos cortos)", "6[10]", interruptible=True),
                    O(12 * push if d > 180 else 4, "correr", "6 5 6[18]", interruptible=True),
                    O(12, "guardia corta", "G[6]"),
                    O(6, "especial de lejos", moves["far_special"]) if d > 120 else None,
                    O(3, "hop adelante", "9[3]") if m.jump_rate < 3 else None]
        elif mode.name == "POKE":
            opts = [O(30 * push, "poke", moves["poke"]),
                    O(15 * push, "barrida 2D", "2D") if d <= 110 else None,
                    O(15, "acercarse (pasos cortos)", "6[8]", interruptible=True),
                    O(10, "retroceder (pasos cortos)", "4[8]", interruptible=True),
                    O(12, "guardia corta", "G[6]")]
        elif mode.name == "PRESSURE" and not attacks_ready:
            # El rival sigue derribado por el ultimo golpe: esperar cubierto, no pegar al aire.
            opts = [O(1, "esperar que el rival se levante", "G[8]")]
        elif (mode.name == "PRESSURE" and self.pressure_needs_calm and d <= CALM_PRESSURE_RANGE
              and not m.rival_passive(state.frame)):
            # Rival activo y pegado: no iniciar presion; guardia y a esperar su error (los
            # castigos seguros/a golpe fallado los propone el arbitro por separado).
            opts = [O(40, "guardia corta", "G[8]"), O(6, "golpe bajo 2B", "2B")]
        elif mode.name == "PRESSURE":
            opts = [O(20 * push * cornered_rival, "golpe bajo 2B", "2B"),
                    O(15 * push * cornered_rival, "combo corto 2B", "2B>2A") ]
            opts += [O(25 * push / max(len(combos_in_range), 1), f"combo: {name}", notation)
                     for name, notation in combos_in_range.items()]
            if d <= 45:
                opts += [O(8 * blocks, "agarre C", "6C"), O(6 * blocks, "agarre D", "6D")]
            opts += [O(6 * blocks * (1.5 if not lows else 1), "overhead", moves["overhead"]),
                     O(12, "backdash", "4 5 4") if not state.back_to_wall else None,
                     O(10, "guardia corta", "G[8]")]
        elif mode.name == "BAIT":
            # Entrar y salir del alcance del rival sin atacar, para que falle y castigarlo.
            opts = [O(30, "amague: entrar y salir", "6[8]4[10]", interruptible=True),
                    O(20, "guardia corta", "G[10]"),
                    O(10, "retroceder (pasos cortos)", "4[8]", interruptible=True),
                    O(8 * push, "poke", moves["poke"])]
        elif mode.name == "RETREAT":
            opts = [O(30, "retroceder (pasos cortos)", "4[10]", interruptible=True),
                    O(15, "backdash", "4 5 4") if not state.back_to_wall else None,
                    O(20, "guardia corta", "G[8]"),
                    O(8, "poke", moves["poke"])]
        else:
            opts = [O(20, "guardia corta", "G[8]"), O(20, "acercarse (pasos cortos)", "6[8]", interruptible=True)]

        # riesgo: lo muy castigable pesa menos fuera de una oportunidad confirmada
        opts = [o for o in opts if o is not None]
        return f"NEUTRAL:{mode.name}", [_with_risk(o, option_cls) for o in opts]


def _with_risk(option, option_cls):
    risk = RISK.get(option.name, 0)
    if risk == 0:
        return option
    return option_cls(option.weight / (1 + risk), option.name, option.notation, option.interruptible)


USEFUL_PREFIXES = ("acercarse", "correr", "poke", "barrida", "golpe bajo", "combo", "agarre",
                   "overhead", "amague", "especial de lejos", "castigo", "anti-aire")


def is_useful(option_name):
    return option_name.startswith(USEFUL_PREFIXES)
