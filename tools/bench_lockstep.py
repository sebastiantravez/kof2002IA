"""Mide la velocidad maxima de la conexion por frames (sin bot): responde a cada
frame lo mas rapido posible con turbo activado. Uso: python tools/bench_lockstep.py [segundos]"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kof_ai.lockstep import Lockstep  # noqa: E402

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 10
hold = int(sys.argv[2]) if len(sys.argv) > 2 else 1   # frames por intercambio
link = Lockstep(ROOT)
link.on_round_end = lambda s: None
link.step()
link.send("TURBO")
start = time.perf_counter()
python_time = 0.0
frames = 0
exchanges = 0
while time.perf_counter() - start < seconds:
    t0 = time.perf_counter()
    link.step(hold)
    python_time += time.perf_counter() - t0
    frames += hold
    exchanges += 1
elapsed = time.perf_counter() - start
link.send("NORMAL")
link.step()
print(f"{frames} frames en {elapsed:.1f}s = {frames / elapsed:.0f} fps ({frames / elapsed / 59.19:.1f}x)")
print(f"{hold} frames por intercambio; {1000 * python_time / exchanges:.2f} ms por intercambio")
