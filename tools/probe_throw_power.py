"""Busca en la RAM:
  1) el bit "me estan agarrando" (en el struct del DUMMY mientras P1 lo agarra),
  2) el byte de barras de poder de P1 (baja al usar un DM).

Usar en modo practica con P1 = Kim, dummy quieto, lua/kof_state.lua cargado.
"""
import sys

from probe_common import ROOT, clock, focus_emulator, keyboard, read_raw, record

from kof_ai.game_state import StateReader
from kof_ai.motions import parse, play

reader = StateReader(ROOT / "state.txt")
DM = sys.argv[1] if len(sys.argv) > 1 else "236236D"   # Kim: Hou'ou Hiten Kyaku


def approach(max_distance=28):
    for _ in range(50):
        s = reader.read()
        if s.distance <= max_distance:
            return s
        play(keyboard, clock, parse("6[4]"), s.facing_right)
    return reader.read()


focus_emulator()

# 1) agarrado: P2 mientras lo agarro (6C / 6D) frente a P2 mientras recibe golpes normales
thrown, hit, calm = [], [], []
for button in ("C", "D", "C"):
    s = approach()
    clock.wait_frames(30)
    calm += [p2 for _, p2 in record("5[20]", 20)]
    frames = [p2 for _, p2 in record(f"6{button}", 70, s.facing_right)]
    lives = [f[0x139] for f in frames]
    if lives[-1] < lives[0]:
        thrown.append(frames[3:40])
        print(f"agarre 6{button}: vida dummy {lives[0]} -> {lives[-1]}")
    else:
        print(f"agarre 6{button}: no conecto (vida {lives[0]} -> {lives[-1]})")
    clock.wait_frames(150)
for _ in range(3):
    s = approach(40)
    clock.wait_frames(30)
    hit += [p2 for _, p2 in record("2B", 30, s.facing_right)]
    clock.wait_frames(60)

print("\nBits candidatos 'me estan agarrando' (encendidos en todos los agarres, nunca al recibir golpes ni quieto):")
off_frames = hit + calm
found = []
for off in range(0x200):
    for bit in range(8):
        mask = 1 << bit
        if any(f[off] & mask for f in off_frames):
            continue
        if thrown and all(any(f[off] & mask for f in seg) for seg in thrown):
            found.append((sum(sum(1 for f in seg if f[off] & mask) for seg in thrown), off, mask))
for cov, off, mask in sorted(found, reverse=True)[:10]:
    print(f"  +0x{off:03x} mask 0x{mask:02x} cobertura {cov}")
if not found:
    print("  ninguno")

# 2) barras: struct de P1 antes y despues de un DM
s = approach(60)
clock.wait_frames(40)
before = read_raw()[1]
play(keyboard, clock, parse(DM), s.facing_right)
clock.wait_frames(120)
after = read_raw()[1]
keyboard.release_all()
print(f"\nBytes de P1 que bajaron tras el DM ({DM}):")
for off in range(0x200):
    if after[off] < before[off] and before[off] <= 5:
        print(f"  +0x{off:03x}: {before[off]} -> {after[off]}   <- candidato a barras (0..5)")
print("(si no hay candidatos, las barras no estan en el struct del jugador)")
