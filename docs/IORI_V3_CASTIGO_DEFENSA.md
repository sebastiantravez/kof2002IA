# Iori V3 experimental: castigo, presión y defensa

Referencia local: sesión `20261010_114159`, Iori contra CPU `id10`, 10 minutos.
7 ganadas, 0 perdidas, 1 otra; 84 ataques con daño y 482 fallidos; 22 intentos
de combo sin completar; defensa correcta estimada 66,2%. No comparar directamente
con `id30`: son rivales diferentes.

El CSV registra 14 castigos 2B con éxito y ninguno fallido; C registra 5 con éxito
y 2 fallidos; correr + 2B registra 4 con éxito y 3 fallidos. En 11 golpes recibidos
la acción al impacto era `combo corto 2B`. Esto orienta cambios, no prueba que cada
acción sea la causa del golpe: los registros son observaciones heurísticas.

## Cambios

- `strategy.py`: mayor peso al acercamiento en rango de poke, menos guardia neutral
  y retroceso/backdash solo ante un modelo de rival muy agresivo. Sustituir
  `2B>2A` en neutral por C cercano: esa ruta no completó ningún combo en la sesión.
  Conservar 2B, agarres y presión de cerca. Revalidar rangos aunque la histéresis
  mantenga el modo anterior. Las amenazas reales conservan la prioridad.
- `brain.py`: esperar confirmación del fin de un golpe fallado, incluyendo que
  ambos estén en el suelo. En rango, castigar con normal; fuera del rango de
  barrida, acercarse con un paso interrumpible y volver a decidir. Eliminar
  correr una distancia fija y lanzar 2B a ciegas. En castigo confirmado de cerca,
  ofrecer `C>623C` únicamente en BALANCED_EXPERIMENTAL y si la ruta figura en el
  perfil. El especial requiere confirmación de impacto del C; no se añade al neutral.
- `bot.py`: reajustar guardia cada frame, incluyendo cambio de lado y altura;
  interrumpir combos experimentales ante urgencia defensiva. Un castigo disponible
  sigue cortando la espera de guardia. No se modifica la clasificación de bajos ni
  se promete distinguir overheads: la RAM disponible no lo permite con certeza.
- `defense_log.py`: contar C cercano como ataque para conservar el diagnóstico.
- `bot.py` y `train_fast.py`: impedir el guardado final del aprendizaje en `--play`.
  Antes, desactivar el guardado periódico no evitaba el `_save()` del cierre.
  No se restauran ni borran los datos locales existentes.
- `lockstep.py`: avisar al logger también en el intercambio que provoca KO.
  Antes `_resetting` omitía ese intercambio, perdiendo el daño final. El logger
  continúa descartando el incremento de vida al recargar. Una regresión reproduce
  un KO con 12 de daño y comprueba que se registra exactamente una vez.

## Validación y siguiente sesión

`python -m unittest discover tests`: 95 pruebas, 93 aprobadas y 2 omisiones
intencionales. Compilación Python de los módulos de combate y runner correcta.
Pruebas nuevas: confirmación de whiff, reinicio de ataque, rango de castigo/combo,
histéresis fuera de rango, guardia por frame, interrupción para castigo, cierre sin
guardar en `--play` y daño en KO.

Estos cambios todavía no se han validado jugando en Fightcade. La guardia por
frame puede aumentar el coste de comunicación: comprobar fps y daño recibido.
La pérdida de daño en KO explica una causa concreta de divergencia; no permite
reconstruir con certeza los 78 puntos de diferencia histórica sin traza completa.

Con Arcade offline, Iori P1 y el mismo savestate de la sesión contra `id10`:

```bat
python tools\train_fast.py Iori 10 --play --mode=BALANCED_EXPERIMENTAL --offense=strategic --reuse-save --rival=id10
python tools\compare_sessions.py Iori id10 --play --by-session
```

Evaluar daño hecho/recibido (incluido raspado), porcentaje de ataques con daño,
castigos exitosos, combos completos, defensa y pasividad. El logger ahora cuenta
golpes finales de KO: una subida del daño hecho respecto a registros viejos puede
deberse parcialmente a esta corrección de medición. Revisar también el diagnóstico
del cerebro. Mantener registros anteriores sin modificarlos.
