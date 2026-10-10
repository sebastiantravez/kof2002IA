"""Rank read-only RAM correlations. Candidates are NOT verified writable parameters."""
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path


def correlation(xs, ys):
    if len(xs) < 3:
        return 0.0
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    xx = sum((x - mx) ** 2 for x in xs)
    yy = sum((y - my) ** 2 for y in ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(xx * yy) if xx and yy else 0.0


def scan(rows):
    samples, group_counts = [], Counter()
    previous = None
    streak = 0
    old_direction = 0
    for row in rows:
        raw, rival = bytes.fromhex(row['p1raw']), bytes.fromhex(row['p2raw'])
        if len(raw) != 512 or len(rival) != 512:
            raise ValueError('Invalid RAM structure length')
        word = lambda data, off: int.from_bytes(data[off:off + 2], 'big')
        current = (int(row['frame']), int(row['sample']), raw, rival, row['input_before'])
        if previous:
            pf, ps, pr, po, pi = previous
            dx = word(raw, 0x18) - word(pr, 0x18)
            direction = 1 if dx > 0 else -1 if dx < 0 else 0
            def clean(data, other, inputs):
                p1 = {key for key in inputs.split('|') if key.startswith('P1 ')}
                return (data[0x71] == 21 and 0 < data[0x139] <= 102 and 0 < other[0x139] <= 102
                        and word(data, 0x20) == 0 and not data[0xe0] & 1
                        and 65 < word(data, 0x18) < 710
                        and abs(word(data, 0x18) - word(other, 0x18)) >= 80
                        and p1 in ({'P1 Left'}, {'P1 Right'}))
            valid = (current[0] == pf + 1 and current[1] == ps + 1 and 0 < abs(dx) <= 8
                     and raw[0x139] == pr[0x139] and rival[0x139] == po[0x139]
                     and clean(raw, rival, row['input_before']) and clean(pr, po, pi))
            streak = streak + 1 if valid and direction == old_direction else 1 if valid else 0
            if streak >= 8:
                bucket = 'fast' if abs(dx) >= 6 else 'slow' if abs(dx) <= 3 else 'transition'
                if bucket != 'transition':
                    samples.append((pr, raw, dx, bucket, direction))
                    group_counts[f'{bucket}_{direction}'] += 1
            old_direction = direction
        previous = current
    # Exclude known positions, height, character, attack flags and life.
    known = set(range(0x18, 0x1c)) | set(range(0x20, 0x28)) | {0x71, 0xe0, 0x139}
    candidates = []
    ys = [s[2] for s in samples]
    for size in (2, 4):
        for offset in range(0, 512 - size + 1, 2):
            if any(i in known for i in range(offset, offset + size)):
                continue
            for timing, index in [('previous', 0), ('current', 1)]:
                values = [int.from_bytes(s[index][offset:offset + size], 'big', signed=True) for s in samples]
                score = correlation(values, ys)
                if abs(score) < 0.75:
                    continue
                groups = {}
                for bucket, direction in [('slow', 1), ('slow', -1), ('fast', 1), ('fast', -1)]:
                    counter = Counter(v for v, s in zip(values, samples) if s[3:] == (bucket, direction))
                    groups[f'{bucket}_{direction}'] = counter.most_common(4)
                candidates.append({'offset': f'0x{offset:03x}', 'address_p1': f'0x{0x108100 + offset:06x}',
                                   'signed_bits': size * 8, 'timing': timing,
                                   'correlation_with_signed_dx': score, 'common_values': groups})
    candidates.sort(key=lambda c: abs(c['correlation_with_signed_dx']), reverse=True)
    return {'filtered_samples': len(samples), 'groups': dict(group_counts), 'candidates': candidates[:20],
            'status': 'Correlations only; no write performed or approved. Slow/fast are displacement buckets, '
                      'not verified game states. No fast-left data means direction validation is incomplete.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    args = parser.parse_args()
    with args.csv.open(encoding='utf-8', newline='') as stream:
        result = scan(csv.DictReader(stream))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
