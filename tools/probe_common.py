"""Utilidades para buscar bits en la RAM del jugador (P1) mientras se le controla."""
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kof_ai import emulator  # noqa: E402
from kof_ai.keyboard import VirtualKeyboard  # noqa: E402
from kof_ai.motions import FrameClock, parse, play  # noqa: E402

STATE = ROOT / "state.txt"
config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
keyboard = VirtualKeyboard(config["keys"])
clock = FrameClock(config["fps"])


def read_raw():
    """(frame, struct P1, struct P2) del ultimo frame exportado por el script Lua."""
    for _ in range(50):
        try:
            lines = STATE.read_text().split()
            if len(lines) == 3 and len(lines[1]) == 1024 and len(lines[2]) == 1024:
                return int(lines[0]), bytes.fromhex(lines[1]), bytes.fromhex(lines[2])
        except OSError:
            pass
        time.sleep(0.002)
    raise SystemExit("Sin state.txt: carga lua/kof_state.lua")


def record(notation, frames, facing_right=True):
    """Ejecuta la notacion en paralelo y graba 'frames' frames: lista de (struct P1, struct P2)."""
    t = threading.Thread(target=play, args=(keyboard, clock, parse(notation), facing_right))
    t.start()
    samples, last = [], None
    while len(samples) < frames:
        frame, p1, p2 = read_raw()
        if frame != last:
            samples.append((p1, p2))
            last = frame
        time.sleep(0.004)
    t.join()
    return samples


def focus_emulator():
    found = emulator.find_emulator_window(config["emulator_processes"])
    if not found or not emulator.focus(found[0]):
        raise SystemExit("No se pudo dar foco al emulador.")
    clock.wait_frames(5)


def find_values(on_segments, off_frames):
    """Bytes cuyos valores en on_segments nunca aparecen en off_frames (y que toman
    algun valor 'on' en cada segmento). Devuelve [(cobertura, offset, valores_on, valores_off)]."""
    found = []
    for off in range(0x200):
        off_vals = {raw[off] for raw in off_frames}
        hits = [[raw[off] for raw in seg if raw[off] not in off_vals] for seg in on_segments]
        if all(hits):
            coverage = sum(map(len, hits))
            found.append((coverage, off, sorted({v for h in hits for v in h}), sorted(off_vals)))
    return sorted(found, reverse=True)


def find_bits(on_segments, off_frames):
    """Bits que nunca se encienden en off_frames y se encienden en cada segmento de on_segments.
    Devuelve [(cobertura, offset, mascara)] ordenado por cobertura."""
    found = []
    for off in range(0x200):
        for bit in range(8):
            mask = 1 << bit
            if any(raw[off] & mask for raw in off_frames):
                continue
            if all(any(raw[off] & mask for raw in seg) for seg in on_segments):
                coverage = sum(sum(1 for raw in seg if raw[off] & mask) for seg in on_segments)
                found.append((coverage, off, mask))
    return sorted(found, reverse=True)
