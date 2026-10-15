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

TECH_REPEATS = 2         # repeticiones por celda del barrido de la ventana de agarre
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


def pressure(ctx):
    """Presion sostenida sobre Iori acorralado: 5A, 2B y 5C con huecos de 6-16 frames, 4 ciclos
    (los huecos son donde una salida de esquina tiene que decidir)."""
    for _ in range(4):
        for gen in (approach(ctx, 45), press(ctx, 5, "A", pre=0, post=0), idle(8), press(ctx, 2, "B"),
                    idle(6), press(ctx, 5, "C", pre=0, post=0), idle(16)):
            yield from gen
    yield from idle(30)


# Ventana de escape de agarres: Kim agarra y Iori (SCRIPTADO, sin reaccion) pulsa un boton en un
# frame fijo respecto al del agarre. t = 0 es el primer frame con boton de Kim; offset negativo =
# Iori pulsa ANTES. Si hay una ventana de escape, aparece como un offset donde Iori no es agarrado.
TECH_INPUTS = tuple(str(opt.get("--tech-inputs", "-,C,D,4C,4D,6C,6D")).split(","))
_lo, _hi = (int(x) for x in str(opt.get("--tech-offsets", "-6:5")).split(":"))
TECH_OFFSETS = tuple(range(_lo, _hi))
# El agarre de Kim aparece en la RAM en t=6 (Iori en 168) y el escape (estado 76, sin danio) sale
# 5 frames despues de pulsar. Medido con una persona (tools/tech_record.py): los escapes fueron con
# pulsaciones en t=13..21, DENTRO del estado 168. El barrido original (-6..4) terminaba antes.
TECH_FRAMES = int(opt.get("--tech-frames", 46))


def tech(ctx, trial):
    yield from approach(ctx, 12)
    inp, off, kb = trial["p1_input"], trial["offset"], trial["kim_button"]
    direction = int(inp[0]) if inp[0].isdigit() else 5
    button = inp[-1] if inp != "-" else ""
    for t in range(-4, TECH_FRAMES):
        if t < 0:
            kim = p2_keys(ctx.state, 6)
        elif t < 3:
            kim = p2_keys(ctx.state, 6, kb)
        elif t < 7:
            kim = p2_keys(ctx.state, 6)
        else:
            kim = set()
        iori = set(keys_for(direction, button, ctx.state.facing_right)) if button and off <= t < off + 3 else set()
        yield (iori, kim)


TRIAL_SCENARIOS = {"tecnica": tech}      # reciben (ctx, trial) y pueden mover tambien a P1

SCENARIOS = {
    "tecnica":       tech,
    "bajo":          lambda c: [approach(c, 40), press(c, 2, "B"), idle(40)],
    "barrida":       lambda c: [approach(c, 50), press(c, 2, "D"), idle(50)],
    "medio":         lambda c: [approach(c, 40), press(c, 5, "C"), idle(45)],
    "salto":         lambda c: [approach(c, 110), press(c, 9, "", 3, pre=0, post=0), idle(14), press(c, 5, "D", pre=0, post=0), idle(50)],
    "overhead":      lambda c: [approach(c, 40), notation(c, p2_overhead), idle(45)],
    "bajo_overhead": lambda c: [approach(c, 40), press(c, 2, "B"), idle(12), notation(c, p2_overhead), idle(45)],
    "overhead_bajo": lambda c: [approach(c, 40), notation(c, p2_overhead), idle(16), press(c, 2, "B"), idle(45)],
    "esquina":       lambda c: [pressure(c)],
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
# se insiste hasta ~60 s (da tiempo a entrar en la pelea si el juego estaba en una pantalla de menu).
moved = 0
for _ in range(180):                                     # ~60 s a velocidad normal
    x0 = link.state.rival.x
    step_with(p2=p2_keys(link.state, 4), frames=20)      # P2 retrocede
    moved = abs(link.state.rival.x - x0)
    if moved >= 4:
        break
if moved < 4:
    sys.exit("P2 no responde a joypad.set (no se movio en 60 s): hace falta modo VERSUS (P2 entra con "
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
if isinstance(opt.get("--sides"), str):          # --sides=A: solo un lado (barridos largos)
    sides = {s: n for s, n in sides.items() if s in opt["--sides"].upper()}

# Esquinas: desde cada lado, Iori camina hacia atras hasta la pared y Kim lo sigue a ~60.
corner_slots = {}
if "esquina" in names:
    for side, slot in sides.items():
        link.send(f"LOAD{slot}")
        wait_commands()
        step_with(frames=20)
        for _ in range(900):
            s = link.state
            if s.back_to_wall:
                break
            step_with(p1=keys_for(4, "", s.facing_right), p2=p2_keys(s, 6 if s.distance > 58 else 5))
        step_with(frames=10)
        place_p2(60)
        if link.state.back_to_wall:
            link.send(f"SAVE{slot + 2}")
            wait_commands()
            corner_slots[side] = slot + 2
    print("Esquinas guardadas: " + (", ".join(f"lado {s} (ranura {n})" for s, n in corner_slots.items())
                                    or "NINGUNA (Iori no llego a la pared)"))
    if not corner_slots:
        sys.exit("No se pudo poner a Iori en la esquina.")


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
        self.p1_keys = set()          # teclas de P1 scriptadas (solo escenarios 'tecnica')

    def on_step(self, state, keys):
        self.ctx.state = state
        self.trace.observe(state, keys, link.p2_keys)
        if self.done:
            link.p2_keys, self.p1_keys = set(), set()
            return
        trial = self.trials[0]
        if self.phase == "idle":
            link.p2_keys, self.p1_keys = set(), set()
            link.send(f"LOAD{trial['slot']}")
            self.phase, self.wait = "loading", LOAD_SETTLE
        elif self.phase == "loading":
            link.p2_keys, self.p1_keys = set(), set()
            if not link.commands_pending:
                self.wait -= 1
                if self.wait <= 0:
                    scenario = SCENARIOS[trial["scenario"]]
                    parts = scenario(self.ctx, trial) if trial["scenario"] in TRIAL_SCENARIOS else scenario(self.ctx)
                    if trial["scenario"] in TRIAL_SCENARIOS:
                        parts = [parts]
                    self.gen = (k for part in parts for k in part)
                    self.stocks0 = state.me.stocks
                    self.p2_states = []
                    self.phase = "run"
                    self.life, self.prev_keys = state.me.life, set(keys)
                    self.hit = self.chip = 0
                    self.p2_attacked = False
                    self.p2_move_state = None     # +0x73 de P2 al empezar su ataque (id del movimiento)
                    self.p1_states = []           # +0x73 de P1 desde que P2 ataca (bloqueo / golpe)
                    self.hit_keys = None
                    self.n_hits = 0               # golpes recibidos (no raspado)
                    self.escapes = 0              # veces que el bot eligio una salida de esquina
                    self.last_action = ""
        elif self.phase == "run":
            self.trace.note = f"{trial['id']}"
            drop = self.life - state.me.life
            back = ("left" if state.facing_right else "right") in self.prev_keys
            if 0 < drop <= CHIP and back:
                self.chip += drop
            elif drop > 0:
                self.hit += drop
                self.n_hits += 1
                self.hit_keys = self.hit_keys or ("+".join(sorted(self.prev_keys)) or "nada")
            info = self.trace._bot_info() if self.trace._bot_info else None
            action = str(info[1]) if info and info[1] else ""
            special = ("salida de esquina", "cancelar guardia")
            if action.startswith(special) and not self.last_action.startswith(special):
                self.escapes += 1
            self.last_action = action
            self.p2_states.append(state.rival.state_id)
            self.life, self.prev_keys = state.me.life, set(keys)
            if state.rival.attacking and not self.p2_attacked:
                self.p2_move_state = state.rival.state_id
            self.p2_attacked |= state.rival.attacking
            # Todos los estados de P1 durante el intento: los agarres NO encienden el bit de
            # ataque del rival, asi que filtrar por p2_attacked perdia justo el estado 168.
            self.p1_states.append(state.me.state_id)
            try:
                item = next(self.gen)
                if isinstance(item, tuple):               # (teclas de P1, teclas de P2)
                    self.p1_keys, link.p2_keys = set(item[0]), set(item[1])
                else:
                    self.p1_keys, link.p2_keys = set(), set(item)
            except StopIteration:
                link.p2_keys, self.p1_keys = set(), set()
                self.results.append({**trial, "danio": self.hit, "raspado": self.chip,
                                     "estados_p2": sorted(set(self.p2_states)),
                                     "barras_usadas": self.stocks0 - state.me.stocks,
                                     "p2_ataco": self.p2_attacked, "teclas_p1_al_golpe": self.hit_keys,
                                     "estado_p2_ataque": self.p2_move_state,
                                     "estados_p1": sorted(set(self.p1_states)),
                                     "golpes": self.n_hits, "salidas": self.escapes,
                                     "salio_esquina": not state.back_to_wall, "x_final": state.me.x})
                self.trials.pop(0)
                self.phase = "idle"
                self.done = not self.trials


def make_trials(phase):
    trials, n = [], 0
    for scenario in names:
        if scenario == "tecnica":
            # barrido de la ventana de agarre: solo en la fase de control (P1 scriptado, sin bot)
            if phase == "control":
                for side, slot in sides.items():
                    for kb in ("C", "D"):
                        for inp in TECH_INPUTS:
                            for off in TECH_OFFSETS:
                                for r in range(TECH_REPEATS):
                                    n += 1
                                    trials.append({"id": f"{phase}-tecnica-{side}-{kb}-{inp}-{off}-{r + 1}",
                                                   "fase": phase, "scenario": "tecnica", "side": side,
                                                   "slot": slot, "kim_button": kb, "p1_input": inp,
                                                   "offset": off})
            continue
        for side, slot in (corner_slots if scenario == "esquina" else sides).items():
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
    step_with(p1=runner.p1_keys, p2=link.p2_keys)
runner.trace.close()
control = runner.results

# GUARDIA: el bot real (GUARD_ONLY_TEST por defecto), cada intercambio = 1 frame. Con
# --variants=4C,4D,matching,... se repite la fase una vez por variante de escape de agarre.
variants = str(opt["--variants"]).split(",") if isinstance(opt.get("--variants"), str) else [None]
guard = []
for variant in variants:
    moves = {**config["characters"][p1_char], "combat_mode": MODE}
    if variant and variant.startswith("corner:"):
        moves["corner_escape"] = variant.split(":", 1)[1]      # none | roll | jump | reversal
    elif variant and variant.startswith("gc:"):
        moves["guard_cancel"] = variant.split(":", 1)[1]       # none | roll_b | roll_f | atk | atk_d
    elif variant:
        moves["throw_escape"] = variant
    brain = RuleBrain(reader, moves)
    clock = LockstepClock(link)
    clock.WATCH_CHUNK = clock.FREE_CHUNK = 1
    bot = RuleBot(LockstepKeyboard(link), clock, config, None, lambda: reader.read().facing_right,
                  lambda m: None, reader, moves, brain, focus_required=False, fight_check=lambda: True)
    phase = "guardia" if not variant else f"guardia:{variant}"
    trace_name = ("traza_guardia.csv" if not variant
                  else "traza_guardia_" + variant.replace(":", "-") + ".csv")
    runner = Runner(make_trials(phase), FrameTrace(out_dir / trace_name, lambda: bot.current))
    if runner.done:                      # p. ej. solo 'tecnica': no hay fase con bot
        continue
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

corner_rows = [r for r in guard if r["scenario"] == "esquina"]
if corner_rows:
    print("\n== Presion en la esquina (Kim: 4 ciclos de 5A, 2B, 5C; Iori solo guardia + salida) ==")
    print(f"  {'variante':22s}{'intentos':>9s}{'danio medio':>12s}{'golpes':>8s}{'salio':>7s}"
          f"{'salidas':>9s}{'barras':>8s}")
    for phase in sorted({r["fase"] for r in corner_rows}):
        rs = [r for r in corner_rows if r["fase"] == phase]
        n = len(rs)
        print(f"  {phase:22s}{n:9d}{sum(r['danio'] for r in rs) / n:12.1f}"
              f"{sum(r['golpes'] for r in rs) / n:8.1f}{100 * sum(r['salio_esquina'] for r in rs) / n:6.0f}%"
              f"{sum(r['salidas'] for r in rs) / n:9.1f}{sum(r['barras_usadas'] for r in rs) / n:8.1f}")
    ctl = [r for r in control if r["scenario"] == "esquina"]
    if ctl:
        print(f"  {'(control: sin guardia)':22s}{len(ctl):9d}{sum(r['danio'] for r in ctl) / len(ctl):12.1f}")

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

tech_rows = [r for r in control if r["scenario"] == "tecnica"]
if tech_rows:
    print("\n== Ventana de escape de agarres (Iori SCRIPTADO pulsa en el frame t respecto al boton de Kim) ==")
    print("   celda = % de intentos en que Iori NO fue agarrado (estado 168) / intentos en que Kim agarro")
    for kb in ("C", "D"):
        print(f"\n  Kim agarra con {kb}:   offset " + "".join(f"{o:>7d}" for o in TECH_OFFSETS))
        for inp in TECH_INPUTS:
            line = f"    Iori pulsa {inp:>2s}:       "
            for o in TECH_OFFSETS:
                rs = [r for r in tech_rows if r["kim_button"] == kb and r["p1_input"] == inp and r["offset"] == o
                      and any(s in r["estados_p2"] for s in (229, 230, 231, 232))]
                # soltado = sin danio y con el estado de escape (76); el agarre siempre pasa antes por 168
                free = sum((76 in r["estados_p1"] and r["danio"] == 0) or 168 not in r["estados_p1"] for r in rs)
                line += f"{f'{free}/{len(rs)}' if rs else '-':>7s}"
            print(line)
    extra = Counter(s for r in tech_rows if 168 not in r["estados_p1"] for s in r["estados_p1"] if s not in (0, 1, 2, 23, 21, 46, 45, 48, 47))
    print("\n  Estados de Iori en los intentos donde NO fue agarrado:", extra.most_common(10))

print(f"\n== Guardia de {p1_char} contra {p2_char} ({REPEATS} intentos por escenario y lado) ==")
print(f"{'escenario':16s}{'lado':6s}{'control: le pega':>18s}{'bloqueado':>11s}{'golpeado':>10s}")
for scenario in [n for n in names if n != "tecnica"]:
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
