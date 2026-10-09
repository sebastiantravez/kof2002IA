"""Movimientos en notacion numerica (numpad), la estandar de juegos de pelea.

    7 8 9        arriba-atras   arriba   arriba-adelante
    4 5 6   =>   atras          neutro   adelante
    1 2 3        abajo-atras    abajo    abajo-adelante

Todo se define mirando a la derecha; si el personaje mira a la izquierda
se espeja (4 <-> 6, 1 <-> 3, 7 <-> 9).
"""
import ctypes
import time
from dataclasses import dataclass

_DIRECTION_KEYS = {
    1: ("down", "left"),
    2: ("down",),
    3: ("down", "right"),
    4: ("left",),
    5: (),
    6: ("right",),
    7: ("up", "left"),
    8: ("up",),
    9: ("up", "right"),
}
_MIRROR = {1: 3, 3: 1, 4: 6, 6: 4, 7: 9, 9: 7}
BUTTONS = "ABCD"


@dataclass(frozen=True)
class Step:
    direction: int
    buttons: str
    frames: int


def parse(notation, step_frames=2, button_frames=3):
    """Convierte '236A', '214B', '2[40]8A' (carga) o '6C' en pasos.

    '[N]' tras una direccion la mantiene N frames (para cargas); tras botones ('6C[4]', 'B[2]')
    los mantiene N frames en vez de button_frames (inputs grabados al frame).
    """
    steps = []
    i = 0
    while i < len(notation):
        ch = notation[i]
        if ch.isdigit():
            direction = int(ch)
            frames = step_frames
            if i + 1 < len(notation) and notation[i + 1] == "[":
                end = notation.index("]", i)
                frames = int(notation[i + 2:end])
                i = end
            buttons = ""
            while i + 1 < len(notation) and notation[i + 1] in BUTTONS:
                buttons += notation[i + 1]
                i += 1
            if buttons:
                held, i = _held(notation, i, button_frames)
                steps.append(Step(direction, buttons, held))
            else:
                steps.append(Step(direction, buttons, frames))
        elif ch in BUTTONS:
            buttons = ch
            while i + 1 < len(notation) and notation[i + 1] in BUTTONS:
                buttons += notation[i + 1]
                i += 1
            held, i = _held(notation, i, button_frames)
            steps.append(Step(5, buttons, held))
        elif ch != " ":
            raise ValueError(f"Caracter invalido en {notation!r}: {ch!r}")
        i += 1
    steps.append(Step(5, "", 1))
    return steps


def _held(notation, i, default):
    """'6C[4]': boton(es) mantenidos N frames (para reproducir inputs grabados al frame).
    Devuelve (frames, indice del ultimo caracter usado)."""
    if i + 1 < len(notation) and notation[i + 1] == "[":
        end = notation.index("]", i + 1)
        return int(notation[i + 2:end]), end
    return default, i


def keys_for(direction, buttons, facing_right=True):
    if not facing_right:
        direction = _MIRROR.get(direction, direction)
    return set(_DIRECTION_KEYS[direction]) | set(buttons)


class FrameClock:
    """Espera por frames del juego con precision de ~1 ms."""

    def __init__(self, fps):
        self.frame = 1.0 / fps
        ctypes.WinDLL("winmm").timeBeginPeriod(1)

    def wait_frames(self, frames, should_stop=None):
        deadline = time.perf_counter() + frames * self.frame
        while True:
            if should_stop and should_stop():
                return False
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return True
            if remaining > 0.002:
                time.sleep(min(remaining - 0.0015, self.frame))


def play(keyboard, clock, steps, facing_right=True, should_stop=None):
    """Ejecuta los pasos en el teclado virtual. Devuelve False si se cancelo."""
    try:
        for step in steps:
            keyboard.set_state(keys_for(step.direction, step.buttons, facing_right))
            if not clock.wait_frames(step.frames, should_stop):
                return False
        return True
    finally:
        keyboard.release_all()


# Comandos genericos y algunos de Terry Bogard para la prueba.
# Verifica la lista de movimientos de tu personaje en KOF 2002.
MOVES = {
    "Cuarto de circulo adelante (236A)": "236A",
    "Cuarto de circulo atras (214A)": "214A",
    "Dragon punch (623A)": "623A",
    "Medio circulo adelante (41236C)": "41236C",
    "Terry - Power Wave (236A)": "236A",
    "Terry - Burn Knuckle (214A)": "214A",
    "Terry - Crack Shoot (214B)": "214B",
    "Terry - Rising Tackle (2[45]8A)": "2[45]8A",
    "Correr (66)": "6 5 6[30]",
    "Retroceso / backdash (44)": "4 5 4",
    "Roll adelante (AB)": "AB",
}
