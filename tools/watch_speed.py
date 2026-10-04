"""Mide la velocidad real del emulador (frames por segundo de reloj) leyendo
lua_frame.txt, que escribe lua/test_capacidades.lua. Uso: python tools/watch_speed.py [segundos]"""
import sys
import time
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "lua_frame.txt"
total = float(sys.argv[1]) if len(sys.argv) > 1 else 40
start = time.time()
last = None
while time.time() - start < total:
    try:
        frame = int(PATH.read_text().split()[0])
    except (OSError, ValueError, IndexError):
        time.sleep(0.05)
        continue
    now = time.time()
    if last and frame != last[0]:
        fps = (frame - last[0]) / (now - last[1])
        if frame - last[0] >= 60:
            print(f"t={now - start:5.1f}s frame {frame:5d}  {fps:6.0f} fps ({fps / 59.19:.1f}x)")
            last = (frame, now)
    elif last is None:
        last = (frame, now)
    if frame >= 885:
        break
    time.sleep(0.05)
