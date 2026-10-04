"""Captura del area de juego (client area) de la ventana del emulador."""
import ctypes
from ctypes import wintypes

import mss
import numpy as np

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))

# Sin esto, con escalado de Windows (125%, 150%) las coordenadas no coinciden con los pixeles.
try:
    ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
except OSError:
    user32.SetProcessDPIAware()


def client_region(hwnd):
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return {"left": origin.x, "top": origin.y, "width": rect.right, "height": rect.bottom}


class WindowCapture:
    """Devuelve frames BGR (formato OpenCV) del area de juego."""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self._sct = mss.mss()

    def grab(self):
        region = client_region(self.hwnd)
        if region["width"] <= 0 or region["height"] <= 0:
            return None
        shot = self._sct.grab(region)
        return np.asarray(shot)[:, :, :3]

    def close(self):
        self._sct.close()
