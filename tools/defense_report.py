"""Reporte defensivo acumulado de todas las sesiones (logs/defensa_<personaje>_*.csv).

Uso: python tools/defense_report.py [personaje]
Agrupa por tipo de amenaza y por rival: ataques evitados, golpes recibidos, motivos y
castigos. Solo informacion observable (ver kof_ai/defense_log.py).
"""
import csv
import glob
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
character = sys.argv[1] if len(sys.argv) > 1 else "*"
files = sorted(glob.glob(str(ROOT / "logs" / f"defensa_{character}_*.csv")))
if not files:
    sys.exit("No hay registros en logs/ (se generan con tools/train_fast.py).")

by_threat = defaultdict(Counter)
by_rival = defaultdict(Counter)
reasons = Counter()
punish = Counter()
damage = Counter()
for path in files:
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["evento"] == "castigo":
                punish[row["resultado"]] += 1
                continue
            result = row["resultado"]
            by_threat[row["amenaza"]][result] += 1
            by_rival[row["rival"]][result] += 1
            if result == "golpeado":
                damage[row["amenaza"]] += int(row["danio"] or 0)
                if row["motivo"]:
                    reasons[row["motivo"]] += 1

print(f"{len(files)} sesiones\n")
print("== Por tipo de amenaza ==")
for threat, c in sorted(by_threat.items(), key=lambda kv: -sum(kv[1].values())):
    total = sum(c.values())
    print(f"  {threat:40s} {total:5d}  evitados {100 * c['evitado'] / total:4.0f}%  "
          f"golpeado {c['golpeado']:4d}  danio {damage[threat]}")
print("\n== Por rival ==")
for rival, c in sorted(by_rival.items(), key=lambda kv: -sum(kv[1].values())):
    total = sum(c.values())
    print(f"  {rival:10s} {total:5d}  evitados {100 * c['evitado'] / total:4.0f}%  golpeado {c['golpeado']}")
print("\n== Motivos de los golpes recibidos ==")
for reason, n in reasons.most_common():
    print(f"  {n:5d}  {reason}")
total_p = sum(punish.values())
if total_p:
    print(f"\n== Castigos ==\n  {total_p} intentos, {punish['exito']} con danio ({100 * punish['exito'] / total_p:.0f}%)")
