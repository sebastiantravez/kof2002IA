# Iori Speed Lab — medición manual y ensayo de movimiento

Estado: observadores de lectura y **ensayo experimental de movimiento**.
El ensayo cambia temporalmente D0 durante una suma de movimiento verificada,
con restauración inmediata; su estabilidad real requiere validación manual.
No hay modificador directo de RAM/ROM ni mejoras de inicio/recuperación.
El joystick y los botones siguen bajo control del jugador. Este laboratorio no
importa el bot, no manda entradas, no cambia la velocidad global, no carga partidas
guardadas, no modifica RAM y no toca ROM/configuración de Fightcade.

## Investigación realizada

El [motor Lua de Fightcade FBNeo](https://github.com/fightcadeorg/fightcade-fbneo/blob/master/src/burner/luaengine.cpp)
expone `memory.writebyte`, `memory.writeword`, `joypad.get` y callbacks de frame.
Eso permite investigar RAM; **no verifica el significado ni la reversibilidad de
un parámetro de KOF**. El script registra disponibilidad de escritura sin invocarla.
Si existe `emu.isonline`, rechaza su ejecución cuando indica modo online. En versiones
sin esa API, el usuario debe garantizar el entorno offline; no se afirma detección
automática universal del modo de partida. Algunas implementaciones de
`emu.isonline()` retornan cero resultados Lua cuando el estado es falso: Lua recibe
`nil`. Ese caso se informa como desconocido y no bloquea la captura de solo lectura;
el usuario debe ejecutar Test Game offline. Un retorno online explícito sigue
bloqueándose. No se usa esta API para autorizar escrituras: no existe modificador.

Offsets ya usados para lectura en el proyecto, respecto a P1 `0x108100` y
P2 `0x108300`: X `+0x18`, altura `+0x20`, coordenadas de pantalla `+0x24/+0x26`,
personaje `+0x71`, flags `+0xE0`, vida `+0x139`. Estos no se consideran parámetros
escribibles. El bit de ataque incluye arranque, actividad y recuperación: no
sirve para separar esas fases. No se ha identificado velocidad fija/fraccionaria,
contador de animación, estado accionable ni caja activa verificados para esta ROM.

No se necesita parche de ROM para leer RAM. Todavía no se sabe si las mejoras
pueden hacerse únicamente con RAM o si requerirían editar tablas/código en una
copia de la ROM. Nunca sumar X por frame para fingir velocidad: eso puede alterar
colisiones, cámara, posición secundaria y empuje. No saltar frames de animación
sin verificar hitboxes, cancelaciones y sincronización de estado.

`settings.lua` registra objetivos +5% caminar, +8% correr y -1 frame de arranque/
recuperación. Son objetivos, **no parámetros activos**. Activar
`modifications_enabled` provoca un error; no existe un modificador aprobado.
Activar/desactivar captura sí está disponible. Los observadores no escriben RAM
ni registros. El ensayo separado al final de esta guía respalda/restaura D0;
`modifications_enabled` no lo activa. Una modificación directa de RAM necesitaría respaldar el valor real,
verificar su restauración y abortar ante cambios de personaje/ROM/estado.

## Cómo medir en Windows

1. Detener el runner de Python con F8 y esperar su salida. Detener todas las
   ventanas Lua, especialmente `kof_train.lua`, grabadores y training mode con
   funciones automáticas. No ejecutar `train_fast.py` durante este experimento.
2. Abrir un test offline/práctica con Iori P1 y adversario quieto. Velocidad normal;
   misma posición, rival, escenario y lado para cada ensayo. La captura requiere
   driver `kf2k2pls`; otra variante se rechaza hasta verificar sus offsets.
3. Desde la raíz del repositorio:

```powershell
python experiments\iori_speed_lab\analyze.py label idle
```

Esto crea la carpeta local de capturas. En Game > Lua Scripting cargar
`experiments\iori_speed_lab\capture.lua` y Run. Revisar que imprima READ ONLY.
Las rutas están en `capture.lua` y `settings.lua`, separadas del ROOT del bot.

4. Grabar reposo unos 3 segundos. Seleccionar una etiqueta y realizar únicamente
   esa acción con el joystick. Las etiquetas no se deducen automáticamente:

```powershell
python experiments\iori_speed_lab\analyze.py label walk
python experiments\iori_speed_lab\analyze.py label run
python experiments\iori_speed_lab\analyze.py label normal_A
```

Caminar/correr repetidamente por la parte central del escenario sin golpear,
recibir daño ni chocar con el rival. Usar ambos lados y al menos 5 recorridos de
100 unidades, recolocándose entre ellos. Grabar caminar y correr en capturas
separadas facilita el control. Para normales, hacer un golpe aislado por vez,
esperando vuelta a reposo; repetir 10 veces por botón. Probar también B/C/D.
Al cambiar de acción, dejar un breve intervalo: la etiqueta se revisa cada 10 frames.

5. Medir throughput mientras el juego corre sin pausas, con y sin captura para
   comparar el coste de instrumentación (el monitor requiere el script activo):

```powershell
python experiments\iori_speed_lab\analyze.py fps --seconds 20
python experiments\iori_speed_lab\analyze.py label idle --off
python experiments\iori_speed_lab\analyze.py fps --seconds 20
```

`--off` detiene el volcado de RAM, pero mantiene el heartbeat de medición. Stop
en Lua cierra el CSV. Analizar el archivo generado, usando su nombre real:

```powershell
python experiments\iori_speed_lab\analyze.py report experiments\iori_speed_lab\captures\baseline_FECHA_HORA.csv --distance 100
```

No arrancar nuevamente en el mismo segundo: los nombres únicos evitan sobrescribir
capturas. La instrumentación puede perder el último segundo si el proceso se cierra
bruscamente, porque se vacía el búfer cada 60 callbacks.

## Qué se mide y qué falta

| Variable | Medición actual | Validación que falta |
|---|---|---|
| Caminar/correr | X por frame y tiempo de recorridos de 100 unidades; media de frames en movimiento | Etiquetas manuales correctas, despeje, aceleración inicial y repetición en ambos lados |
| Entrada | Botones observados antes/después del frame y demora hasta bit de ataque | Momento de muestreo de la versión local; no es latencia física |
| Arranque | No reportado | Primer frame con hitbox activa, comparado con frame de aceptación del input |
| Recuperación | No reportada | Último activo y primer frame en que otro input es aceptado; verificar manualmente por frame |
| FPS | Frames del emulador por tiempo monotónico externo | Frame pacing/renderizado; comparar sin captura; no demuestra latencia del monitor |

La posición X entera puede ocultar movimiento fraccionario: promediar recorridos
largos en vez de interpretar diferencias de un solo frame. Rechazar muestras con
ataques, saltos, daños, límites del escenario o discontinuidades. No se puede
rechazar automáticamente todo empuje/collision: controlar eso durante el ensayo.
El objetivo de 60 FPS es nominal; KOF/Neo Geo usa aproximadamente 59,19 según
la configuración del proyecto. No forzar 60 ni confundir turbo con menor latencia.

## Latencia del emulador

Lectura local: `fcadefbneo.exe` informa versión 0.2.97.44, `bVidVSync=0`,
`bVidDWMSync=0`, `nVidSelect=4`, audio seleccionado 0 y 6 segmentos.
No se modificó ninguna opción. El valor de segmentos por sí solo no determina
la latencia del botón; hay que medir el camino completo.
Para medir input-to-photon, filmar a alta velocidad el botón/indicador del joystick
y la primera respuesta visible, repetir 20 veces y calcular mediana/dispersión.
Alternar una sola opción de presentación/audio por vez en una configuración
respaldada; comprobar tirones, tearing y estabilidad. Lua no ve el instante de
contacto eléctrico ni el panel, por lo que no puede medir esa latencia por sí sola.

El [runahead documentado por Libretro](https://docs.libretro.com/library/fbneo/)
pertenece al core usado con RetroArch. No se asume que sus opciones existan en
el ejecutable de Fightcade ni se aplica una configuración de otro frontend.

## Criterio para habilitar escritura en una fase futura

Guardar captura base manual, identificar candidato de velocidad/animación mediante
trazas completas, comprobar ancho, signo, fracción y propietario del valor. Verificar
correlación en reposo/caminar/correr/saltar/ataque/daño/esquinas. Luego, en una instancia
offline aislada y con respaldo del estado/ROM si corresponde, probar una modificación
mínima y su restauración, frame a frame. Confirmar desplazamiento natural, colisiones,
cámara y que el rival no cambia. Probar izquierda/derecha, cambio de lado, bloqueo,
combos y transiciones. Solo después permitir +5%/+8% o -1 frame. No mantener una
escritura constante en una dirección de significado desconocido.

## Pruebas automatizadas

`python -m unittest discover tests` cubre análisis de velocidad, recorridos,
exclusión de saltos/daños/reset y separación de proxies de arranque/latencia real.
Incluye prueba opcional del script con Lua simulado que falla ante escrituras o
inyección de botones. En este equipo la DLL Lua es de 32 bits y Python de 64 bits:
esa prueba se omite por incompatibilidad; ejecutar el script en FBNeo aún requiere
validación manual. Las capturas manuales y sus resultados están documentados en
`FINDINGS_20261010.md`.

## Traza de accesos del 68000: siguiente fase de solo lectura

`trace_access.lua` registra accesos a X y los candidatos +0x44/+0x50, con PC,
PPC, D0/D1, A0/A1/A3/A4 y seis palabras de código a partir de PPC. Usa las APIs de
observación documentadas en el código de Fightcade FBNeo; su funcionamiento en
el ejecutable local requiere una ejecución manual. No interpreta automáticamente
instrucciones ni demuestra causalidad antes de examinar el resultado.

1. En Test Game offline, tener a Iori como P1 en la pelea. Detener todas las otras
   ventanas Lua y el runner del bot.
2. Cargar `experiments\iori_speed_lab\trace_access.lua` en la ventana Lua y Run.
3. Volver a la ventana del juego. Durante unos 30 segundos, caminar brevemente y luego correr hacia delante,
   con el rival lejos. Iori conserva tus controles y su velocidad original.
4. Esperar `TRACE FINISHED`. La captura termina a los 1.800 frames o 60.000 eventos;
   el límite de eventos puede producir una traza parcial. Stop también cierra el CSV.
5. El resultado está en `captures/access_FECHA_HORA.csv`. Cero eventos significa
   que no se ha confirmado soporte de hooks, no ausencia de accesos del juego.

Los hooks observan escrituras del juego: el script no escribe memoria. En el código
consultado, el hook de escritura precede la escritura y el valor de un hook de
lectura es cero; no interpretarlo como el contenido leído. PC/PPC necesitan validar
su alineación con la instrucción responsable. Las palabras de código se leen al
final del frame y podrían no reflejar código RAM modificado durante el frame.
Esta instrumentación puede ralentizar la emulación; no usarla para medir FPS o
latencia base. El script retira sus hooks al finalizar y no debe ejecutarse junto
con otro observador. No se modifica ROM, RAM, registros CPU o botones.

## Comprobar el momento de ejecución

La siguiente sonda es `probe_execution.lua`, también de solo lectura. Cargarla
sola en lugar de `trace_access.lua`, con Iori P1 en Test Game offline. Pulsar Run,
volver al juego y caminar/correr hacia delante durante unos 30 segundos.
Termina con `PROBE FINISHED` y produce `captures/execution_FECHA_HORA.csv`.

Comprueba primero las palabras exactas de seis instrucciones identificadas en
las trazas locales. Si difieren, se detiene antes de instalar hooks. Observa los
puntos que cargan +0x50 en D0 y los que suman D0 a X; registra PC, PPC, A4, D0,
X fraccionaria, velocidad, personaje, vida, altura, flag de ataque y dos palabras
de estado. Esas palabras no se interpretan como estados semánticos verificados.
No usa hooks de lectura/escritura simultáneos ni modifica registros CPU.

La comprobación esperada es PC igual al punto observado, D0 igual a +0x50 en
el punto de suma, y X todavía sin la suma entre los dos puntos de un mismo
frame. Una discrepancia impide asumir que el hook se ejecuta antes de la
instrucción. Se debe contrastar con vida, altura y flags para separar transiciones.
Los tests simulan ese orden: no demuestran el orden del ejecutable local.

Todavía no existe una prueba real de modificación/restauración. Esta sonda
prepara esa decisión, no activa +5%/+8%. No repetir capturas generales si esta
sonda ya cubre los puntos: analizar el archivo de ejecución.

## Ensayo de mejora de movimiento (experimental)

`speed_trial.lua` cambia D0 solo en tres sumas de P1 verificadas y lo restaura
en el hook de la instrucción siguiente. No escribe +0x50 ni tablas compartidas:
la referencia de velocidad permanece original. Filtra personaje Iori, vida,
suelo, flags de ataque, firmas observadas, PC, A4, D0 y velocidad. Conserva
las correcciones de posición posteriores. La caminata en ambos sentidos y
la carrera hacia izquierda están cubiertas; la carrera positiva sigue sin
validarse y queda excluida de este ensayo.

Primera ejecución, +1% para comprobar modificación/desactivación:

1. Abrir Test Game offline, Iori P1 a la derecha de un rival quieto y alejado.
   Detener todos los otros scripts Lua y cualquier runner del bot.
2. En PowerShell, desde la raíz del proyecto:

```powershell
python experiments\iori_speed_lab\trial.py arm --offline
```

3. Dentro de los siguientes 120 segundos, cargar
   `experiments\iori_speed_lab\speed_trial.lua` y Run. La declaración offline
   se consume: cada ejecución necesita armarse de nuevo. Esta declaración
   confirma el entorno elegido por el usuario; no es detección infalible de red.
   Un resultado online explícito de la API bloquea el ensayo.
4. Volver al juego, caminar y correr hacia delante a la izquierda durante
   unos 45 segundos. Repetir movimientos similares en las tres fases:
   REFERENCIA (15 s), MEJORA ACTIVA (15 s), DESACTIVADO/COMPARACIÓN (15 s).
   Si la API gráfica está disponible, la fase aparece sobre el juego.
5. Esperar `TRIAL FINISHED`. El CSV `captures/trial_FECHA_HORA.csv` contiene
   original/aplicado, X antes/después de cada suma, +0x50 y D0 restaurado.

El 1% inicial puede ser apenas perceptible: se comprueba numéricamente antes
de aumentar factores. Objetivos posteriores, solo después de validar el ensayo:

```powershell
python experiments\iori_speed_lab\trial.py arm --offline --walk 1.05 --run 1.08
```

Para desactivar antes de finalizar, pulsar Stop en Lua o ejecutar:

```powershell
python experiments\iori_speed_lab\trial.py off
```

Stop retira los hooks; el comando se procesa al final del siguiente frame.
La desactivación devuelve futuros movimientos a su operando original, no a
la posición donde empezó Iori. No se guardan/cargan estados ni se restauran
posiciones por escritura. Si aparece `FAILED` o `UNRESOLVED ADD`, el ensayo
no está validado; detenerlo y reiniciar el test offline para no continuar con
un estado CPU incierto. No intentar restaurar registros antiguos fuera de
la instrucción a la que pertenecían.

La suma exacta y restauración se verifican en cada intervención. Eso no prueba
por sí solo animaciones, colisiones, cámara, combos, P2 o estabilidad de FPS.
Requieren observación y capturas de contexto adicionales. No cambiar ataques,
saltos ni recuperación en este ensayo. No ejecutar en partidas online.
