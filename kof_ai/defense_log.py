"""Registro defensivo: que ataca el rival, que hacia el bot, que paso y por que.

Solo usa informacion observable en la RAM (ver kof_ai/game_state.py):
- tipo de amenaza: aereo (rival en el aire), bajo (atacó justo despues de estar
  agachado), de pie (incluye overheads: no se distinguen de un golpe de pie);
- golpes recibidos sin ningun ataque visible del rival: posible agarre (de cerca) o
  posible proyectil (de lejos). No hay deteccion fiable de agarres ni proyectiles.
Los motivos de fallo son heuristicos y lo dicen cuando la causa no es observable.
"""
import csv
from collections import Counter
from pathlib import Path

ATTACK_WINDOW = 40        # frames que se sigue un ataque rival para ver si pego
PUNISH_WINDOW = 60        # frames para ver si un castigo hizo danio
NEAR = 180                # ataques mas lejos no se cuentan como amenaza
LOW_WINDOW = 4
MAX_DAMAGE = 60
CHIP_DAMAGE = 2           # perdida de vida con guardia puesta que es raspado de un especial bloqueado
                          # (medido: 1 punto casi siempre con guardia; los golpes reales quitan >= 4)
COUNTER_WINDOW = 120      # ofensiva tras defensa: danio hecho hasta N frames despues de evitar un ataque
ATTACK_RESULT_FRAMES = 40 # un ataque nuestro "fallo" si no hizo danio en N frames

# Situacion del cerebro -> estado de la maquina V2 (para el tiempo por estado).
STATE_OF = {"rival ataca": "DEFEND", "presion del rival": "DEFEND", "rival cae hacia mi": "DEFEND",
            "rival ataca desde el aire": "DEFEND", "acorralado": "DEFEND", "me agarran": "DEFEND",
            "rival en el aire": "DEFEND", "me golpearon": "RECOVERY", "estoy en el aire": "RECOVERY",
            "castigar": "BLOCK_PUNISH", "castigo tras bloqueo": "BLOCK_PUNISH",
            "castigo a golpe fallado": "WHIFF_PUNISH", "castigo seguro": "SAFE_PUNISH"}
OFFENSIVE_PREFIXES = ("poke", "barrida", "golpe bajo", "golpe cercano", "combo", "agarre", "overhead",
                      "especial de lejos", "castigo", "anti-aire")


def state_of(situation):
    if not situation:
        return "NEUTRAL"
    if situation.startswith("NEUTRAL:"):
        return situation.split(":", 1)[1]
    return STATE_OF.get(situation, "NEUTRAL")


class DefenseLogger:
    def __init__(self, path, bot_info):
        """bot_info() -> (situacion, nombre de la opcion) que el bot esta ejecutando."""
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._bot_info = bot_info
        self._file = open(self.path, "w", newline="", encoding="utf-8")
        self._csv = csv.writer(self._file)
        self._csv.writerow(["frame", "evento", "amenaza", "rival", "distancia", "acorralado",
                            "situacion_bot", "accion_bot", "guardia", "resultado", "danio", "motivo",
                            "situacion_impacto", "accion_impacto", "teclas_frame_previo",
                            "rival_cambio_de_lado", "altura_rival"])
        self._impact = ("", "", "", "", "")
        self._prev_keys = set()
        self._prev = None
        self._crouch_frame = -999
        self._events = []          # ataques rivales abiertos
        self._punish = None        # castigo abierto
        self._last_situation = None
        self.threats = Counter()   # (amenaza, resultado) -> veces
        self.reasons = Counter()
        self.punishes = Counter()  # (tipo de castigo, exito/fallo) -> veces
        self.state_frames = Counter()
        self.idle_frames = 0       # neutral sin amenaza: sin pulsar nada
        self.idle_guard_frames = 0 # neutral sin amenaza: cubriendose
        self.neutral_frames = 0
        self.dealt = self.taken = 0
        self.chip = self.chip_blocks = 0   # raspado de especiales bloqueados (no son golpes)
        self.rounds = 1
        self._last_taken_frame = -10_000
        self._rival_end = None     # fin del ultimo ataque rival cercano
        self.attack_gaps = Counter()   # frames entre fin de un ataque rival y el siguiente (cerca)
        self.attacks = Counter()   # nuestros ataques: con danio / fallidos
        self.counters = Counter()  # ataques evitados seguidos de danio nuestro (ofensiva tras defensa)
        self._counter_deadline = -1
        self._last_decision = None
        self._attack = None        # ataque nuestro abierto

    def observe(self, state, keys):
        prev = self._prev
        self._prev = state
        prev_keys, self._prev_keys = self._prev_keys, set(keys)
        if prev is None:
            return
        f = state.frame
        me, rival = state.me, state.rival
        if me.life > prev.me.life + MAX_DAMAGE or rival.life > prev.rival.life + MAX_DAMAGE:
            # Se recargo la ronda: lo abierto no tiene resultado observable.
            self._events.clear()
            self._punish = None
            self._attack = None
            self._counter_deadline = -1
            self.rounds += 1
            return
        if prev.rival.crouching:
            self._crouch_frame = prev.frame
        info = self._bot_info()
        situation, option = info[0], info[1]
        decision = info[2] if len(info) > 2 else None
        guard = self._guard(keys, state.facing_right)
        dealt = prev.rival.life - rival.life
        dealt = dealt if 0 < dealt <= MAX_DAMAGE else 0
        self.dealt += dealt
        self._track_state(state, situation, guard, keys)
        self._track_our_attack(f, option, decision, dealt)
        if dealt and f <= self._counter_deadline:
            self.counters["con danio"] += 1
            self._counter_deadline = -1

        # Nuevo ataque rival cercano
        if rival.attacking and not prev.rival.attacking and state.distance <= NEAR:
            kind = ("aereo" if rival.airborne else
                    "bajo" if f - self._crouch_frame <= LOW_WINDOW else "de pie/overhead")
            self._events.append({"start": f, "kind": kind, "dist": state.distance,
                                 "corner": state.back_to_wall, "situation": situation,
                                 "option": option, "rival": rival.character, "guards": [],
                                 "rival_right": rival.x > me.x})
        for event in self._events:
            event["guards"].append(guard)

        # Golpe recibido
        taken = prev.me.life - me.life
        guard_before = self._guard(prev_keys, prev.facing_right)
        if 0 < taken <= CHIP_DAMAGE and guard_before in ("de pie", "abajo"):
            # Medido: perder 1 punto con la guardia puesta es el raspado de un especial
            # BLOQUEADO (docs/DEFENSE_AUDIT_V4.md): no es un golpe; el ataque sigue abierto.
            self.taken += taken
            self.chip += taken
            self.chip_blocks += 1
        elif 0 < taken <= MAX_DAMAGE:
            self.taken += taken
            event = self._events[-1] if self._events else None
            # Teclas que estaban aplicadas en el frame anterior (las de este intercambio se
            # aplican desde ahora) y si el rival paso al otro lado desde que empezo su ataque.
            crossed = "" if not event else ("si" if (rival.x > me.x) != event["rival_right"] else "no")
            self._impact = (situation, option, "+".join(sorted(prev_keys)) or "nada", crossed, rival.height)
            if event:
                reason = self._reason(event["kind"], guard)
                self._close(event, f, "golpeado", taken, reason, guard)
                self._events.remove(event)
            else:
                kind = ("continuacion de combo (golpe seguido)" if f - self._last_taken_frame <= 40 else
                        "sin ataque visible (posible agarre)" if state.distance <= 35
                        else "sin ataque visible (posible proyectil)")
                self._write(f, "golpe", kind, rival.character, state.distance, state.back_to_wall,
                            situation, option, guard, "golpeado", taken, "no observable")
                self.threats[(kind, "golpeado")] += 1
            self._last_taken_frame = f

        # Pausas entre ataques rivales cercanos (para calibrar punish_confirm_frames)
        if prev.rival.attacking and not rival.attacking and state.distance <= NEAR:
            self._rival_end = f
        if rival.attacking and not prev.rival.attacking and self._rival_end is not None:
            gap = f - self._rival_end
            if gap <= 30:
                self.attack_gaps[gap] += 1
            self._rival_end = None

        # Ataques que pasaron sin pegar
        for event in [e for e in self._events if f - e["start"] > ATTACK_WINDOW]:
            guards = Counter(event["guards"]).most_common(1)[0][0] if event["guards"] else "nada"
            self._close(event, f, "evitado", 0, "", guards)
            self._events.remove(event)
            self.counters["defensas"] += 1
            self._counter_deadline = f + COUNTER_WINDOW

        # Castigos (tras bloqueo o a golpe fallado)
        is_punish = situation in ("castigar", "castigo tras bloqueo", "castigo a golpe fallado", "castigo seguro")
        if is_punish and situation != self._last_situation and not self._punish:
            self._punish = {"start": f, "option": option, "life0": rival.life, "dist": state.distance,
                            "kind": situation}
        if self._punish and f - self._punish["start"] > PUNISH_WINDOW:
            done = max(0, self._punish["life0"] - rival.life)
            ok = "exito" if done > 0 else "fallo"
            self.punishes[(self._punish["kind"], ok)] += 1
            self._write(f, "castigo", "", rival.character, self._punish["dist"], state.back_to_wall,
                        self._punish["kind"], self._punish["option"], "", ok, done, "")
            self._punish = None
        self._last_situation = situation

    def _track_state(self, state, situation, guard, keys):
        name = state_of(situation)
        self.state_frames[name] += 1
        threat = state.rival.attacking or (state.rival.airborne and state.distance <= NEAR)
        if name in ("DEFEND", "RECOVERY", "BLOCK_PUNISH", "WHIFF_PUNISH") or threat:
            return
        self.neutral_frames += 1
        if not keys:
            self.idle_frames += 1
        elif guard in ("abajo", "de pie") and not (keys & set("ABCD")):
            self.idle_guard_frames += 1

    def _track_our_attack(self, f, option, decision, dealt):
        if self._attack:
            if dealt:
                self.attacks["con danio"] += 1
                self._attack = None
            elif f - self._attack["start"] > ATTACK_RESULT_FRAMES:
                self.attacks["fallidos"] += 1
                self._attack = None
        new_decision = decision is not None and decision != self._last_decision
        self._last_decision = decision
        if new_decision and option and option.startswith(OFFENSIVE_PREFIXES):
            if self._attack:   # se paso a otra accion sin que la anterior hiciera danio
                self.attacks["fallidos"] += 1
            self._attack = {"start": f, "option": option}

    @staticmethod
    def _guard(keys, facing_right):
        back = "left" if facing_right else "right"
        if back in keys and "down" in keys:
            return "abajo"
        if back in keys:
            return "de pie"
        if keys & set("ABCD"):
            return "atacando"
        return "moviendo" if keys else "nada"

    @staticmethod
    def _reason(kind, guard):
        if guard == "atacando":
            return "estaba atacando"
        if guard in ("moviendo", "nada"):
            return "sin guardia"
        if kind == "aereo" and guard == "abajo":
            return "guardia baja contra ataque aereo"
        if kind == "bajo" and guard == "de pie":
            return "guardia alta contra ataque bajo"
        return "guardia correcta: causa no observable (overhead, cruce o golpe multiple)"

    def _close(self, event, f, result, damage, reason, guard):
        self.threats[(event["kind"], result)] += 1
        if reason:
            self.reasons[reason] += 1
        self._write(f, "ataque rival", event["kind"], event["rival"], event["dist"], event["corner"],
                    event["situation"], event["option"], guard, result, damage, reason)

    def _write(self, *row):
        # Columnas de impacto (solo en golpes recibidos): lo que pasaba en el frame del golpe.
        impact = self._impact if row[9] == "golpeado" else ("", "", "", "", "")
        self._csv.writerow(row + tuple(impact))
        self._file.flush()   # que un corte brusco no pierda el registro

    def close(self):
        self._file.close()

    def report(self):
        lines = ["== Defensa (solo informacion observable) =="]
        kinds = sorted({k for k, _ in self.threats})
        for kind in kinds:
            hit = self.threats[(kind, "golpeado")]
            ok = self.threats[(kind, "evitado")]
            total = hit + ok
            pct = f"{100 * ok / total:.0f}% evitados" if ok or "visible" not in kind else ""
            lines.append(f"  {kind:40s} {total:4d}  golpeado {hit:3d}  {pct}")
        if self.chip_blocks:
            lines.append(f"  Bloqueos con raspado (especial bloqueado, no es golpe): {self.chip_blocks}, "
                         f"{self.chip} de vida")
        if self.reasons:
            lines.append("  Motivos de los golpes recibidos:")
            for reason, n in self.reasons.most_common():
                lines.append(f"    {n:3d}  {reason}")
        for kind in sorted({k for k, _ in self.punishes}):
            ok, bad = self.punishes[(kind, "exito")], self.punishes[(kind, "fallo")]
            lines.append(f"  Castigos ({kind}): {ok + bad}, con danio {ok} ({100 * ok / max(ok + bad, 1):.0f}%)")
        m = self.metrics()
        lines.append("== Ofensiva y tiempo ==")
        lines.append(f"  Por ronda ({m['rondas']}): danio hecho {m['danio_hecho_por_ronda']:.1f}, "
                     f"recibido {m['danio_recibido_por_ronda']:.1f}")
        lines.append(f"  Defensa correcta: {m['defensa_correcta_pct']:.0f}% de los ataques rivales")
        lines.append(f"  Ataques nuestros: {self.attacks['con danio']} con danio, {self.attacks['fallidos']} fallidos")
        lines.append(f"  Ofensiva tras defensa: {self.counters['con danio']} de {self.counters['defensas']} "
                     f"defensas seguidas de danio en {COUNTER_WINDOW} frames ({m['ofensiva_tras_defensa_pct']:.0f}%)")
        lines.append(f"  Neutral sin amenaza: {m['quieto_pct']:.0f}% sin pulsar nada, "
                     f"{m['guardia_sin_amenaza_pct']:.0f}% cubriendose sin motivo")
        if self.attack_gaps:
            gaps = sorted(self.attack_gaps.elements())
            lines.append(f"  Pausa entre ataques rivales seguidos (<=30 f): {len(gaps)} casos, "
                         f"mediana {gaps[len(gaps) // 2]} f, 90% <= {gaps[int(len(gaps) * 0.9)]} f")
        total = sum(self.state_frames.values()) or 1
        lines.append("  Tiempo por estado: " + ", ".join(
            f"{k} {100 * n / total:.0f}%" for k, n in self.state_frames.most_common()))
        lines.append(f"  Detalle en {self.path}")
        return "\n".join(lines)

    def metrics(self, rounds=None):
        """Resumen numerico de la sesion (para comparar versiones)."""
        ok = sum(n for (k, r), n in self.threats.items() if r == "evitado")
        hit = sum(n for (k, r), n in self.threats.items() if r == "golpeado" and "visible" not in k)
        neutral = max(self.neutral_frames, 1)
        punish_ok = sum(n for (_, r), n in self.punishes.items() if r == "exito")
        total = sum(self.state_frames.values()) or 1
        return {
            "rondas": rounds or self.rounds,
            "danio_hecho": self.dealt, "danio_recibido": self.taken,
            "bloqueos_con_raspado": self.chip_blocks, "danio_raspado": self.chip,
            "pausas_entre_ataques": dict(sorted(self.attack_gaps.items())),
            "danio_hecho_por_ronda": self.dealt / (rounds or self.rounds),
            "danio_recibido_por_ronda": self.taken / (rounds or self.rounds),
            "defensa_correcta_pct": 100 * ok / max(ok + hit, 1),
            "castigos": sum(self.punishes.values()), "castigos_con_danio": punish_ok,
            "ataques_con_danio": self.attacks["con danio"], "ataques_fallidos": self.attacks["fallidos"],
            "ofensiva_tras_defensa_pct": 100 * self.counters["con danio"] / max(self.counters["defensas"], 1),
            "quieto_pct": 100 * self.idle_frames / neutral,
            "guardia_sin_amenaza_pct": 100 * self.idle_guard_frames / neutral,
            "tiempo_por_estado_pct": {k: 100 * n / total for k, n in self.state_frames.items()},
        }
