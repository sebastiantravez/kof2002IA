"""Teclado virtual usando SendInput de Windows con scancodes.

FBNeo lee el teclado via DirectInput, que trabaja con scancodes y no con
virtual-keys, por eso se envia KEYEVENTF_SCANCODE.
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0

ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUTUNION(ctypes.Union):
    _fields_ = (("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", _INPUTUNION))


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT

# (scancode, extendida)
_SPECIAL_KEYS = {
    "up": (0x48, True),
    "down": (0x50, True),
    "left": (0x4B, True),
    "right": (0x4D, True),
    "space": (0x39, False),
    "enter": (0x1C, False),
    "lshift": (0x2A, False),
    "rshift": (0x36, False),
    "lctrl": (0x1D, False),
    "lalt": (0x38, False),
    "tab": (0x0F, False),
    "numpad0": (0x52, False),
    "numpad1": (0x4F, False),
    "numpad2": (0x50, False),
    "numpad3": (0x51, False),
    "numpad4": (0x4B, False),
    "numpad5": (0x4C, False),
    "numpad6": (0x4D, False),
    "numpad7": (0x47, False),
    "numpad8": (0x48, False),
    "numpad9": (0x49, False),
}


def scancode_for(name):
    """Devuelve (scancode, extendida) para un nombre de tecla del config."""
    key = name.lower()
    if key in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[key]
    if len(key) == 1 and key.isalnum():
        scan = user32.MapVirtualKeyW(ord(key.upper()), MAPVK_VK_TO_VSC)
        if scan:
            return scan, False
    raise ValueError(f"Tecla no soportada en config.json: {name!r}")


class VirtualKeyboard:
    """Mantiene el conjunto de teclas presionadas y envia solo los cambios."""

    def __init__(self, key_names):
        self._codes = {logical: scancode_for(physical) for logical, physical in key_names.items()}
        self._pressed = set()

    def set_state(self, logical_keys):
        """Deja presionadas exactamente estas teclas logicas (up, A, ...)."""
        desired = set(logical_keys)
        events = [(k, True) for k in desired - self._pressed]
        events += [(k, False) for k in self._pressed - desired]
        self._send(events)
        self._pressed = desired

    def release_all(self):
        self.set_state(())

    def _send(self, events):
        if not events:
            return
        inputs = (INPUT * len(events))()
        for i, (logical, down) in enumerate(events):
            scan, extended = self._codes[logical]
            flags = KEYEVENTF_SCANCODE
            if extended:
                flags |= KEYEVENTF_EXTENDEDKEY
            if not down:
                flags |= KEYEVENTF_KEYUP
            inputs[i].type = INPUT_KEYBOARD
            inputs[i].ki = KEYBDINPUT(0, scan, flags, 0, 0)
        sent = user32.SendInput(len(events), inputs, ctypes.sizeof(INPUT))
        if sent != len(events):
            raise ctypes.WinError(ctypes.get_last_error())
