# Cambios de ChatGPT — defensa experimental

Rama: `mis-cambios-chatgpt` (main intacta).

## Primera iteración

- `kof_ai/brain.py`: no inferir recuperación del rival solo por antigüedad de la animación; el castigo exige comprobación conservadora de fin de ataque.
- Mientras el rival ataca cerca o mantiene presión, seleccionar guardia en lugar de rodadas, backdash o reversals aleatorios.
- Tras recibir daño, preferir guardia sin iniciar escapes aleatorios.
- En `DEFENSE_ONLY`, limitar el castigo confirmado a un golpe corto.
- `tests/test_defense_regression.py`: prueba adicional de regresión para el castigo prematuro.

## Validación pendiente

Estas modificaciones se subieron mediante GitHub y **no se han ejecutado ni probado dentro de Fightcade/FBNeo** después de la publicación. La prueba añadida debe ejecutarse en Windows junto con la suite completa.

No se han corregido aún la detección de agarres, clasificación de golpes bajos/overheads ni los timings de combos.

## V2: Iori agresivo-controlado (sesion id30, 2026-10-09)

Referencia: 4 ganadas / 4 perdidas / 4 otras; 71 ataques con dano y 227 fallidos;
16 intentos de combo y 2 completos; 63% del tiempo en DEFEND.
La mejora es experimental: requiere validar en FBNeo y comparar contra el mismo rival.

- `kof_ai/arbiter.py`: permitir propuestas estrategicas cuando la defensa clasifica
  `acorralado` sin amenaza. Las amenazas duras conservan prioridad absoluta.
- `kof_ai/strategy.py`: evitar retroceso/backdash contra la pared, reducir BAIT,
  preferir pasos cortos, no presionar con 2B fuera de su rango, y evitar combos
  largos sin confirmacion de impacto (la RAM no expone hitstun confirmado).
- `kof_ai/brain.py`: favorecer castigo corto 2B sobre C segun resultados de la
  sesion de referencia (17/26 vs 15/30, respectivamente).
- `tests/test_strategy.py`: regresiones de esquina, amenaza y rango de combo.

Para comparar sin alterar el aprendizaje, repetir:
```bat
python -m unittest discover tests
python tools\train_fast.py Iori 10 --play --mode=BALANCED_EXPERIMENTAL --offense=strategic --reuse-save
```
No cambiar `main`. No asumir mejora hasta ver los nuevos registros.
