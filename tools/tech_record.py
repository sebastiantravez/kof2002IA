"""Graba COMO SUELTA UNA PERSONA un agarre, frame a frame: quien agarra es un script y la persona
pulsa C/D para soltarse. Registra cuando pulsa y si lo agarraron.

Mide dos cosas que el barrido scriptado de tools/guard_test.py no pudo resolver:
  - en que frame (respecto al boton del que agarra) pulsa quien SI logra soltarse;
  - en que frame la RAM muestra el agarre frente a eso.

Papeles (--victim): "p2" (por defecto) = Iori P1 es scriptado y agarra con 6C / 6D, la persona
es P2 (Kim) y suelta; "p1" = al reves (Kim P2 scriptada agarra a la persona que juega Iori en P1).
Requisitos: modo VERSUS, cronometro en 99, kof_train.lua cargado (version con lock_pad.txt).
Uso: python tools/tech_record.py [--victim=p2|p1] [--trials=30]
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

from kof_ai.lockstep import Lockstep  # noqa: E402
from kof_ai.motions import keys_for  # noqa: E402

START_DISTANCE = 120
LOAD_SETTLE = 20
GRAB_DISTANCE = 12
IDLE_STATES = {0, 1, 2}
BITS = {1: "up", 2: "down", 4: "left", 8: "right", 16: "A", 32: "B", 64: "C", 128: "D"}

opt = {a.split("=")[0]: (a.split("=", 1)[1] if "=" in a else True) for a in sys.argv[1:] if a.startswith("--")}
TRIALS = int(opt.get("--trials", 30))
VICTIM = str(opt.get("--victim", "p2")).lower()          # quien suelta: la persona
PAD_FILE = ROOT / "lock_pad.txt"

link = Lockstep(ROOT)
print("Esperando a lua/kof_train.lua...")
first = link.step()
print(f"P1 = {first.me.character}, P2 = {first.rival.character}; la persona es "
      f"{'P2 (' + first.rival.character + ')' if VICTIM == 'p2' else 'P1 (' + first.me.character + ')'} "
      f"y suelta; el script agarra con {first.me.character if VICTIM == 'p2' else first.rival.character}.")


def read_pad(seq):
    """Mascara de teclas fisicas del jugador humano (la victima) para este seq (0 si no corresponde)."""
    for _ in range(20):
        try:
            parts = PAD_FILE.read_text().split()
        except OSError:
            continue
        if len(parts) == 4 and parts[0] == parts[3] and int(parts[0]) == seq:
            return int(parts[2] if VICTIM == "p2" else parts[1])
    return 0


def victim(st):
    return st.rival if VICTIM == "p2" else st.me


def attacker(st):
    return st.me if VICTIM == "p2" else st.rival


def att_keys(st, direction, buttons=""):
    """Teclas del script (el que agarra), con 6 = hacia la victima."""
    a, v = attacker(st), victim(st)
    return set(keys_for(direction, buttons, a.x <= v.x))


def step_with(att=(), frames=1):
    """Un frame: solo el script pulsa (la victima la pone la persona, sin teclas del bot)."""
    if VICTIM == "p2":
        link.keys, link.p2_keys = set(att), set()
    else:
        link.keys, link.p2_keys = set(), set(att)
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
    step_with(att_keys(link.state, 6 if d > START_DISTANCE else 4))
step_with(frames=20)
link.send("SAVE2")
wait_commands()
HALF = max(TRIALS // 2, 1)
print(f"Posicion guardada. {TRIALS} intentos: {HALF} con C y {TRIALS - HALF} con D.")
time.sleep(2)

out_dir = ROOT / "logs" / f"tech_{time.strftime('%Y%m%d_%H%M%S')}"
out_dir.mkdir(parents=True, exist_ok=True)
frames_f = open(out_dir / "frames.csv", "w", newline="", encoding="utf-8")
frames_w = csv.writer(frames_f)
frames_w.writerow(["intento", "t", "teclas_victima", "estado_victima", "estado_agarra", "vida_victima",
                   "boton_agarre", "distancia"])
results = []

for n in range(1, TRIALS + 1):
    kb = "C" if n <= HALF else "D"              # primero un bloque con C, despues otro con D
    if n in (1, HALF + 1):
        print(f"\n=== BLOQUE {kb}: te agarran con {kb}; suelta con {kb} en cuanto veas el agarre ===")
        time.sleep(3)
    delay = random.randint(0, 45)               # espera antes del agarre: no se puede anticipar
    link.send("LOAD2")
    wait_commands()
    step_with(frames=LOAD_SETTLE)

    rows = []                                   # (t, mask, victima, agarra, vida, boton)
    life0 = victim(link.state).life
    t = None                                    # None hasta que empieza el agarre; luego frames desde el boton
    pre = waited = 0
    for frame in range(400):
        st = link.state
        keys = set()
        if t is None:
            if st.distance > GRAB_DISTANCE and pre < 150:
                keys, pre = att_keys(st, 6), pre + 1
            elif waited < delay:
                waited += 1
            else:
                t = -4
        if t is not None:
            if t < 3:
                keys = att_keys(st, 6, kb if t >= 0 else "")
            elif t < 7:
                keys = att_keys(st, 6)
        step_with(keys)
        s = link.state
        mask = read_pad(link.last_seq)
        v, a = victim(s), attacker(s)
        rows.append((t if t is not None else "", mask, v.state_id, a.state_id, v.life,
                     kb if (t is not None and 0 <= t < 3) else ""))
        r = rows[-1]
        frames_w.writerow([n, r[0], pad_names(r[1]), r[2], r[3], r[4], r[5], f"{s.distance:.0f}"])
        if t is not None:
            t += 1
            if t > 60:
                break
    frames_f.flush()

    timed = [r for r in rows if r[0] != ""]
    lost = life0 - timed[-1][4] if timed else 0
    first_grab = next((r[0] for r in timed if r[2] not in IDLE_STATES), None)   # primer estado de la victima != reposo
    presses, prev = [], False
    for r in timed:
        on = bool(r[1] & (64 | 128))
        if on and not prev:
            presses.append((r[0], pad_names(r[1])))
        prev = on
    seq = []
    for r in timed:
        if not seq or seq[-1] != r[2]:
            seq.append(r[2])
    results.append({"intento": n, "boton_agarre": kb, "vida_perdida": lost, "t_primer_estado": first_grab,
                    "pulsaciones": " ".join(f"{t_}{b}" for t_, b in presses),
                    "estados_victima": " ".join(map(str, seq))})
    r = results[-1]
    print(f"{n:2d}/{TRIALS} {kb}  " + ("AGARRADO (-%d)" % lost if lost > 0 else "sin dano (soltaste o no llego)")
          + f"   pulsaciones: {r['pulsaciones'] or '-'}")

frames_f.close()
with open(out_dir / "intentos.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(results[0]))
    w.writeheader()
    w.writerows(results)

print("\nPor boton:")
for kb in "CD":
    rs = [r for r in results if r["boton_agarre"] == kb]
    print(f"  {kb}: {sum(r['vida_perdida'] == 0 for r in rs)}/{len(rs)} sin dano; estados de la victima: "
          + str(Counter(r["estados_victima"] for r in rs).most_common(3)))
print(f"\nGuardado en {out_dir}")
