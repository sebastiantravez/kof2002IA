"""Deteccion y foco de la ventana del emulador FBNeo de Fightcade."""
import ctypes
import os
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.BringWindowToTop.argtypes = (wintypes.HWND,)
user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)


def _process_name(pid):
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return None
    finally:
        kernel32.CloseHandle(handle)


def find_emulator_window(process_names):
    """Devuelve (hwnd, titulo) de la ventana principal del emulador o None."""
    windows = find_emulator_windows(process_names)
    return windows[0] if windows else None


def find_emulator_windows(process_names):
    """Ventanas principales de todos los emuladores abiertos (una por proceso),
    la de titulo mas largo primero. Con mas de una (p.ej. una repeticion y el arcade)
    el bot no sabe cual controlar."""
    targets = {name.lower() for name in process_names}
    found = []

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if _process_name(pid.value) in targets:
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            found.append((pid.value, hwnd, title.value))
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    # Por proceso, la ventana del juego es la de titulo mas largo (incluye el nombre del ROM).
    best = {}
    for pid, hwnd, title in found:
        if pid not in best or len(title) > len(best[pid][1]):
            best[pid] = (hwnd, title)
    return sorted(best.values(), key=lambda item: -len(item[1]))


def is_window(hwnd):
    return bool(hwnd) and bool(user32.IsWindow(hwnd))


def focus(hwnd):
    """Trae la ventana al frente. SendInput siempre va a la ventana con foco."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    if user32.SetForegroundWindow(hwnd) and has_focus(hwnd):
        return True
    # Windows bloquea SetForegroundWindow si el proceso no tiene el foco:
    # compartir la cola de input con la ventana que lo tiene lo permite.
    # (No usar el truco de pulsar Alt: abre el menu del emulador.)
    current = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(current, None)
    my_thread = kernel32.GetCurrentThreadId()
    attached = fg_thread != my_thread and user32.AttachThreadInput(my_thread, fg_thread, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(my_thread, fg_thread, False)
    return has_focus(hwnd)


def has_focus(hwnd):
    return user32.GetForegroundWindow() == hwnd
