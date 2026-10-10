# V2 de Iori: validación local (10 de octubre de 2026)

La carpeta local fue vinculada al historial de `mis-cambios-chatgpt`, cuyo
commit remoto era `e3a0e1895e4a6fc3248f52a819061a696df3e6ae`. Se conservaron
los archivos locales al crear el índice Git. Los cinco archivos pendientes de
V2 se respaldaron en `backups/antes_V2_20261010_113416/` antes de actualizarlos:
`kof_ai/arbiter.py`, `kof_ai/brain.py`, `kof_ai/strategy.py`,
`tests/test_strategy.py` y `CAMBIOS_CHATGPT.md`.

## Pruebas

Comando: `python -m unittest discover tests`.

- Antes de V2: 79 pruebas, 77 aprobadas y 2 omitidas.
- Después de V2: 83 pruebas, 81 aprobadas y 2 omitidas; sin errores.
- Las omisiones son `test_long_attack_is_punished` en los modos
  `BalancedExperimental` y `DefenseWithPunish`: esa prueba del castigo original
  corresponde a `DEFENSE_ONLY`; la clase `SafePunish` verifica los otros modos.

Esto valida las regresiones unitarias, no el comportamiento en Fightcade/FBNeo.
Los datos aprendidos, los registros y el `ROOT` local de Lua se preservaron.

## Preparación de la comparación offline

1. Abrir KOF 2002 Magic Plus en Arcade, Iori como P1 contra la CPU.
2. Ejecutar únicamente `lua/kof_train.lua` en la ventana Lua del emulador.
3. Mantener disponible el mismo savestate usado en la referencia. El JSON
   `logs/punto_reinicio.json` identifica Iori contra `id30`, guardado el
   9 de octubre de 2026 a las 21:02:27; el JSON por sí solo no garantiza que
   el emulador conserve el savestate correspondiente.
4. Ejecutar desde la raíz:

```bat
python tools\train_fast.py Iori 10 --play --mode=BALANCED_EXPERIMENTAL --offense=strategic --reuse-save --rival=id30
```

`--rival=id30` verifica el rival después de cargar el punto de reinicio.
`--play` evita guardar modificaciones del aprendizaje; sí genera diagnósticos.
Para terminar antes de tiempo, crear `logs/STOP`.

Registrar daño, ataques con daño/fallidos, combos completos, defensa y pasividad.
Conservar separadas las 4 rondas ganadas, 4 perdidas y 4 otras de la referencia.
No se ejecutó una sesión nueva de 10 minutos durante esta validación.

## Limitaciones de las métricas

El resumen principal de terminal usa los contadores de `RuleBrain`; el JSON
usa `DefenseLogger.metrics()`. El cerebro separa `taken_total` y `chip_total`,
mientras que el logger incluye el raspado en `taken` y también lo informa
en `chip`. Por ello las cifras de daño recibido no significan lo mismo.

La referencia muestra 759 de golpes + 130 de raspado en terminal (889 total),
frente a 825 en el JSON. También muestra 669 frente a 649 de daño hecho.
La separación del raspado no explica toda la diferencia. Los observadores
recorren el estado en puntos distintos: el logger recibe cada paso del enlace,
y el cerebro contabiliza al consultar su estado. Falta una reproducción con
traza por frame para atribuir y corregir las diferencias restantes.

Además, `tools/compare_sessions.py` excluye actualmente los JSON con
`modo_prueba: true`, incluido el de referencia. No usar ese comando para
afirmar una comparación de las sesiones `--play` sin corregir primero el filtro.
Las métricas históricas se conservan tal como fueron generadas.
