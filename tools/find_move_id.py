"""Busca en la memoria del jugador el byte que identifica el MOVIMIENTO en curso, usando
una grabacion etiquetada (lua/kof_record.lua en practica: un movimiento repetido muchas veces).

Etiqueta = lo que pulso el jugador (direcciones recientes + boton), sacada de los inputs.
Candidato = byte (offset) cuyo valor, K frames despues de la pulsacion, es el MISMO en todas las
repeticiones de un movimiento y DISTINTO entre movimientos.
Tambien mide, por movimiento, cuando se enciende el bit de ataque (+0xE0 bit0) y cuanto dura
(frame data observable).

Uso: python tools/find_move_id.py [grabacion.csv] [--me=1] [--min=5]
"""
import glob
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from analyze_my_play import facing, load, numpad, player, pressed_button  # noqa: E402
from learn_from_replays import label_press  # noqa: E402

STRUCT = 0x200
AFTER = range(1, 13)        # frames despues de la pulsacion que se examinan
MIN_REPS = 5
QUIET_BEFORE = 20           # frames sin boton antes de la pulsacion (movimiento "limpio")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    me = int(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--me=")), 1))
    min_reps = int(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--min=")), MIN_REPS))
    path = Path(args[0]) if args else Path(max(glob.glob(str(ROOT / "recordings" / "rec_*.csv")),
                                               key=lambda p: Path(p).stat().st_mtime))
    rows = load(path)
    data = path.with_suffix(".bin").read_bytes()
    if len(data) < len(rows) * 2 * STRUCT:
        sys.exit("El volcado .bin es mas corto que el CSV.")
    other = 3 - me

    def struct(i):
        start = i * 2 * STRUCT + (me - 1) * STRUCT
        return data[start:start + STRUCT]

    # 1) pulsaciones etiquetadas
    events = []          # (indice, etiqueta)
    dirs = []
    last_press = -999
    for i, row in enumerate(rows):
        face = facing(row, me, other)
        dirs.append(numpad(row["inputs"], me, face))
        if i == 0:
            continue
        for b in pressed_button(row, rows[i - 1], me):
            if i - last_press >= QUIET_BEFORE and player(row, me)["h"] == 0:
                events.append((i, label_press(dirs, b)))
            elif i - last_press < QUIET_BEFORE:
                events.append((i, f"(seguido) {label_press(dirs, b)}"))
            else:
                events.append((i, f"(aire) {label_press(dirs, b)}"))
            last_press = i
    counts = Counter(lab for _, lab in events)
    labels = [lab for lab, n in counts.most_common() if n >= min_reps and not lab.startswith("(seguido)")]
    print(f"{path.name}: {len(events)} pulsaciones. Movimientos con >= {min_reps} repeticiones limpias:")
    for lab in labels:
        print(f"  {counts[lab]:3d}  {lab}")
    if len(labels) < 2:
        sys.exit("Hacen falta al menos 2 movimientos distintos con repeticiones.")

    # 2) frame data observable por movimiento: bit de ataque (+0xE0 bit0)
    print("\nBit de ataque (+0xE0 bit0) por movimiento: frames desde la pulsacion hasta encenderse, y duracion")
    for lab in labels:
        starts, durs = [], []
        for i, l in events:
            if l != lab:
                continue
            on = next((k for k in range(0, 40) if i + k < len(rows) and player(rows[i + k], me)["attacking"]), None)
            if on is None:
                continue
            off = next((k for k in range(on, 200) if i + k >= len(rows) or not player(rows[i + k], me)["attacking"]), None)
            starts.append(on)
            if off is not None:
                durs.append(off - on)
        if starts:
            med = sorted(starts)[len(starts) // 2]
            medd = sorted(durs)[len(durs) // 2] if durs else -1
            print(f"  {lab:12s} enciende a +{med} f ({min(starts)}-{max(starts)}), dura {medd} f ({min(durs) if durs else '-'}-{max(durs) if durs else '-'})  n={len(starts)}")
        else:
            print(f"  {lab:12s} el bit de ataque no se enciende (n={counts[lab]})")

    # 3) byte identificador: igual dentro del movimiento, distinto entre movimientos
    print("\nCandidatos a byte de movimiento (valor K frames tras la pulsacion):")
    results = []
    for off in range(STRUCT):
        best = None
        for k in AFTER:
            modes = {}
            consistency = []
            for lab in labels:
                vals = Counter(struct(i + k)[off] for i, l in events if l == lab and i + k < len(rows))
                if not vals:
                    continue
                v, n = vals.most_common(1)[0]
                modes[lab] = v
                consistency.append(n / sum(vals.values()))
            if len(modes) < len(labels):
                continue
            within = sum(consistency) / len(consistency)
            distinct = len(set(modes.values())) / len(labels)
            score = within * distinct
            if best is None or score > best[0]:
                best = (score, k, within, distinct, modes)
        if best and best[0] > 0.5:
            results.append((best, off))
    results.sort(key=lambda r: -r[0][0])
    for (score, k, within, distinct, modes), off in results[:10]:
        print(f"  +0x{off:03X} a +{k} f: consistencia {100 * within:.0f}%, distintos {100 * distinct:.0f}%  "
              f"valores: " + ", ".join(f"{lab}={v}" for lab, v in modes.items()))
    if not results:
        print("  ninguno con puntuacion > 0.5")


if __name__ == "__main__":
    main()
