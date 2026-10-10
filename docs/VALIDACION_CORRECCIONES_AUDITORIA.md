# Validación en FBNeo de las correcciones de la auditoría externa (rama fix/defensa-fiable)

Condiciones: arcade, Iori (P1, bot) contra id34 (CPU), el mismo punto de reinicio (ranura 1,
guardado 2026-10-08 17:49), `DEFENSE_ONLY` + guardia preventiva, turbo ~4x, una sesión por
configuración. Logs: `logs/sesion_Iori_20261009_204502` (A), `20261010_110616` (B),
`20261010_111617` (C), con su `defensa_*.csv`.

| | A: antes (`--legacy-punish --legacy-escapes`) | B: corrección 1 (`--legacy-escapes`) | C: correcciones 1 y 2 |
|---|---|---|---|
| Minutos de juego | 28,8 | 38,5 | 40,9 |
| Rondas ganadas / perdidas / por tiempo | 16 / 1 / 11 | 17 / 0 / 18 | 12 / 0 / 23 |
| **Daño recibido por minuto (golpes)** | **65,5** | 54,0 | **49,3** |
| Raspado por minuto (especiales bloqueados) | 2,1 | 3,2 | 4,4 |
| Daño hecho por minuto | 109,4 | 103,7 | 110,4 |
| Ataques rivales evitados | 80% | 85% | 87% |
| Castigos intentados por minuto | 7,4 | 4,4 | 5,4 |
| **Castigos que hicieron daño** | **38%** | 74% | **81%** |
| **Golpes recibidos castigando, por minuto** | **1,39** | 0,05 | **0,00** |
| **Golpes recibidos durante un escape, por minuto** | **0,56** | 0,49 | **0,00** |
| Golpes recibidos atacando, por minuto | 0,42 | 0,10 | 0,07 |
| Acorralado al empezar un ataque rival | 16% | 17% | 19% |

Lectura:
- Corrección 1 (`_can_punish`): los golpes recibidos mientras castigaba pasan de 1,39 a 0,05 por
  minuto y el castigo acierta 74% en vez de 38%.
- Corrección 2 (`_threat_guard`): los golpes recibidos durante un reversal/rodada/backdash/salto
  pasan de 0,49 a 0 por minuto.
- Daño recibido por minuto: 65,5 → 54,0 → 49,3 (−25% en total); el daño hecho se mantiene.
- Costo: más rondas terminan por tiempo (11 → 23): Iori es más pasivo.

Limitaciones:
- Una sesión por configuración, contra un solo rival; el aprendizaje sigue activo entre sesiones
  (la tabla cambia de una sesión a la siguiente), lo que mezcla algo de efecto.
- "Castigar" sigue sin una señal de vulnerabilidad: ahora es "atacar cuando el ataque rival
  terminó", no un castigo garantizado.
- No mide el bloqueo alto/bajo de forma controlada ni los agarres: eso requiere
  `tools/guard_test.py` en modo versus (pendiente).

## Ofensiva estratégica (sesiones D y E, mismo id34, mismo punto de reinicio)

| | C: solo defensa | D: + ofensiva estratégica | E: ofensiva con 3 correcciones |
|---|---|---|---|
| Rondas KO / perdidas / por tiempo | 12 / 0 / 23 | 19 / 0 / 12 | **21 / 0 / 14** |
| Daño hecho por minuto | **110** | 84 | 101 |
| Daño recibido por minuto | **49** | 54 | 61 |
| Ataques rivales evitados | **87%** | 77% | 76% |
| Castigos con daño | 81% | 56% | 55% |
| Golpes "rival ataca \| guardia" | 23 | 54 | 65 |

Las 3 correcciones de E (pausa siempre en guardia, no pegar con el rival derribado, amague con
enfriamiento) subieron el daño hecho (84 → 101) y los KO, pero NO bajaron el daño recibido.
Los 65 golpes "rival ataca | guardia" de E: 53 "de pie", daño medio 9,6, 30 de ellos a distancia
~100, con Iori agachado en guardia el frame anterior. Es un ataque de pie de media distancia de
id34 que entra antes de que la guardia pase de agachada a de pie (3-5 frames). La ofensiva pasa
más tiempo a esa distancia (modo POKE 60-130) y por eso recibe más de esos golpes.
Sin saber qué movimiento es (byte de animación: pendiente) no se puede elegir la altura de la
guardia con certeza; cualquier ajuste aquí es específico de id34.
Decisión: la versión estable sigue siendo C (DEFENSE_ONLY + preventiva); E queda disponible con
`--mode=BALANCED_EXPERIMENTAL` como modo de ataque. El aprendizaje acumuló ~20k experiencias
entre A y E, así que las comparaciones no están limpias.
