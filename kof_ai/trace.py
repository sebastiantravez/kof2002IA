"""Traza por frame: que teclas estaban aplicadas en cada jugador, que decidia el bot y el
estado observable de los dos personajes. Para ver EXACTAMENTE cuando Iori queda expuesto
(teclas sueltas, accion no interrumpible, recuperacion) en lugar de suponerlo.

Se conecta a Lockstep.on_step: cada fila es un intercambio con el emulador. Con
LockstepClock.WATCH_CHUNK = FREE_CHUNK = 1 cada intercambio es un frame.
Las teclas de una fila son las que se aplican desde ese frame hasta la fila siguiente.
"""
import csv
from pathlib import Path

COLUMNS = ["frame", "situacion", "accion", "teclas_p1", "teclas_p2", "distancia", "p1_mira_derecha",
           "p1_x", "p1_altura", "p1_vida", "p1_atacando", "p1_agachado",
           "p2_x", "p2_altura", "p2_vida", "p2_atacando", "p2_agachado", "nota"]


class FrameTrace:
    def __init__(self, path, bot_info=None):
        """bot_info() -> (situacion, accion, ...) que el bot esta ejecutando (o None)."""
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "w", newline="", encoding="utf-8")
        self._csv = csv.writer(self._file)
        self._csv.writerow(COLUMNS)
        self._bot_info = bot_info
        self.note = ""

    def observe(self, state, p1_keys, p2_keys=()):
        info = self._bot_info() if self._bot_info else ("", "")
        me, rival = state.me, state.rival
        self._csv.writerow([
            state.frame, info[0], info[1], "+".join(sorted(p1_keys)) or "-", "+".join(sorted(p2_keys)) or "-",
            state.distance, int(state.facing_right),
            me.x, me.height, me.life, int(me.attacking), int(me.crouching),
            rival.x, rival.height, rival.life, int(rival.attacking), int(rival.crouching), self.note])
        self.note = ""

    def close(self):
        self._file.close()
