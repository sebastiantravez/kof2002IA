"""Laboratorio de combos con lua/kof_train.lua (sin foco, frame exacto, acelerado):
prueba los combos sacados de tus grabaciones (tools/combos_from_recordings.py) y los del
perfil, siempre desde la MISMA posicion guardada (ranura 2), y mide el danio real.

Uso: python tools/combo_lab_fast.py <personaje> [--top=10] [--repeats=3] [--normal] [--apply]
  En modo PRACTICA, con el personaje como P1 y el muneco quieto, con kof_train.lua cargado.
  --normal: sin acelerar (para mirarlo).  --apply: agrega al perfil los combos tuyos que
  conectaron en todos los intentos (con su rango de distancia).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kof_ai.combo import is_combo, play_combo  # noqa: E402
from kof_ai.lockstep import Lockstep, LockstepClock, LockstepKeyboard  # noqa: E402
from kof_ai.motions import parse, play  # noqa: E402

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


def approach(target):
    for _ in range(60):
        d = link.state.distance
        if abs(d - target) <= 6:
            break
        play(kb, clock, parse("6[2]" if d > target else "4[2]"), link.state.facing_right)
    settle(12)


# Posicion base: ahora mismo, con los dos en el suelo y quietos.
settle(30)
link.send("SAVE2", *([] if "--normal" in opt else ["TURBO"]))
while link.commands_pending:
    link.step()
print(f"Posicion base guardada (distancia {link.state.distance}). Probando {len(candidates)} combos x {REPEATS}...")

results = []
for c in candidates:
    tries = []
    for _ in range(REPEATS):
        load_base()
        approach(c["distancia"])
        watch = Watch()
        if is_combo(c["notacion"]):
            # watch como should_stop: se llama cada frame y cuenta impactos (siempre False)
            play_combo(kb, clock, c["notacion"], link.state.facing_right, lambda: link.state.rival.life,
                       step_frames, button_frames, watch)
        else:
            play(kb, clock, parse(c["notacion"], step_frames, button_frames), link.state.facing_right, watch)
        clock.wait_frames(90, watch)
        tries.append((watch.damage, watch.hits))
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
