"""Fase 4: aprendizaje por refuerzo (bandit contextual sobre el cerebro de reglas).

- Contexto: situacion de RuleBrain + tramo de distancia.
- Acciones: las opciones que las reglas ofrecen en esa situacion.
- Recompensa: danio hecho - TAKEN_WEIGHT * danio recibido en los REWARD_FRAMES
  siguientes a empezar la accion.
- Eleccion: softmax(log(peso de la regla) + valor aprendido / TEMPERATURE),
  asi lo que funciona sale mas, pero nunca siempre (sigue siendo impredecible).
"""
import json
import math
import random
import threading
from pathlib import Path

from .brain import DISTANCE_BUCKET, RuleBrain
from .combo import is_dm

REWARD_FRAMES = 40
DM_REWARD_FRAMES = 150   # los DM golpean tras la pausa de super y su recorrido
TAKEN_WEIGHT = 2.0  # recibir danio pesa el doble: priorizar cubrirse
TEMPERATURE = 4.0
SHRINK = 3          # pocas muestras -> valor cerca de 0 (no confiar en la suerte)


class LearningBrain(RuleBrain):
    def __init__(self, reader, moves, table_path, explore=True, imitation=None):
        super().__init__(reader, moves, imitation)
        self.table_path = Path(table_path)
        self.explore = explore
        self._lock = threading.Lock()
        self.table = self._load()
        self._pending = []   # (key, option_name, frame0, dealt0, taken0)
        self.updates = 0
        self.reward_sum = 0.0

    # ---- decision ----

    def _choose(self, state, situation, options):
        self._settle(state)
        if len(options) == 1:
            return options[0]
        key = self.context_key(state, situation)
        stats = self.table.get(key, {})
        scores = []
        for o in options:
            n, mean = stats.get(o.name, (0, 0.0))
            value = mean * n / (n + SHRINK)
            score = math.log(o.weight * self._repeat_penalty(o)) + value / TEMPERATURE
            if self.explore:
                score += 0.5 / math.sqrt(n + 1)  # un poco de curiosidad por lo poco probado
            scores.append(score)
        top = max(scores)
        weights = [math.exp(s - top) for s in scores]
        choice = random.choices(options, weights=weights)[0]
        # Un DM golpea mucho despues de elegirlo: su recompensa necesita una ventana larga.
        window = DM_REWARD_FRAMES if is_dm(choice.notation) else REWARD_FRAMES
        self._pending.append((key, choice.name, state.frame, self.dealt_total, self.taken_total, window))
        return choice

    @staticmethod
    def context_key(state, situation):
        bucket = min(state.distance // DISTANCE_BUCKET, 7)
        return f"{situation}|d{bucket}"

    # ---- recompensas ----

    def _settle(self, state):
        """Cierra las decisiones cuya ventana de recompensa ya paso."""
        still = []
        for entry in self._pending:
            key, name, frame0, dealt0, taken0, window = entry
            elapsed = state.frame - frame0
            if elapsed < 0 or elapsed > window * 3:
                continue  # el juego se reinicio o paso demasiado tiempo (menus): descartar
            if elapsed < window:
                still.append(entry)
                continue
            reward = (self.dealt_total - dealt0) - TAKEN_WEIGHT * (self.taken_total - taken0)
            self._update(key, name, reward)
        self._pending = still

    def discard_pending(self):
        """Fuera de pelea (KO, menus) las recompensas pendientes no son fiables."""
        self._pending = []

    def _update(self, key, name, reward):
        with self._lock:
            n, mean = self.table.setdefault(key, {}).get(name, (0, 0.0))
            n += 1
            mean += (reward - mean) / n
            self.table[key][name] = (n, round(mean, 3))
        self.updates += 1
        self.reward_sum += reward

    # ---- persistencia ----

    def _load(self):
        try:
            raw = json.loads(self.table_path.read_text(encoding="utf-8"))
            return {k: {a: tuple(v) for a, v in acts.items()} for k, acts in raw.items()}
        except (OSError, ValueError):
            return {}

    def save(self):
        with self._lock:
            data = {k: {a: list(v) for a, v in acts.items()} for k, acts in sorted(self.table.items())}
        tmp = self.table_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.table_path)

    def summary(self, top=3):
        """Texto con lo mejor aprendido por contexto (solo contextos con datos)."""
        lines = []
        with self._lock:
            for key, acts in sorted(self.table.items()):
                ranked = sorted(acts.items(), key=lambda kv: kv[1][1] * kv[1][0] / (kv[1][0] + SHRINK),
                                reverse=True)
                total = sum(n for n, _ in acts.values())
                best = ", ".join(f"{a} {m:+.1f} (n={n})" for a, (n, m) in ranked[:top])
                lines.append(f"{key:45s} [{total:4d}] {best}")
        return "\n".join(lines)
