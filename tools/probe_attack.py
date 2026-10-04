"""Busca en la RAM del jugador el bit que indica "esta atacando".

Hace atacar a P1 (C, B, 2B, 236A) y tambien caminar/agacharse/estar quieto, y
busca bits que se encienden en todos los ataques y nunca en lo demas.
Usar en modo practica (dummy quieto) con lua/kof_state.lua cargado.
Resultado encontrado: +0x0E0 bit0 (ver kof_ai/game_state.py).
"""
from probe_common import focus_emulator, find_bits, keyboard, record

focus_emulator()
calm, attacks = [], []
for _ in range(2):
    calm += [p1 for p1, _ in record("5[40]", 40)[10:]]
    attacks.append([p1 for p1, _ in record("C", 35)[:15]])
    calm += [p1 for p1, _ in record("5[40]", 40)[15:]]
    attacks.append([p1 for p1, _ in record("B", 30)[:12]])
    calm += [p1 for p1, _ in record("5[40]", 40)[15:]]
    calm += [p1 for p1, _ in record("6[30]", 30)[5:]]
    calm += [p1 for p1, _ in record("4[30]", 30)[5:]]
    calm += [p1 for p1, _ in record("1[30]", 30)[8:]]
    calm += [p1 for p1, _ in record("5[40]", 40)[15:]]
    attacks.append([p1 for p1, _ in record("2B", 30)[:10]])
    calm += [p1 for p1, _ in record("5[50]", 50)[15:]]
    attacks.append([p1 for p1, _ in record("236A", 50)[8:30]])
    calm += [p1 for p1, _ in record("5[60]", 60)[30:]]
keyboard.release_all()

found = find_bits(attacks, calm)
print(f"Bits candidatos (cobertura sobre {sum(map(len, attacks))} frames de ataque):")
for coverage, offset, mask in found[:15]:
    print(f"  +0x{offset:03x} mask 0x{mask:02x}  cobertura {coverage}")
if not found:
    print("Ninguno: repetir en practica con el dummy quieto.")
