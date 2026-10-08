"""Analiza TUS peleas grabadas con lua/kof_record.lua (en vivo o desde la repeticion):
combos que hiciste y cuanto quitaron, cada golpe que recibiste con su causa probable
(con evidencia de los inputs de los dos jugadores), y busqueda en la RAM de senales
que el bot aun no tiene (ataque bajo, guardia/bloqueo), usando el volcado .bin.

Uso: python tools/analyze_my_play.py [grabacion.csv] [--me=1|2]
     python tools/analyze_my_play.py --ram [grabaciones.csv...]   (RAM juntando grabaciones)
     sin archivo: la grabacion mas reciente de recordings/.  --me: que jugador eras tu
     (sin --me se analizan los dos lados).
Solo informacion observable: lo que no se puede saber se dice.
"""
import glob
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from learn_from_replays import (BUTTONS, COMBO_GAP, HIT_WINDOW, char_name, in_fight,  # noqa: E402
                                label_press, load, numpad, player)

STRUCT = 0x200
ATTACK_LOOKBACK = 30     # un golpe recibido se atribuye al ataque rival que empezo en estos frames
THROW_RANGE = 40         # golpe sin ataque visible a esta distancia: posible agarre
MIN_SAMPLES = 10         # minimo de casos por grupo para proponer un bit de la RAM


def pressed_button(row, prev, n):
    return [b for b in BUTTONS if f"P{n} Button {b}" in row["inputs"]
            and (prev is None or f"P{n} Button {b}" not in prev["inputs"])]


def facing(row, me, rv):
    return player(row, me)["x"] <= player(row, rv)["x"]


def analyze_side(rows, me):
    rv = 3 - me
    dirs = []
    pending = []                 # mis pulsaciones esperando ver si conectan
    hits = []                    # (frame, etiqueta, danio)
    taken = []                   # golpes recibidos clasificados
    attack_start = None          # (frame, i, bajo_por_input, aereo, etiqueta del rival)
    rival_dirs = []
    last_hit_frame = -999
    my_last_press = -999
    rounds = []
    last_ko = -10 ** 9
    dealt = recv = 0
    prev = None
    for i, row in enumerate(rows):
        if not in_fight(row):
            # KO real: la vida baja a 0 desde un golpe (no un salto de pantalla), uno por round
            if prev is not None and row["frame"] - last_ko > 600:
                if player(row, rv)["life"] == 0 and 0 < player(prev, rv)["life"] <= 60:
                    rounds.append("ganado")
                    last_ko = row["frame"]
                elif player(row, me)["life"] == 0 and 0 < player(prev, me)["life"] <= 60:
                    rounds.append("perdido")
                    last_ko = row["frame"]
            dirs, rival_dirs, pending, prev, attack_start = [], [], [], None, None
            continue
        m, r = player(row, me), player(row, rv)
        f = row["frame"]
        face = facing(row, me, rv)
        dirs.append(numpad(row["inputs"], me, face))
        rival_dirs.append(numpad(row["inputs"], rv, not face))
        if prev is None:
            prev = row
            continue
        pm, pr = player(prev, me), player(prev, rv)
        for b in pressed_button(row, prev, me):
            pending.append((f, label_press(dirs, b)))
            my_last_press = f
        # inicio de ataque rival: etiqueta por SUS inputs (abajo + boton = bajo)
        if r["attacking"] and not pr["attacking"]:
            recent = [d for d in rival_dirs[-4:]]
            low = any(d in (1, 2, 3) for d in recent) and r["h"] == 0
            label = "?"
            for j in range(max(1, i - 8), i + 1):
                bs = pressed_button(rows[j], rows[j - 1] if j else None, rv)
                if bs:
                    label = label_press(rival_dirs[:len(rival_dirs) - (i - j)] or [5], bs[0])
            attack_start = (f, i, low, r["h"] > 0, label)
        # danio hecho
        dmg = pr["life"] - r["life"]
        if 0 < dmg <= 60:
            dealt += dmg
            hits.append((f, pending[-1][1] if pending else "?", dmg, char_name(row[f"p{me}char"])))
        pending = [(pf, pl) for pf, pl in pending if f - pf <= HIT_WINDOW]
        # danio recibido
        got = pm["life"] - m["life"]
        if 0 < got <= 60:
            recv += got
            guard = dirs[-3] if len(dirs) >= 3 else 5     # lo que sostenia justo antes del impacto
            taken.append(classify_hit(f, got, guard, attack_start, last_hit_frame, my_last_press,
                                      abs(m["x"] - r["x"])))
            last_hit_frame = f
        prev = row
    return hits, taken, (rounds, dealt, recv)


def classify_hit(f, dmg, guard, attack_start, last_hit_frame, my_last_press, dist):
    guard_name = {1: "abajo-atras", 4: "atras (de pie)"}.get(guard, "sin guardia")
    atk = attack_start if attack_start and f - attack_start[0] <= ATTACK_LOOKBACK else None
    rival_move = atk[4] if atk else "?"
    if f - last_hit_frame <= COMBO_GAP and (atk is None or atk[0] < last_hit_frame):
        cause = "COMBO_CONTINUATION (ya estaba recibiendo un combo)"
    elif atk is None:
        cause = ("POSSIBLE_THROW (sin ataque visible y muy cerca)" if dist <= THROW_RANGE
                 else "UNKNOWN (sin ataque visible: proyectil u otro, no observable)")
    elif guard_name == "sin guardia":
        cause = ("ATTACKING (me pegaron mientras atacaba)" if f - my_last_press <= 20
                 else "NO_GUARD (no sostenia atras)")
    elif atk[3] and guard == 1:
        cause = "HIGH_GUARD_FAILURE (agachado contra ataque aereo)"
    elif atk[2] and guard == 4:
        cause = "LOW_GUARD_FAILURE (de pie contra ataque bajo: el rival tenia abajo)"
    else:
        cause = "GUARD_OK_UNKNOWN (guardia aparentemente correcta: overhead, cruce o golpe imbloqueable)"
    return {"frame": f, "danio": dmg, "guardia": guard_name, "movimiento_rival": rival_move,
            "distancia": dist, "causa": cause}


def combos_of(hits):
    """{personaje: {combo: [(golpes, danio), ...]}}"""
    combos = defaultdict(lambda: defaultdict(list))
    group = []
    for h in hits + [(10 ** 9, None, 0, None)]:
        if group and (h[0] - group[-1][0] > COMBO_GAP or h[3] != group[-1][3]):
            labels = []
            for _, lab, _, _ in group:
                if not labels or labels[-1] != lab:
                    labels.append(lab)
            combos[group[0][3]][">".join(labels)].append((len(group), sum(x[2] for x in group)))
            group = []
        if h[1] is not None:
            group.append(h)
    return combos


# Etiquetas (sacadas de los inputs del jugador, no supuestas) para buscar bits en la RAM.
RAM_PAIRS = (("ataque agachado", "ataque de pie"), ("defendiendo (sin perder vida)", "sin sostener atras"))


def collect_ram_samples(rows, bin_path, groups):
    """Agrega a groups[etiqueta] tuplas (estructura de 0x200 bytes, personaje)."""
    data = bin_path.read_bytes()
    if len(data) < len(rows) * 2 * STRUCT:
        return f"{bin_path.name}: el volcado es mas corto que el CSV, se omite"
    def struct(i, n):
        start = i * 2 * STRUCT + (n - 1) * STRUCT
        return data[start:start + STRUCT]
    for n in (1, 2):
        other = 3 - n
        for i in range(4, len(rows) - 4):
            row, prev = rows[i], rows[i - 1]
            if not (in_fight(row) and in_fight(prev)):
                continue
            p, pp = player(row, n), player(prev, n)
            face = facing(row, n, other)
            char = char_name(row[f"p{n}char"])
            started = p["attacking"] and not pp["attacking"] and p["h"] == 0
            if started and (pressed_button(row, prev, n) or pressed_button(prev, rows[i - 2], n)):
                crouch = any(numpad(rows[j]["inputs"], n, face) in (1, 2, 3) for j in range(i - 2, i + 1))
                for k in range(1, 4):
                    groups["ataque agachado" if crouch else "ataque de pie"].append((struct(i + k, n), char))
            # bloqueo: el rival ataca cerca, yo sostengo atras y no pierdo vida
            o = player(row, other)
            if o["attacking"] and abs(p["x"] - o["x"]) <= 120:
                d = numpad(row["inputs"], n, face)
                lost = player(rows[i + 3], n)["life"] < p["life"]
                if d in (1, 4) and not lost:
                    groups["defendiendo (sin perder vida)"].append((struct(i, n), char))
                elif d not in (1, 4):
                    groups["sin sostener atras"].append((struct(i, n), char))
    return None


def ram_report(groups):
    lines = []
    for a, b in RAM_PAIRS:
        ga, gb = groups[a], groups[b]
        lines.append(f"  {a} ({len(ga)}) vs {b} ({len(gb)}):")
        if len(ga) < MIN_SAMPLES or len(gb) < MIN_SAMPLES:
            lines.append(f"    pocos casos (minimo {MIN_SAMPLES} por grupo): grabar mas")
            continue
        scores = []
        for off in range(STRUCT):
            for bit in range(8):
                fa = sum(s[off] >> bit & 1 for s, _ in ga) / len(ga)
                fb = sum(s[off] >> bit & 1 for s, _ in gb) / len(gb)
                scores.append((abs(fa - fb), off, bit, fa, fb))
        scores.sort(reverse=True)
        chars = sorted({c for _, c in ga} & {c for _, c in gb})
        for sep, off, bit, fa, fb in scores[:6]:
            lines.append(f"    +0x{off:03X} bit{bit}: {100 * fa:5.1f}% vs {100 * fb:5.1f}%  (separacion {sep:.2f})")
            # Un bit util tiene que separar con TODOS los personajes, no solo con uno.
            per = []
            for c in chars:
                ca = [s for s, ch in ga if ch == c]
                cb = [s for s, ch in gb if ch == c]
                if len(ca) >= 3 and len(cb) >= 3:
                    pa = sum(s[off] >> bit & 1 for s in ca) / len(ca)
                    pb = sum(s[off] >> bit & 1 for s in cb) / len(cb)
                    per.append(f"{c} {100 * pa:.0f}/{100 * pb:.0f}")
            if per:
                lines.append("        por personaje (%): " + ", ".join(per))
    lines.append("  Un bit candidato se confirma solo con una prueba controlada (ver docs/DEFENSE_AUDIT_V4.md).")
    return lines


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    me_arg = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--me=")), None)
    if "--ram" in sys.argv:
        # Busqueda en la RAM juntando varias grabaciones (mas casos, varios personajes).
        paths = [Path(a) for a in args] or [Path(p) for p in glob.glob(str(ROOT / "recordings" / "rec_*.csv"))]
        groups = defaultdict(list)
        for path in paths:
            if not path.with_suffix(".bin").exists():
                continue
            rows = load(path)
            if rows and "p1char" in rows[0]:
                problem = collect_ram_samples(rows, path.with_suffix(".bin"), groups)
                print(problem or f"{path.name}: {len(rows)} frames")
        print("\n===== Busqueda en la RAM (todas las grabaciones) =====")
        print("\n".join(ram_report(groups)))
        return
    path = Path(args[0]) if args else Path(max(glob.glob(str(ROOT / "recordings" / "rec_*.csv")),
                                               key=lambda p: Path(p).stat().st_mtime))
    rows = load(path)
    if not rows or "p1char" not in rows[0]:
        sys.exit(f"{path.name}: grabacion vacia o sin columna de personaje.")
    print(f"Grabacion {path.name}: {len(rows)} frames ({len(rows) / 3600:.1f} min)")
    sides = [int(me_arg)] if me_arg else [1, 2]
    for me in sides:
        chars = Counter(char_name(r[f"p{me}char"]) for r in rows if in_fight(r))
        rivals = Counter(char_name(r[f"p{3 - me}char"]) for r in rows if in_fight(r))
        hits, taken, (rounds, dealt, recv) = analyze_side(rows, me)
        print(f"\n===== P{me}: {', '.join(c for c, _ in chars.most_common(3))} "
              f"vs {', '.join(c for c, _ in rivals.most_common(3))} =====")
        print(f"KO: {rounds.count('ganado')} ganados, {rounds.count('perdido')} perdidos; "
              f"danio hecho {dealt}, recibido {recv}")
        print("Combos (2+ golpes distintos), por personaje y danio medio:")
        any_combo = False
        for char, combos in sorted(combos_of(hits).items()):
            multi = sorted(((sum(d for _, d in v) / len(v), k, v) for k, v in combos.items() if ">" in k),
                           reverse=True)
            if multi:
                any_combo = True
                print(f"  -- {char}")
                for avg, key, v in multi[:8]:
                    print(f"    {avg:5.1f} danio  x{len(v):<3d} {key}")
        if not any_combo:
            print("  ninguno")
        print("Golpes recibidos por causa:")
        for cause, n in Counter(t["causa"] for t in taken).most_common():
            dmg = sum(t["danio"] for t in taken if t["causa"] == cause)
            print(f"  {n:4d} golpes, {dmg:4d} danio  {cause}")
        worst = Counter((t["movimiento_rival"], t["causa"].split(" ")[0]) for t in taken
                        if not t["causa"].startswith("COMBO"))
        if worst:
            print("Movimientos rivales que mas te pegaron (por sus inputs):")
            for (move, cause), n in worst.most_common(8):
                print(f"  {n:4d}  {move:10s} {cause}")
    bin_path = path.with_suffix(".bin")
    print("\n===== Busqueda en la RAM =====")
    if bin_path.exists():
        groups = defaultdict(list)
        problem = collect_ram_samples(rows, bin_path, groups)
        print(problem or "\n".join(ram_report(groups)))
    else:
        print("  Sin volcado .bin (grabacion anterior al volcado completo).")


if __name__ == "__main__":
    main()
