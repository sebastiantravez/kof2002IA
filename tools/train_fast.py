"""Entrenamiento acelerado con lua/kof_train.lua: el juego corre sin limite de
velocidad, el bot controla a P1 frame a frame (sin foco: puedes usar la PC) y cada
ronda que termina se reinicia al instante cargando la partida guardada.

Uso:
  1) En el emulador, en una pelea (arcade o practica) al INICIO de una ronda,
     cargar lua/kof_train.lua.
  2) python tools/train_fast.py <personaje> [minutos] [--normal] [--play] [--no-reset]
     --normal:   sin acelerar (para mirar como juega).
     --play:     modo prueba: usa lo aprendido sin explorar y SIN GUARDAR nada, a
                 velocidad normal. Sirve para mirarlo o pelear contra el como P2.
     --no-reset: no recargar la ronda al terminar (el juego sigue normal; para
                 pelear contra el bot en versus).
     --mode=DEFENSE_ONLY|DEFENSE_WITH_PUNISH|BALANCED_EXPERIMENTAL: modo de combate
                 (comparar con tools/compare_sessions.py). --offense=off|strategic sigue valiendo.
     --reuse-save: no guardar un punto de reinicio nuevo: cargar el de la sesion anterior
                 (mismo rival y escenario, para comparar modos en igualdad de condiciones).
     --rival=Chin: detener si P2 no es ese personaje.
     --preventive=on|off: guardia preventiva (sin acciones largas cerca del rival).
     --corner=none|roll|jump|reversal: salida de esquina bajo presion (ver docs/DEFENSE_AUDIT_V4.md).
     --calm-pressure: sin presion cercana mientras el rival ataca (BALANCED_EXPERIMENTAL).
     --speed=N: como maximo N veces la velocidad normal (tambien con --play).
     --legacy-punish / --legacy-escapes: comportamiento ANTERIOR a las correcciones de la
                 auditoria externa (castigo con el ataque rival activo / escapes al azar bajo
                 amenaza), solo para compararlo en las mismas condiciones.
  Se detiene solo si P1 no es el personaje pedido (p. ej. la demo del arcade).
"""
import json
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kof_ai.bot import RuleBot  # noqa: E402
from kof_ai.defense_log import DefenseLogger  # noqa: E402
from kof_ai.game_state import MAX_LIFE  # noqa: E402
from kof_ai.imitation import Imitation  # noqa: E402
from kof_ai.learning import LearningBrain  # noqa: E402
from kof_ai.lockstep import Lockstep, LockstepClock, LockstepKeyboard, LockstepReader  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
character = args[0] if args else "Kim"
minutes = float(args[1]) if len(args) > 1 else 10
play = "--play" in sys.argv
# --speed=N: N veces la velocidad normal como maximo (tambien en --play, para mirarlo mas rapido)
speed = next((float(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--speed=")), None)
turbo = ("--normal" not in sys.argv and not play) or speed is not None
reset = "--no-reset" not in sys.argv
reuse_save = "--reuse-save" in sys.argv
wanted_rival = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--rival=")), None)
config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
moves = dict(config["characters"][character])
for a in sys.argv[1:]:
    if a in ("--legacy-punish", "--legacy-escapes"):   # reproducir el comportamiento anterior (comparar)
        moves[a[2:].replace("-", "_")] = True
    if a.startswith("--preventive="):   # guardia preventiva on|off (docs/DEFENSE_AUDIT_V4.md)
        moves["preventive_guard"] = a.split("=", 1)[1].lower() in ("on", "1", "true", "si")
    if a == "--calm-pressure":       # presion cercana solo con el rival pasivo (ver strategy.py)
        moves["pressure_needs_calm"] = True
    if a.startswith("--corner="):    # salida de esquina: none | roll | jump | reversal
        moves["corner_escape"] = a.split("=", 1)[1].lower()
    if a.startswith("--mode="):      # modo de combate (kof_ai/arbiter.py)
        moves["combat_mode"] = a.split("=", 1)[1].upper()
    if a.startswith("--offense="):   # compatibilidad: off | strategic
        moves["combat_mode"] = {"strategic": "BALANCED_EXPERIMENTAL"}.get(a.split("=", 1)[1], "DEFENSE_ONLY")

link = Lockstep(ROOT)
if speed:
    link.max_fps = 59.19 * speed
print("Esperando a lua/kof_train.lua en el emulador...")
first = link.step()
print(f"Conectado. P1 = {first.me.character}, P2 = {first.rival.character}, "
      f"vida {first.me.life}/{first.rival.life}")
SAVE_INFO = ROOT / "logs" / "punto_reinicio.json"


def check_fighters(state, when):
    """No entrenar con otro personaje (p. ej. la demo del arcade) ni contra otro rival."""
    problems = []
    if state.me.character != character:
        problems.append(f"P1 es {state.me.character}, no {character}")
    if wanted_rival and state.rival.character != wanted_rival:
        problems.append(f"P2 es {state.rival.character}, no {wanted_rival}")
    if problems:
        link.send("NORMAL")
        link.step()
        sys.exit(f"Detenido ({when}): {'; '.join(problems)}. Entra a la pelea correcta y vuelve a lanzar.")


def wait_full_life(message):
    waited = 0
    while not (link.state.me.life == MAX_LIFE and link.state.rival.life == MAX_LIFE):
        if waited == 0:
            print(message)
        link.step()
        waited += 1
        if waited > 60 * 120:
            sys.exit("No llego un inicio de ronda en 2 minutos de juego.")


if reset and reuse_save:
    # Mismo punto de reinicio que la sesion anterior: mismo rival y escenario (comparar modos).
    info = json.loads(SAVE_INFO.read_text(encoding="utf-8")) if SAVE_INFO.exists() else {}
    print(f"Reutilizando el punto de reinicio guardado {info.get('guardado', '(sin datos)')}: "
          f"{info.get('p1', '?')} vs {info.get('p2', '?')}")
    link.send("LOAD", *(["TURBO"] if turbo else []))
    for _ in range(30):
        link.step()
    wait_full_life("Esperando a que cargue el punto de reinicio...")
    check_fighters(link.state, "tras cargar el punto de reinicio")
    link.auto_reset = True
    link._round_start = link.frames
    print("Punto de reinicio cargado." + (" Acelerando..." if turbo else ""))
elif reset:
    # El punto de reinicio tiene que ser el inicio de una ronda: esperar vida llena en los dos.
    wait_full_life("Esperando el inicio de una ronda (vida llena en los dos) para guardar el punto de reinicio...")
    check_fighters(link.state, "antes de guardar el punto de reinicio")
    link.send("SAVE", *(["TURBO"] if turbo else []))   # inicio de ronda + acelerar
    link.auto_reset = True   # desde ahora, cada ronda terminada recarga ESTE punto de reinicio
    link._round_start = link.frames
    SAVE_INFO.parent.mkdir(exist_ok=True)
    SAVE_INFO.write_text(json.dumps({"p1": link.state.me.character, "p2": link.state.rival.character,
                                     "guardado": time.strftime("%Y-%m-%d %H:%M:%S")}), encoding="utf-8")
    print(f"Punto de reinicio guardado: {link.state.me.character} vs {link.state.rival.character}."
          + (" Acelerando..." if turbo else ""))
else:
    check_fighters(first, "al conectar")
    if turbo:
        link.send("TURBO")
if turbo:   # si el script Lua se reinicia, vuelve a velocidad normal: re-acelerar
    link.on_reconnect = lambda: link.send("TURBO")
if play:
    print("MODO PRUEBA: usa lo aprendido, sin explorar y sin guardar nada.")

stats = Counter()
combo_stats = Counter()
chosen = Counter()        # acciones elegidas por el bot (nombre -> veces)
combo_timing = Counter()  # (frames desde el ultimo golpe al rival, conecto el primer golpe) -> veces


def on_round_end(state):
    if state.rival.life == 0 and state.me.life > 0:
        stats["ganadas"] += 1
    elif state.me.life == 0 and state.rival.life > 0:
        stats["perdidas"] += 1
    else:
        stats["empates"] += 1
    brain.discard_pending()   # la recarga cambia la vida de golpe: no es un golpe


def on_log(message):
    if message.startswith("  -> "):   # accion elegida: "  -> nombre (notacion) d=..."
        chosen[message[5:].split(" (")[0]] += 1
    elif message.strip().startswith("combo:"):
        done, total = message.split(":")[1].split("partes")[0].strip().split("/")
        combo_stats["intentos"] += 1
        combo_stats["completos"] += int(done) == int(total)
        combo_stats["con 2+ golpes"] += int(done) >= 2
        if "desde golpe" in message:   # cuanto hacia que el rival recibio el ultimo golpe
            since = int(message.rsplit("desde golpe", 1)[1])
            bucket = ("<60 f" if since < 60 else "60-119 f" if since < 120 else ">=120 f")
            combo_timing[(bucket, int(done) >= 1)] += 1
    elif message.startswith("Deteniendo") or message.startswith("IA "):
        print(message)


reader = LockstepReader(link)
table_path = ROOT / f"learned_{character}.json"
backup = None
if table_path.exists():   # respaldo antes de entrenar (por si la sesion sale mal)
    backup = ROOT / "backups" / f"learned_{character}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    backup.parent.mkdir(exist_ok=True)
    shutil.copy(table_path, backup)
imitation = Imitation.load(ROOT / "recordings" / "imitation.json", character)
brain = LearningBrain(reader, moves, table_path, explore=not play, imitation=imitation)
link.on_round_end = on_round_end
known_before = sum(n for acts in brain.table.values() for n, _ in acts.values())
def in_fight():
    """Pelea real (no menus ni pantallas de continuar, donde A/B/C/D eligen opciones)."""
    s = reader.read()
    return (s is not None and 0 < s.me.life <= MAX_LIFE and 0 < s.rival.life <= MAX_LIFE
            and 150 <= s.me.screen_y <= 240 and 150 <= s.rival.screen_y <= 240)


bot = RuleBot(LockstepKeyboard(link), LockstepClock(link), config, None,
              lambda: reader.read().facing_right, on_log, reader, moves, brain,
              focus_required=False, fight_check=in_fight)
bot.save_every = float("inf") if play else 120   # en modo prueba no se guarda nada
defense = DefenseLogger(ROOT / "logs" / f"defensa_{character}_{time.strftime('%Y%m%d_%H%M%S')}.csv",
                        lambda: bot.current)
link.on_step = defense.observe
offense = brain.combat_mode
print(f"Estilo: {brain.style}, modo: {offense}, guardia preventiva: {'si' if brain.preventive_guard else 'no'}, "
      f"tiempo de reaccion extra: {brain.reaction_frames} frames")

start = time.time()
frames0 = link.frames
bot.start()
next_report = start + 30
practice_suspect = False
stop_file = ROOT / "logs" / "STOP"   # crear este archivo corta la sesion guardando todo
stop_file.unlink(missing_ok=True)
while bot.running and time.time() - start < minutes * 60:
    time.sleep(1)
    if stop_file.exists():
        stop_file.unlink(missing_ok=True)
        print("Corte pedido (logs/STOP): termino la sesion guardando el resumen.")
        break
    # Contra el dummy de practica (no ataca) el bot aprende que atacar siempre sale bien.
    if not play and link.frames - frames0 > 60 * 60 and brain.taken_total == 0:
        practice_suspect = True
        print("AVISO: 1 minuto de juego sin recibir ningun golpe: parece el modo practica "
              "(el dummy no ataca). Detengo para no sesgar el aprendizaje. Usa el arcade.")
        break
    if time.time() >= next_report:
        elapsed = time.time() - start
        fps = (link.frames - frames0) / elapsed
        rounds = stats["ganadas"] + stats["perdidas"] + stats["empates"]
        print(f"[{elapsed / 60:4.1f} min] {fps:5.0f} fps ({fps / 59.19:4.1f}x)  rondas {rounds}: "
              f"{stats['ganadas']} ganadas / {stats['perdidas']} perdidas  "
              f"experiencias +{brain.updates}")
        next_report += 30
bot.stop()
while bot.running:
    time.sleep(0.05)

# volver a velocidad normal y soltar todo
link.keys = set()
link.send("NORMAL")
link.step()
if play:
    print("Modo prueba: no se guardo nada de esta sesion.")
elif practice_suspect:
    # El bot guarda cada 30 s durante la sesion: deshacer con el respaldo.
    if backup:
        shutil.copy(backup, table_path)
    elif table_path.exists():
        table_path.unlink()
    print("Lo de esta sesion NO se guarda (contra el dummy): restaurado el respaldo.")
else:
    brain.save()

elapsed = time.time() - start
frames = link.frames - frames0
rounds = stats["ganadas"] + stats["perdidas"] + stats["empates"]
print("\n== Resumen del entrenamiento acelerado ==")
print(f"Tiempo real {elapsed / 60:.1f} min, frames de juego {frames} "
      f"({frames / 59.19 / 60:.1f} min de juego, {frames / max(elapsed, 1) / 59.19:.1f}x)")
print(f"Rondas {rounds}: {stats['ganadas']} ganadas, {stats['perdidas']} perdidas, {stats['empates']} otras "
      f"({100 * stats['ganadas'] / max(rounds, 1):.0f}% ganadas)")
print(f"Danio hecho {brain.dealt_total}, recibido {brain.taken_total} en golpes "
      f"+ {brain.chip_total} de raspado bloqueando especiales")
print(f"Combos: {combo_stats['intentos']} intentos, {combo_stats['con 2+ golpes']} con 2+ golpes, "
      f"{combo_stats['completos']} completos")
combo_choices = [(n, c) for n, c in chosen.most_common() if "combo" in n or "castigo" in n]
if combo_choices:
    print("Combos y castigos elegidos: " + ", ".join(f"{n} x{c}" for n, c in combo_choices[:10]))
if combo_timing:
    print("Primer golpe del combo segun el tiempo desde el ultimo golpe al rival: " + ", ".join(
        f"{b}: {combo_timing[(b, True)]} conecto / {combo_timing[(b, False)]} no"
        for b in ("<60 f", "60-119 f", ">=120 f") if combo_timing[(b, True)] + combo_timing[(b, False)]))
print(f"Aprendizaje: +{brain.updates} experiencias (antes {known_before}), "
      f"recompensa media {brain.reward_sum / max(brain.updates, 1):+.2f}")
defense.close()
print(defense.report())
if brain.strategy:
    print(f"Modelo del rival: {brain.strategy.model.summary()}")
# Resumen de la sesion para comparar versiones (tools/compare_sessions.py)
summary = {"personaje": character, "modo": offense, "estilo": brain.style, "modo_prueba": play,
           "minutos_juego": frames / 59.19 / 60, "ganadas": stats["ganadas"], "perdidas": stats["perdidas"],
           "otras": stats["empates"], "combos": dict(combo_stats), "rival": first.rival.character,
           "decisiones": dict(brain.arbiter.decisions), "preventiva": brain.preventive_guard,
           "legacy_punish": brain.legacy_punish, "legacy_escapes": brain.legacy_escapes,
           **defense.metrics(rounds)}
session_path = defense.path.with_name(defense.path.stem.replace("defensa_", "sesion_") + ".json")
session_path.write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Resumen de sesion: {session_path}")
