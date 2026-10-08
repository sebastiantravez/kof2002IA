# prueba de juego kof2002IA — KOF AI Lab

Experimento: una app de Windows que controla sola a un personaje de
The King of Fighters 2002 en Fightcade 2 (emulador FBNeo).

> Úsalo solo en **Training / partidas locales u offline**. No contra jugadores
> reales en matchmaking: es injusto y te expone a sanciones de Fightcade.

## Fases

| Fase | Objetivo | Estado |
|---|---|---|
| 1 | Controles virtuales: mover, golpear y hacer especiales con timing por frames | **probado y funcionando** |
| 2 | "Ojos": leer la RAM del juego con un script Lua → vida, posición, altura, distancia | **funcionando** |
| 3 | Cerebro por reglas + aleatoriedad controlada según el estado | **funcionando** (`kof_ai/brain.py`) |
| 4 | Aprendizaje por refuerzo (recompensas por golpear, ganar, etc.) | **funcionando**, entrenando (`kof_ai/learning.py`) |
| 5 | Imitación de jugadores top (repeticiones de Fightcade grabadas con Lua) | **funcionando** (`kof_ai/imitation.py`) |
| 6 | Entrenamiento acelerado: control desde Lua, sin foco, partida guardada por ronda | **funcionando**, ~3,5-4x (`tools/train_fast.py`) |

## Entrenamiento acelerado (recomendado)

El bot controla a P1 desde dentro del emulador (`joypad.set`), con el juego sin límite de
velocidad y sin necesitar el foco: se puede usar la PC mientras entrena. Cada ronda que termina
(KO o más de 80 s) se reinicia al instante cargando la partida guardada al inicio de la ronda.

1. Arcade (no práctica) con tu personaje, en una pelea.
2. Cargar `lua\kof_train.lua` en el emulador (detener antes `kof_state.lua`).
3. `python tools\train_fast.py Kim 15` (personaje, minutos; `--normal` para mirar sin acelerar).

**Probar lo aprendido** (sin explorar y sin guardar, a velocidad normal):
`python tools\train_fast.py Kim 10 --play` para mirarlo contra la CPU, o
`python tools\train_fast.py Kim 10 --play --no-reset` para pelear tú contra él como P2.

Respalda lo aprendido en `backups\` antes de cada sesión y se detiene solo (restaurando el
respaldo) si en 1 minuto de juego no recibe ningún golpe, señal de que es el dummy de práctica.

## Defensa (estilo defensivo, Iori)

`config.json` → perfil → `"style": "defensive"` y `"reaction_frames"` (retraso de percepción
configurable). El bot se cubre alto/bajo según el rival, no suelta la guardia bajo presión,
castiga solo ataques largos/fallados, se defiende distinto acorralado y no usa el anti-aire
automáticamente. Cada sesión deja `logs\defensa_*.csv`; resumen acumulado por amenaza y por rival:
`python tools\defense_report.py Iori`. Agarres y proyectiles no se detectan en la RAM leída: se
reportan como "posible".

## Ofensiva estratégica (DEFENSIVE OFFENSE AI V2)

`config.json` → perfil → `"offense": "strategic"` (o `"off"` para la versión solo defensiva).
La defensa sigue teniendo prioridad: solo sin amenaza real el bot pasa a NEUTRAL y elige un modo
(APPROACH, POKE, PRESSURE, BAIT, RETREAT) según distancia, esquina, ventaja de vida y el modelo del
rival (saltos, agresividad, ataques bajos, golpes fallados, si se cubre mucho), con histéresis de
20 frames. Añade WHIFF_PUNISH (castiga corriendo un golpe fallado de lejos), un `passivity_score`
que empuja a hacer algo útil si se queda quieto, y penaliza las acciones arriesgadas. Entre
acciones solo se cubre si hay amenaza. Código en [kof_ai/strategy.py](kof_ai/strategy.py).

Comparar versiones: `python tools\train_fast.py Iori 15 --offense=off`, luego
`--offense=strategic`, y `python tools\compare_sessions.py Iori` (daño por ronda, defensa correcta,
castigos, ataques fallidos, ofensiva tras defensa, tiempo quieto y tiempo por estado).
Pruebas sin el juego: `python -m unittest discover tests`.

## Imitación de jugadores top

1. En Fightcade abre una repetición de un buen jugador y carga `lua\kof_record_turbo.lua`
   (graba ~9x más rápido; `kof_record.lua` a velocidad normal). Cada una va a `recordings\`.
2. `python tools\learn_from_replays.py` → combos reales por personaje, defensa y qué hacen en
   cada situación → `recordings\imitation.json`, que el cerebro usa automáticamente.
3. Verificar combos en práctica con `python tools\combo_lab.py <personaje>` (con `kof_state.lua`).

## Datos de la RAM (por jugador: P1 0x108100, P2 0x108300)

`+0x18` X, `+0x20` altura, `+0x24/+0x26` X/Y en pantalla, `+0x71` personaje (Kyo 0, Kim 6,
Choi 8, Iori 21), `+0xE0` bit0 atacando / bit2 agachado, `+0x139` vida (102), `+0x1E3` barras.
Detalles en [kof_ai/game_state.py](kof_ai/game_state.py).

## Requisitos

- Windows 10/11
- Python 3.12+ desde https://www.python.org/downloads/ (marca **"Add python.exe to PATH"** al instalar)
- Fightcade 2 con KOF 2002

En la Fase 1 no hace falta instalar paquetes: solo se usa la librería estándar.

## Configurar las teclas en FBNeo

La app manda pulsaciones de teclado. FBNeo tiene que tener el Jugador 1 mapeado a las mismas
teclas que `config.json`:

1. Abre KOF 2002 en Fightcade (Training / "Test game").
2. En el emulador: **Game → Map game inputs**.
3. Asigna al P1: flechas = direcciones, `A`=botón A, `S`=B, `D`=C, `F`=D.
   (O cambia `config.json` → `keys` para que coincida con tu mapeo actual.)

Tu Brook puede seguir conectada: FBNeo acepta teclado y joystick a la vez.

## Cargar la visión (Fase 2)

En el emulador: **Game → Lua Scripting → New Lua Script Window → Browse** →
`lua\kof_state.lua` → **Run**. Hay que hacerlo cada vez que abras el juego.

El script lee la RAM de la Neo Geo en cada frame (P1 en `0x108100`, P2 en `0x108300`) y la escribe
en `state.txt`; la app la muestra en "Visión en vivo". Offsets verificados en
[kof_ai/game_state.py](kof_ai/game_state.py). Si cambias de carpeta el proyecto, edita la ruta
`OUT` al inicio del script.

Se descartó la visión por imagen para las posiciones: la cámara se desplaza y hay espectadores en
los escenarios. `tools/snapshot.py` sigue disponible para guardar capturas.

## Ejecutar

```bash
cd "C:\Users\Sebas PC\Desktop\kof2002IA"
python app.py
```

1. Abre KOF 2002 en Fightcade y entra al modo práctica.
2. En la app pulsa **Buscar**: debe mostrar "● Emulador detectado".
3. Prueba **→** (el personaje camina) y **A** (golpea).
4. Prueba **Terry - Power Wave (236A)**.
5. Pulsa **ACTIVAR IA**: el personaje se mueve solo con acciones aleatorias ponderadas.
   Se detiene con **F8**, con el botón o si cambias de ventana.

La notación es la numérica de juegos de pelea (numpad: 2=abajo, 6=adelante, 236A = cuarto de
círculo + A). `2[45]8A` = mantener abajo 45 frames y luego arriba+A (carga).

## IA con reglas (Fase 3)

Elige "Con reglas", el personaje y pulsa **ACTIVAR IA**. El cerebro clasifica la situación
(rival lejos / media distancia / pegado / rival salta hacia mí / me golpearon / estoy en el aire)
y elige entre varias respuestas con pesos; lo que acaba de usar pierde peso para no repetir.
Si el rival salta cerca o te golpean, corta caminatas y esperas para reaccionar.

Los comandos de cada personaje están en `config.json` → `characters` (anti-aire, reversal,
especiales, combo). Verifícalos con la lista de movimientos de KOF 2002 y ajústalos ahí. Los
umbrales de distancia están al inicio de `kof_ai/brain.py`.

## Aprendizaje (Fase 4)

Modo **"Aprende"** en la app, o desde consola: `python tools/fight_test.py 300 Kyo learn`.

- Contexto = situación de las reglas + tramo de distancia (cada 40 unidades).
- Recompensa = daño hecho − 1,2 × daño recibido en los 40 frames siguientes a cada decisión.
- Elige con softmax sobre (peso de la regla + valor aprendido): lo que funciona sale más, pero
  nunca siempre.
- Se guarda en `learned_<personaje>.json` cada 30 s y al detener; se acumula entre sesiones.
  Botón **"Ver lo aprendido"** para inspeccionarlo. Borra el archivo para empezar de cero.
- Entrena mejor en arcade contra la CPU. Si pierde, pulsa Start para continuar: el bot espera
  sin pulsar nada fuera de la pelea y retoma solo.

**Importante:** la detección de pelea mira la pantalla (el reloj del centro arriba). No tapes esa
zona del emulador con otra ventana, tampoco con la propia app.

## Problemas comunes

- **No pasa nada al pulsar**: el mapeo de teclas no coincide o el emulador no tiene el foco.
- **Fightcade se ejecuta como administrador**: Windows bloquea el input de una app
  normal hacia una elevada. Ejecuta los dos con el mismo nivel.
- **Los especiales no salen**: sube `motion_step_frames` a 3 en `config.json`.

## Estructura

```
app.py              Interfaz (tkinter)
config.json         Teclas, FPS y timings
kof_ai/keyboard.py  Teclado virtual (SendInput con scancodes)
kof_ai/emulator.py  Detecta y da foco a la ventana de FBNeo
kof_ai/motions.py   Notación numérica → pasos por frame
kof_ai/bot.py       IA de Fase 1 (aleatoria ponderada)
kof_ai/game_state.py  Lee state.txt → vida, posición, altura, distancia
kof_ai/capture.py   Captura del área de juego (mss)
lua/kof_state.lua   Script del emulador que exporta la RAM de los jugadores
kof_ai/brain.py     Cerebro de reglas (Fase 3)
kof_ai/hud.py       Detecta por imagen si hay pelea (no pulsar botones en menús/continue)
tools/snapshot.py   Guarda capturas en captures/
tools/fight_test.py Prueba de pelea con métricas: python tools/fight_test.py 60 Kyo
kof_ai/learning.py  Aprendizaje por refuerzo (bandit contextual) → learned_<personaje>.json
kof_ai/imitation.py Ajusta decisiones y combos con lo que hacen jugadores reales
kof_ai/combo.py     Combos con confirmación de golpe ("2B>2A>214C")
kof_ai/lockstep.py  Conexión frame a frame con lua/kof_train.lua
lua/kof_train.lua   Entrenamiento acelerado (joypad.set, savestate, turbo)
lua/kof_record*.lua Grabación de repeticiones (normal / turbo)
tools/train_fast.py Entrenamiento acelerado
tools/learn_from_replays.py  Análisis de repeticiones grabadas
tools/combo_lab.py  Laboratorio de combos en modo práctica
tools/probe_*.py    Búsqueda de datos en la RAM
recordings/         Repeticiones grabadas (CSV) e imitation.json
```
