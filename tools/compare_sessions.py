"""Compara sesiones de train_fast.py por modo de combate (DEFENSE_ONLY = defensa original,
DEFENSE_WITH_PUNISH, BALANCED_EXPERIMENTAL) y por rival. Lee logs/sesion_*.json.

Uso: python tools/compare_sessions.py [personaje] [rival] [--play] [--by-session]
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ROWS = [("minutos de juego", "minutos_juego", "sum"), ("rondas", "rondas", "sum"),
        ("ganadas %", None, "win"), ("danio hecho / ronda", "danio_hecho_por_ronda", "avg"),
        ("danio recibido / ronda", "danio_recibido_por_ronda", "avg"),
        ("defensa correcta %", "defensa_correcta_pct", "avg"),
        ("castigos", "castigos", "sum"), ("castigos con danio", "castigos_con_danio", "sum"),
        ("ataques con danio", "ataques_con_danio", "sum"), ("ataques fallidos", "ataques_fallidos", "sum"),
        ("ofensiva tras defensa %", "ofensiva_tras_defensa_pct", "avg"),
        ("neutral quieto %", "quieto_pct", "avg"), ("neutral cubriendose sin motivo %", "guardia_sin_amenaza_pct", "avg")]

def load_groups(logs, character, rival=None, play=False, by_session=False):
    groups = defaultdict(list)
    for path in sorted(Path(logs).glob(f"sesion_{character}_*.json")):
        s = json.loads(path.read_text(encoding="utf-8"))
        if bool(s.get("modo_prueba")) != play or (rival is not None and s.get("rival") != rival):
            continue
        mode = s.get("modo") or {"strategic": "BALANCED_EXPERIMENTAL"}.get(s.get("ofensiva"), "DEFENSE_ONLY")
        name = mode + (" + preventiva" if s.get("preventiva") else "")
        name += f" / {s.get('rival', 'sin rival')} / {'prueba' if play else 'entrenamiento'}"
        if by_session:
            name = path.stem + " / " + name
        groups[name].append(s)
    return groups


def value(sessions, key, how):
    if how == "win":
        won = sum(s["ganadas"] for s in sessions)
        total = sum(s["ganadas"] + s["perdidas"] + s["otras"] for s in sessions)
        return 100 * won / max(total, 1)
    if how == "sum":
        return sum(s.get(key, 0) for s in sessions)
    weights = [max(s.get("minutos_juego", 1), 0.01) for s in sessions]   # promedio ponderado por tiempo
    return sum(s.get(key, 0) * w for s, w in zip(sessions, weights)) / sum(weights)


def main(argv=None, logs=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("character", nargs="?", default="Iori")
    parser.add_argument("rival", nargs="?")
    parser.add_argument("--play", action="store_true", help="Comparar solo pruebas sin guardar aprendizaje")
    parser.add_argument("--by-session", action="store_true", help="Mostrar cada sesion por separado")
    args = parser.parse_args(argv)
    groups = load_groups(logs if logs is not None else ROOT / "logs",
                         args.character, args.rival, args.play, args.by_session)
    if not groups:
        print(f"No hay sesiones de {args.character} con esos filtros.")
        return 1
    names = sorted(groups)
    print("Danio recibido incluye raspado; los registros historicos conservan sus mediciones originales.")
    for i, name in enumerate(names, 1):
        print(f"[{i}] {name} ({len(groups[name])})")
    print(f"{'':34s}" + "".join(f"{f'[{i}]':>18s}" for i in range(1, len(names) + 1)))
    for label, key, how in ROWS:
        print(f"{label:34s}" + "".join(f"{value(groups[n], key, how):18.1f}" for n in names))
    states = sorted({k for g in groups.values() for s in g for k in s.get("tiempo_por_estado_pct", {})})
    print("tiempo por estado %:")
    for st in states:
        print(f"  {st:32s}" + "".join(
            f"{value([{**s, 'v': s.get('tiempo_por_estado_pct', {}).get(st, 0)} for s in groups[n]], 'v', 'avg'):18.1f}"
            for n in names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
