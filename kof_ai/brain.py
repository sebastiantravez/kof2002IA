"""Cerebro de Fase 3: decide segun el estado de la pelea, con aleatoriedad controlada.

Cada situacion tiene varias respuestas razonables con pesos. Se elige una al
azar, y las que se acaban de usar pierden peso para no repetir patrones.
"""
import random
import re
import time
from collections import deque
from dataclasses import dataclass, replace

from .arbiter import BALANCED_EXPERIMENTAL, DEFENSE_ONLY, CombatActionArbiter, Proposal, mode_from_profile
from .strategy import Strategy, is_useful

# Distancias en unidades del escenario (la pantalla mide ~304).
CLOSE = 75
MID = 180
ANTI_AIR_RANGE = 120     # el rival tiene que estar cayendo dentro de este rango
ANTI_AIR_MAX_HEIGHT = 70  # y ya no muy alto, para que el anti-aire conecte
HIT_MEMORY_FRAMES = 40   # cuanto tiempo "recuerdo" haber recibido un golpe
MAX_DAMAGE_PER_FRAME = 60  # caidas mayores son KO/transiciones de ronda, no golpes
WHIFF_PUNISH_RANGE = 130  # golpe fallado del rival: se castiga corriendo hasta esta distancia
PUNISH_WINDOW = 12       # frames tras el fin de un ataque rival en los que se puede castigar
BLOCK_FRAMES = 18         # primeros frames de un ataque rival: bloquear; despues es recuperacion
CLOSE_C_RANGE = 45        # distancia maxima para que salga el C de cerca (cancelable)
LIGHT_RANGE = 55          # alcance de un ligero (2B) para empezar un combo; mas lejos falla
HEAVY_START = re.compile(r"^[1-9]?[CD]")  # combo que empieza con C/D (o 6C...): solo pegado
DISTANCE_BUCKET = 40      # igual que en learning.py (tramos de distancia de los contextos)
LOW_ATTACK_WINDOW = 4     # ataque que empieza <= N frames despues de estar agachado = low
PRESSURE_FRAMES = 30      # el rival ataco hace <= N frames y sigue cerca: la presion no termino
LONG_ATTACK_FRAMES = 24   # ataque rival que dura >= N frames: lo deja vulnerable al terminar
# Castigo seguro (DEFENSE_WITH_PUNISH): el ataque rival tiene que llevar N frames terminado
# sin que empiece otro (ataques de varias partes apagan el bit de ataque entre partes).
# Configurable por perfil: "punish_confirm_frames".
PUNISH_CONFIRM_FRAMES = 4

# Estilo "defensive" (perfil "style" en config.json): multiplicadores de peso por opcion.
# Mas guardia y retroceso; menos riesgo; combos solo como castigo confirmado.
DEFENSIVE_STYLE = {
    "guardia": 1.6, "backdash": 1.4, "retroceder": 1.4, "retroceder un paso": 1.4,
    "salto atras (evitar agarre)": 1.3, "roll atras": 1.3,
    "hop adelante": 0.4, "overhead": 0.5, "reversal": 0.3, "especial de media": 0.6,
    "correr": 0.7, "proyectil / especial de lejos": 0.8, "anti-aire especial": 0.8,
}
DEFENSIVE_PREFIXES = {"combo: ": 0.6, "combo DM: ": 0.5}


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
        self.style = moves.get("style", "balanced")
        # Tiempo de reaccion: el cerebro ve el juego con N frames de retraso (como un
        # humano). 0 = sin retraso extra (solo la latencia propia del sistema).
        self.reaction_frames = int(moves.get("reaction_frames", 0))
        self._history = deque(maxlen=120)
        self._rival_attack_duration = 0
        # Modo de combate (kof_ai/arbiter.py): DEFENSE_ONLY | DEFENSE_WITH_PUNISH |
        # BALANCED_EXPERIMENTAL. La defensa original propone siempre; el arbitro decide.
        self.combat_mode = mode_from_profile(moves)
        self.arbiter = CombatActionArbiter(self.combat_mode)
        self.punish_confirm_frames = int(moves.get("punish_confirm_frames", PUNISH_CONFIRM_FRAMES))
        # Ofensiva estrategica (kof_ai/strategy.py): solo en BALANCED_EXPERIMENTAL.
        self.strategy = Strategy() if self.combat_mode == BALANCED_EXPERIMENTAL else None
        self._attack_min_dist = 999       # distancia minima durante el ataque rival en curso
        self._guarded_attack = False      # estaba en guardia durante ese ataque
        self._last_choice = None
        self._our_attacks = []            # (frame, danio hecho antes) para el modelo del rival
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
            state = self._perceived(self._reader.read())
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
                ended_clean = False
                if state.rival.attacking and not self._cached.rival.attacking:
                    self._rival_attack_start_frame = state.frame
                    self._rival_attack_low = state.frame - self._rival_crouch_frame <= LOW_ATTACK_WINDOW
                    self._attack_min_dist = state.distance
                    self._guarded_attack = False
                if state.rival.attacking:
                    self._attack_min_dist = min(self._attack_min_dist, state.distance)
                    if self._last_choice and self._last_choice.notation.startswith("G["):
                        self._guarded_attack = True
                if self._cached.rival.attacking and not state.rival.attacking:
                    self._rival_attack_end_frame = state.frame
                    self._rival_attack_hit_me = self._recently_hit(state, 30)
                    self._rival_attack_duration = state.frame - self._rival_attack_start_frame
                    ended_clean = not self._rival_attack_hit_me
                if self.strategy:
                    self.strategy.model.observe(self._cached, state, self._rival_attack_low, ended_clean)
                    self._settle_our_attacks(state)
            self._cached = state
        return self._cached

    def _perceived(self, latest):
        """Estado que 've' el cerebro: el de hace reaction_frames frames."""
        if latest is None or self.reaction_frames <= 0:
            return latest
        if not self._history or self._history[-1].frame != latest.frame:
            self._history.append(latest)
        target = latest.frame - self.reaction_frames
        for past in reversed(self._history):
            if past.frame <= target:
                return past
        return self._history[0]

    def decide(self):
        """Devuelve (situacion, Option) o None si no hay estado."""
        state = self.state()
        if state is None:
            return None
        situation, options = self._options_for(state)
        if self._imitation:
            bucket = min(state.distance // DISTANCE_BUCKET, 7)
            options = self._imitation.adjust(situation, bucket, options)
        if self.style == "defensive" and not situation.startswith("NEUTRAL:"):
            # En NEUTRAL la estrategia ya pondera riesgo; el estilo defensivo aplica a lo demas.
            options = [self._defensive_weight(o) for o in options]
        choice = self._choose(state, situation, options)
        self._recent.append(choice.name)
        self._last_choice = choice
        if self.strategy:
            if is_useful(choice.name):
                self.strategy.mark_useful(state.frame)
            if is_useful(choice.name) and state.distance <= 90 and not situation.startswith("castigo"):
                self._our_attacks.append((state.frame, self.dealt_total))
        return situation, choice

    def _settle_our_attacks(self, state):
        """Nuestros ataques de cerca: hicieron danio en 40 frames? (rival que se cubre)."""
        still = []
        for frame0, dealt0 in self._our_attacks:
            if state.frame - frame0 >= 40:
                self.strategy.model.record_our_attack(frame0, self.dealt_total > dealt0)
            else:
                still.append((frame0, dealt0))
        self._our_attacks = still

    def threat_now(self):
        """Hay una amenaza real (para no soltar la guardia entre acciones)."""
        state = self.state()
        if state is None:
            return False
        return (self._rival_attacking_near(state) or self._under_pressure(state)
                or self._rival_jumping_in(state) or self._recently_hit(state)
                or (state.rival.airborne and state.distance <= MID))

    @staticmethod
    def _defensive_weight(option):
        factor = DEFENSIVE_STYLE.get(option.name, 1.0)
        for prefix, value in DEFENSIVE_PREFIXES.items():
            if option.name.startswith(prefix):
                factor = value
        return option if factor == 1.0 else replace(option, weight=option.weight * factor)

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
        if self.style == "defensive" and just_ended and not recovering:
            # Un ataque corto que termina puede seguir en cadena: castigar solo los
            # largos (fallados o muy recuperables), que dejan al rival vendido.
            return self._rival_attack_duration >= LONG_ATTACK_FRAMES
        return recovering or just_ended

    def _under_pressure(self, state):
        """El rival ataco hace poco y sigue cerca: no soltar la guardia todavia."""
        last_attack = max(self._rival_attack_start_frame, self._rival_attack_end_frame)
        return (state.distance <= MID and not state.rival.airborne
                and (state.rival.attacking or state.frame - last_attack <= PRESSURE_FRAMES))

    def guard_low(self):
        """True -> bloquear abajo (rival agachado o atacando desde agachado: lows).
        False -> bloquear de pie (rival de pie o en el aire: overheads y saltos)."""
        state = self.state()
        if state is None or state.rival.airborne:
            return False
        return state.rival.crouching or (state.rival.attacking and self._rival_attack_low)

    def can_punish_now(self):
        """Hay que cortar la guardia para castigar (segun el modo de combate)."""
        state = self.state()
        if state is None:
            return False
        if self.combat_mode == DEFENSE_ONLY:
            return self._can_punish(state)
        return self._confirmed_punish(state) or (self.strategy is not None and self._whiff_punishable(state))

    def _confirmed_punish(self, state):
        """Castigo seguro: el rival hizo un ataque largo, se lo bloquee (estaba en guardia y
        no me pego), termino hace >= punish_confirm_frames y no empezo otro; esta en el
        suelo y al alcance de un golpe corto. Todo observable en la RAM."""
        since_end = state.frame - self._rival_attack_end_frame
        return (not state.rival.attacking and not state.rival.airborne and not state.me.airborne
                and self.punish_confirm_frames <= since_end <= self.punish_confirm_frames + PUNISH_WINDOW
                and self._rival_attack_duration >= LONG_ATTACK_FRAMES
                and self._guarded_attack and not self._rival_attack_hit_me
                and not self._recently_hit(state, 20) and state.distance <= LIGHT_RANGE)

    def _whiff_punishable(self, state):
        """WHIFF_PUNISH (solo BALANCED_EXPERIMENTAL): el ataque rival termino sin estar
        nunca cerca de mi: lo fallo; se castiga corriendo."""
        just_ended = (state.frame - self._rival_attack_end_frame <= PUNISH_WINDOW
                      and not self._rival_attack_hit_me)
        return (just_ended and not state.rival.attacking and not state.rival.airborne
                and self._attack_min_dist > 90 and state.distance <= WHIFF_PUNISH_RANGE
                and not self._recently_hit(state, 20))

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
        """La defensa original y el ataque proponen por separado; el arbitro elige."""
        if self.combat_mode == DEFENSE_ONLY:
            return self.arbiter.select(Proposal(*self._defense_options(state, allow_punish=True)))
        defense = Proposal(*self._defense_options(state, allow_punish=False))
        return self.arbiter.select(defense, self._punish_proposal(state), self._attack_proposal(state))

    def _punish_proposal(self, state):
        d = state.distance
        if self._confirmed_punish(state):
            # Golpe corto y de vuelta a neutral (nada de combos largos todavia).
            options = [Option(50, "castigo seguro: 2B", "2B")]
            if d <= CLOSE_C_RANGE:
                options.append(Option(50, "castigo seguro: C", "C"))
            return Proposal("castigo seguro", options)
        if self.strategy is not None and self._whiff_punishable(state):
            m = self._moves
            options = [Option(45, "castigo: correr + 2B", "6 5 6[8]2B") if d > LIGHT_RANGE
                       else Option(45, "castigo: 2B", "2B"),
                       Option(20, "castigo: barrida 2D", "2D") if d <= 110 else
                       Option(20, "castigo: poke", m["poke"])]
            return Proposal("castigo a golpe fallado", options)
        return None

    def _attack_proposal(self, state):
        if self.strategy is None:
            return None
        d = state.distance
        return Proposal(*self.strategy.options(state, self._moves, Option,
                                               self._in_range(self._moves["combos"], d),
                                               state.me.life - state.rival.life))

    def _defense_options(self, state, allow_punish):
        """Sistema defensivo original (sin cambios de reglas ni tiempos). Con
        allow_punish=False no castiga: el castigo lo propone _punish_proposal."""
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

        if allow_punish and self._can_punish(state):
            # El rival fallo o le bloquee un ataque: mi turno, con combo segun la distancia.
            punish = self._in_range(m["punish"], d) or self._in_range(m["combos"], d)
            options = [Option(45 / max(len(punish), 1), f"castigo: {name}", notation)
                       for name, notation in punish.items()]
            options += self._dm_combos(me, d, total_weight=35, prefix="castigo DM")
            return "castigar", options + [
                Option(12, "agarre", "6C") if d <= CLOSE_C_RANGE else Option(12, "barrida 2D", "2D"),
                Option(8, "golpe bajo 2B", "2B"),
            ]

        if self._rival_jumping_in(state):
            # El anti-aire no es automatico: cubrirse de pie tambien es una respuesta
            # valida (y segura); el aprendizaje mide cual conviene en cada distancia.
            options = [
                Option(40, "anti-aire especial", m["anti_air"]),
                Option(25, "anti-aire normal", m["anti_air_normal"]),
                Option(35, "guardia", "G[15]"),
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
                Option(10, "backdash", "4 5 4") if not state.back_to_wall else Option(10, "roll adelante", "AB"),
                Option(5, "reversal", m["reversal"]),
            ]

        if self._under_pressure(state):
            # Entre golpes de una cadena del rival: seguir cubierto hasta que termine.
            escape = (Option(8, "roll adelante (salir de la esquina)", "AB") if state.back_to_wall
                      else Option(8, "backdash", "4 5 4"))
            return "presion del rival", [
                Option(80, "guardia", "G[10]"),
                escape,
                Option(6, "roll atras", "4AB") if not state.back_to_wall else Option(6, "salto adelante", "9[8]"),
            ]

        if state.back_to_wall and d <= MID and not rival.airborne:
            # Acorralado: no retroceder contra la pared; cubrirse, salir rodando o saltando,
            # o castigar/atacar si hay rango.
            in_range = self._in_range(m["combos"], d)
            attack = [Option(15 / max(len(in_range), 1), f"combo: {name}", notation)
                      for name, notation in in_range.items()]
            return "acorralado", attack + [
                Option(40, "guardia", "G[14]"),
                Option(20, "roll adelante (salir de la esquina)", "AB"),
                Option(10, "salto adelante", "9[8]"),
                Option(10, "poke", m["poke"]),
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
        combos += self._dm_combos(me, d, total_weight=15, prefix="combo DM")
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
