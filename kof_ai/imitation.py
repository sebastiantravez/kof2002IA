"""Aprendizaje por imitacion: ajusta las opciones del cerebro con lo que hacen
jugadores reales en las repeticiones (recordings/imitation.json, generado por
tools/learn_from_replays.py).

- Pesos: en cada situacion y tramo de distancia, las opciones se multiplican por
  un factor segun cuan seguido los jugadores reales eligieron esa clase de accion.
- Combos: se agregan los mejores combos reales del personaje (con al menos un especial).
"""
import json
import re
from dataclasses import replace
from pathlib import Path

MIN_SAMPLES = 100        # contexto con menos muestras: no se ajusta
FACTOR_RANGE = (0.3, 3.0)
SMOOTH = 0.03
MAX_PRO_COMBOS = 3
MAX_COMBO_PARTS = 5
MIN_COMBO_DAMAGE = 10
DM_MOTIONS = ("41236", "6321463214", "236236", "2363214", "21441236", "2141236")

# situacion del cerebro -> situacion del analizador de repeticiones
SITUATION_MAP = {
    "estoy en el aire": "estoy en el aire",
    "rival cae hacia mi": "rival en el aire cerca",
    "rival en el aire, esperando": "rival en el aire cerca",
    "rival ataca desde el aire": "rival en el aire cerca",
    "rival ataca": "rival ataca",
    "presion del rival": "rival ataca",
    "acorralado": "pegado al rival",
    "rival lejos": "rival lejos",
    "media distancia": "media distancia",
    "pegado al rival": "pegado al rival",
}
GUARD = ("guardia agachado", "guardia de pie / retroceder")
THROWS = {"6C", "4C", "6D", "4D"}
_PREFIX = re.compile(r"^(?:[145]\[\d+\])+")   # esperas/guardias previas: "5[4]D", "1[8]623C"
_CHARGE = re.compile(r"^([24])\[\d+\]([68])")   # "2[35]8B" -> "[2]8B" como en el analizador


class Imitation:
    def __init__(self, data, character):
        self.situations = data.get("situations", {})
        self.known = {cat for counts in self.situations.values() for cat in counts}
        self.combos = self._pick_combos(data.get("combos", {}).get(character, {}))

    @classmethod
    def load(cls, path, character):
        try:
            return cls(json.loads(Path(path).read_text(encoding="utf-8")), character)
        except (OSError, ValueError):
            return None

    def adjust(self, situation, bucket, options):
        """Multiplica el peso de cada opcion segun lo que hacen los jugadores reales."""
        pro_sit = SITUATION_MAP.get(situation)
        counts = self.situations.get(f"{pro_sit}|d{bucket}") if pro_sit else None
        if not counts or sum(counts.values()) < MIN_SAMPLES:
            return options
        total = sum(n for cat, n in counts.items() if cat != "esperar")
        if total == 0:
            return options
        shares = []
        for option in options:
            cats = self.categories(option)
            # Accion que los jugadores reales nunca muestran en ningun contexto (p.ej. roll):
            # no se puede comparar, se deja igual.
            if cats is None or not any(c in self.known for c in cats):
                shares.append(None)
            else:
                shares.append(sum(counts.get(c, 0) for c in cats) / total)
        known = [s for s in shares if s is not None]
        if not known:
            return options
        mean = sum(known) / len(known)
        adjusted = []
        for option, share in zip(options, shares):
            if share is None:
                adjusted.append(option)
                continue
            factor = (share + SMOOTH) / (mean + SMOOTH)
            factor = min(max(factor, FACTOR_RANGE[0]), FACTOR_RANGE[1])
            adjusted.append(replace(option, weight=option.weight * factor))
        return adjusted

    @staticmethod
    def categories(option):
        """Categorias del analizador que corresponden a esta opcion (None = no comparable)."""
        n = option.notation
        if n.startswith("G["):
            return GUARD
        if n.startswith("4[") or n.startswith("4 5 4"):
            return ("guardia de pie / retroceder",)
        if re.fullmatch(r"1\[\d+\]", n):
            return ("guardia agachado",)
        if n.startswith("6[") or n.startswith("6 5 6"):
            return ("avanzar",)
        if n[:2] in ("7[", "8[", "9["):
            return ("salto",)
        if re.fullmatch(r"5\[\d+\]", n):
            return None   # esperar: no se compara
        first = _PREFIX.sub("", n.split(">")[0]) or n
        first = _CHARGE.sub(r"[\1]\2", first)
        if first in THROWS:
            return (f"agarre/comando {first}",)
        if len(first) > 2 and first[0].isdigit() or "[" in first:
            return (f"especial {first}",)
        return (f"golpe {first}",)

    @staticmethod
    def _pick_combos(combos):
        """Mejores combos reales: con al menos un especial, ordenados por veces y danio.
        Se descartan los que parecen ruido: golpes multi-hit que el analizador atribuye a
        botones pulsados de mas (muchas partes o botones repetidos) y los de poco danio."""
        def plausible(notation):
            parts = notation.split(">")
            has_special = any(len(p) > 2 and p[0].isdigit() or "[" in p for p in parts)
            # Los DM todavia no conectan en esta version (gastan barra sin danio): fuera.
            has_dm = any(any(dm in p for dm in DM_MOTIONS) for p in parts)
            return (has_special and not has_dm and 2 <= len(parts) <= MAX_COMBO_PARTS
                    and len(set(parts)) >= len(parts) - 1)
        good = [(info["veces"], info["danio_medio"], notation) for notation, info in combos.items()
                if plausible(notation) and info["danio_medio"] >= MIN_COMBO_DAMAGE]
        good.sort(reverse=True)
        return {f"pro: {notation}": notation for _, _, notation in good[:MAX_PRO_COMBOS]}
