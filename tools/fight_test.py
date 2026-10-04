"""Prueba de pelea completa con la IA de reglas y reporte de metricas.

Uso: python tools/fight_test.py [segundos] [personaje] [rules|learn]
     learn = Fase 4: aprende y guarda en learned_<personaje>.json
No toques la PC mientras corre: si el emulador pierde el foco, la IA se detiene.
"""
import json
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kof_ai import emulator  # noqa: E402
from kof_ai.bot import RuleBot  # noqa: E402
from kof_ai.capture import WindowCapture  # noqa: E402
from kof_ai.game_state import StateReader  # noqa: E402
from kof_ai.keyboard import VirtualKeyboard  # noqa: E402
from kof_ai.brain import MAX_DAMAGE_PER_FRAME, RuleBrain  # noqa: E402
from kof_ai.imitation import Imitation  # noqa: E402
from kof_ai.learning import LearningBrain  # noqa: E402
from kof_ai.motions import FrameClock  # noqa: E402

seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 60
character = sys.argv[2] if len(sys.argv) > 2 else "Kyo"
mode = sys.argv[3] if len(sys.argv) > 3 else "rules"
config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
windows = emulator.find_emulator_windows(config["emulator_processes"])
if not windows:
    sys.exit("Emulador no encontrado.")
if len(windows) > 1:
    sys.exit(f"Hay {len(windows)} emuladores abiertos (¿una repeticion y el arcade?). "
             "Cierra los que no sean la partida del bot.")
hwnd, _ = windows[0]
reader = StateReader(ROOT / "state.txt")
if reader.read() is None:
    sys.exit("Sin vision: carga lua/kof_state.lua en el emulador.")
if not reader.single_source():
    sys.exit("Dos scripts Lua escriben state.txt a la vez. Deja kof_state.lua solo en la partida del bot.")

keyboard = VirtualKeyboard(config["keys"])
clock = FrameClock(config["fps"])
out = ROOT / "captures" / f"fight_{time.strftime('%H%M%S')}"
out.mkdir(parents=True, exist_ok=True)
log_lines = []
situations = Counter()
combo_stats = Counter()
actions = Counter()
current = {"situation": None}
start = time.perf_counter()


def on_log(message):
    stamp = f"{time.perf_counter() - start:6.2f}"
    log_lines.append(f"{stamp} {message}")
    if message.startswith("["):
        current["situation"] = message.strip("[]")
    elif message.startswith("  -> "):
        situations[current["situation"]] += 1
        actions[message[5:].split(" (")[0]] += 1
    elif message.startswith("Fuera de pelea"):
        situations["fuera de pelea"] += 1
    elif message.strip().startswith("combo:"):
        # "combo: 3/3 partes conectaron, danio 14"
        done, total = message.split(":")[1].split("partes")[0].strip().split("/")
        combo_stats["intentos"] += 1
        combo_stats["completos"] += int(done) == int(total)
        combo_stats["con 2+ golpes"] += int(done) >= 2
        combo_stats["danio"] += int(message.rsplit(" ", 1)[1])


def facing():
    state = reader.read()
    return state.facing_right if state else True


# Metricas muestreadas a ~60 Hz en paralelo.
metrics = {"dealt": 0, "taken": 0, "hits_dealt": 0, "hits_taken": 0,
           "rival_jumps": 0, "aa_hits": 0, "dist_sum": 0, "samples": 0,
           "rival_attacks": 0, "rival_attacks_hit": 0}
pending_attacks = []
stop_sampler = threading.Event()


jump_traces = []

# Diagnostico de defensa: que me pego y que guardia tenia en ese momento.
marks = {"rival_crouch": -999, "rival_air": -999, "me_thrown": -999, "attack_low": False}
hits_taken = Counter()       # (tipo de golpe, mi guardia) -> veces
damage_taken = Counter()     # (tipo de golpe, mi guardia) -> danio


def diagnose_hit(state, damage):
    f = state.frame
    if f - marks["me_thrown"] <= 30:
        kind = "agarre"
    elif f - marks["rival_air"] <= 8:
        kind = "salto/aereo"
    elif marks["attack_low"]:
        kind = "bajo"
    else:
        kind = "de pie/otro"
    pressed = set(keyboard._pressed)
    back = "left" if state.facing_right else "right"
    if back in pressed and "down" in pressed:
        guard = "guardia abajo"
    elif back in pressed:
        guard = "guardia de pie"
    elif pressed & set("ABCD"):
        guard = "atacando"
    elif pressed:
        guard = "moviendose"
    else:
        guard = "sin guardia"
    hits_taken[(kind, guard)] += 1
    damage_taken[(kind, guard)] += damage


def sampler():
    prev = reader.read()
    trace = None
    while not stop_sampler.is_set():
        time.sleep(1 / 60)
        state = reader.read()
        if state is None or prev is None:
            prev = state
            continue
        if 0 < prev.rival.life - state.rival.life <= MAX_DAMAGE_PER_FRAME:
            metrics["dealt"] += prev.rival.life - state.rival.life
            metrics["hits_dealt"] += 1
            if prev.rival.airborne:
                metrics["aa_hits"] += 1
        if state.rival.crouching:
            marks["rival_crouch"] = state.frame
        if state.rival.airborne:
            marks["rival_air"] = state.frame
        if state.me.thrown:
            marks["me_thrown"] = state.frame
        if state.rival.attacking and not prev.rival.attacking:
            marks["attack_low"] = state.frame - marks["rival_crouch"] <= 4
        if 0 < prev.me.life - state.me.life <= MAX_DAMAGE_PER_FRAME:
            metrics["taken"] += prev.me.life - state.me.life
            metrics["hits_taken"] += 1
            diagnose_hit(state, prev.me.life - state.me.life)
        # Defensa: ataques del rival iniciados cerca y si me pegaron en los 40 frames siguientes.
        if state.rival.attacking and not prev.rival.attacking and state.distance <= 180:
            metrics["rival_attacks"] += 1
            pending_attacks.append((state.frame, state.me.life))
        for start, life0 in list(pending_attacks):
            if state.me.life < life0:
                metrics["rival_attacks_hit"] += 1
                pending_attacks.remove((start, life0))
            elif state.frame - start > 40:
                pending_attacks.remove((start, life0))
        if state.rival.airborne and not prev.rival.airborne:
            metrics["rival_jumps"] += 1
            trace = []
        if trace is not None and state.frame != prev.frame:
            trace.append((state.distance, state.rival.height, state.me.life))
            if not state.rival.airborne:
                jump_traces.append(trace)
                trace = None
        metrics["dist_sum"] += state.distance
        metrics["samples"] += 1
        prev = state


cap = WindowCapture(hwnd)
if not emulator.focus(hwnd):
    sys.exit("No se pudo dar foco al emulador.")
clock.wait_frames(5)
threading.Thread(target=sampler, daemon=True).start()
moves = config["characters"][character]
imitation = Imitation.load(ROOT / "recordings" / "imitation.json", character)
if imitation:
    print(f"Imitacion: {len(imitation.combos)} combos de jugadores reales: {list(imitation.combos)}")
if mode == "learn":
    brain = LearningBrain(reader, moves, ROOT / f"learned_{character}.json", imitation=imitation)
    known_before = sum(n for acts in brain.table.values() for n, _ in acts.values())
else:
    brain = RuleBrain(reader, moves, imitation)
bot = RuleBot(keyboard, clock, config, hwnd, facing, on_log, reader, moves, brain)
bot.start()
shot = 0
while bot.running and time.perf_counter() - start < seconds:
    time.sleep(0.25)
    if time.perf_counter() - start >= shot * 10:
        frame = cap.grab()
        if frame is not None:
            cv2.imwrite(str(out / f"t{shot * 10:03d}s.png"), frame)
        shot += 1
bot.stop()
time.sleep(0.3)
stop_sampler.set()
cap.close()
elapsed = time.perf_counter() - start

decisions = sum(actions.values())
report = [
    f"Duracion: {elapsed:.1f}s  (personaje: {character})",
    f"Decisiones: {decisions}  ({decisions / max(elapsed, 1):.1f} por segundo)",
    f"Danio hecho:    {metrics['dealt']} en {metrics['hits_dealt']} impactos",
    f"Danio recibido: {metrics['taken']} en {metrics['hits_taken']} impactos",
    f"Saltos del rival: {metrics['rival_jumps']}  golpes al rival en el aire: {metrics['aa_hits']}",
    f"Combos: {combo_stats['intentos']} intentos, {combo_stats['con 2+ golpes']} con 2+ golpes, "
    f"{combo_stats['completos']} completos, danio total {combo_stats['danio']}",
    f"Ataques del rival de cerca: {metrics['rival_attacks']}, me pegaron {metrics['rival_attacks_hit']} "
    f"({100 * metrics['rival_attacks_hit'] / max(metrics['rival_attacks'], 1):.0f}%)",
    f"Distancia promedio: {metrics['dist_sum'] / max(metrics['samples'], 1):.0f}",
    "Situaciones: " + ", ".join(f"{k} {v}" for k, v in situations.most_common()),
    "Acciones:    " + ", ".join(f"{k} {v}" for k, v in actions.most_common()),
]
report.append("Golpes recibidos por tipo y guardia que tenia:")
for (kind, guard), n in hits_taken.most_common():
    report.append(f"  {kind:12s} con {guard:15s} {n:3d} veces, danio {damage_taken[(kind, guard)]}")
if metrics["rival_attacks"] == 0 and elapsed > 60:
    report.insert(0, "AVISO: el rival no ataco nunca. ¿Estabas en modo practica con el dummy? "
                     "Para entrenar defensa usa el arcade contra la CPU.")
if brain:
    report.append(f"Aprendizaje: {brain.updates} experiencias nuevas (antes habia {known_before}), "
                  f"recompensa media {brain.reward_sum / max(brain.updates, 1):+.2f}")
    report.append(brain.summary())
for i, tr in enumerate(jump_traces):
    hit = " ME GOLPEO" if tr[-1][2] < tr[0][2] else ""
    report.append(f"Salto {i + 1}: (d,h) " + " ".join(f"{d},{h}" for d, h, _ in tr[::3]) + hit)
(out / "log.txt").write_text("\n".join(log_lines + [""] + report), encoding="utf-8")
print("\n".join(line for line in report if not line.startswith("Salto")))
print("Ultimas lineas del log:")
print("\n".join(log_lines[-8:]))
print(f"Capturas y log en {out}")
