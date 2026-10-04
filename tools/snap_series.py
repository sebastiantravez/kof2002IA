"""Guarda cada N segundos una captura del juego + la RAM de los jugadores (state.txt).

Sirve para identificar datos en la RAM mirando las capturas (por ejemplo, el ID de
personaje). Uso: python tools/snap_series.py [segundos_total] [intervalo]
"""
import json
import shutil
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kof_ai import emulator  # noqa: E402
from kof_ai.capture import WindowCapture  # noqa: E402

total = float(sys.argv[1]) if len(sys.argv) > 1 else 600
interval = float(sys.argv[2]) if len(sys.argv) > 2 else 3
config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
hwnd, _ = emulator.find_emulator_window(config["emulator_processes"])
out = ROOT / "recordings" / f"snaps_{time.strftime('%H%M%S')}"
out.mkdir(parents=True, exist_ok=True)
cap = WindowCapture(hwnd)
start = time.time()
n = 0
while time.time() - start < total:
    if not emulator.is_window(hwnd):
        print("El emulador se cerro.")
        break
    try:
        image = cap.grab()
        frame = (ROOT / "state.txt").read_text().split()[0]
        shutil.copy(ROOT / "state.txt", out / f"{n:04d}_f{frame}.txt")
        if image is not None and image.size:   # ventana minimizada: solo la RAM
            cv2.imwrite(str(out / f"{n:04d}_f{frame}.png"), image)
        n += 1
    except (OSError, IndexError, cv2.error):
        pass
    time.sleep(interval)
print(f"{n} capturas en {out}")
