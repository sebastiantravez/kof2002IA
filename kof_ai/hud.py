"""Detecta por imagen si hay una pelea en pantalla.

Fuera de la pelea (menus, continue, pantallas de KO) el bot no debe pulsar
botones: A/B/C/D eligen opciones. Se mira la caja del reloj del centro, cuyos
digitos (arcade) o el simbolo de infinito (practica) son azul lavanda.
Medido: pelea 0.22-0.37, continue/KO/menus 0.00.
"""
import numpy as np

_BOX_X = (0.46, 0.54)
_BOX_Y = (0.05, 0.14)
THRESHOLD = 0.12


def timer_ratio(frame):
    h, w = frame.shape[:2]
    box = frame[int(_BOX_Y[0] * h):int(_BOX_Y[1] * h), int(_BOX_X[0] * w):int(_BOX_X[1] * w)]
    box = box.reshape(-1, 3).astype(np.int16)
    b, g, r = box[:, 0], box[:, 1], box[:, 2]
    lavender = (b > 180) & (r > 90) & (r < 200) & (g > 90) & (g < 200) & (b - r > 40)
    return float(np.mean(lavender))


def fight_hud_visible(frame):
    return frame is not None and timer_ratio(frame) >= THRESHOLD
