"""Estado de la pelea leido del archivo que exporta lua/kof_state.lua.

Offsets de la estructura de cada jugador (P1 en 0x108100, P2 en 0x108300),
verificados en KOF 2002 moviendo, saltando y golpeando:
    +0x18 word  X en el escenario
    +0x20 word  altura sobre el suelo (0 = en el suelo)
    +0x24 word  X en pantalla (0..304)
    +0x26 word  Y en pantalla (220 = suelo, menor = mas alto)
    +0x031 byte 1 = mira a la derecha, 0 = a la izquierda (orientacion REAL del juego)
    +0x0E0 bit0 en animacion de ataque (arranque + activo + recuperacion)
    +0x0E0 bit2 agachado quieto (se apaga al atacar agachado)
    +0x139 byte vida (102 = llena)
    +0x071 byte ID de personaje (ver CHARACTER_IDS)
    +0x073 bit1 lo estan agarrando
    +0x1E3 byte barras de poder llenas (0..5)
"""
import time
from dataclasses import dataclass
from pathlib import Path

MAX_LIFE = 102
# Paredes del escenario (x en el escenario), medidas en las grabaciones: picos de
# personajes acorralados en x~32 y x~736-751.
LEFT_WALL_X = 32
RIGHT_WALL_X = 751
CORNER_MARGIN = 28
CHARACTER_OFFSET = 0x071
# Verificados con capturas de una repeticion (KOF 2002 Plus): Kyo 0, Kim 6, Choi 8, Iori 21.
# 39 = Rugal: deducido (el usuario vio a Rugal y un jugador lo uso toda la repeticion), sin captura.
CHARACTER_IDS = {0: "Kyo", 6: "Kim", 8: "Choi", 9: "Athena", 11: "Chin", 21: "Iori", 39: "Rugal"}
STRUCT_SIZE = 0x200


@dataclass(frozen=True)
class Fighter:
    x: int
    screen_x: int
    screen_y: int
    height: int
    life: int

    @property
    def life_pct(self):
        return min(100, round(self.life * 100 / MAX_LIFE))

    attacking: bool = False
    crouching: bool = False
    character_id: int = -1
    stocks: int = 0          # barras de poder llenas (para DMs)
    state_id: int = 0        # +0x073: identificador de animacion/estado (ver STATE_OFFSET)
    facing_right_raw: int = -1   # +0x031 del juego: 1 derecha, 0 izquierda, -1 desconocido

    @property
    def character(self):
        return CHARACTER_IDS.get(self.character_id, f"id{self.character_id}")

    @property
    def airborne(self):
        return self.height > 0

    @classmethod
    def from_bytes(cls, raw):
        word = lambda off: int.from_bytes(raw[off:off + 2], "big")
        return cls(x=word(0x18), screen_x=word(0x24), screen_y=word(0x26),
                   height=word(0x20), life=raw[0x139], attacking=_is_attacking(raw),
                   crouching=_is_crouching(raw), character_id=raw[CHARACTER_OFFSET],
                   stocks=raw[POWER_OFFSET] if POWER_OFFSET is not None else 0,
                   state_id=raw[STATE_OFFSET], facing_right_raw=raw[FACING_OFFSET])

    @property
    def down(self):
        """Derribado (cayendo, tirado o levantandose): los botones no hacen nada."""
        return self.state_id in DOWN_STATES

    @property
    def thrown(self):
        """Me estan agarrando: estado 168 (medido en tools/guard_test.py, agarres C y D de Kim
        sobre Iori, 20/20; empieza en el frame en que atrapan y NO enciende el bit de ataque)."""
        return self.state_id in THROWN_STATES


# Bit "en animacion de ataque" (encontrado con tools/probe_attack.py): se enciende en el
# primer frame de C, 2B, D, 236A... y dura hasta el fin de la recuperacion. No se enciende
# al caminar, agacharse, estar quieto ni al recibir golpes.
ATTACK_OFFSET = 0x0E0
ATTACK_MASK = 0x01


def _is_attacking(raw):
    return ATTACK_OFFSET is not None and bool(raw[ATTACK_OFFSET] & ATTACK_MASK)


# Bit "agachado quieto" (encontrado con tools/probe_crouch.py): encendido al mantener
# abajo (2 o 1); se apaga al empezar un ataque agachado (2B, 2D), por eso el cerebro
# considera "amenaza baja" un ataque que empieza justo despues de estar agachado.
CROUCH_OFFSET = 0x0E0
CROUCH_MASK = 0x04


# Encontrados con tools/probe_throw_power.py (modo practica, Kim agarrando al dummy y
# haciendo un DM): +0x073 bit1 se enciende mientras te agarran (con C y con D) y nunca
# al recibir golpes normales; +0x1E3 = barras de poder llenas (5 -> 4 al hacer un DM).
# OJO: +0x073 bit1 dio falsos positivos en arcade (se encendia 276 veces en 98 s, no solo
# en agarres). Desactivado hasta verificarlo con tools/probe_thrown_verify.py.
THROWN_OFFSET = None
THROWN_MASK = 0x02
# +0x073 = identificador de animacion/estado del jugador (encontrado 2026-10-14 con
# tools/find_move_id.py y tools/state_table.py sobre grabaciones etiquetadas): 0 en reposo,
# un valor fijo por movimiento mientras dura (Iori: 98 = 6C, 129 = 236C, 183 = patada aerea...),
# reacciones al golpe 148/149/151/169. Por eso el "bit1 = agarrado" daba falsos positivos:
# era este byte. La tabla de valores (bloqueo, agarre, por personaje) se completa con
# tools/guard_test.py en modo versus.
STATE_OFFSET = 0x73
# Orientacion real (encontrado 2026-10-16 en 8 volcados .bin: coincide con la posicion el 95-99% y
# los desacuerdos son el juego girando tarde: levantarse de espaldas, cruces). Decide hacia donde
# se cubre: en la esquina, levantandose mirando a la pared, la guardia por posicion salia al reves.
FACING_OFFSET = 0x31
# Valores de +0x073 medidos en tools/guard_test.py (Iori defendiendo, Kim atacando, 2026-10-14):
THROWN_STATES = {168}                      # agarrado (entrada del agarre, C y D)
BLOCKSTUN_STATES = set(range(27, 38))      # bloqueando: 27-31 de pie, 32-37 agachado (segun golpe)
THROWING_STATES = {229, 230, 231, 232}     # Kim agarrando (C: 229-231, D: 232); otros personajes: por medir
# Movimientos del rival que hay que bloquear AGACHADO (golpes bajos que no salen de agachado, asi que
# el bit de agachado no los delata), por personaje. Kim 137 = Haki Kyaku (abajo-abajo + D, golpea el
# piso): pelea 2026-10-15, 18 de 22 entraron con Iori cubriendo DE PIE, 9-10 de danio cada uno.
#  Kim 144/146 = arranque y barrida del Hou'ou Kyaku (DM): si esa barrida entra, el resto (167, 14 de
#  danio por golpe) ya no se bloquea. Pelea 19:27: 5 veces, las 5 con Iori cubriendo DE PIE.
LOW_HIT_STATES = {"Kim": {137, 144, 146}}
# Derribado: cayendo al suelo (78), tirado (73) y levantandose (72, ~50 frames). Medido en las trazas
# del 2026-10-15 (Iori): 20 entradas, 0 ataques salieron con el boton pulsado dentro, las rodadas y
# castigos que el bot pidio ahi se perdieron. Lo unico util es levantarse cubierto.
DOWN_STATES = {72, 73, 78}
# Movimientos que hay que bloquear DE PIE (overheads de pie): ninguno medido aun.
OVERHEAD_STATES = {}
POWER_OFFSET = 0x1E3


def _is_crouching(raw):
    return CROUCH_OFFSET is not None and bool(raw[CROUCH_OFFSET] & CROUCH_MASK)


@dataclass(frozen=True)
class GameState:
    frame: int
    me: Fighter
    rival: Fighter

    @property
    def distance(self):
        return abs(self.rival.x - self.me.x)

    @property
    def facing_right(self):
        """Hacia donde mira el juego a mi personaje (+0x31); por posicion si no se conoce."""
        if self.me.facing_right_raw in (0, 1):
            return self.me.facing_right_raw == 1
        return self.me.x <= self.rival.x

    @property
    def back_to_wall(self):
        """Estoy acorralado: la pared esta detras de mi (no puedo retroceder)."""
        if self.facing_right:
            return self.me.x <= LEFT_WALL_X + CORNER_MARGIN
        return self.me.x >= RIGHT_WALL_X - CORNER_MARGIN

    def near_wall(self, margin=100):
        """La pared que tengo detras esta a menos de `margin`: retroceder me acorrala. Pelea
        2026-10-15: Iori acorralado el 58% del tiempo recibiendo 240/min (153/min libre)."""
        if self.facing_right:
            return self.me.x <= LEFT_WALL_X + margin
        return self.me.x >= RIGHT_WALL_X - margin

    @property
    def rival_cornered(self):
        if self.facing_right:
            return self.rival.x >= RIGHT_WALL_X - CORNER_MARGIN
        return self.rival.x <= LEFT_WALL_X + CORNER_MARGIN


class StateReader:
    """Lee el ultimo estado. Devuelve None si el script Lua no esta corriendo."""

    def __init__(self, path, me_is_p1=True, stale_seconds=0.5):
        self.path = Path(path)
        self.me_is_p1 = me_is_p1
        self.stale_seconds = stale_seconds

    def single_source(self, samples=8):
        """False si dos emuladores escriben state.txt a la vez (los frames saltan
        hacia atras): el bot mezclaria dos peleas."""
        frames = []
        for _ in range(samples):
            state = self.read()
            if state:
                frames.append(state.frame)
            time.sleep(0.03)
        return all(b >= a for a, b in zip(frames, frames[1:]))

    def read(self):
        # El script Lua borra y renombra el archivo en cada frame: reintentar un poco
        # cubre el instante en que no existe.
        for _ in range(30):
            try:
                if time.time() - self.path.stat().st_mtime > self.stale_seconds:
                    return None
                lines = self.path.read_text().split()
            except OSError:
                time.sleep(0.002)
                continue
            if len(lines) != 3 or any(len(line) != STRUCT_SIZE * 2 for line in lines[1:]):
                time.sleep(0.002)
                continue
            p1 = Fighter.from_bytes(bytes.fromhex(lines[1]))
            p2 = Fighter.from_bytes(bytes.fromhex(lines[2]))
            me, rival = (p1, p2) if self.me_is_p1 else (p2, p1)
            return GameState(int(lines[0]), me, rival)
        return None
