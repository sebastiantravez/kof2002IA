"""Guarda capturas del area de juego en captures/ para calibrar la vision.

Uso: python tools/snapshot.py [cantidad] [segundos_entre_capturas]
"""
import json
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kof_ai import emulator  # noqa: E402
from kof_ai.capture import WindowCapture  # noqa: E402

config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
interval = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5

found = emulator.find_emulator_window(config["emulator_processes"])
if not found:
    sys.exit("Emulador no encontrado. Abre KOF 2002 en Fightcade.")
hwnd, title = found
out = ROOT / "captures"
out.mkdir(exist_ok=True)
cap = WindowCapture(hwnd)
for i in range(count):
    frame = cap.grab()
    path = out / f"frame_{int(time.time() * 1000)}.png"
    cv2.imwrite(str(path), frame)
    print(f"{path} {frame.shape[1]}x{frame.shape[0]}")
    time.sleep(interval)
cap.close()
