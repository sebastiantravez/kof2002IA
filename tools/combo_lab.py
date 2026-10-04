"""Laboratorio de combos: prueba cada combo del personaje contra el dummy y mide
cuantas partes conectan (combos con hit-confirm, ver kof_ai/combo.py).

Uso: python tools/combo_lab.py [personaje]
Usar en modo practica, dummy quieto y SIN guardia, con lua/kof_state.lua cargado.
Prueba variantes de velocidad de los movimientos (frames por direccion) y de pausa
tras cada impacto, y reporta la mejor.
"""
import json
import sys
import time

from probe_common import ROOT, clock, config, focus_emulator, keyboard, read_raw

from kof_ai.combo import play_combo
from kof_ai.game_state import StateReader
from kof_ai.imitation import Imitation
from kof_ai.motions import parse, play

STEP_FRAMES = (2,)
AFTER_HIT_DELAYS = (2, 4)
REPEATS = 3
APPROACH_DISTANCE = 32
KNOCKDOWN_RECOVERY_FRAMES = 160


def approach(reader):
    for _ in range(40):
        state = reader.read()
        if state is None:
            raise SystemExit("Sin vision: carga lua/kof_state.lua")
        if state.distance <= APPROACH_DISTANCE:
            return state
        play(keyboard, clock, parse("6[5]"), state.facing_right)
    return reader.read()


def wait_dummy_recovered():
    """Espera a que la vida del dummy deje de cambiar (en practica se recupera sola)."""
    last, stable = None, 0
    for _ in range(240):
        clock.wait_frames(1)
        _, _, p2 = read_raw()
        stable = stable + 1 if p2[0x139] == last else 0
        last = p2[0x139]
        if stable >= 20:
            return


def rival_life():
    return read_raw()[2][0x139]


def test_combo(reader, name, notation):
    parts = notation.count(">") + 1
    print(f"\n== {name}: {notation}  ({parts} partes)")
    rows = []
    for step in STEP_FRAMES:
        for delay in AFTER_HIT_DELAYS:
            connected = damage = tries = 0
            for _ in range(REPEATS * 2):
                if tries == REPEATS:
                    break
                state = approach(reader)
                wait_dummy_recovered()
                state = reader.read()
                if state.distance > APPROACH_DISTANCE + 8:
                    print(f"      (intento saltado: distancia {state.distance})")
                    play(keyboard, clock, parse("4[30]"), state.facing_right)  # despegarse de la esquina
                    continue
                tries += 1
                c, dmg, _ = play_combo(keyboard, clock, notation, state.facing_right, rival_life,
                                       step, config["button_hold_frames"], after_hit_delay=delay)
                clock.wait_frames(KNOCKDOWN_RECOVERY_FRAMES)  # si lo derribo, que se levante
                connected += c
                damage += dmg
            tries = max(tries, 1)
            rows.append((connected / tries, damage / tries, step, delay))
            print(f"   paso {step}f, pausa {delay}f: {connected / tries:.1f}/{parts} partes  "
                  f"danio {damage / tries:5.1f}")
    best = max(rows)
    print(f"   MEJOR: paso {best[2]}f, pausa {best[3]}f -> {best[0]:.1f}/{parts} partes, {best[1]:.1f} de danio")
    return {"notation": notation, "parts": parts, "connected": best[0], "damage": best[1],
            "step_frames": best[2], "after_hit_delay": best[3]}


def main():
    character = next((a for a in sys.argv[1:] if not a.startswith("--")), "Kyo")
    moves = config["characters"][character]
    reader = StateReader(ROOT / "state.txt")
    combos = {**moves.get("combos", {}), **moves.get("punish", {})}
    imitation = Imitation.load(ROOT / "recordings" / "imitation.json", character)
    if imitation:
        combos.update(imitation.combos)   # tambien los combos de jugadores reales
    focus_emulator()
    results = {name: test_combo(reader, name, notation) for name, notation in combos.items()}
    keyboard.release_all()
    out = ROOT / "captures" / f"combo_lab_{character}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nResultados en {out}")


if __name__ == "__main__":
    main()
