"""Saca de tus grabaciones (lua/kof_record.lua) los combos de un personaje con los inputs
EXACTOS, frame a frame, y los escribe en notacion del bot para probarlos con
tools/combo_lab_fast.py.

Uso: python tools/combos_from_recordings.py <personaje> [grabaciones.csv...] [--me=1]
     sin archivos: todas las grabaciones de recordings/.  --me: lado del jugador (por defecto 1).
Escribe recordings/combos_<personaje>.json: [{notacion, danio, golpes, distancia, origen}].
"""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from analyze_my_play import facing, load, numpad, player, pressed_button  # noqa: E402
from learn_from_replays import BUTTONS, COMBO_GAP, char_name  # noqa: E402

MIN_HITS = 3          # combos de al menos 3 impactos
LEAD_FRAMES = 14      # inputs antes de la primera pulsacion (movimientos circulares)
PRESS_BEFORE_HIT = 25 # la primera pulsacion que conecto tiene que estar a <= N frames del impacto


def on_screen(row):
    return 150 <= row["p1sy"] <= 240 and 150 <= row["p2sy"] <= 240 and row["p1life"] > 0


def frame_inputs(row, me, face):
    d = numpad(row["inputs"], me, face)
    buttons = "".join(b for b in BUTTONS if f"P{me} Button {b}" in row["inputs"])
    return d, buttons


def to_notation(frames):
    """[(dir, botones)] por frame -> '6[3] 6C[2] 5[4] ...' (runs con duracion exacta)."""
    runs = []
    for d, b in frames:
        if runs and runs[-1][0] == d and runs[-1][1] == b:
            runs[-1][2] += 1
        else:
            runs.append([d, b, 1])
    return " ".join(f"{d}{b}[{n}]" for d, b, n in runs)


def combos_in(path, character, me):
    rows = load(path)
    other = 3 - me
    hits = []                         # (indice, danio)
    for i in range(1, len(rows)):
        row, prev = rows[i], rows[i - 1]
        if not (on_screen(row) and on_screen(prev)):
            continue
        if char_name(row[f"p{me}char"]) != character:
            continue
        dmg = player(prev, other)["life"] - player(row, other)["life"]
        if 0 < dmg <= 60:
            hits.append((i, dmg))
    groups, group = [], []
    for h in hits:
        if group and rows[h[0]]["frame"] - rows[group[-1][0]]["frame"] > COMBO_GAP:
            groups.append(group)
            group = []
        group.append(h)
    if group:
        groups.append(group)
    found = []
    for g in groups:
        if len(g) < MIN_HITS:
            continue
        first, last = g[0][0], g[-1][0]
        press = next((j for j in range(first, max(first - PRESS_BEFORE_HIT, 1), -1)
                      if pressed_button(rows[j], rows[j - 1], me)), None)
        if press is None:
            continue
        start = max(press - LEAD_FRAMES, 1)
        # que no se mezcle con un combo anterior ni con un golpe recibido
        if any(player(rows[j - 1], me)["life"] > player(rows[j], me)["life"] for j in range(start, last + 1)):
            continue
        frames = [frame_inputs(rows[j], me, facing(rows[j], me, other)) for j in range(start, last + 1)]
        # Punto de control '|' justo despues del frame del primer impacto: si al reproducirlo
        # el primer golpe no conecta (bloqueado o fallado), el combo se corta ahi.
        k = first - start + 1
        notation = to_notation(frames[:k]) + (" | " + to_notation(frames[k:]) if frames[k:] else "")
        found.append({"notacion": notation, "danio": sum(d for _, d in g), "golpes": len(g),
                      "distancia": abs(player(rows[start], me)["x"] - player(rows[start], other)["x"]),
                      "origen": f"{path.name} frame {rows[start]['frame']}"})
    return found


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    character = args[0]
    me = int(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--me=")), 1))
    paths = [Path(a) for a in args[1:]] or [Path(p) for p in sorted(glob.glob(str(ROOT / "recordings" / "rec_*.csv")))]
    combos = []
    for path in paths:
        rows_ok = load(path)
        if not rows_ok or "p1char" not in rows_ok[0]:
            continue
        combos += combos_in(path, character, me)
    combos.sort(key=lambda c: -c["danio"])
    out = ROOT / "recordings" / f"combos_{character}.json"
    out.write_text(json.dumps(combos, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(combos)} combos de {character} con {MIN_HITS}+ golpes -> {out}")
    for c in combos[:10]:
        print(f"  {c['danio']:3d} danio, {c['golpes']} golpes, distancia {c['distancia']:3d}  ({c['origen']})")


if __name__ == "__main__":
    main()
