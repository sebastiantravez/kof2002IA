"""KOF AI Lab - Fase 1: controlar KOF 2002 (Fightcade/FBNeo) desde una app.

Uso solo en Training / partidas locales u offline.
"""
import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from kof_ai import emulator
from kof_ai.bot import RandomBot, RuleBot
from kof_ai.game_state import StateReader
from kof_ai.keyboard import VirtualKeyboard
from kof_ai.brain import RuleBrain
from kof_ai.imitation import Imitation
from kof_ai.learning import LearningBrain
from kof_ai.motions import MOVES, FrameClock, parse, play

CONFIG_PATH = Path(__file__).with_name("config.json")
STATE_PATH = Path(__file__).with_name("state.txt")
IMITATION_PATH = Path(__file__).parent / "recordings" / "imitation.json"


class App:
    def __init__(self, root):
        self.root = root
        self.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.keyboard = VirtualKeyboard(self.config["keys"])
        self.clock = FrameClock(self.config["fps"])
        self.hwnd = None
        self.bot = None
        self.busy = threading.Lock()
        self.logs = queue.Queue()
        self.reader = StateReader(STATE_PATH, me_is_p1=True)
        self.state = None

        root.title("KOF AI Lab - prueba de juego kof2002IA")
        root.attributes("-topmost", True)
        root.resizable(False, False)
        self._build_ui()
        self._refresh_emulator()
        self._drain_logs()
        self._poll_state()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}
        frm = ttk.Frame(self.root, padding=10)
        frm.grid()

        status = ttk.LabelFrame(frm, text="Estado")
        status.grid(row=0, column=0, columnspan=2, sticky="ew", **pad)
        self.status_var = tk.StringVar(value="Buscando emulador...")
        ttk.Label(status, textvariable=self.status_var, width=48).grid(row=0, column=0, **pad)
        ttk.Button(status, text="Buscar", command=self._refresh_emulator).grid(row=0, column=1, **pad)

        opts = ttk.LabelFrame(frm, text="Opciones")
        opts.grid(row=1, column=0, columnspan=2, sticky="ew", **pad)
        self.auto_facing = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Orientacion automatica (usa la vision)",
                        variable=self.auto_facing).grid(row=0, column=0, sticky="w", **pad)
        self.facing_right = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Si no: mira a la derecha",
                        variable=self.facing_right).grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(opts, text="Frames al mantener direccion:").grid(row=1, column=0, sticky="w", **pad)
        self.hold_frames = tk.IntVar(value=20)
        ttk.Spinbox(opts, from_=1, to=240, textvariable=self.hold_frames, width=6).grid(row=1, column=1, **pad)

        pad_frame = ttk.LabelFrame(frm, text="Control manual")
        pad_frame.grid(row=2, column=0, sticky="n", **pad)
        layout = [("7", "↖"), ("8", "↑"), ("9", "↗"),
                  ("4", "←"), ("5", "·"), ("6", "→"),
                  ("1", "↙"), ("2", "↓"), ("3", "↘")]
        for idx, (num, label) in enumerate(layout):
            ttk.Button(pad_frame, text=label, width=4,
                       command=lambda n=num: self._run_notation(f"{n}[{self.hold_frames.get()}]")
                       ).grid(row=idx // 3, column=idx % 3, padx=2, pady=2)
        buttons = ttk.Frame(pad_frame)
        buttons.grid(row=3, column=0, columnspan=3, pady=4)
        for idx, btn in enumerate("ABCD"):
            ttk.Button(buttons, text=btn, width=4,
                       command=lambda b=btn: self._run_notation(b)).grid(row=0, column=idx, padx=2)

        moves = ttk.LabelFrame(frm, text="Movimientos especiales")
        moves.grid(row=2, column=1, sticky="n", **pad)
        for idx, (name, notation) in enumerate(MOVES.items()):
            ttk.Button(moves, text=name, width=34,
                       command=lambda n=notation: self._run_notation(n)).grid(row=idx, column=0, padx=2, pady=1)
        custom = ttk.Frame(moves)
        custom.grid(row=len(MOVES), column=0, pady=4)
        self.custom_var = tk.StringVar(value="236A")
        ttk.Entry(custom, textvariable=self.custom_var, width=20).grid(row=0, column=0, padx=2)
        ttk.Button(custom, text="Ejecutar", command=lambda: self._run_notation(self.custom_var.get())
                   ).grid(row=0, column=1, padx=2)

        ai = ttk.LabelFrame(frm, text="IA")
        ai.grid(row=3, column=0, columnspan=2, sticky="ew", **pad)
        self.ai_mode = tk.StringVar(value="learn")
        modes = ttk.Frame(ai)
        modes.grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Radiobutton(modes, text="Aprende (Fase 4)", value="learn",
                        variable=self.ai_mode).grid(row=0, column=0, sticky="w", **pad)
        ttk.Radiobutton(modes, text="Con reglas (Fase 3)", value="rules",
                        variable=self.ai_mode).grid(row=0, column=1, sticky="w", **pad)
        ttk.Radiobutton(modes, text="Aleatoria (Fase 1)", value="random",
                        variable=self.ai_mode).grid(row=0, column=2, sticky="w", **pad)
        ttk.Button(modes, text="Ver lo aprendido", command=self._show_learning
                   ).grid(row=0, column=3, **pad)
        ttk.Label(ai, text="Personaje:").grid(row=1, column=0, sticky="e", **pad)
        characters = list(self.config["characters"])
        self.character = tk.StringVar(value=characters[0])
        ttk.Combobox(ai, textvariable=self.character, values=characters, state="readonly",
                     width=12).grid(row=1, column=1, sticky="w", **pad)
        self.ai_button = ttk.Button(ai, text="ACTIVAR IA", command=self._toggle_ai)
        self.ai_button.grid(row=2, column=0, **pad)
        ttk.Label(ai, text=f"Emergencia: {self.config.get('kill_switch_key', 'F8')} "
                           "o cambiar de ventana").grid(row=2, column=1, **pad)

        vision = ttk.LabelFrame(frm, text="Vision en vivo (Fase 2, via lua/kof_state.lua)")
        vision.grid(row=4, column=0, columnspan=2, sticky="ew", **pad)
        self.vision_var = tk.StringVar(value="Sin datos: carga lua/kof_state.lua en el emulador")
        ttk.Label(vision, textvariable=self.vision_var, font=("Consolas", 10),
                  justify="left").grid(row=0, column=0, sticky="w", **pad)

        self.log_box = tk.Text(frm, height=8, width=70, state="disabled")
        self.log_box.grid(row=5, column=0, columnspan=2, **pad)

    def _refresh_emulator(self):
        windows = emulator.find_emulator_windows(self.config["emulator_processes"])
        if len(windows) > 1:
            self.hwnd = None
            self.status_var.set(f"⚠ {len(windows)} emuladores abiertos: deja solo la partida del bot")
        elif windows:
            self.hwnd, title = windows[0]
            self.status_var.set(f"● Emulador detectado: {title[:40]}")
        else:
            self.hwnd = None
            self.status_var.set("○ Emulador no encontrado (abre KOF 2002 en Fightcade)")

    def _focus_emulator(self):
        if not emulator.is_window(self.hwnd):
            self._refresh_emulator()
        if not self.hwnd:
            self.log("No hay emulador abierto.")
            return False
        if not emulator.focus(self.hwnd):
            self.log("No se pudo dar foco al emulador. Haz clic en su ventana y reintenta.")
            return False
        self.clock.wait_frames(self.config["focus_delay_frames"])
        return True

    def _run_notation(self, notation):
        if self.bot and self.bot.running:
            self.log("Detén la IA antes de usar el control manual.")
            return
        try:
            steps = parse(notation, self.config["motion_step_frames"], self.config["button_hold_frames"])
        except ValueError as exc:
            self.log(str(exc))
            return
        facing = self._facing_right()

        def worker():
            if not self.busy.acquire(blocking=False):
                return
            try:
                if self._focus_emulator():
                    play(self.keyboard, self.clock, steps, facing)
                    self.log(f"Ejecutado: {notation}")
            finally:
                self.busy.release()

        threading.Thread(target=worker, daemon=True).start()

    def _toggle_ai(self):
        if self.bot and self.bot.running:
            self.bot.stop()
            return
        if not self._focus_emulator():
            return
        auto, fallback = self.auto_facing.get(), self.facing_right.get()

        def facing():
            state = self.reader.read() if auto else None
            return state.facing_right if state else fallback

        mode = self.ai_mode.get()
        if mode in ("rules", "learn"):
            if self.reader.read() is None:
                self.log("Sin vision: carga lua/kof_state.lua en el emulador.")
                return
            if not self.reader.single_source():
                self.log("Dos scripts Lua escriben state.txt: deja kof_state.lua solo en la partida del bot.")
                return
            moves = self.config["characters"][self.character.get()]
            imitation = Imitation.load(IMITATION_PATH, self.character.get())
            if imitation:
                self.log(f"Imitacion cargada: {len(imitation.combos)} combos de jugadores reales.")
            if mode == "learn":
                brain = LearningBrain(self.reader, moves, self._learning_path(), imitation=imitation)
                self.log(f"Aprendizaje cargado: {len(brain.table)} situaciones conocidas.")
            else:
                brain = RuleBrain(self.reader, moves, imitation)
            self.bot = RuleBot(self.keyboard, self.clock, self.config, self.hwnd, facing, self.log,
                               self.reader, moves, brain)
        else:
            self.bot = RandomBot(self.keyboard, self.clock, self.config, self.hwnd, facing, self.log)
        self.bot.start()
        self.ai_button.config(text="DETENER IA")
        self._watch_bot()

    def _watch_bot(self):
        if self.bot and self.bot.running:
            self.root.after(200, self._watch_bot)
        else:
            self.ai_button.config(text="ACTIVAR IA")

    def _learning_path(self):
        return CONFIG_PATH.with_name(f"learned_{self.character.get()}.json")

    def _show_learning(self):
        brain = LearningBrain(self.reader, {}, self._learning_path())
        text = brain.summary() or "Todavia no hay nada aprendido para este personaje."
        win = tk.Toplevel(self.root)
        win.title(f"Lo aprendido - {self.character.get()}")
        win.attributes("-topmost", True)
        box = tk.Text(win, width=130, height=30, font=("Consolas", 9))
        box.insert("1.0", "contexto                                      [veces] mejores acciones "
                          "(recompensa media, n)\n\n" + text)
        box.config(state="disabled")
        box.pack(fill="both", expand=True)

    def _facing_right(self):
        state = self.reader.read() if self.auto_facing.get() else None
        return state.facing_right if state else self.facing_right.get()

    def _poll_state(self):
        state = self.reader.read()
        if state:
            me, rival = state.me, state.rival
            self.vision_var.set(
                f"Frame {state.frame}\n"
                f"YO     vida {me.life_pct:3d}%  x {me.x:4d}  {'EN EL AIRE' if me.airborne else 'suelo'}\n"
                f"RIVAL  vida {rival.life_pct:3d}%  x {rival.x:4d}  {'EN EL AIRE' if rival.airborne else 'suelo'}"
                f"{'  ATACA' if rival.attacking else ''}\n"
                f"Distancia {state.distance:4d}   Miro a la {'derecha' if state.facing_right else 'izquierda'}")
        else:
            self.vision_var.set("Sin datos: carga lua/kof_state.lua en el emulador")
        self.root.after(50, self._poll_state)

    def log(self, message):
        self.logs.put(message)

    def _drain_logs(self):
        while not self.logs.empty():
            self.log_box.config(state="normal")
            self.log_box.insert("end", self.logs.get() + "\n")
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.root.after(100, self._drain_logs)

    def _on_close(self):
        if self.bot:
            self.bot.stop()
        self.keyboard.release_all()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
