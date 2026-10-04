"""Aprendizaje por imitacion: analiza grabaciones de peleas reales (lua/kof_record.lua)
y extrae combos, defensa y que hacen los jugadores en cada situacion.

Uso: python tools/learn_from_replays.py [archivos.csv...]   (por defecto: recordings/rec_*.csv)
Escribe recordings/imitation.json, que el cerebro usa como punto de partida.
"""
import csv
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bisect  # noqa: E402

from kof_ai.brain import ANTI_AIR_RANGE, CLOSE, MID  # noqa: E402
from kof_ai.game_state import CHARACTER_IDS, CHARACTER_OFFSET  # noqa: E402
from kof_ai.learning import DISTANCE_BUCKET  # noqa: E402

BUTTONS = "ABCD"
MOTIONS = ["41236", "63214", "2363214", "236", "214", "623", "421", "22"]  # de mas largo a mas corto
CHARGE_FRAMES = 30
COMBO_GAP = 40          # frames maximos entre impactos del mismo combo
HIT_WINDOW = 25         # un boton "conecto" si la vida del rival baja en estos frames
DEFENSE_WINDOW = 20     # frames tras el inicio de un ataque rival en que se mira la guardia


def load(path):
    rows = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                rows.append({k: int(v) for k, v in r.items() if k not in ("inputs", None)}
                            | {"inputs": set((r["inputs"] or "").split("|"))})
            except ValueError:
                continue
    return rows


def snapshot_characters():
    """(frames, [(p1char, p2char)]) de las capturas con RAM (tools/snap_series.py), para
    grabaciones antiguas sin columna de personaje."""
    points = []
    for path in glob.glob(str(ROOT / "recordings" / "snaps_*" / "*.txt")):
        lines = Path(path).read_text().split()
        if len(lines) == 3 and len(lines[1]) == 1024:
            p1, p2 = bytes.fromhex(lines[1]), bytes.fromhex(lines[2])
            points.append((int(lines[0]), p1[CHARACTER_OFFSET], p2[CHARACTER_OFFSET]))
    points.sort()
    return [p[0] for p in points], [(p[1], p[2]) for p in points]


def fill_characters(rows):
    if rows and "p1char" in rows[0]:
        return
    frames, chars = snapshot_characters()
    for row in rows:
        i = bisect.bisect_right(frames, row["frame"]) - 1
        row["p1char"], row["p2char"] = chars[i] if i >= 0 and frames else (-1, -1)


def char_name(cid):
    return CHARACTER_IDS.get(cid, f"id{cid}")


def player(row, n):
    p = f"p{n}"
    return {"x": row[p + "x"], "h": row[p + "h"], "sy": row[p + "sy"], "life": row[p + "life"],
            "attacking": bool(row[p + "flags"] & 1), "crouching": bool(row[p + "flags"] & 4)}


def in_fight(row):
    return 150 <= row["p1sy"] <= 240 and 150 <= row["p2sy"] <= 240 and row["p1life"] > 0 and row["p2life"] > 0


def numpad(inputs, n, facing_right):
    up, down = f"P{n} Up" in inputs, f"P{n} Down" in inputs
    left, right = f"P{n} Left" in inputs, f"P{n} Right" in inputs
    fwd, back = (right, left) if facing_right else (left, right)
    v = 7 if up else (1 if down else 4)          # fila: 7 arriba, 4 medio, 1 abajo
    return v + (2 if fwd else 0 if back else 1)  # 7/8/9, 4/5/6, 1/2/3


def label_press(dirs, button):
    """dirs: historial de direcciones numpad (frame a frame, el ultimo es el actual)."""
    compact = []
    for d in dirs[-16:]:
        if not compact or compact[-1] != d:
            compact.append(d)
    seq = "".join(map(str, compact))
    for motion in MOTIONS:
        # permitir diagonales/neutro intermedios: subsecuencia en orden dentro de las ultimas entradas
        it = iter(seq[-(len(motion) + 3):])
        if all(c in it for c in motion):
            return motion + button
    held = dirs[-CHARGE_FRAMES - 8:-6]
    if dirs[-1] in (7, 8, 9) and held and all(d in (1, 2, 3) for d in held):
        return f"[2]8{button}"
    if dirs[-1] in (3, 6, 9) and held and all(d in (1, 4, 7) for d in held):
        return f"[4]6{button}"
    d = dirs[-1]
    return (f"{d}{button}" if d != 5 else button)


def analyze(rows):
    combos = defaultdict(Counter)          # personaje -> combo -> veces
    combo_damage = defaultdict(list)       # (personaje, combo) -> danios
    defense = defaultdict(Counter)        # (tipo de ataque, guardia) -> {golpeado, bloqueado}
    situations = defaultdict(Counter)     # contexto -> accion
    presses = Counter()

    for me, rv in ((1, 2), (2, 1)):
        dirs = []
        hits = []                          # (frame, label, danio) de mis golpes que conectaron
        pending = []                       # pulsaciones esperando ver si conectan
        last_crouch = -999
        attack_start = None
        prev = None
        for i, row in enumerate(rows):
            if not in_fight(row):
                dirs, pending, prev = [], [], None
                continue
            m, r = player(row, me), player(row, rv)
            facing = m["x"] <= r["x"]
            d = numpad(row["inputs"], me, facing)
            dirs.append(d)
            f = row["frame"]
            dist = abs(m["x"] - r["x"])
            # botones pulsados en este frame (flanco de subida)
            if prev is not None:
                for b in BUTTONS:
                    key = f"P{me} Button {b}"
                    if key in row["inputs"] and key not in prev["inputs"]:
                        lab = label_press(dirs, b)
                        presses[lab] += 1
                        pending.append((f, lab))
                        situations[context(m, r, dist, row, prev, me, rv)][action_category(lab, dist)] += 1
                # acciones sin boton: salto, guardia, avanzar
                pd = dirs[-2] if len(dirs) > 1 else 5
                if d in (7, 8, 9) and pd not in (7, 8, 9):
                    situations[context(m, r, dist, row, prev, me, rv)]["salto"] += 1
                elif i % 6 == 0 and not any(f"P{me} Button {b}" in row["inputs"] for b in BUTTONS):
                    cat = {4: "guardia de pie / retroceder", 1: "guardia agachado", 6: "avanzar",
                           3: "avanzar agachado", 2: "agacharse", 5: "esperar"}.get(d)
                    if cat:
                        situations[context(m, r, dist, row, prev, me, rv)][cat] += 1
                # impactos al rival
                pr = player(prev, rv)
                dmg = pr["life"] - r["life"]
                if 0 < dmg <= 60:
                    lab = pending[-1][1] if pending else "?"
                    hits.append((f, lab, dmg, char_name(row[f"p{me}char"])))
                pending = [(pf, pl) for pf, pl in pending if f - pf <= HIT_WINDOW]
                # defensa: ataques del rival cerca
                if r["crouching"] or player(prev, rv)["crouching"]:
                    last_crouch = f
                if r["attacking"] and not player(prev, rv)["attacking"] and dist <= MID:
                    low = f - last_crouch <= 4
                    kind = "aereo" if r["h"] > 0 else ("bajo" if low else "de pie")
                    attack_start = (f, kind, m["life"], i)
                if attack_start and f - attack_start[0] == DEFENSE_WINDOW:
                    sf, kind, life0, si = attack_start
                    guard_dirs = [numpad(rows[j]["inputs"], me, player(rows[j], me)["x"] <= player(rows[j], rv)["x"])
                                  for j in range(si, i)]
                    common = Counter(guard_dirs).most_common(1)[0][0] if guard_dirs else 5
                    guard = {4: "de pie", 1: "agachado"}.get(common, "sin guardia")
                    got_hit = m["life"] < life0
                    defense[(kind, guard)]["golpeado" if got_hit else "ok"] += 1
                    attack_start = None
            prev = row
        # agrupar impactos en combos
        group = []
        for hit in hits:
            if group and (hit[0] - group[-1][0] > COMBO_GAP or hit[3] != group[-1][3]):
                record_combo(group, combos, combo_damage)
                group = []
            group.append(hit)
        record_combo(group, combos, combo_damage)
    return combos, combo_damage, defense, situations, presses


def record_combo(group, combos, combo_damage):
    if len(group) < 2:
        return
    labels = []
    for _, lab, _, _ in group:
        if not labels or labels[-1] != lab:
            labels.append(lab)
    if len(labels) < 2 or "?" in labels:
        return
    key = ">".join(labels)
    char = group[0][3]
    combos[char][key] += 1
    combo_damage[(char, key)].append(sum(h[2] for h in group))


def to_bot_notation(combo):
    """Etiquetas del analizador -> notacion del bot ([2]8B -> 2[35]8B)."""
    return combo.replace("[2]8", "2[35]8").replace("[4]6", "4[35]6")


def context(m, r, dist, row, prev, me, rv):
    if m["h"] > 0:
        sit = "estoy en el aire"
    elif r["h"] > 0 and dist <= ANTI_AIR_RANGE:
        sit = "rival en el aire cerca"
    elif r["attacking"] and dist <= MID:
        sit = "rival ataca"
    elif dist > MID:
        sit = "rival lejos"
    elif dist > CLOSE:
        sit = "media distancia"
    else:
        sit = "pegado al rival"
    return f"{sit}|d{min(dist // DISTANCE_BUCKET, 7)}"


def action_category(label, dist):
    if label[0].isdigit() and len(label) > 2 or label.startswith("["):
        return f"especial {label}"
    if label in ("6C", "4C", "6D", "4D") and dist <= CLOSE:
        return f"agarre/comando {label}"
    return f"golpe {label}"


def main():
    files = sys.argv[1:] or sorted(glob.glob(str(ROOT / "recordings" / "rec_*.csv")))
    combos, combo_damage = defaultdict(Counter), defaultdict(list)
    defense, situations, presses = defaultdict(Counter), defaultdict(Counter), Counter()
    total_fight = 0
    for path in files:
        rows = load(path)
        fill_characters(rows)
        total_fight += sum(1 for r in rows if in_fight(r))
        c, cd, d, s, p = analyze(rows)
        for char, counter in c.items():
            combos[char].update(counter)
        for k, v in cd.items():
            combo_damage[k] += v
        for k, v in d.items():
            defense[k].update(v)
        for k, v in s.items():
            situations[k].update(v)
        presses.update(p)
    print(f"{len(files)} grabaciones, ~{total_fight / 60:.0f} s de pelea")

    print("\n== Combos reales por personaje (2+ golpes distintos)")
    for char in sorted(combos):
        print(f"  -- {char}")
        for key, n in combos[char].most_common(8):
            dmg = combo_damage[(char, key)]
            print(f"     {n:3d}x  {key:35s} danio medio {sum(dmg) / len(dmg):.1f}")

    print("\n== Defensa: que guardia usan contra cada tipo de ataque cercano")
    for (kind, guard), c in sorted(defense.items()):
        total = c["ok"] + c["golpeado"]
        print(f"  ataque {kind:7s} + guardia {guard:12s}: {total:4d} veces, les pegaron {100 * c['golpeado'] / total:3.0f}%")

    print("\n== Botones mas usados")
    print("  " + ", ".join(f"{k} {v}" for k, v in presses.most_common(20)))

    print("\n== Que hacen en cada situacion (top 4)")
    for ctx in sorted(situations):
        c = situations[ctx]
        total = sum(c.values())
        if total < 15:
            continue
        top = ", ".join(f"{a} {100 * n / total:.0f}%" for a, n in c.most_common(4))
        print(f"  {ctx:28s} [{total:4d}] {top}")

    out = ROOT / "recordings" / "imitation.json"
    out.write_text(json.dumps({
        "combos": {char: {to_bot_notation(k): {"veces": n, "danio_medio":
                                               sum(combo_damage[(char, k)]) / len(combo_damage[(char, k)])}
                          for k, n in counter.most_common(30)}
                   for char, counter in combos.items()},
        "defense": {f"{k}|{g}": dict(c) for (k, g), c in defense.items()},
        "situations": {k: dict(c) for k, c in situations.items()},
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nGuardado en {out}")


if __name__ == "__main__":
    main()
