"""Entrenamiento acelerado con lua/kof_train.lua: el juego corre sin limite de
velocidad, el bot controla a P1 frame a frame (sin foco: puedes usar la PC) y cada
ronda que termina se reinicia al instante cargando la partida guardada.

Uso:
  1) En el emulador, en una pelea (arcade o practica) al INICIO de una ronda,
     cargar lua/kof_train.lua.
  2) python tools/train_fast.py <personaje> [minutos] [--normal]
     --normal: sin acelerar (para mirar como juega).
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
from kof_ai.game_state import MAX_LIFE  # noqa: E402
from kof_ai.imitation import Imitation  # noqa: E402
from kof_ai.learning import LearningBrain  # noqa: E402
from kof_ai.lockstep import Lockstep, LockstepClock, LockstepKeyboard, LockstepReader  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
character = args[0] if args else "Kim"
minutes = float(args[1]) if len(args) > 1 else 10
turbo = "--normal" not in sys.argv
config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
moves = config["characters"][character]

link = Lockstep(ROOT)
print("Esperando a lua/kof_train.lua en el emulador...")
first = link.step()
print(f"Conectado. P1 = {first.me.character}, P2 = {first.rival.character}, "
      f"vida {first.me.life}/{first.rival.life}")
if first.me.character != character:
    print(f"AVISO: el personaje de P1 es {first.me.character}, no {character}.")
# El punto de reinicio tiene que ser el inicio de una ronda: esperar vida llena en los dos.
waited = 0
while not (link.state.me.life == MAX_LIFE and link.state.rival.life == MAX_LIFE):
    if waited == 0:
        print("Esperando el inicio de una ronda (vida llena en los dos) para guardar el punto de reinicio...")
    link.step()
    waited += 1
    if waited > 60 * 120:
        sys.exit("No llego un inicio de ronda en 2 minutos de juego.")
link.send("SAVE", *(["TURBO"] if turbo else []))   # inicio de ronda + acelerar
link.auto_reset = True   # desde ahora, cada ronda terminada recarga ESTE punto de reinicio
link._round_start = link.frames
if turbo:   # si el script Lua se reinicia, vuelve a velocidad normal: re-acelerar
    link.on_reconnect = lambda: link.send("TURBO")
print("Punto de reinicio guardado." + (" Acelerando..." if turbo else ""))

stats = Counter()
combo_stats = Counter()


def on_round_end(state):
    if state.rival.life == 0 and state.me.life > 0:
        stats["ganadas"] += 1
    elif state.me.life == 0 and state.rival.life > 0:
        stats["perdidas"] += 1
    else:
        stats["empates"] += 1
    brain.discard_pending()   # la recarga cambia la vida de golpe: no es un golpe


def on_log(message):
    if message.strip().startswith("combo:"):
        done, total = message.split(":")[1].split("partes")[0].strip().split("/")
        combo_stats["intentos"] += 1
        combo_stats["completos"] += int(done) == int(total)
        combo_stats["con 2+ golpes"] += int(done) >= 2
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
brain = LearningBrain(reader, moves, table_path, imitation=imitation)
link.on_round_end = on_round_end
known_before = sum(n for acts in brain.table.values() for n, _ in acts.values())
bot = RuleBot(LockstepKeyboard(link), LockstepClock(link), config, None,
              lambda: reader.read().facing_right, on_log, reader, moves, brain,
              focus_required=False, fight_check=lambda: True)
bot.save_every = 120   # guardar menos seguido: cada guardado frena unos ms al emulador

start = time.time()
frames0 = link.frames
bot.start()
next_report = start + 30
practice_suspect = False
while bot.running and time.time() - start < minutes * 60:
    time.sleep(1)
    # Contra el dummy de practica (no ataca) el bot aprende que atacar siempre sale bien.
    if link.frames - frames0 > 60 * 60 and brain.taken_total == 0:
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
if practice_suspect:
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
print(f"Danio hecho {brain.dealt_total}, recibido {brain.taken_total}")
print(f"Combos: {combo_stats['intentos']} intentos, {combo_stats['con 2+ golpes']} con 2+ golpes, "
      f"{combo_stats['completos']} completos")
print(f"Aprendizaje: +{brain.updates} experiencias (antes {known_before}), "
      f"recompensa media {brain.reward_sum / max(brain.updates, 1):+.2f}")
