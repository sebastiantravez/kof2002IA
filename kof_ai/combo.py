"""Combos con confirmacion de golpe (hit-confirm).

Notacion: partes separadas por '>', por ejemplo "2B>2A>3D" o "C>236C>63214A".
Cada parte se ejecuta cuando la anterior CONECTA: en KOF el siguiente golpe solo
encadena si se pulsa despues del impacto, no antes. Si una parte no conecta
(bloqueada o fallada) el combo se corta y no queda vendido.

Un impacto = la vida del rival baja de un frame al siguiente. No se compara con la
vida de antes del combo porque en modo practica la vida del dummy se regenera.
"""
from .motions import parse, play

SEPARATOR = ">"
CONFIRM_TIMEOUT = 24   # frames maximos esperando a que conecte cada parte
# Los DM (supers) golpean despues de la pausa de "super" y su recorrido: el danio
# llega mucho mas tarde que en un golpe normal.
DM_CONFIRM_TIMEOUT = 150
DM_MIN_DIRECTIONS = 7  # un movimiento de 7+ direcciones (236 63214, 214 41236...) es un DM


def is_dm(notation):
    """True si la notacion contiene el movimiento largo de un DM."""
    return sum(ch.isdigit() for ch in notation.split("[")[0]) >= DM_MIN_DIRECTIONS


def is_combo(notation):
    return SEPARATOR in notation


def play_combo(keyboard, clock, notation, facing_right, rival_life, step_frames, button_frames,
               should_stop=None, after_hit_delay=2):
    """Ejecuta el combo. rival_life() devuelve la vida actual del rival.
    Devuelve (partes_que_conectaron, danio, completado). Si should_stop corta, completado=False."""
    watch = _HitWatcher(rival_life, should_stop)
    parts = notation.split(SEPARATOR)
    connected = 0
    for i, part in enumerate(parts):
        watch.hit = False
        if not play(keyboard, clock, parse(part, step_frames, button_frames), facing_right, watch):
            return connected, watch.damage, False
        timeout = DM_CONFIRM_TIMEOUT if is_dm(part) else CONFIRM_TIMEOUT
        if not watch.hit and not _wait_hit(clock, watch, timeout):
            return connected, watch.damage, i == len(parts) - 1   # no conecto: cortar el combo
        connected += 1
        if after_hit_delay and i < len(parts) - 1:
            clock.wait_frames(after_hit_delay, watch)
    # recoger el danio de los ultimos golpes (un DM sigue pegando mucho tiempo)
    clock.wait_frames(DM_CONFIRM_TIMEOUT if is_dm(parts[-1]) else 20, watch)
    return connected, watch.damage, True


class _HitWatcher:
    """Callback para play(): detecta bajadas de vida del rival frame a frame."""

    def __init__(self, rival_life, should_stop):
        self._rival_life = rival_life
        self._should_stop = should_stop
        self._last = rival_life()
        self.hit = False
        self.damage = 0

    def __call__(self):
        life = self._rival_life()
        if life is not None:
            if self._last is not None and life < self._last:
                self.hit = True
                self.damage += self._last - life
            self._last = life
        return bool(self._should_stop and self._should_stop())


def _wait_hit(clock, watch, timeout=CONFIRM_TIMEOUT):
    for _ in range(timeout):
        if not clock.wait_frames(1, watch):
            return False
        if watch.hit:
            return True
    return False
