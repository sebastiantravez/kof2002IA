"""Laboratorio de combos con lua/kof_train.lua (sin foco, frame exacto, acelerado):
prueba los combos sacados de tus grabaciones (tools/combos_from_recordings.py) y los del
perfil, siempre desde la MISMA posicion guardada (ranura 2), y mide el danio real.

Uso: python tools/combo_lab_fast.py <personaje> [--top=10] [--repeats=3] [--normal] [--apply]
  En modo PRACTICA, con el personaje como P1 y el muneco quieto, con kof_train.lua cargado.
  --normal: sin acelerar (para mirarlo).  --apply: agrega al perfil los combos tuyos que
  conectaron en todos los intentos (con su rango de distancia).
  --sweep: prueba los combos "tuyo" del perfil a varias distancias (--from=8 --to=72 --step=4)
  y con --apply guarda en combo_ranges el tramo donde conectan siempre.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kof_ai.combo import is_combo, play_combo  # noqa: E402
from kof_ai.lockstep import Lockstep, LockstepClock, LockstepKeyboard  # noqa: E402
from kof_ai.motions import keys_for, parse, play  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args:
    sys.exit(__doc__)
character = args[0]
opt = {a.split("=")[0]: (a.split("=", 1)[1] if "=" in a else True) for a in sys.argv[1:] if a.startswith("--")}
TOP = int(opt.get("--top", 10))
REPEATS = int(opt.get("--repeats", 3))
RANGE_MARGIN = 15
config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
profile = config["characters"][character]
step_frames, button_frames = config["motion_step_frames"], config["button_hold_frames"]

mine = json.loads((ROOT / "recordings" / f"combos_{character}.json").read_text(encoding="utf-8"))[:TOP]
candidates = [{"nombre": f"tuyo {c['danio']} ({c['origen']})", **c} for c in mine]
candidates += [{"nombre": f"perfil: {n}", "notacion": s, "danio": None, "distancia": 30}
               for n, s in profile.get("combos", {}).items()]

link = Lockstep(ROOT)
kb, clock = LockstepKeyboard(link), LockstepClock(link)
print("Esperando a lua/kof_train.lua (modo practica)...")
first = link.step()
if first.me.character != character:
    sys.exit(f"P1 es {first.me.character}, no {character}: elige {character} en practica.")


class Watch:
    """Cuenta impactos y danio al muneco frame a frame (en practica su vida se recupera)."""
    def __init__(self):
        self.last = link.state.rival.life
        self.damage = self.hits = 0

    def __call__(self):
        life = link.state.rival.life
        if life < self.last:
            self.damage += self.last - life
            self.hits += 1
        self.last = life
        return False


def settle(frames):
    kb.release_all()
    clock.wait_frames(frames, lambda: False)


def load_base():
    link.send("LOAD2")
    while link.commands_pending:
        link.step()
    settle(20)


def approach(target, tolerance=6):
    """Caminar SOSTENIENDO la direccion: tocar adelante-neutro-adelante es el input de
    correr (66) y Kim se pasaba de la distancia pedida."""
    for _ in range(400):
        d = link.state.distance
        if abs(d - target) <= tolerance:
            break
        kb.set_state(keys_for(6 if d > target else 4, "", link.state.facing_right))
        clock.wait_frames(1, lambda: False)
    settle(12)


def run_one(notation):
    watch = Watch()
    if is_combo(notation):
        # watch como should_stop: se llama cada frame y cuenta impactos (siempre False)
        play_combo(kb, clock, notation, link.state.facing_right, lambda: link.state.rival.life,
                   step_frames, button_frames, watch)
    else:
        play(kb, clock, parse(notation, step_frames, button_frames), link.state.facing_right, watch)
    clock.wait_frames(90, watch)
    return watch.damage, watch.hits


# Posicion base: ahora mismo, con los dos en el suelo y quietos.
settle(30)
link.send("SAVE2", *([] if "--normal" in opt else ["TURBO"]))
while link.commands_pending:
    link.step()
print(f"Posicion base guardada (distancia {link.state.distance}).")

if "--sweep" in opt:
    # Barrido de distancia de los combos tuyos del perfil: en que distancias conectan.
    SWEEP = range(int(opt.get("--from", 8)), int(opt.get("--to", 72)) + 1, int(opt.get("--step", 4)))
    ranges = profile.setdefault("combo_ranges", {})
    for name, notation in profile.get("combos", {}).items():
        if not name.startswith("tuyo"):
            continue
        rows = []
        for target in SWEEP:
            load_base()
            approach(target, tolerance=2)
            dist = link.state.distance
            dmg, hits = run_one(notation)
            rows.append((dist, dmg, hits))
        best = max(d for _, d, _ in rows)
        print(f"\n{name}  (mejor {best})")
        print("  " + "  ".join(f"{dist}:{dmg}" for dist, dmg, _ in rows))
        # tramo continuo mas largo con >= 80% del mejor danio y al menos 2 golpes
        good = [(dist, dmg >= 0.8 * best and hits >= 2) for dist, dmg, hits in rows]
        run, best_run = [], []
        for dist, ok in good:
            run = run + [dist] if ok else []
            if len(run) > len(best_run):
                best_run = run
        old = ranges.get(name)
        if best_run and best > 0:
            ranges[name] = [min(best_run), max(best_run)]
            print(f"  rango fiable: {min(best_run)}-{max(best_run)} (antes {old})")
        else:
            print("  sin rango fiable")
    link.send("NORMAL")
    settle(2)
    if "--apply" in opt:
        (ROOT / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("\nRangos guardados en config.json.")
    sys.exit(0)

print(f"Probando {len(candidates)} combos x {REPEATS}...")

results = []
for c in candidates:
    tries = []
    for _ in range(REPEATS):
        load_base()
        approach(c["distancia"])
        tries.append(run_one(c["notacion"]))
    results.append((c, tries))
    expected = f"(grabado {c['danio']})" if c["danio"] else ""
    print(f"  {c['nombre'][:60]:60s} danio {[t[0] for t in tries]} golpes {[t[1] for t in tries]} {expected}")

link.send("NORMAL")
settle(2)

accepted = [(c, t) for c, t in results
            if c["danio"] and all(d >= 0.8 * c["danio"] for d, _ in t)]
print(f"\nTuyos que conectaron en los {REPEATS} intentos (>= 80% del danio grabado): {len(accepted)}")
for c, t in accepted:
    print(f"  {min(d for d, _ in t)}-{max(d for d, _ in t)} danio, distancia {c['distancia']}: {c['nombre']}")

if "--apply" in opt and accepted:
    profile.setdefault("combos", {})
    ranges = profile.setdefault("combo_ranges", {})
    for c, t in accepted:
        name = f"tuyo {min(d for d, _ in t)} dmg ({c['origen']})"
        profile["combos"][name] = c["notacion"]
        ranges[name] = [max(0, c["distancia"] - RANGE_MARGIN), c["distancia"] + RANGE_MARGIN]
    (ROOT / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Agregados {len(accepted)} combos al perfil de {character} en config.json.")
