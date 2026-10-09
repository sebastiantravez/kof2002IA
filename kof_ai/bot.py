"""Bots que controlan al personaje.

- RandomBot (Fase 1): acciones aleatorias ponderadas, sin vision.
- RuleBot (Fase 3): decide segun el estado de la pelea (kof_ai.brain).
  Con un LearningBrain (Fase 4) aprende de los resultados y guarda lo aprendido.
"""
import ctypes
import random
import re
import threading
import time

from . import emulator
from .brain import RuleBrain
from .capture import WindowCapture
from .combo import is_combo, play_combo
from .hud import fight_hud_visible
from .motions import keys_for, parse, play

user32 = ctypes.WinDLL("user32")

GUARD_PATTERN = re.compile(r"G\[(\d+)\]")  # notacion especial: guardia dinamica N frames
GUARD_PAUSE_DISTANCE = 180

_VK_CODES = {f"F{n}": 0x6F + n for n in range(1, 13)}
_VK_CODES["ESC"] = 0x1B

# (peso, nombre, notacion)
ACTIONS = [
    (20, "caminar adelante", "6[25]"),
    (8, "caminar atras", "4[20]"),
    (8, "correr", "6 5 6[25]"),
    (5, "backdash", "4 5 4"),
    (8, "salto adelante", "9[8]"),
    (4, "hop adelante", "9[3]"),
    (3, "salto atras", "7[8]"),
    (10, "agacharse y bloquear", "1[30]"),
    (6, "golpe A", "A"),
    (6, "patada B", "B"),
    (5, "golpe fuerte C", "C"),
    (5, "patada fuerte D", "D"),
    (4, "barrida 2D", "2D"),
    (4, "236A", "236A"),
    (4, "214A", "214A"),
    (3, "623A", "623A"),
    (3, "roll", "AB"),
    (6, "esperar", "5[15]"),
]


class _BaseBot:
    def __init__(self, keyboard, clock, config, hwnd, facing_right, on_log,
                 focus_required=True, fight_check=None):
        """focus_required=False y fight_check (funcion) para el modo lockstep
        (kof_ai/lockstep.py): ahi no se usa el teclado de Windows ni la pantalla."""
        self._focus_required = focus_required
        self._fight_check = fight_check
        self._keyboard = keyboard
        self._clock = clock
        self._config = config
        self._hwnd = hwnd
        self._facing_right = facing_right  # funcion: True si miro a la derecha
        self._log = on_log
        self._stop = threading.Event()
        self._kill_vk = _VK_CODES[config.get("kill_switch_key", "F8").upper()]
        self._thread = None
        self._capture = None
        self._in_fight = False
        self._fight_checked_at = 0.0

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def _should_stop(self):
        if self._stop.is_set():
            return True
        if user32.GetAsyncKeyState(self._kill_vk) & 0x8000:
            self._halt(f"tecla de emergencia {self._config.get('kill_switch_key', 'F8')}")
        # Si el emulador pierde el foco, el input iria a otra ventana: detener.
        elif self._focus_required and not emulator.has_focus(self._hwnd):
            self._halt("el emulador perdio el foco")
        return self._stop.is_set()

    def _halt(self, reason):
        self._log(f"Deteniendo IA: {reason}")
        self._stop.set()

    def _play(self, notation, interrupt=None):
        """Ejecuta la notacion. Devuelve False si hay que detener el bot."""
        steps = parse(notation, self._config["motion_step_frames"], self._config["button_hold_frames"])
        check = self._should_stop if interrupt is None else (lambda: self._should_stop() or interrupt())
        play(self._keyboard, self._clock, steps, self._facing_right(), check)
        return not self._should_stop()

    def _fight_on_screen(self):
        """Mira la pantalla cada ~150 ms. mss debe crearse en el hilo que lo usa."""
        if self._fight_check:
            return self._fight_check()
        now = time.perf_counter()
        if now - self._fight_checked_at > 0.15:
            if self._capture is None:
                self._capture = WindowCapture(self._hwnd)
            self._in_fight = fight_hud_visible(self._capture.grab())
            self._fight_checked_at = now
        return self._in_fight

    def _run(self):
        self._log("IA activa. Pulsa la tecla de emergencia para detener.")
        waiting = False
        try:
            while not self._should_stop():
                if not self._fight_on_screen():
                    # Menus, continue, KO: no pulsar nada.
                    if not waiting:
                        self._keyboard.release_all()
                        self._on_fight_paused()
                        self._log("Fuera de pelea: esperando sin pulsar botones...")
                        waiting = True
                    self._clock.wait_frames(6, self._should_stop)
                    continue
                if waiting:
                    self._log("Pelea detectada: retomando.")
                    waiting = False
                if not self._tick():
                    break
        finally:
            self._keyboard.release_all()
            if self._capture:
                self._capture.close()
            self._log("IA detenida.")

    def _tick(self):
        raise NotImplementedError

    def _on_fight_paused(self):
        pass


class RandomBot(_BaseBot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._weights = [a[0] for a in ACTIONS]

    def _tick(self):
        _, name, notation = random.choices(ACTIONS, weights=self._weights)[0]
        self._log(f"IA -> {name}")
        if not self._play(notation):
            return False
        # Pausa variable entre acciones para que no sea robotico.
        return self._clock.wait_frames(random.randint(2, 12), self._should_stop)


class RuleBot(_BaseBot):
    def __init__(self, keyboard, clock, config, hwnd, facing_right, on_log, reader, moves, brain=None,
                 **mode):
        super().__init__(keyboard, clock, config, hwnd, facing_right, on_log, **mode)
        self._brain = brain or RuleBrain(reader, moves)
        # El cerebro distingue el raspado de un especial bloqueado de un golpe con las teclas
        # que estan aplicadas (guardia = atras sostenido).
        self._brain.held_keys = lambda: getattr(self._keyboard, "_pressed", None)
        self._last_situation = None
        self.current = (None, None, 0)   # (situacion, accion, numero de decision)
        self._saved_at = time.perf_counter()
        self.save_every = 30   # segundos entre guardados de lo aprendido

    @property
    def brain(self):
        return self._brain

    def _run(self):
        try:
            super()._run()
        finally:
            self._save()

    def _on_fight_paused(self):
        discard = getattr(self._brain, "discard_pending", None)
        if discard:
            discard()

    def _save(self):
        save = getattr(self._brain, "save", None)
        if save:
            save()
            self._log(f"Aprendizaje guardado ({self._brain.updates} experiencias en esta sesion).")
        self._saved_at = time.perf_counter()

    def _tick(self):
        if time.perf_counter() - self._saved_at > self.save_every and hasattr(self._brain, "save"):
            self._save()
        decision = self._brain.decide()
        if decision is None:
            self._halt("sin vision (carga lua/kof_state.lua)")
            return False
        situation, option = decision
        self.current = (situation, option.name, self.current[2] + 1)   # para el registro defensivo
        if situation != self._last_situation:
            self._log(f"[{situation}]")
            self._last_situation = situation
        state = self._brain.state()
        detail = f" d={state.distance} h_rival={state.rival.height}" if state else ""
        self._log(f"  -> {option.name} ({option.notation}){detail}")
        guard = GUARD_PATTERN.fullmatch(option.notation)
        if situation == "me agarran":
            # El escape no se corta por "me agarran" (justamente es la respuesta).
            if not self._play(option.notation):
                return False
            self._log("     escape de agarre intentado")
            return not self._should_stop()
        if guard:
            if not self._guard(int(guard.group(1))):
                return False
        elif is_combo(option.notation):
            if not self._combo(option.notation):
                return False
        else:
            urgent = self._brain.urgent if option.interruptible else (lambda: False)
            if not self._play(option.notation, lambda: urgent() or self._brain.being_thrown()):
                return False
        # Pausa corta entre acciones: en guardia si el rival esta cerca, si no, neutral.
        # Con ofensiva estrategica solo se guarda ante una amenaza real (y la pausa es mas
        # corta) para no quedarse quieto cubriendose sin motivo.
        state = self._brain.state()
        if getattr(self._brain, "strategy", None):
            if self._brain.threat_now():
                return self._guard(random.randint(2, 6))
            pause = random.randint(1, 3)
        else:
            pause = random.randint(2, 6)
            if state and state.distance <= GUARD_PAUSE_DISTANCE:
                return self._guard(pause)
        return self._clock.wait_frames(
            pause, lambda: self._should_stop() or self._brain.urgent() or self._brain.being_thrown()) \
            or not self._should_stop()

    def _combo(self, notation):
        """Combo con hit-confirm: cada parte solo si la anterior conecto."""
        def rival_life():
            state = self._brain.state()
            return state.rival.life if state else None

        parts = notation.count(">") + 1
        connected, damage, _ = play_combo(self._keyboard, self._clock, notation, self._facing_right(),
                                          rival_life, self._config["motion_step_frames"],
                                          self._config["button_hold_frames"],
                                          lambda: self._should_stop() or self._brain.being_thrown())
        self._log(f"     combo: {connected}/{parts} partes conectaron, danio {damage}")
        return not self._should_stop()

    def _guard(self, frames):
        """Guardia que se reajusta cada frame: abajo si el rival esta agachado (lows),
        de pie si esta de pie o en el aire (overheads y saltos). Se corta si aparece
        una oportunidad de castigo. Devuelve False si hay que detener el bot."""
        # En modo lockstep cada intercambio con el emulador es caro: reajustar cada 2 frames.
        step = getattr(self._clock, "WATCH_CHUNK", 1)
        for _ in range(0, frames, step):
            state = self._brain.state()
            if state is None:
                break
            low = self._brain.guard_low()
            self._keyboard.set_state(keys_for(1 if low else 4, "", state.facing_right))
            if not self._clock.wait_frames(step, self._should_stop):
                return False
            if self._brain.can_punish_now() or self._brain.being_thrown():
                break
        return not self._should_stop()
