# Auditoría de defensa V4 — Iori (2026-10-07)

Solo hechos comprobados en el código o en los registros. Lo no comprobado se marca **SIN EVIDENCIA**.
Registros usados: `logs/defensa_Iori_20261007_203716.csv` (Chin, DEFENSE_ONLY, 53,7 min de juego)
y `logs/defensa_Iori_20261007_210917.csv` (Athena, DEFENSE_WITH_PUNISH, 8,9 min).

## 1. Qué información existe realmente

`lua/kof_train.lua` envía 13 bytes por jugador y frame (`OFFSETS`): x, altura, x/y en pantalla,
personaje (+0x71), +0x73, +0xE0, vida (+0x139), barras (+0x1E3). Nada más.

| Señal | Origen | Fiabilidad |
|---|---|---|
| Posición, altura (en el aire), vida, barras | RAM verificada | buena |
| Rival atacando | +0xE0 bit0 | cubre toda la animación, incluida la recuperación |
| Rival agachado | +0xE0 bit2 | **corregido (sección 4): también se enciende en ataques agachados, 74–87% desde el primer frame** |
| Ataque bajo | inferido del bit de agachado | **corregido (sección 4): sí detecta el 2B/2D directo desde de pie (87%)** |
| Overhead | no existe señal | todo golpe de pie se trata igual |
| Agarre recibido | +0x73 bit1 desactivado por falsos positivos (`THROWN_OFFSET = None`) | **no hay detección** |
| Proyectiles | no existe señal | — |
| Orientación | calculada: `me.x <= rival.x` (`game_state.py`) | **no es la orientación real del juego**; en cruces puede diferir — SIN EVIDENCIA de cuánto |
| Bloqueo exitoso / blockstun | no existe señal | solo se infiere por "no perdió vida" |
| Qué movimiento hace el rival | no existe señal | — |

## 2. Hallazgos con evidencia

### H1 — (CORREGIDO en la sección 4) La guardia baja casi nunca se activa
- Código: `RuleBrain.guard_low()` → abajo solo si el rival está agachado quieto, o si su ataque
  empezó ≤4 frames después de estar agachado quieto. En cualquier otro caso: guardia de pie.
- Datos (Chin): de 930 ataques rivales cercanos, solo **29** se clasificaron "bajo"; 869 como
  "de pie/overhead". Con guardia de pie recibió **117** golpes; con guardia abajo, 26.
- Consecuencia: un golpe bajo que la CPU lanza sin agacharse antes se bloquea de pie y entra.
  No se puede contar cuántos de esos 117 eran bajos: **no hay señal en la RAM leída** (H5).
- En KOF la guardia agachada (abajo-atrás) cubre todo salvo overheads y ataques aéreos; la guardia
  de pie pierde ante cualquier bajo. Hoy el bot usa por defecto la que pierde ante lo más común.

### H2 — Más de la mitad de los golpes llegan sin guardia
- Datos (Chin): de 304 golpes "de pie/overhead", la tecla dominante durante el ataque fue:
  ninguna 118, atacando 23, moviéndose 20 → **161 (53%) sin guardia**.
- Acción del bot cuando empezó ese ataque: "presión del rival / guardia" 26, "castigar / combo DM" 20,
  "media distancia / caminar adelante" 16, "media distancia / guardia" 16, "rival lejos / caminar" 14,
  "pegado / combo DM" 9.
- Hechos de código que lo explican en parte:
  - Las acciones no interrumpibles (combos, DM, pokes, saltos) se ejecutan completas aunque el
    rival ataque (`bot._tick`: solo las `interruptible` se cortan con `urgent()`).
  - Entre acciones, si la distancia es >180 la pausa es neutral, sin guardia.
  - Las opciones "esperar" (`5[n]`) y los pasos neutrales de "4 5 4"/"6 5 6" no pulsan nada.
- **SIN EVIDENCIA**: por qué aparece "ninguna tecla" incluso cuando la acción elegida era "guardia".
  El registro solo guarda la tecla dominante por evento, no frame a frame. Hace falta la traza
  por frame (experimento E2).

### H3 — Agarres: no se detectan ni se escapan
- Datos (Chin): **116** golpes sin ataque visible a ≤35 de distancia (compatible con agarre,
  no demostrado). Guardia en esos golpes: ninguna 52, de pie 43.
- El escape de agarre ("me agarran" → `4CD`) depende de `me.thrown`, que está desactivado:
  **hoy nunca se ejecuta**.
- No hay datos de qué agarres tiene cada rival ni cuáles se pueden romper en esta ROM.

### H4 — Latencia de percepción y respuesta (por código)
- `kof_train.lua` usa `emu.registerbefore`: en el frame N publica la RAM del frame N-1 y aplica las
  teclas de Python al frame N. Mínimo: el input llega 1 frame después de que el bit de ataque
  aparece en la RAM.
- Python solo ve un estado por intercambio: cada 2 frames si vigila algo (`WATCH_CHUNK`) y cada 8
  si no (`FREE_CHUNK`, solo en esperas sin vigilancia). Durante guardias y acciones vigiladas
  el peor caso es +1 frame.
- La guardia reevalúa alto/bajo cada 2 frames.
- **SIN EVIDENCIA**: en qué frame del ataque se enciende el bit +0xE0 respecto al primer frame
  activo del golpe. Si se enciende tarde, ninguna latencia del bot basta. Se mide en E2.

### H5 — Faltan señales en la RAM leída
Bajo, overhead, agarre, bloqueo y orientación real no están en los 13 bytes. Los 0x200 bytes de
cada estructura no se han explorado para eso. Es la causa raíz de H1 y H3.

### H6 — "La ofensiva empeoró la defensa": no hay evidencia
- La ofensiva estratégica nunca se ejecutó en el juego.
- `DEFENSE_ONLY` decide igual que la defensa original: 0 diferencias en 120.000 estados (prueba de
  equivalencia contra la rama `respaldo/v2-ofensiva-estrategica`).
- La diferencia observada viene del rival: contra Chin, 109 de daño recibido por minuto; contra el
  id27 de la sesión buena, 54.

### H7 — Hilos y conflictos de inputs
- En el entrenamiento solo el hilo del bot escribe las teclas (`link.keys`); el hilo principal solo
  duerme y lee estadísticas. No hay dos escritores.
- `play()` suelta todas las teclas al terminar cada acción, pero en lockstep no avanza ningún frame
  entre ese "soltar" y la siguiente orden: no hay frames sin guardia por eso.
- La diagonal abajo-atrás se envía en el mismo frame (`{"down","left"}` → `joypad.set` con las dos
  a la vez); no son dos pulsaciones separadas.
- La dirección "atrás" se calcula con la orientación inferida (H5).

## 3. Experimentos necesarios (antes de cambiar la defensa)

| Id | Qué | Cómo | Necesita |
|---|---|---|---|
| E1 | Buscar en la RAM: ataque agachado, overhead, orientación real, agarrado, en guardia/blockstun | Volcar las estructuras completas (2 × 0x200 bytes) por frame junto con los inputs de ambos jugadores (`joypad.get`) en una pelea controlada; los inputs del humano son la etiqueta (p. ej. abajo+B = bajo) | Tú en P2 con tu Brook |
| E2 | Prueba controlada de bloqueo bajo y alto | Iori solo se defiende; tú haces 2B/2D repetidos, luego overhead (6A en muchos personajes), mezclas bajo→alto, saltos; desde los dos lados. Traza por frame: bits del rival, teclas enviadas, vida → bloqueado o golpeado; latencia bit→tecla→resultado | Tú en P2 |
| E3 | Agarres | Tú agarras a Iori repetidamente (agarres normales C y D, de los dos lados) para encontrar la señal y medir la ventana real de escape con el mismo botón | Tú en P2 |

Con E1–E3 se corrigen H1, H3 y H5 con datos. La regla de guardia por defecto (H1) se cambia solo
después de E2, comparando bloqueos con la regla actual y la nueva sobre la misma traza.

## 4. Mediciones con grabaciones del usuario (2026-10-08)

Datos: 6 grabaciones propias (`recordings/rec_20261008_*`: práctica con Iori/Kim/Kyo/Choi/Rugal y dos
repeticiones online), ~60 min de juego, con inputs de los dos jugadores y la memoria completa por frame.
Herramientas: `tools/analyze_my_play.py --ram` y los scripts de medición descritos abajo.

### Corrección de H1: el bit de agachado SÍ marca los ataques agachados
`+0x0E0 bit2` frame a frame alrededor del inicio del ataque (frame 0 = primer frame con el bit de
ataque; la etiqueta sale de los inputs del jugador):

| Grupo | casos | frame −1 | frame 0 | frame 5 | frame 10 |
|---|---|---|---|---|---|
| Ataque agachado, ya agachado antes | 450 | 53% | 74% | 74% | 67% |
| Ataque agachado directo desde de pie | 78 | 66% | 87% | 87% | 79% |
| Ataque de pie | 485 | 3% | 1% | 1% | 2% |

La afirmación anterior ("el bit se apaga durante el ataque agachado") era falsa. El resto (~13–26%)
es compatible con etiquetas imperfectas: un especial con `623`/`236` pasa por abajo-adelante y se
cuenta como "agachado" sin serlo. `guard_low()` ya usa este bit, así que el bot SÍ puede ver los
ataques agachados a tiempo. Ojo: "agachado" no es lo mismo que "bajo" (algunos puños agachados se
cubren de pie), pero la guardia agachada cubre ambos. Contra Chin solo 29 de 930 ataques fueron
agachados: allí los golpes bajos no eran el problema principal.

### H4 medido: el bit de ataque llega con poco margen
- De la pulsación del botón al encendido del bit de ataque: **4 frames** en 105 de 131 casos.
- Del encendido del bit al impacto (primer golpe de cada intercambio, 208 casos): **3 frames 22%,
  ≤4 frames 48%, ≤5 frames 61%**.
- El bot aplica su input 1 frame después de ver el bit (2 si está en una espera vigilada). Si en
  ese momento ya está en guardia o libre, llega justo; si está atacando, caminando sin cortar, o en
  la recuperación de su propio golpe, **no llega**.
- Conclusión con datos: reaccionar al bit de ataque solo sirve si Iori ya está libre para cubrirse.
  La guardia tiene que ser preventiva cuando el rival está en rango, no una reacción; y las acciones
  no interrumpibles cerca del rival son las que dejan los huecos (H2).

### Sin señal todavía
- Bloqueo/blockstun: la etiqueta "sostiene atrás y no pierde vida" es demasiado amplia; los bits
  con mayor separación dependían del personaje (artefacto). Hace falta etiquetar golpes realmente
  bloqueados (el rival conecta a distancia corta y la vida no baja).
- Agarres: sin datos etiquetados.

### Corrección de medición: el raspado de especiales bloqueados se contaba como golpe
Sesión de diagnóstico contra id34 (2026-10-08) con lo que pasaba en el frame del impacto: de 99
"golpes aéreos", 84 llegaron con Iori sosteniendo atrás, sin cruce (98 de 99) y con el rival a punto
de aterrizar; **57 de esos quitaron exactamente 1 punto**. En las 4 sesiones registradas, perder 1
punto ocurre casi solo con guardia puesta (105 vs 18, 142 vs 22, 116 vs 15, 177 vs 53): es el
raspado de un especial bloqueado, no un golpe. Los golpes reales quitan 4 o más.

`DefenseLogger` ahora cuenta ≤2 puntos con guardia puesta el frame anterior como bloqueo con raspado.
Recalculado (ataques rivales evitados): original 60% → **71%**; con guardia preventiva 66% → **76%**
(aéreos 49% → 71%, bajos 81% → 89%, de pie 70% → 77%).

Pendiente (no cambiado): el cerebro también trata ese raspado como "me golpearon" (`_recently_hit`)
y el aprendizaje lo penaliza como daño recibido.

## 5. Prueba controlada en FBNeo (versus, 2026-10-14): Iori (bot, GUARD_ONLY_TEST) contra Kim (script)

`tools/guard_test.py`, 5 intentos por escenario y lado, posiciones guardadas, fase de control
(sin guardia: el ataque llega 90/90) y fase de guardia. Trazas en `logs/guard_test_20261014_175549`.

| Escenario de Kim | Estado de Kim (+0x73) | Bloqueado / golpeado |
|---|---|---|
| 2B (bajo) | 97 | 10 / 0 |
| 2D (barrida) | 115 | 10 / 0 |
| 5C (medio) | 98 | 10 / 0 |
| salto + D | 123 | 10 / 0 |
| 2B → 6B, 6B → 2B | 97 / 89 | 10 / 0 cada uno |
| **agarre C** (pegado, 6 + C) | 229–231 | **0 / 10** |
| **agarre D** | 232 | **0 / 10** |

- La primera ejecución dio 90/90 "bloqueado" incluidos los agarres: las entradas de P2 pulsaban
  dirección y botón en el mismo frame y los soltaban juntos, y el juego las leía como golpes DE PIE
  (2B → B de pie, estado 89). Corregido (dirección antes y después del botón). Lección: sin la
  fase de control y sin los estados, el 100% habría pasado por bueno.
- **El 6B de Kim no salió como overhead** (estado 89 = B de pie, se bloquea agachado): el
  escenario de overhead queda SIN validar.
- **Agarres:** no encienden el bit de ataque (+0xE0 bit0). El que agarra pasa a 229–232; el
  agarrado pasa a **168** en el frame en que lo atrapan (10/10 con C y con D), aunque esté en
  guardia agachada. `Fighter.thrown = state_id == 168`.
- **Bloqueo:** Iori en guardia pasa a 27–31 (de pie) o 32–37 (agachado), según el golpe.
  Golpeado sin guardia: 4 (B/C de pie), 12 (salto D), 51/53/57 (barrida: derribo).
- Pendiente: medir la ventana de escape (DEFENSE_ONLY, solo agarres), un overhead real, y los
  estados de otros personajes como atacantes.
