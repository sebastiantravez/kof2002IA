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
