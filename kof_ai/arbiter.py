"""Arbitro de acciones (V2.1): la defensa y el ataque proponen por separado y el
arbitro elige UNA sola situacion/opciones. El ataque nunca sobrescribe a la defensa:
solo actua cuando la defensa dice que no hay una amenaza que exija respuesta.

Prioridades:
  1. DEFENSA        amenaza inmediata -> la propuesta defensiva original, siempre.
  2. CASTIGO SEGURO rival vulnerable comprobado -> golpe corto y vuelta a neutral.
  3. ATAQUE         sin amenaza (solo BALANCED_EXPERIMENTAL).
  4. MOVIMIENTO     lo que proponga la defensa en neutral (caminar, guardia, etc).

Modos (perfil "combat_mode" en config.json):
  DEFENSE_ONLY          la defensa original tal cual (incluido su castigo de siempre).
  DEFENSE_WITH_PUNISH   defensa original + solo castigos seguros confirmados.
  BALANCED_EXPERIMENTAL ademas la ofensiva estrategica en neutral (desactivado por defecto).
"""
from dataclasses import dataclass

DEFENSE_ONLY = "DEFENSE_ONLY"
DEFENSE_WITH_PUNISH = "DEFENSE_WITH_PUNISH"
BALANCED_EXPERIMENTAL = "BALANCED_EXPERIMENTAL"
MODES = (DEFENSE_ONLY, DEFENSE_WITH_PUNISH, BALANCED_EXPERIMENTAL)

# Situaciones defensivas que el ataque no puede interrumpir nunca.
HARD_THREATS = {"ronda terminada", "me agarran", "en el aire (esperando aterrizar)", "estoy en el aire",
                "me golpearon", "rival cae hacia mi", "rival ataca desde el aire", "rival ataca"}
# Neutral de la defensa original: sin amenaza, el ataque estrategico puede proponer.
NEUTRAL_SITUATIONS = {"rival lejos", "media distancia", "pegado al rival", "acorralado"}


def mode_from_profile(moves):
    mode = moves.get("combat_mode")
    if mode is None:   # compatibilidad con "offense": "strategic" | "off"
        mode = BALANCED_EXPERIMENTAL if moves.get("offense") == "strategic" else DEFENSE_ONLY
    if mode not in MODES:
        raise ValueError(f"combat_mode desconocido: {mode} (usa {', '.join(MODES)})")
    return mode


@dataclass(frozen=True)
class Proposal:
    situation: str
    options: list


class CombatActionArbiter:
    def __init__(self, mode):
        self.mode = mode
        self.decisions = {"defensa": 0, "castigo": 0, "ataque": 0}

    def select(self, defense, punish=None, attack=None):
        """defense: Proposal de la defensa original (siempre).
        punish: Proposal de castigo seguro confirmado, o None.
        attack: Proposal de la ofensiva estrategica, o None.
        Devuelve (situacion, opciones)."""
        chosen, kind = self._select(defense, punish, attack)
        self.decisions[kind] += 1
        return chosen.situation, chosen.options

    def _select(self, defense, punish, attack):
        if self.mode == DEFENSE_ONLY or defense.situation in HARD_THREATS:
            return defense, "defensa"
        if punish is not None:
            return punish, "castigo"
        if (self.mode == BALANCED_EXPERIMENTAL and attack is not None
                and defense.situation in NEUTRAL_SITUATIONS):
            return attack, "ataque"
        return defense, "defensa"
