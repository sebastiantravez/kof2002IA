"""Busca en la RAM el bit "agachado" de P1.

Encendido: agachado quieto (2), agachado-atras (1), ataques agachados (2B, 2A, 2D).
Apagado: de pie, caminando, ataques de pie (C, B), saltando.
Usar en modo practica (dummy quieto) con lua/kof_state.lua cargado.
"""
from probe_common import focus_emulator, find_bits, find_values, keyboard, record

focus_emulator()
on, off = [], []
for _ in range(2):
    off += [p1 for p1, _ in record("5[30]", 30)[5:]]
    on.append([p1 for p1, _ in record("2[30]", 30)[6:28]])
    off += [p1 for p1, _ in record("5[30]", 30)[12:]]
    on.append([p1 for p1, _ in record("1[30]", 30)[6:28]])
    off += [p1 for p1, _ in record("5[30]", 30)[12:]]
    on.append([p1 for p1, _ in record("2B", 25)[4:14]])
    off += [p1 for p1, _ in record("5[40]", 40)[25:]]
    on.append([p1 for p1, _ in record("2D", 35)[4:20]])
    off += [p1 for p1, _ in record("5[50]", 50)[35:]]
    off += [p1 for p1, _ in record("6[30]", 30)[5:]]
    off += [p1 for p1, _ in record("C", 40)[4:30]]
    off += [p1 for p1, _ in record("5[40]", 40)[20:]]
    off += [p1 for p1, _ in record("B", 30)[4:20]]
    off += [p1 for p1, _ in record("5[40]", 40)[20:]]
    off += [p1 for p1, _ in record("8[3]", 50)[6:40]]
    off += [p1 for p1, _ in record("5[40]", 40)[20:]]
keyboard.release_all()

found = find_bits(on, off)
print(f"Bits candidatos para 'agachado' (cobertura sobre {sum(map(len, on))} frames agachado):")
for coverage, offset, mask in found[:12]:
    print(f"  +0x{offset:03x} mask 0x{mask:02x}  cobertura {coverage}")
if not found:
    print("  ninguno")

total = sum(map(len, on))
print(f"\nBytes cuyos valores 'agachado' no aparecen de pie (cobertura sobre {total}):")
for coverage, offset, on_vals, off_vals in find_values(on, off)[:12]:
    print(f"  +0x{offset:03x} cobertura {coverage:3d}  agachado={on_vals[:8]}  resto={off_vals[:10]}")
