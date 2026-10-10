"""Analyze manual baseline recordings; no emulator access or input injection."""
import argparse
import csv
import json
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def decode(row):
    raw = bytes.fromhex(row['p1raw'])
    rival = bytes.fromhex(row['p2raw'])
    if len(raw) != 512 or len(rival) != 512:
        raise ValueError('Expected two complete 512-byte structures')
    word = lambda off: int.from_bytes(raw[off:off + 2], 'big')
    return dict(row, frame=int(row['frame']), sample=int(row['sample']),
                x=word(0x18), height=word(0x20), life=raw[0x139],
                rival_life=rival[0x139], character=raw[0x71], attacking=bool(raw[0xe0] & 1))


def summarize(rows, distance=100):
    rows = [decode(row) for row in rows]
    velocities, traversals, proxy_lags, durations = [], [], [], []
    start = None
    press = None
    attack = None
    for i, row in enumerate(rows):
        prev = rows[i - 1] if i else None
        continuous = (prev is not None and row['frame'] == prev['frame'] + 1
                      and row['sample'] == prev['sample'] + 1 and row['label'] == prev['label'])
        if not continuous:
            start = press = attack = None
            continue
        movement = (row['label'] in {'walk', 'run'} and row['character'] == prev['character'] == 21
                    and row['height'] == prev['height'] == 0 and not row['attacking'] and not prev['attacking']
                    and row['life'] == prev['life'] and row['rival_life'] == prev['rival_life']
                    and 65 < row['x'] < 710 and 65 < prev['x'] < 710)
        dx = row['x'] - prev['x']
        if movement and 0 < abs(dx) <= 12:
            velocities.append(abs(dx))
            if start is None or start[2] != (1 if dx > 0 else -1):
                start = (prev['frame'], prev['x'], 1 if dx > 0 else -1)
            if abs(row['x'] - start[1]) >= distance:
                traversals.append(row['frame'] - start[0])
                start = None
        else:
            start = None
        # Input observed by Lua -> animation bit, NOT active hitbox/startup or hardware latency.
        buttons = lambda r: {k for k in r['input_before'].split('|') if k.startswith('P1 Button ')}
        if row['label'].startswith('normal_') and row['input_ok'] == prev['input_ok'] == '1':
            if buttons(row) - buttons(prev) and not prev['attacking']:
                press = row['frame']
            if row['attacking'] and not prev['attacking']:
                if press is not None and row['frame'] - press <= 30:
                    proxy_lags.append(row['frame'] - press)
                press = None
                attack = row['frame']
            if prev['attacking'] and not row['attacking'] and attack is not None:
                durations.append(row['frame'] - attack)
                attack = None
    return {'samples': len(rows), 'moving_samples': len(velocities),
            'speed_units_per_frame': statistics.mean(velocities) if velocities else None,
            'distance_units': distance, 'traversal_frames': traversals,
            'input_to_animation_flag_frames': proxy_lags, 'attack_flag_duration_frames': durations,
            'startup_frames': None, 'recovery_frames': None, 'physical_input_latency_ms': None,
            'limitations': 'Manual labels; integer X; filtered moving frames only, not startup acceleration. '
                           'Attack bit includes startup/active/recovery. No hitbox or actionable-state verification.'}


def monitor(seconds):
    start, last, readings = time.perf_counter(), None, []
    session = None
    while time.perf_counter() - start < seconds:
        try:
            tag, sample, frame = (ROOT / 'status.txt').read_text().split()
            current = (time.perf_counter(), int(frame), int(sample))
            if session != tag:
                session, last, readings = tag, None, []
            if last and current[2] > last[2] and current[1] > last[1]:
                readings.append((current[0], current[1], current[2]))
            elif last and current[1] < last[1]:
                readings = []  # savestate/reset: do not average across a frame discontinuity
            if last is None or current[2] != last[2]:
                last = current
        except (OSError, ValueError):
            pass
        time.sleep(0.01)
    if len(readings) < 2:
        raise SystemExit('No fresh Lua samples. Run capture.lua, unpause and retry.')
    elapsed = readings[-1][0] - readings[0][0]
    print(json.dumps({'measured_seconds': elapsed,
                      'emulator_frames_per_wall_second': (readings[-1][1] - readings[0][1]) / elapsed,
                      'note': 'Callback throughput, not display latency or input-to-photon latency.'}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    control = sub.add_parser('label')
    control.add_argument('name', choices=['idle', 'walk', 'run', 'normal_A', 'normal_B', 'normal_C', 'normal_D'])
    control.add_argument('--off', action='store_true', help='Disable capture only; no speed modifier exists')
    report = sub.add_parser('report')
    report.add_argument('csv', type=Path)
    report.add_argument('--distance', type=int, default=100)
    fps = sub.add_parser('fps')
    fps.add_argument('--seconds', type=float, default=20)
    args = parser.parse_args()
    if args.command == 'label':
        (ROOT / 'captures').mkdir(exist_ok=True)
        tmp = ROOT / 'control.txt.tmp'
        tmp.write_text(f'{0 if args.off else 1}|{args.name}\n', encoding='ascii')
        tmp.replace(ROOT / 'control.txt')
    elif args.command == 'fps':
        if args.seconds <= 0:
            parser.error('seconds must be positive')
        monitor(args.seconds)
    else:
        if args.distance <= 0:
            parser.error('distance must be positive')
        with args.csv.open(encoding='utf-8', newline='') as stream:
            rows = list(csv.DictReader(stream))
        groups = sorted({r['label'] for r in rows})
        print(json.dumps({tag: summarize([r for r in rows if r['label'] == tag], args.distance)
                          for tag in groups}, indent=2))


if __name__ == '__main__':
    main()
