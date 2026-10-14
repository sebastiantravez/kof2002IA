"""Prueba controlada de guardia DENTRO de Fightcade/FBNeo: P2 (controlado por este script)
lanza ataques etiquetados y P1 se defiende con el bot real en modo GUARD_ONLY_TEST.

Cada escenario se prueba en los dos lados de la pantalla, siempre desde la misma posicion
guardada, en dos fases:
  CONTROL  P1 no pulsa nada: comprueba que el ataque de P2 de verdad llega (si no pega
           sin guardia, el escenario no sirve para medir la guardia).
  GUARDIA  P1 = RuleBot con GUARD_ONLY_TEST (solo guardia dinamica alta/baja).

Resultado por intento: golpeado (perdio > CHIP de vida), bloqueado (el ataque llega en el
control y aqui no hizo danio, o solo raspado con atras sostenido).
Deja una traza por frame (teclas de P1 y P2, estado de los dos) en logs/guard_test_<fecha>/.

Requisitos: modo VERSUS con P1 = personaje con perfil en config.json (Iori) y P2 controlable
por el joystick de P2 (este script pulsa sus botones con joypad.set), kof_train.lua cargado.
Uso: python tools/guard_test.py [--repeats=5] [--scenarios=bajo,barrida,medio,salto,overhead,
     bajo_overhead,overhead_bajo] [--normal]
"""
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kof_ai.bot import RuleBot  # noqa: E402
from kof_ai.brain import RuleBrain  # noqa: E402
from kof_ai.lockstep import Lockstep, LockstepClock, LockstepKeyboard, LockstepReader  # noqa: E402
from kof_ai.motions import keys_for, parse  # noqa: E402
from kof_ai.trace import FrameTrace  # noqa: E402

CHIP = 2                 # perder <= 2 con atras sostenido = raspado de un ataque bloqueado (medido)
START_DISTANCE = 120     # distancia de las posiciones guardadas
LOAD_SETTLE = 20         # frames quietos tras cargar la posicion

opt = {a.split("=")[0]: (a.split("=", 1)[1] if "=" in a else True) for a in sys.argv[1:] if a.startswith("--")}
REPEATS = int(opt.get("--repeats", 5))
MODE = str(opt.get("--mode", "GUARD_ONLY_TEST")).upper()   # DEFENSE_ONLY para probar el escape de agarres
config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

link = Lockstep(ROOT)
reader = LockstepReader(link)
print("Esperando a lua/kof_train.lua...")
first = link.step()
p1_char, p2_char = first.me.character, first.rival.character
if p1_char not in config["characters"]:
    sys.exit(f"P1 es {p1_char}: necesita un perfil en config.json (usa Iori).")
p2_overhead = config["characters"].get(p2_char, {}).get("overhead")
print(f"P1 = {p1_char} (bot), P2 = {p2_char} (este script)"
      + ("" if p2_overhead else "  [P2 sin perfil: se omiten los escenarios con overhead]"))


# ---------- P2: entradas relativas (6 = hacia P1) ----------

def p2_keys(st, direction, buttons=""):
    p2_faces_right = st.rival.x <= st.me.x
    return set(keys_for(direction, buttons, p2_faces_right))


def approach(ctx, target, max_frames=120):
    for _ in range(max_frames):
        if ctx.state.distance <= target:
            return
        yield p2_keys(ctx.state, 6)


def press(ctx, direction, buttons, frames=3, pre=4, post=4):
    """Como una persona: direccion sola unos frames (agacharse / adelantar), luego el boton, y
    la direccion se mantiene al soltar el boton. (Medido: direccion+boton en el mismo frame y
    soltados juntos salen como golpe DE PIE: 2B -> B de pie, 6C -> C de pie.)"""
    for _ in range(pre):
        yield p2_keys(ctx.state, direction)
    for _ in range(frames):
        yield p2_keys(ctx.state, direction, buttons)
    for _ in range(post):
        yield p2_keys(ctx.state, direction)


def idle(frames):
    for _ in range(frames):
        yield set()


def notation(ctx, text):
    for step in parse(text, config["motion_step_frames"], config["button_hold_frames"]):
        for _ in range(step.frames):
            yield p2_keys(ctx.state, step.direction, step.buttons)


SCENARIOS = {
    "bajo":          lambda c: [approach(c, 40), press(c, 2, "B"), idle(40)],
    "barrida":       lambda c: [approach(c, 50), press(c, 2, "D"), idle(50)],
    "medio":         lambda c: [approach(c, 40), press(c, 5, "C"), idle(45)],
    "salto":         lambda c: [approach(c, 110), press(c, 9, "", 3, pre=0, post=0), idle(14), press(c, 5, "D", pre=0, post=0), idle(50)],
    "overhead":      lambda c: [approach(c, 40), notation(c, p2_overhead), idle(45)],
    "bajo_overhead": lambda c: [approach(c, 40), press(c, 2, "B"), idle(12), notation(c, p2_overhead), idle(45)],
    "overhead_bajo": lambda c: [approach(c, 40), notation(c, p2_overhead), idle(16), press(c, 2, "B"), idle(45)],
    "agarre_C":      lambda c: [approach(c, 12), press(c, 6, "C"), idle(70)],
    "agarre_D":      lambda c: [approach(c, 12), press(c, 6, "D"), idle(70)],
}
wanted = opt.get("--scenarios")
names = [n for n in (wanted.split(",") if isinstance(wanted, str) else SCENARIOS) if n in SCENARIOS]
if not p2_overhead:
    names = [n for n in names if "overhead" not in n]


# ---------- preparacion: posiciones guardadas en los dos lados ----------

def step_with(p1=(), p2=(), frames=1):
    link.keys, link.p2_keys = set(p1), set(p2)
    for _ in range(frames):
        link.step()


def wait_commands():
    while link.commands_pending:
        step_with()


def place_p2(distance):
    for _ in range(300):
        d = link.state.distance
        if abs(d - distance) <= 4:
            break
        step_with(p2=p2_keys(link.state, 6 if d > distance else 4))
    step_with(frames=20)


# P2 tiene que poder moverse: durante la animacion de inicio de ronda nadie se mueve, asi que
# se insiste hasta 15 s (si la ronda termina por tiempo, la siguiente vuelve a empezar).
moved = 0
for _ in range(45):
    x0 = link.state.rival.x
    step_with(p2=p2_keys(link.state, 4), frames=20)      # P2 retrocede
    moved = abs(link.state.rival.x - x0)
    if moved >= 4:
        break
if moved < 4:
    sys.exit("P2 no responde a joypad.set (no se movio en 15 s): hace falta modo VERSUS (P2 entra con "
             "Start) o un muneco controlado por el jugador 2.")
print(f"P2 responde (se movio {moved}).")
if "--normal" not in opt:
    link.send("TURBO")
place_p2(START_DISTANCE)
link.send("SAVE2")
wait_commands()
sides = {"A": 2}
side_a_right = link.state.rival.x > link.state.me.x
for attempt in range(3):              # lado B: P2 salta por encima de P1
    place_p2(36)
    step_with(p2=p2_keys(link.state, 9), frames=4)
    step_with(frames=50)
    if (link.state.rival.x > link.state.me.x) != side_a_right:
        place_p2(START_DISTANCE)
        link.send("SAVE3")
        wait_commands()
        sides["B"] = 3
        break
print(f"Posiciones guardadas: {', '.join(f'lado {s} (ranura {n})' for s, n in sides.items())}"
      + ("" if "B" in sides else "  [no se pudo cambiar de lado: solo lado A]"))


# ---------- intentos (se ejecutan dentro de on_step, en el hilo que avanza los frames) ----------

class Ctx:
    state = None


class Runner:
    def __init__(self, trials, trace):
        self.trials = list(trials)
        self.trace = trace
        self.results = []
        self.phase = "idle"
        self.done = not self.trials
        self.ctx = Ctx()

    def on_step(self, state, keys):
        self.ctx.state = state
        self.trace.observe(state, keys, link.p2_keys)
        if self.done:
            link.p2_keys = set()
            return
        trial = self.trials[0]
        if self.phase == "idle":
            link.p2_keys = set()
            link.send(f"LOAD{trial['slot']}")
            self.phase, self.wait = "loading", LOAD_SETTLE
        elif self.phase == "loading":
            link.p2_keys = set()
            if not link.commands_pending:
                self.wait -= 1
                if self.wait <= 0:
                    self.gen = (k for part in SCENARIOS[trial["scenario"]](self.ctx) for k in part)
                    self.phase = "run"
                    self.life, self.prev_keys = state.me.life, set(keys)
                    self.hit = self.chip = 0
                    self.p2_attacked = False
                    self.p2_move_state = None     # +0x73 de P2 al empezar su ataque (id del movimiento)
                    self.p1_states = []           # +0x73 de P1 desde que P2 ataca (bloqueo / golpe)
                    self.hit_keys = None
        elif self.phase == "run":
            self.trace.note = f"{trial['id']}"
            drop = self.life - state.me.life
            back = ("left" if state.facing_right else "right") in self.prev_keys
            if 0 < drop <= CHIP and back:
                self.chip += drop
            elif drop > 0:
                self.hit += drop
                self.hit_keys = self.hit_keys or ("+".join(sorted(self.prev_keys)) or "nada")
            self.life, self.prev_keys = state.me.life, set(keys)
            if state.rival.attacking and not self.p2_attacked:
                self.p2_move_state = state.rival.state_id
            self.p2_attacked |= state.rival.attacking
            # Todos los estados de P1 durante el intento: los agarres NO encienden el bit de
            # ataque del rival, asi que filtrar por p2_attacked perdia justo el estado 168.
            self.p1_states.append(state.me.state_id)
            try:
                link.p2_keys = next(self.gen)
            except StopIteration:
                link.p2_keys = set()
                self.results.append({**trial, "danio": self.hit, "raspado": self.chip,
                                     "p2_ataco": self.p2_attacked, "teclas_p1_al_golpe": self.hit_keys,
                                     "estado_p2_ataque": self.p2_move_state,
                                     "estados_p1": sorted(set(self.p1_states))})
                self.trials.pop(0)
                self.phase = "idle"
                self.done = not self.trials


def make_trials(phase):
    trials, n = [], 0
    for scenario in names:
        for side, slot in sides.items():
            for r in range(REPEATS):
                n += 1
                trials.append({"id": f"{phase}-{scenario}-{side}-{r + 1}", "fase": phase,
                               "scenario": scenario, "side": side, "slot": slot})
    return trials


out_dir = ROOT / "logs" / f"guard_test_{time.strftime('%Y%m%d_%H%M%S')}"

# CONTROL: P1 sin pulsar nada
runner = Runner(make_trials("control"), FrameTrace(out_dir / "traza_control.csv"))
link.on_step = runner.on_step
print(f"CONTROL: {len(runner.trials)} intentos sin guardia...")
while not runner.done:
    step_with(p2=link.p2_keys)
runner.trace.close()
control = runner.results

# GUARDIA: el bot real (GUARD_ONLY_TEST por defecto), cada intercambio = 1 frame. Con
# --variants=4C,4D,matching,... se repite la fase una vez por variante de escape de agarre.
variants = str(opt["--variants"]).split(",") if isinstance(opt.get("--variants"), str) else [None]
guard = []
for variant in variants:
    moves = {**config["characters"][p1_char], "combat_mode": MODE}
    if variant:
        moves["throw_escape"] = variant
    brain = RuleBrain(reader, moves)
    clock = LockstepClock(link)
    clock.WATCH_CHUNK = clock.FREE_CHUNK = 1
    bot = RuleBot(LockstepKeyboard(link), clock, config, None, lambda: reader.read().facing_right,
                  lambda m: None, reader, moves, brain, focus_required=False, fight_check=lambda: True)
    phase = "guardia" if not variant else f"guardia:{variant}"
    trace_name = "traza_guardia.csv" if not variant else f"traza_guardia_{variant}.csv"
    runner = Runner(make_trials(phase), FrameTrace(out_dir / trace_name, lambda: bot.current))
    link.on_step = runner.on_step
    print(f"GUARDIA: {len(runner.trials)} intentos con {p1_char} en {MODE}"
          + (f", escape {variant}" if variant else "") + "...")
    bot.start()
    while not runner.done and bot.running:
        time.sleep(0.2)
    bot.stop()
    while bot.running:
        time.sleep(0.05)
    runner.trace.close()
    guard += runner.results
link.on_step = None
link.keys, link.p2_keys = set(), set()
link.send("NORMAL")
link.step()

# ---------- resumen ----------
reach = defaultdict(list)
for r in control:
    reach[(r["scenario"], r["side"])].append(r["danio"] > 0)
table = defaultdict(Counter)
for r in guard:
    key = (r["scenario"], r["side"])
    if r["danio"] > 0:
        table[key]["golpeado"] += 1
    elif sum(reach[key]) * 2 > len(reach[key]):
        table[key]["bloqueado"] += 1
    else:
        table[key]["no medible"] += 1

# Agarres: solo cuentan los que de verdad atraparon (estado 168 en P1); por variante de escape.
throw_rows = [r for r in guard if r["scenario"].startswith("agarre") and 168 in r["estados_p1"]]
if throw_rows:
    print("\n== Escape de agarres (solo agarres que atraparon de verdad) ==")
    for phase in sorted({r["fase"] for r in throw_rows}):
        for sc in sorted({r["scenario"] for r in throw_rows}):
            rs = [r for r in throw_rows if r["fase"] == phase and r["scenario"] == sc]
            esc = sum(r["danio"] == 0 for r in rs)
            total = sum(1 for r in guard if r["fase"] == phase and r["scenario"] == sc)
            print(f"  {phase:20s} {sc:10s} escapados {esc}/{len(rs)} agarres que conectaron "
                  f"({total - len(rs)} de {total} intentos no agarraron: no cuentan)")

print(f"\n== Guardia de {p1_char} contra {p2_char} ({REPEATS} intentos por escenario y lado) ==")
print(f"{'escenario':16s}{'lado':6s}{'control: le pega':>18s}{'bloqueado':>11s}{'golpeado':>10s}")
for scenario in names:
    for side in sides:
        k = (scenario, side)
        print(f"{scenario:16s}{side:6s}{f'{sum(reach[k])}/{len(reach[k])}':>18s}"
              f"{table[k]['bloqueado']:>11d}{table[k]['golpeado']:>10d}"
              + ("   (el ataque no llega sin guardia: no medible)" if table[k]["no medible"] else ""))
hits = [r for r in guard if r["danio"] > 0]
if hits:
    print("\nTeclas de P1 el frame antes de cada golpe recibido:")
    for (sc, keys), n in Counter((r["scenario"], r["teclas_p1_al_golpe"]) for r in hits).most_common():
        print(f"  {n:3d}  {sc:16s} {keys}")
summary = {"p1": p1_char, "p2": p2_char, "repeticiones": REPEATS, "control": control, "guardia": guard}
(out_dir / "resumen.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"\nTrazas por frame y resumen en {out_dir}")

# ---------- tabla de estados (+0x73) por escenario: id del movimiento de P2 y reaccion de P1 ----------
print("\n== Identificadores de estado (+0x073) ==")
print(f"{'escenario':16s}{'mov. P2':>9s}  P1 sin guardia (control)            P1 con guardia")
for scenario in names:
    p2 = Counter(r["estado_p2_ataque"] for r in control + guard if r["scenario"] == scenario)
    def states(rs):
        c = Counter(s for r in rs if r["scenario"] == scenario for s in r["estados_p1"] if s)
        return ", ".join(f"{s}x{n}" for s, n in c.most_common(4))
    print(f"{scenario:16s}{str(p2.most_common(1)[0][0]) if p2 else '-':>9s}  {states(control):36s} {states(guard)}")
print("(estados que aparecen en 'control' pero no en 'guardia' = golpe; al reves = bloqueo)")
