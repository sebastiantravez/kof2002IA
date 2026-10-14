"""Tabla de estados del byte +0x073 (identificador de animacion/estado del jugador, encontrado
con tools/find_move_id.py): para cada valor, cuantos frames dura, que hacia el jugador (ataca,
agachado, en el aire), que pulsacion lo inicio, si en ese estado perdio vida (golpeado) o si
el rival atacaba cerca y no perdio vida sosteniendo atras (bloqueo probable).

Uso: python tools/state_table.py grabacion.csv [--player=1|2] [--offset=0x73]
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from analyze_my_play import facing, load, numpad, player, pressed_button  # noqa: E402
from learn_from_replays import char_name, label_press  # noqa: E402

STRUCT = 0x200


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--player=")), 1))
    off = int(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--offset=")), "0x73"), 16)
    path = Path(args[0])
    rows = load(path)
    data = path.with_suffix(".bin").read_bytes()
    other = 3 - n

    def val(i):
        return data[i * 2 * STRUCT + (n - 1) * STRUCT + off]

    # pulsaciones etiquetadas del jugador
    dirs, presses = [], {}
    for i, row in enumerate(rows):
        dirs.append(numpad(row["inputs"], n, facing(row, n, other)))
        if i:
            for b in pressed_button(row, rows[i - 1], n):
                presses[i] = label_press(dirs, b)

    # segmentos de valor constante
    segs = []
    start = 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or val(i) != val(start):
            segs.append((val(start), start, i))
            start = i
    table = defaultdict(lambda: {"frames": 0, "segs": 0, "atk": 0, "crouch": 0, "air": 0, "hit": 0,
                                 "block": 0, "labels": Counter(), "chars": Counter(), "lens": []})
    for v, a, b in segs:
        t = table[v]
        t["frames"] += b - a
        t["segs"] += 1
        t["lens"].append(b - a)
        for i in range(a, b):
            p = player(rows[i], n)
            t["atk"] += p["attacking"]
            t["crouch"] += p["crouching"]
            t["air"] += p["h"] > 0
            t["chars"][char_name(rows[i][f"p{n}char"])] += 1
            if i:
                prev = player(rows[i - 1], n)
                lost = prev["life"] - p["life"]
                if 0 < lost <= 60:
                    t["hit"] += 1
                r = player(rows[i], other)
                d = numpad(rows[i]["inputs"], n, facing(rows[i], n, other))
                if r["attacking"] and abs(p["x"] - r["x"]) <= 110 and d in (1, 4) and lost <= 0:
                    t["block"] += 1
        for k in range(a - 6, a + 1):
            if k in presses:
                t["labels"][presses[k]] += 1
    print(f"{path.name} P{n} +0x{off:03X}: {len(segs)} segmentos")
    print(f"{'valor':>5s} {'frames':>7s} {'veces':>6s} {'dur.med':>8s} {'ataca%':>7s} {'agach%':>7s} {'aire%':>6s} {'golpes':>7s} {'bloq?':>6s}  inicio por pulsacion / personajes")
    for v, t in sorted(table.items(), key=lambda kv: -kv[1]["frames"]):
        if t["frames"] < 10:
            continue
        f = t["frames"]
        med = sorted(t["lens"])[len(t["lens"]) // 2]
        labs = ", ".join(f"{l}x{c}" for l, c in t["labels"].most_common(3))
        chars = "/".join(c for c, _ in t["chars"].most_common(3))
        print(f"{v:5d} {f:7d} {t['segs']:6d} {med:8d} {100 * t['atk'] / f:6.0f}% {100 * t['crouch'] / f:6.0f}% "
              f"{100 * t['air'] / f:5.0f}% {t['hit']:7d} {t['block']:6d}  {labs}  [{chars}]")


if __name__ == "__main__":
    main()
