"""Cerebro de Fase 3: decide segun el estado de la pelea, con aleatoriedad controlada.

Cada situacion tiene varias respuestas razonables con pesos. Se elige una al
azar, y las que se acaban de usar pierden peso para no repetir patrones.
"""
import random
import re
import time
from collections import deque
from dataclasses import dataclass

# Distancias en unidades del escenario (la pantalla mide ~304).
CLOSE = 75
MID = 180
ANTI_AIR_RANGE = 120     # el rival tiene que estar cayendo dentro de este rango
ANTI_AIR_MAX_HEIGHT = 70  # y ya no muy alto, para que el anti-aire conecte
HIT_MEMORY_FRAMES = 40   # cuanto tiempo "recuerdo" haber recibido un golpe
MAX_DAMAGE_PER_FRAME = 60  # caidas mayores son KO/transiciones de ronda, no golpes
PUNISH_WINDOW = 12        # frames tras el fin de un ataque rival en los que se puede castigar
BLOCK_FRAMES = 18         # primeros frames de un ataque rival: bloquear; despues es recuperacion
CLOSE_C_RANGE = 45        # distancia maxima para que salga el C de cerca (cancelable)
LIGHT_RANGE = 55          # alcance de un ligero (2B) para empezar un combo; mas lejos falla
HEAVY_START = re.compile(r"^[1-9]?[CD]")  # combo que empieza con C/D (o 6C...): solo pegado
DISTANCE_BUCKET = 40      # igual que en learning.py (tramos de distancia de los contextos)
LOW_ATTACK_WINDOW = 4     # ataque que empieza <= N frames despues de estar agachado = low


@dataclass(frozen=True)
class Option:
    weight: float
    name: str
    notation: str
    interruptible: bool = False  # se puede cortar si pasa algo urgente


class RuleBrain:
    def __init__(self, reader, moves, imitation=None):
        self._reader = reader
        self._imitation = imitation  # kof_ai.imitation.Imitation o None
        pro = imitation.combos if imitation else {}
        # Los combos de jugadores reales se suman a los del perfil.
        self._moves = {**moves, "combos": {**moves.get("combos", {}), **pro},
                       "punish": {**moves.get("punish", {}), **pro}}
        self._recent = deque(maxlen=4)
        self._cached = None
        self._cached_at = 0.0
        self._prev = None            # estado del frame anterior (para velocidades)
        self._last_hit_frame = -10_000
        self._air_attacked = False   # ya ataque en este salto
        self.dealt_total = 0         # danio acumulado hecho / recibido (para recompensas)
        self.taken_total = 0
        self._rival_attack_start_frame = -10_000
        self._rival_crouch_frame = -10_000
        self._rival_attack_low = False
        self._rival_attack_end_frame = -10_000
        self._rival_attack_hit_me = False

    def state(self):
        """Estado cacheado ~8 ms; ademas registra golpes recibidos frame a frame."""
        now = time.perf_counter()
        # Con lectores frame a frame (lockstep) el estado esta en memoria: leer siempre.
        if getattr(self._reader, "live", False) or now - self._cached_at > 0.008:
            state = self._reader.read()
            self._cached_at = now
            if state and self._cached and state.frame != self._cached.frame:
                self._prev = self._cached
                taken = self._cached.me.life - state.me.life
                dealt = self._cached.rival.life - state.rival.life
                if 0 < taken <= MAX_DAMAGE_PER_FRAME:
                    self._last_hit_frame = state.frame
                    self.taken_total += taken
                if 0 < dealt <= MAX_DAMAGE_PER_FRAME:
                    self.dealt_total += dealt
                if self._cached.rival.crouching:
                    self._rival_crouch_frame = self._cached.frame
                if state.rival.attacking and not self._cached.rival.attacking:
                    self._rival_attack_start_frame = state.frame
                    self._rival_attack_low = state.frame - self._rival_crouch_frame <= LOW_ATTACK_WINDOW
                if self._cached.rival.attacking and not state.rival.attacking:
                    self._rival_attack_end_frame = state.frame
                    self._rival_attack_hit_me = self._recently_hit(state, 30)
            self._cached = state
        return self._cached

    def decide(self):
        """Devuelve (situacion, Option) o None si no hay estado."""
        state = self.state()
        if state is None:
            return None
        situation, options = self._options_for(state)
        if self._imitation:
            bucket = min(state.distance // DISTANCE_BUCKET, 7)
            options = self._imitation.adjust(situation, bucket, options)
        choice = self._choose(state, situation, options)
        self._recent.append(choice.name)
        return situation, choice

    def _choose(self, state, situation, options):
        weights = [o.weight * self._repeat_penalty(o) for o in options]
        return random.choices(options, weights=weights)[0]

    def _repeat_penalty(self, option):
        return 0.35 if option.name in self._recent else 1.0

    def urgent(self):
        """True si conviene cortar la accion actual para reaccionar."""
        state = self.state()
        return state is not None and (self._rival_jumping_in(state) or self._recently_hit(state, 2)
                                      or self._rival_attacking_near(state))

    def being_thrown(self):
        """Me estan agarrando: hay que cortar cualquier accion y escapar YA."""
        state = self.state()
        return state is not None and state.me.thrown

    def _rival_attack_age(self, state):
        return state.frame - self._rival_attack_start_frame

    def _rival_attacking_near(self, state):
        """Ataque rival en su fase peligrosa (arranque/activo) y cerca: bloquear."""
        return (state.rival.attacking and state.distance <= MID
                and self._rival_attack_age(state) <= BLOCK_FRAMES)

    def _can_punish(self, state):
        """El rival esta en la recuperacion de un ataque que no me pego (o acaba de
        terminarlo) y esta cerca."""
        if state.rival.airborne or state.distance > CLOSE + 25 or self._recently_hit(state, 20):
            return False
        recovering = state.rival.attacking and self._rival_attack_age(state) > BLOCK_FRAMES
        just_ended = (state.frame - self._rival_attack_end_frame <= PUNISH_WINDOW
                      and not self._rival_attack_hit_me)
        return recovering or just_ended

    def guard_low(self):
        """True -> bloquear abajo (rival agachado o atacando desde agachado: lows).
        False -> bloquear de pie (rival de pie o en el aire: overheads y saltos)."""
        state = self.state()
        if state is None or state.rival.airborne:
            return False
        return state.rival.crouching or (state.rival.attacking and self._rival_attack_low)

    def can_punish_now(self):
        state = self.state()
        return state is not None and self._can_punish(state)

    def _recently_hit(self, state, frames=HIT_MEMORY_FRAMES):
        return state.frame - self._last_hit_frame <= frames

    def _rival_descending(self, state):
        prev = self._prev
        return prev is not None and state.rival.height < prev.rival.height

    def _rival_jumping_in(self, state):
        rival = state.rival
        return (rival.airborne and state.distance <= ANTI_AIR_RANGE
                and rival.height <= ANTI_AIR_MAX_HEIGHT and self._rival_descending(state))

    def _options_for(self, state):
        m = self._moves
        me, rival = state.me, state.rival
        d = state.distance

        if rival.life == 0 or me.life == 0:
            return "ronda terminada", [Option(1, "esperar", "5[30]")]

        if me.thrown:
            # Escape de agarre: direccion + C y D a la vez cubre agarres con C y con D.
            return "me agarran", [Option(1, "escapar agarre", "4CD5[1]4CD")]

        if me.airborne:
            # Un solo ataque por salto, y ninguno si me lanzaron por un golpe.
            if self._air_attacked or self._recently_hit(state):
                return "en el aire (esperando aterrizar)", [Option(1, "esperar", "5[4]")]
            self._air_attacked = True
            return "estoy en el aire", [
                Option(55, "golpe aereo D", "5[4]D"),
                Option(35, "golpe aereo C", "5[4]C"),
                Option(10, "sin ataque", "5[4]"),
            ]
        self._air_attacked = False

        if self._recently_hit(state):
            # En hitstun los botones no hacen nada; la guardia dinamica bloquea en cuanto se pueda.
            return "me golpearon", [
                Option(75, "guardia", "G[18]"),
                Option(15, "reversal", "1[8]" + m["reversal"]),
                Option(10, "roll atras", "1[8]4AB"),
            ]

        if self._can_punish(state):
            # El rival fallo o le bloquee un ataque: mi turno, con combo segun la distancia.
            punish = self._in_range(m["punish"], d) or self._in_range(m["combos"], d)
            options = [Option(45 / max(len(punish), 1), f"castigo: {name}", notation)
                       for name, notation in punish.items()]
            options += self._dm_combos(me, d, total_weight=12, prefix="castigo DM")
            return "castigar", options + [
                Option(12, "agarre", "6C") if d <= CLOSE_C_RANGE else Option(12, "barrida 2D", "2D"),
                Option(8, "golpe bajo 2B", "2B"),
            ]

        if self._rival_jumping_in(state):
            options = [
                Option(50, "anti-aire especial", m["anti_air"]),
                Option(30, "anti-aire normal", m["anti_air_normal"]),
                Option(20, "guardia", "G[15]"),
            ]
            if me.stocks >= 1 and m.get("anti_air_dm"):
                options.append(Option(30, "anti-aire DM", m["anti_air_dm"]))
            return "rival cae hacia mi", options

        if self._rival_attacking_near(state):
            # La guardia elige alto/bajo cada frame segun la postura del rival.
            if rival.airborne:
                return "rival ataca desde el aire", [
                    Option(75, "guardia", "G[12]"),
                    Option(15, "anti-aire normal", m["anti_air_normal"]),
                    Option(10, "retroceder", "4[8]"),
                ]
            return "rival ataca", [
                Option(85, "guardia", "G[12]"),
                Option(10, "backdash", "4 5 4"),
                Option(5, "reversal", m["reversal"]),
            ]

        if rival.airborne and d <= MID:
            # Esta saltando pero aun alto o subiendo: esperar el momento justo.
            return "rival en el aire, esperando", [
                Option(45, "esperar", "5[3]", interruptible=True),
                Option(40, "guardia", "G[4]"),
                Option(15, "retroceder un paso", "4[6]", interruptible=True),
            ]

        if d > MID:
            return "rival lejos", [
                Option(30, "correr", "6 5 6[25]", interruptible=True),
                Option(25, "caminar adelante", "6[30]", interruptible=True),
                Option(15, "hop adelante", "9[3]"),
                Option(15, "proyectil / especial de lejos", m["far_special"]),
                Option(15, "esperar", "1[20]", interruptible=True),
            ]

        if d > CLOSE:
            return "media distancia", [
                Option(20, "caminar adelante", "6[15]", interruptible=True),
                Option(12, "hop adelante", "9[3]"),
                Option(15, "poke", m["poke"]),
                Option(10, "barrida 2D", "2D"),
                Option(10, "especial de media", m["mid_special"]),
                Option(8, "roll adelante", "AB"),
                Option(25, "guardia", "G[20]"),
            ]

        in_range = self._in_range(m["combos"], d)
        combos = [Option(40 / max(len(in_range), 1), f"combo: {name}", notation)
                  for name, notation in in_range.items()]
        if not in_range:
            # Cerca pero fuera del alcance de los combos: acercarse un paso.
            combos = [Option(25, "acercarse a rango de combo", "6[6]", interruptible=True)]
        combos += self._dm_combos(me, d, total_weight=8, prefix="combo DM")
        # Mezclas para romper la guardia: agarre (gana a quien se cubre), golpe por
        # arriba (gana a guardia abajo) y golpe bajo (gana a guardia de pie).
        if d <= CLOSE_C_RANGE:
            mixups = [Option(10, "agarre C", "6C"), Option(8, "agarre D", "6D")]
        else:
            mixups = [Option(10, "barrida 2D", "2D")]
        return "pegado al rival", combos + mixups + [
            Option(10, "golpe bajo 2B", "2B"),
            Option(10, "overhead", m["overhead"]),
            Option(25, "guardia", "G[18]"),
            Option(8, "backdash", "4 5 4"),
            Option(6, "salto atras (evitar agarre)", "7[8]"),
            Option(3, "reversal", m["reversal"]),
        ]

    def _dm_combos(self, me, d, total_weight, prefix):
        """Combos que terminan en DM: solo con al menos una barra llena."""
        if me.stocks < 1:
            return []
        dm = self._in_range(self._moves.get("dm_combos", {}), d)
        return [Option(total_weight / len(dm), f"{prefix}: {name}", notation)
                for name, notation in dm.items()]

    @staticmethod
    def _in_range(combos, d):
        """Combos cuyo primer golpe alcanza a esta distancia. Los que empiezan con C
        (close C) solo salen pegado; mas lejos sale el C lejano, que no se cancela.
        Los que empiezan con un ligero (2B) alcanzan un poco mas."""
        return {name: notation for name, notation in combos.items()
                if d <= (CLOSE_C_RANGE if HEAVY_START.match(notation) else LIGHT_RANGE)}
