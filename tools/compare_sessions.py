"""Compara sesiones de train_fast.py por tipo de ofensiva (off = defensiva anterior,
strategic = DEFENSIVE OFFENSE AI V2). Lee logs/sesion_*.json.

Uso: python tools/compare_sessions.py [personaje]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
character = sys.argv[1] if len(sys.argv) > 1 else "Iori"

ROWS = [("minutos de juego", "minutos_juego", "sum"), ("rondas", "rondas", "sum"),
        ("ganadas %", None, "win"), ("danio hecho / ronda", "danio_hecho_por_ronda", "avg"),
        ("danio recibido / ronda", "danio_recibido_por_ronda", "avg"),
        ("defensa correcta %", "defensa_correcta_pct", "avg"),
        ("castigos", "castigos", "sum"), ("castigos con danio", "castigos_con_danio", "sum"),
        ("ataques con danio", "ataques_con_danio", "sum"), ("ataques fallidos", "ataques_fallidos", "sum"),
        ("ofensiva tras defensa %", "ofensiva_tras_defensa_pct", "avg"),
        ("neutral quieto %", "quieto_pct", "avg"), ("neutral cubriendose sin motivo %", "guardia_sin_amenaza_pct", "avg")]

groups = defaultdict(list)
for path in sorted((ROOT / "logs").glob(f"sesion_{character}_*.json")):
    s = json.loads(path.read_text(encoding="utf-8"))
    if not s.get("modo_prueba"):
        groups[s.get("ofensiva", "off")].append(s)
if not groups:
    sys.exit(f"No hay sesiones de {character} en logs/ (corre tools/train_fast.py primero).")


def value(sessions, key, how):
    if how == "win":
        won = sum(s["ganadas"] for s in sessions)
        total = sum(s["ganadas"] + s["perdidas"] + s["otras"] for s in sessions)
        return 100 * won / max(total, 1)
    if how == "sum":
        return sum(s.get(key, 0) for s in sessions)
    weights = [max(s.get("minutos_juego", 1), 0.01) for s in sessions]   # promedio ponderado por tiempo
    return sum(s.get(key, 0) * w for s, w in zip(sessions, weights)) / sum(weights)


names = sorted(groups)
print(f"{'':34s}" + "".join(f"{n + f' ({len(groups[n])})':>18s}" for n in names))
for label, key, how in ROWS:
    print(f"{label:34s}" + "".join(f"{value(groups[n], key, how):18.1f}" for n in names))
states = sorted({k for g in groups.values() for s in g for k in s.get("tiempo_por_estado_pct", {})})
print("tiempo por estado %:")
for st in states:
    print(f"  {st:32s}" + "".join(
        f"{value([{**s, 'v': s.get('tiempo_por_estado_pct', {}).get(st, 0)} for s in groups[n]], 'v', 'avg'):18.1f}"
        for n in names))
