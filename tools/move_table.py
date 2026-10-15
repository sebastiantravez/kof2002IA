"""Tabla de movimientos del rival a partir de logs/defensa_*.csv (filas 'movimiento').

Para cada (personaje, estado +0x073): cuantas veces lo hizo, cuanto dura el bit de ataque
(animacion completa), y como acabo contra Iori (golpeado / bloqueado / evitado). Los
movimientos largos que terminan bloqueados o evitados son candidatos a castigo; hay que
verificarlos con tools/guard_test.py antes de usarlos.

Uso: python tools/move_table.py [logs/defensa_Iori_....csv ...]   (por defecto: todos)
"""
import csv
import glob
import re
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
paths = sys.argv[1:] or sorted(glob.glob(str(ROOT / "logs" / "defensa_*.csv")))
table = defaultdict(lambda: {"n": 0, "dur": [], "res": defaultdict(int), "dmg": 0})
for path in paths:
    try:
        rows = list(csv.DictReader(open(path, encoding="utf-8")))
    except OSError:
        continue
    for r in rows:
        if r.get("evento") != "movimiento":
            continue
        m = re.search(r"estado (\d+) dura (\d+) f", r.get("motivo", ""))
        if not m:
            continue
        t = table[(r["rival"], int(m.group(1)))]
        t["n"] += 1
        t["dur"].append(int(m.group(2)))
        t["res"][r["resultado"]] += 1
        t["dmg"] += int(r["danio"] or 0)
print(f"{'personaje':10s}{'estado':>7s}{'veces':>6s}{'dur.med':>8s}{'dur.max':>8s}{'golpeado':>9s}{'bloqueado':>10s}{'evitado':>8s}{'danio':>7s}")
for (char, state), t in sorted(table.items(), key=lambda kv: (-kv[1]["n"])):
    if t["n"] < 3:
        continue
    r = t["res"]
    print(f"{char:10s}{state:7d}{t['n']:6d}{median(t['dur']):8.0f}{max(t['dur']):8d}"
          f"{r['golpeado']:9d}{r['bloqueado']:10d}{r['evitado']:8d}{t['dmg']:7d}")
