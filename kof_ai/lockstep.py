"""Conexion frame a frame con lua/kof_train.lua (entrenamiento acelerado).

El emulador avanza un frame solo cuando Python responde, asi que el juego puede ir
sin limite de velocidad y el bot sigue decidiendo a tiempo. Teclado, reloj y lector
virtuales con la misma interfaz que VirtualKeyboard, FrameClock y StateReader: el
cerebro, los combos y la guardia funcionan igual, pero por frames y sin foco.
"""
import time
from pathlib import Path

from .game_state import STRUCT_SIZE, Fighter, GameState

# Bytes del struct de cada jugador que envia lua/kof_train.lua (misma lista que OFFSETS
# alli): x, altura, x/y en pantalla, personaje, agarre, flags, vida, barras. Enviar
# solo estos en vez de los 512 bytes acelera mucho cada frame.
ROUND_MAX_FRAMES = 80 * 60   # ronda sin KO mas larga que esto: recargar igual

SPARSE_OFFSETS = (0x18, 0x19, 0x20, 0x21, 0x24, 0x25, 0x26, 0x27, 0x71, 0x73, 0xE0, 0x139, 0x1E3)


def _fighter_from_sparse(hex_bytes):
    raw = bytearray(STRUCT_SIZE)
    for off, value in zip(SPARSE_OFFSETS, bytes.fromhex(hex_bytes)):
        raw[off] = value
    return Fighter.from_bytes(bytes(raw))


class Lockstep:
    def __init__(self, root, me_is_p1=True, timeout=10.0, max_wait=600.0):
        root = Path(root)
        self.req = root / "lock_req.txt"
        self.resp = root / "lock_resp.txt"
        self.me_is_p1 = me_is_p1
        self.timeout = timeout       # tras esto se avisa que el script no responde
        self.max_wait = max_wait     # y tras esto se abandona
        self.on_reconnect = None     # callback() si el script Lua se reinicio
        self.on_step = None          # callback(estado, teclas) en cada intercambio (registro)
        self.last_seq = None
        # Pedido que ya estaba en el archivo al arrancar: es de un script Lua anterior
        # (posiblemente ya detenido); no tomarlo como conexion.
        try:
            self._stale_seq = int(self.req.read_text().split()[0])
        except (OSError, ValueError, IndexError):
            self._stale_seq = None
        self.state = None
        self.keys = set()
        self.frames = 0
        self.on_round_end = None   # callback(estado) al terminar una ronda (vida 0)
        # Recargar al terminar la ronda solo despues de guardar el punto de reinicio de
        # ESTA sesion: la ranura 1 puede tener una partida vieja (p.ej. modo practica).
        self.auto_reset = False
        # Lote de ordenes pendiente: se repite en cada respuesta hasta que Lua confirma
        # (ack) que lo ejecuto; Lua ejecuta cada id una sola vez.
        self._batch_id = 0
        self._batch = []
        self._ack = 0
        self._resetting = False
        self._round_start = 0

    def send(self, *commands):
        """Ordenes para el script Lua: SAVE, LOAD, TURBO, NORMAL."""
        if self._ack >= self._batch_id:   # el lote anterior ya se ejecuto: empezar otro
            self._batch_id += 1
            self._batch = []
        self._batch.extend(commands)

    @property
    def commands_pending(self):
        return self._ack < self._batch_id

    def step(self, hold=1):
        """Espera el siguiente pedido del emulador, responde con las teclas actuales
        (mantenerlas 'hold' frames sin volver a preguntar) y devuelve el estado. Al
        terminar una ronda recarga la partida guardada."""
        seq, _, self._ack, p1, p2 = self._wait_request()
        if self._ack > self._batch_id:
            # El script Lua viene de una sesion anterior: seguir su numeracion de lotes.
            self._batch_id = self._ack + (1 if self._batch else 0)
        me, rival = (p1, p2) if self.me_is_p1 else (p2, p1)
        # Contador propio de frames: el del emulador retrocede al cargar la partida
        # guardada, y el cerebro mide tiempos con restas de frames.
        self.state = GameState(self.frames, me, rival)
        ko = me.life == 0 or rival.life == 0
        too_long = self.frames - self._round_start > ROUND_MAX_FRAMES
        if (ko or too_long) and not self._resetting and self.auto_reset:
            # Fin de ronda (o ronda eterna): recargar el inicio. Nunca dejar que el
            # juego llegue a fin por tiempo ni a las pantallas de transicion del
            # arcade: ahi el emulador detiene el script Lua.
            self._resetting = True
            self.send("LOAD")
            if self.on_round_end:
                self.on_round_end(self.state)
        elif self._resetting and me.life > 0 and rival.life > 0:
            self._resetting = False
            self._round_start = self.frames
        if self.on_step and not self._resetting:
            self.on_step(self.state, self.keys)
        self._respond(seq, hold)
        self.frames += hold
        return self.state

    def _wait_request(self):
        """Linea "seq frame ack p1 p2 seq"; si los dos seq no coinciden, Lua la estaba
        escribiendo: se descarta y se vuelve a leer."""
        size = len(SPARSE_OFFSETS) * 2
        start = time.time()
        warned = False
        while time.time() - start < self.max_wait:
            if not warned and time.time() - start > self.timeout:
                print("kof_train.lua no responde: esperando que vuelva (Restart en la ventana de Lua)...")
                warned = True
            try:
                parts = self.req.read_text().split()
            except OSError:
                continue
            if len(parts) != 6 or parts[0] != parts[5] or len(parts[3]) != size or len(parts[4]) != size:
                continue
            seq = int(parts[0])
            if self.last_seq is None and seq == self._stale_seq:
                time.sleep(0.01)   # archivo viejo: esperar a que el script Lua escriba
                continue
            if seq == self.last_seq:
                time.sleep(0 if not warned else 0.01)
                continue
            if self.last_seq is not None and seq < self.last_seq:
                # El script se reinicio (su contador volvio a empezar).
                print("kof_train.lua se reinicio: reconectado.")
                if self.on_reconnect:
                    self.on_reconnect()
            self.last_seq = seq
            return (seq, int(parts[1]), int(parts[2]),
                    _fighter_from_sparse(parts[3]), _fighter_from_sparse(parts[4]))
        raise TimeoutError("lua/kof_train.lua no responde: cargalo en el emulador")

    def _respond(self, seq, hold):
        """Linea "seq|teclas|ordenes|hold|seq" reescrita en el mismo lugar (el seq
        repetido al final permite a Lua descartar una lectura a medio escribir)."""
        commands = f"{self._batch_id}:{' '.join(self._batch)}" if self.commands_pending else ""
        line = f"{seq}|{','.join(sorted(self.keys))}|{commands}|{hold}|{seq}\n"
        for _ in range(50):
            try:
                with open(self.resp, "w") as f:
                    f.write(line)
                return
            except PermissionError:
                time.sleep(0)


class LockstepKeyboard:
    def __init__(self, link):
        self.link = link

    def set_state(self, logical_keys):
        self.link.keys = set(logical_keys)

    def release_all(self):
        self.link.keys = set()

    @property
    def _pressed(self):   # para el diagnostico de tools/fight_test.py
        return self.link.keys


class LockstepClock:
    """Agrupa frames por intercambio con el emulador (cada uno cuesta varios ms):
    de a WATCH_CHUNK si hay que vigilar algo (should_stop), si no hasta FREE_CHUNK."""
    WATCH_CHUNK = 2
    FREE_CHUNK = 8

    def __init__(self, link):
        self.link = link

    def wait_frames(self, frames, should_stop=None):
        remaining = frames
        while remaining > 0:
            if should_stop and should_stop():
                return False
            chunk = min(remaining, self.WATCH_CHUNK if should_stop else self.FREE_CHUNK)
            self.link.step(chunk)
            remaining -= chunk
        return True


class LockstepReader:
    live = True   # el cerebro lee en cada llamada (sin cache por tiempo)

    def __init__(self, link):
        self.link = link

    def read(self):
        return self.link.state

    def single_source(self, samples=8):
        return True
