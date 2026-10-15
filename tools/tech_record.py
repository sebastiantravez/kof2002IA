"""Graba COMO SUELTA UNA PERSONA un agarre: Kim (P2, scriptada) agarra con C o D y la persona, en
P1 con Iori, pulsa C/D para soltarse. Se registra frame a frame cuando pulsa y si lo agarraron.

Mide dos cosas que el barrido scriptado de tools/guard_test.py no pudo resolver:
  - en que frame (respecto al boton de Kim) pulsa quien SI logra soltarse;
  - en que frame la RAM muestra el agarre (estado 229-232 de Kim, 168 de Iori) frente a eso.

Requisitos: modo VERSUS, Iori en P1 (la persona), Kim en P2, cronometro en 99, kof_train.lua
cargado (version con lock_pad.txt: las teclas de P1 de la persona pasan al juego, el bot no
manda nada a P1). Uso: python tools/tech_record.py [--trials=30]
Salida: logs/tech_<fecha>/intentos.csv y frames.csv, y una tabla resumen.
"""
import csv
import random
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kof_ai.game_state import THROWING_STATES, THROWN_STATES  # noqa: E402
from kof_ai.lockstep import Lockstep  # noqa: E402
from kof_ai.motions import keys_for  # noqa: E402

START_DISTANCE = 120
LOAD_SETTLE = 20
GRAB_DISTANCE = 12
BITS = {1: "up", 2: "down", 4: "left", 8: "right", 16: "A", 32: "B", 64: "C", 128: "D"}

opt = {a.split("=")[0]: (a.split("=", 1)[1] if "=" in a else True) for a in sys.argv[1:] if a.startswith("--")}
TRIALS = int(opt.get("--trials", 30))
PAD_FILE = ROOT / "lock_pad.txt"

link = Lockstep(ROOT)
print("Esperando a lua/kof_train.lua...")
first = link.step()
print(f"P1 = {first.me.character} (persona), P2 = {first.rival.character} (este script)")


def read_pad(seq):
    """Mascara de teclas fisicas de P1 para este seq (0 si el archivo no corresponde)."""
    for _ in range(20):
        try:
            parts = PAD_FILE.read_text().split()
        except OSError:
            continue
        if len(parts) == 3 and parts[0] == parts[2] and int(parts[0]) == seq:
            return int(parts[1])
    return 0


def p2_keys(st, direction, buttons=""):
    return set(keys_for(direction, buttons, st.rival.x <= st.me.x))


def step_with(p2=(), frames=1):
    link.keys, link.p2_keys = set(), set(p2)       # P1: nada, lo pone la persona
    for _ in range(frames):
        link.step()


def wait_commands():
    while link.commands_pending:
        step_with()


def pad_names(mask):
    return "+".join(n for b, n in BITS.items() if mask & b)


# ---------- preparacion ----------
for _ in range(300):                            # velocidad normal: la persona tiene que reaccionar
    d = link.state.distance
    if abs(d - START_DISTANCE) <= 4:
        break
    step_with(p2=p2_keys(link.state, 6 if d > START_DISTANCE else 4))
step_with(frames=20)
link.send("SAVE2")
wait_commands()
print(f"Posicion guardada. {TRIALS} intentos: Kim te agarra con C o D en momentos distintos.")
print("Tu: suelta con C o D (o ni lo intentes) cuando veas que Kim te va a agarrar. No te muevas.")
time.sleep(2)

out_dir = ROOT / "logs" / f"tech_{time.strftime('%Y%m%d_%H%M%S')}"
out_dir.mkdir(parents=True, exist_ok=True)
frames_f = open(out_dir / "frames.csv", "w", newline="", encoding="utf-8")
frames_w = csv.writer(frames_f)
frames_w.writerow(["intento", "t", "teclas_p1", "estado_p1", "estado_p2", "vida_p1", "boton_kim", "distancia"])
results = []

HALF = max(TRIALS // 2, 1)
for n in range(1, TRIALS + 1):
    # Primero un bloque con C y despues otro con D: la persona sabe con que boton va a soltar
    kb = "C" if n <= HALF else "D"
    if n in (1, HALF + 1):
        print(f"\n=== BLOQUE {kb}: Kim te agarra con {kb}; suelta con {kb} en cuanto veas el agarre ===")
        time.sleep(3)
    delay = random.randint(0, 45)               # espera antes del agarre: no se puede anticipar
    link.send("LOAD2")
    wait_commands()
    step_with(frames=LOAD_SETTLE)

    rows = []                                   # (t, mask, p1_state, p2_state, life, kim_button)
    life0 = link.state.me.life
    t = None                                    # None hasta que empieza el agarre; luego frames desde el boton
    pre = 0
    waited = 0
    for frame in range(400):
        st = link.state
        if t is None:
            if st.distance > GRAB_DISTANCE and pre < 150:
                keys, pre = p2_keys(st, 6), pre + 1
            elif waited < delay:
                keys, waited = set(), waited + 1
            else:
                t = -4
                keys = p2_keys(st, 6)
        if t is not None:
            if t < 0:
                keys = p2_keys(st, 6)
            elif t < 3:
                keys = p2_keys(st, 6, kb)
            elif t < 7:
                keys = p2_keys(st, 6)
            else:
                keys = set()
        link.keys, link.p2_keys = set(), set(keys)
        link.step()
        s = link.state
        mask = read_pad(link.last_seq)
        rows.append((t if t is not None else "", mask, s.me.state_id, s.rival.state_id, s.me.life,
                     kb if (t is not None and 0 <= t < 3) else ""))
        for r in (rows[-1],):
            frames_w.writerow([n, r[0], pad_names(r[1]), r[2], r[3], r[4], r[5], f"{s.distance:.0f}"])
        if t is not None:
            t += 1
            if t > 60:
                break
    frames_f.flush()

    # ---- resumen del intento ----
    timed = [r for r in rows if r[0] != ""]
    thrown = any(r[2] in THROWN_STATES for r in timed)
    grab_t = next((r[0] for r in timed if r[3] in THROWING_STATES), None)
    thrown_t = next((r[0] for r in timed if r[2] in THROWN_STATES), None)
    presses = [(r[0], pad_names(r[1])) for r in timed if r[1] & (64 | 128)]
    first_press = presses[0] if presses else None
    p1_seq = []
    for r in timed:
        if not p1_seq or p1_seq[-1] != r[2]:
            p1_seq.append(r[2])
    results.append({"intento": n, "boton_kim": kb, "agarrado": int(thrown),
                    "vida_perdida": life0 - timed[-1][4] if timed else 0,
                    "t_estado_kim": grab_t, "t_estado_p1_168": thrown_t,
                    "t_primera_pulsacion": first_press[0] if first_press else "",
                    "teclas_pulsacion": first_press[1] if first_press else "",
                    "estados_p1": " ".join(map(str, p1_seq))})
    r = results[-1]
    print(f"{n:2d}/{TRIALS} Kim {kb}  "
          + ("AGARRADO" if r["agarrado"] else "soltado/evitado")
          + (f"   pulsaste {r['teclas_pulsacion']} en t={r['t_primera_pulsacion']}" if first_press else "   sin pulsar C/D")
          + f"   (estado de Kim visible en t={grab_t})")

frames_f.close()
with open(out_dir / "intentos.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(results[0]))
    w.writeheader()
    w.writerows(results)

# ---------- tabla resumen: pulsacion (t respecto al boton de Kim) vs agarrado ----------
print("\nPulsacion de C/D (t = frames desde que Kim pulsa su boton; negativo = antes):")
buckets = Counter()
for r in results:
    p = r["t_primera_pulsacion"]
    key = "sin pulsar" if p == "" else f"{(int(p) // 3) * 3:+d}..{(int(p) // 3) * 3 + 2:+d}"
    buckets[(key, r["agarrado"])] += 1
for key in sorted({k for k, _ in buckets}, key=lambda k: (k != "sin pulsar", k)):
    print(f"  {key:>12s}   agarrado {buckets[(key, 1)]:3d}   no agarrado {buckets[(key, 0)]:3d}")
print(f"\nGuardado en {out_dir}")
