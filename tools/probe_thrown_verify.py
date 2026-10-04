"""Verifica candidatos al bit "me estan agarrando" en mas situaciones que el probe
original: el bit correcto solo debe encenderse cuando agarran al dummy, NO cuando
recibe golpes, cuando lo derriban, cuando se levanta ni cuando el que agarra es P1.

Usar en modo practica con P1 = Kim, dummy quieto y sin guardia, lua/kof_state.lua.
"""
from probe_common import ROOT, clock, focus_emulator, keyboard, record

from kof_ai.game_state import StateReader
from kof_ai.motions import parse, play

CANDIDATES = [(0x073, 0x02), (0x079, 0x02), (0x0BD, 0x10), (0x0BD, 0x08), (0x0BD, 0x01),
              (0x0BD, 0x02), (0x0BD, 0x04), (0x1DD, 0x08), (0x0AD, 0x01), (0x051, 0x08)]
reader = StateReader(ROOT / "state.txt")


def approach(max_distance=28):
    for _ in range(50):
        s = reader.read()
        if s.distance <= max_distance:
            return s
        play(keyboard, clock, parse("6[4]"), s.facing_right)
    return reader.read()


def scenario(name, notation, frames, max_distance=28):
    s = approach(max_distance)
    clock.wait_frames(40)
    samples = record(notation, frames, s.facing_right)
    clock.wait_frames(60)
    return name, samples


focus_emulator()
results = []
for _ in range(2):
    results.append(scenario("agarre 6C", "6C", 90))
    results.append(scenario("agarre 6D", "6D", 90))
    results.append(scenario("golpe 2B", "2B", 40, 40))
    results.append(scenario("golpe C", "C", 50))
    results.append(scenario("barrida 2D (derribo + levantarse)", "2D", 150, 60))
    results.append(scenario("Hangetsu C>214D (derribo)", "C5[6]214D", 150))
    results.append(scenario("quieto", "5[60]", 60))
keyboard.release_all()

print(f"{'candidato':16s}" + "".join(f"{name[:14]:>16s}" for name, _ in results[:7]))
for off, mask in CANDIDATES:
    row = f"+0x{off:03x}/{mask:02x} P2  "
    for name, samples in results[:7]:
        both = [s for n, s in results if n == name]
        on = sum(1 for samp in both for _, p2 in samp if p2[off] & mask)
        row += f"{on:16d}"
    print(row)
    row = f"+0x{off:03x}/{mask:02x} P1  "
    for name, samples in results[:7]:
        both = [s for n, s in results if n == name]
        on = sum(1 for samp in both for p1, _ in samp if p1[off] & mask)
        row += f"{on:16d}"
    print(row)
print("\nEl correcto: P2 > 0 solo en las columnas de agarre; 0 en golpes, derribos y quieto; P1 siempre 0.")
