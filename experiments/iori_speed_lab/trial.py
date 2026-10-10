"""Arm an explicit offline speed trial, or request immediate deactivation."""
import argparse
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['arm', 'off'])
    parser.add_argument('--offline', action='store_true', help='Confirm Test Game offline')
    parser.add_argument('--walk', type=float, default=1.01)
    parser.add_argument('--run', type=float, default=1.01)
    args = parser.parse_args()
    if args.action == 'off':
        (ROOT / 'trial_stop.txt').write_text('stop\n', encoding='ascii')
        print('Desactivacion solicitada; se aplica en el siguiente frame.')
        return
    if not args.offline:
        parser.error('Confirma Test Game offline con --offline; no se permite netplay.')
    if not 1 <= args.walk <= 1.05 or not 1 <= args.run <= 1.08:
        parser.error('Rangos: walk 1..1.05, run 1..1.08')
    (ROOT / 'captures').mkdir(exist_ok=True)
    (ROOT / 'trial_stop.txt').unlink(missing_ok=True)
    (ROOT / 'trial_arm.txt').write_text(
        f'offline\n{int(time.time())}\n{args.walk:.8f}\n{args.run:.8f}\n', encoding='ascii')
    print('Ensayo armado por 120 segundos. Ejecuta speed_trial.lua SOLO en Test Game offline.')
    print('45 segundos: 15 base, 15 aumento, 15 restaurado. Joystick bajo tu control.')


if __name__ == '__main__':
    main()
