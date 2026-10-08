# KOF AI Lab — Manual técnico de Iori Yagami

> Fuente: documento generado por ChatGPT en la conversación compartida
> https://chatgpt.com/share/6ac6e5eb-30f8-83e9-903d-257acdf96bb5
> (`KOF_AI_Lab_Iori_Magic_Plus_Manual.md`, versión 1.0). Texto copiado de la vista previa.

The King of Fighters 2002 / KOF 2002 Magic Plus

**Versión del documento:** 1.0
**Objetivo:** servir como fuente de conocimiento para un agente/IA que controle a Iori Yagami en un
entorno local de entrenamiento y permita a otro modelo (por ejemplo Claude) extraer una
representación estructurada de movimientos, combos, condiciones y decisiones.

**Regla de integridad de datos:** KOF 2002 Magic Plus es una modificación de KOF 2002. La lista
principal de movimientos y el sistema de cancelaciones están documentados con fuentes de KOF 2002
original; los comportamientos o atajos propios de Magic Plus deben conservar la etiqueta
`MAGIC_PLUS` y validarse en la ROM concreta usada en Fightcade antes de incorporarlos como acciones
fiables del agente.

## 1. Convenciones de entrada

Este documento utiliza notación estándar de juegos de pelea.

| Símbolo | Significado |
|---|---|
| f | adelante, hacia el rival |
| b | atrás, alejándose del rival |
| d | abajo |
| u | arriba |
| df | diagonal abajo-adelante |
| db | diagonal abajo-atrás |
| qcf | cuarto de círculo hacia adelante: d, df, f |
| qcb | cuarto de círculo hacia atrás: d, db, b |
| hcf | medio círculo hacia adelante |
| hcb | medio círculo hacia atrás |
| dp | movimiento tipo dragon-punch: f, d, df |
| P | cualquier puño: A o C |
| K | cualquier patada: B o D |
| A | puño débil |
| B | patada débil |
| C | puño fuerte |
| D | patada fuerte |
| AB | A+B simultáneamente |
| BC | B+C simultáneamente; MAX Mode en KOF 2002 |
| CD | C+D |
| AC | A+C simultáneamente |
| (x3) | repetir tres veces |
| Close | ataque ejecutado muy cerca del rival |
| Crouch | ataque agachado |
| Jump | ataque durante salto |
| DM | Desperation Move |
| SDM | Super Desperation Move |
| HSDM | Hidden Super Desperation Move |

**Importante para el agente:** f y b son direcciones relativas. Si Iori cambia de lado, deben
invertirse automáticamente.

## 2. Perfil funcional de Iori

Iori debe modelarse como un personaje orientado a:

- presión a corta y media distancia;
- confirmación desde ataques normales hacia especiales;
- castigo;
- antiaéreo;
- mezcla ofensiva mediante ataques altos/overhead y agarre de comando;
- presión de esquina;
- conversión de recursos de barra en daño alto;
- rutas MAX con cancelaciones.

Para una IA no conviene representar a Iori como una lista de combos. Debe representarse como un
conjunto de acciones con condiciones de uso.

Estados tácticos mínimos recomendados:

NEUTRAL, APPROACH, PRESSURE, DEFENSE, ANTI_AIR, PUNISH, COMBO_CONFIRM, CORNER_PRESSURE, WAKEUP,
MAX_COMBO, RESOURCE_SAVE.

## 3. Normales y acciones universales relevantes

Los ataques A/B/C/D existen de pie, agachado y en salto. Algunos normales cambian según la
distancia.

Para el primer agente deben registrarse como mínimo:

close_A, close_B, close_C, close_D, far_A, far_B, far_C, far_D, crouch_A, crouch_B, crouch_C,
crouch_D, jump_A, jump_B, jump_C, jump_D, blowback_CD, jump_CD

Los datos exactos de startup, active frames, recovery y ventaja de cada normal no deben inventarse.
Deben añadirse posteriormente a partir de frame data fiable o medición en la ROM.

La guía técnica de KOF 2002 documenta que varios normales de Iori admiten cancelación. Para la IA
esto significa que un impacto confirmado puede convertirse en especial o super según el movimiento
y el estado.

## 4. Agarres normales

### 4.1 Sakahagi

- Tipo: agarre normal
- Input: b/f + C estando cerca
- Uso: romper defensa pasiva a distancia de agarre.
- Condición: rival en rango de throw.
- Etiqueta: BASE_2002_VERIFIED

### 4.2 Saka Sakahagi

- Tipo: agarre normal
- Input: b/f + D estando cerca
- Uso: alternativa de agarre normal.
- Condición: rival en rango de throw.
- Etiqueta: BASE_2002_VERIFIED

## 5. Command Moves

### 5.1 Geshiki: Yumebiki

- Input: f + A, A
- Tipo: command move de dos partes.

Propiedades relevantes:
- la segunda parte es cancelable;
- cuando se enlaza desde ciertos normales fuertes, el empuje puede impedir que conecten ambas partes;
- con ataques ligeros cercanos existen mejores posibilidades de conectar la secuencia completa.

Uso IA: confirmación cercana; puente hacia especial/super; presión; rutas de combo.

Riesgo: no asumir que ambos golpes conectarán desde cualquier normal.

Etiqueta: BASE_2002_VERIFIED

### 5.2 Geshiki: Goufu In "Shinigami"

- Input: f + B
- Tipo: command move / overhead.

Propiedades:
- ejecutado por sí solo funciona como overhead;
- al cancelarlo desde un normal cambia su comportamiento de cancelación;
- es relativamente lento y no debe asumirse que siempre forma combo desde el normal previo.

Uso IA: mix-up contra defensa baja; presión; cancelación contextual.

Etiqueta: BASE_2002_VERIFIED

### 5.3 Geshiki: Yuri Ori

- Input: b + B durante salto
- Tipo: ataque aéreo especial/command move.

Propiedad táctica: golpea hacia la parte posterior de Iori y es especialmente útil cuando Iori
cruza sobre el rival.

Uso IA: cross-up; cambio de lado; presión aérea.

Etiqueta: BASE_2002_VERIFIED

## 6. Special Moves

### 6.1 108 Shiki: Yami Barai

- Input: qcf + A/C
- Tipo: proyectil terrestre.

Iori lanza una llama púrpura que se desplaza por el suelo.

Uso IA: control horizontal; obligar al rival a reaccionar; presión a distancia; crear
aproximaciones; setup de situaciones concretas.

Cancelación MAX: la guía técnica indica que Yami Barai no debe tratarse como una salida libre de
Free Cancel.

Etiqueta: BASE_2002_VERIFIED

### 6.2 127 Shiki: Aoihana / Aoi Hana

- Input: qcb + A/C, hasta tres repeticiones
- Forma conceptual: qcb+P → qcb+P → qcb+P
- Tipo: cadena especial.

Propiedades: puede encadenarse hasta tres veces; el tercer ataque tiene propiedad overhead; los
primeros segmentos participan en rutas de Free Cancel/MAX.

Uso IA: combo; presión; confirmación; MAX routes; finalización de cadenas.

Etiqueta: BASE_2002_VERIFIED

### 6.3 212 Shiki: Kototsuki In

- Input: hcb + B/D
- Tipo: avance/ataque especial.

Uso IA: combo desde normal fuerte; avance ofensivo; rutas MAX; conversión de impacto.

La documentación de KOF 2002 lo incluye entre movimientos que pueden intervenir en Free Cancel.

Etiqueta: BASE_2002_VERIFIED

### 6.4 100 Shiki: Oniyaki

- Input: dp + A/C
- Tipo: ataque ascendente / antiaéreo.

Función principal para IA: ANTI_AIR y determinadas conversiones.

La versión C tiene más puntos relevantes para Super Cancel que la versión A. La guía de combos
documenta Super Cancel desde los primeros impactos del Oniyaki C hacia Ya Otome.

Regla inicial sugerida: rival en salto + trayectoria de entrada + distancia apropiada → considerar
Oniyaki; no ejecutarlo automáticamente: introducir evaluación de riesgo porque un Oniyaki fallado
puede ser castigado.

Etiqueta: BASE_2002_VERIFIED

### 6.5 Kuzukaze

- Input: hcb, f + A/C estando cerca
- Tipo: command grab.

Propiedades documentadas: es imbloqueable; cambia de lado con el rival; deja al oponente vulnerable
durante un breve intervalo.

Uso IA: abrir rivales que bloquean demasiado; crear combo; cambiar posición; escapar/revertir
determinadas situaciones de esquina.

Importante: la IA debe conocer si está en rango antes de intentarlo.

Etiqueta: BASE_2002_VERIFIED

## 7. Desperation Moves

### 7.1 Kin 1211 Shiki: Ya Otome

- Input base: qcf, hcb + A/C
- Tipo: DM.

Es uno de los principales supers ofensivos de Iori y puede utilizarse como final de combo.

La documentación de KOF 2002 también registra una versión asociada a AC en condiciones de
super/SDM.

Usos IA: punish con barra; confirmación desde normal; Super Cancel desde Oniyaki C; cierre de ronda
cuando el daño esperado justifique el gasto.

Etiqueta: BASE_2002_VERIFIED

**Buffer útil:** la guía de combos describe que, después de Oniyaki, parte del movimiento
direccional previo puede aprovecharse para reducir la entrada necesaria antes de Ya Otome. Para
implementación no debe asumirse el shortcut hasta verificar el buffer real del emulador/ROM.

## 8. Follow-up: Ura 316 Shiki: Saika

- Input documentado: qcf repetido cuatro veces + AC
- Condición: follow-up de Ya Otome.

No debe modelarse como una acción neutral independiente. Debe aparecer únicamente cuando el estado
indique que Ya Otome está en su fase válida de finalización.

Uso IA: maximizar daño; cierre de ronda; gastar recursos cuando la expectativa de victoria lo
justifique.

Timing: debe comenzar a introducirse antes/finalizando el último tramo de Ya Otome; requiere
validación práctica para convertirlo a frames concretos.

Etiqueta: BASE_2002_VERIFIED

## 9. HSDM — Ura 1219 Shiki

Las fuentes históricas presentan variaciones de romanización/nombre (En'ou / Homurabotogi) y
distintas formas de escribir la entrada. La guía técnica base registra un HSDM de Iori con una
secuencia compleja y documentación comunitaria de Magic Plus también identifica su especial oculto.

Regla para Claude: no normalizar automáticamente nombres o inputs contradictorios. Crear un alias y
conservar la procedencia.

Representación recomendada:

```yaml
id: iori_hsdm_ura_1219
aliases:
  - Ura 1219 Shiki En'ou
  - Ura Shiki Homurabotogi
type: HSDM
version_status: NEEDS_ROM_VALIDATION
```

Para el bot, el input definitivo debe medirse en la misma ROM Magic Plus usada en Fightcade antes
de marcarlo como VALIDATED.

## 10. Sistema de cancelaciones importante para Iori

Según la guía técnica de KOF 2002:

**Super Cancel**
- Oniyaki A: existe ventana relevante en su primer impacto bajo condiciones específicas.
- Oniyaki C: los primeros impactos permiten Super Cancel.

**Free Cancel hacia:** Aoihana, Kototsuki In, Oniyaki.

**Free Cancel desde:** segmentos de Yumebiki; Goufu In; primeros segmentos de Aoihana; impactos
iniciales de Oniyaki; primer tramo de Kototsuki In.

**No tratar como Free Cancel normal:** Yami Barai, Kuzukaze.

Estas reglas son especialmente importantes para un agente porque determinan qué transiciones entre
acciones son legales.

## 11. Biblioteca inicial de combos

Los siguientes patrones proceden de documentación de KOF 2002 base y deben probarse en Magic Plus
antes de asignarles reliability=1.0.

### 11.1 Confirmaciones sencillas

- **Combo A — normal fuerte → Yami Barai:** Close/Crouch C → qcf + A/C. Uso: confirmación sencilla y estable.
- **Combo B — normal fuerte → Oniyaki:** Close/Crouch C → dp + A/C. Uso: daño/castigo cercano.
- **Combo C — normal fuerte → Aoihana:** Close/Crouch C → qcb + A/C ×3. Uso: cadena básica de Iori.
- **Combo D — normal fuerte → Kototsuki In:** Close/Crouch C → hcb + B/D. Uso: conversión cercana.
- **Combo E — normal fuerte → Ya Otome:** Close/Crouch C → qcf,hcb + A/C. Uso: punish/confirmación con barra.

### 11.2 Yumebiki

- **Combo F:** f+A, A → qcf+C
- **Combo G:** f+A, A → qcb+P ×3
- **Combo H:** f+A, A → Ya Otome

Debe considerarse la diferencia de empuje cuando Yumebiki viene precedido por un normal fuerte.

### 11.3 Goufu In

Rutas documentadas permiten continuar f+B hacia especiales/super en situaciones apropiadas, pero el
normal anterior no necesariamente conecta con el overhead. Para el agente debe diferenciarse:

`pressure_transition ≠ true_combo`

Nunca marcar una cadena como combo garantizado solo porque sus acciones pueden cancelarse.

## 12. Combo de esquina

Patrón base documentado: **Yami Barai A → Ya Otome C**

La utilidad aumenta en esquina porque el proyectil no puede empujar al rival indefinidamente hacia
atrás.

Estado requerido: opponent_in_corner=true.

Etiqueta: BASE_2002_VERIFIED / MAGIC_PLUS_TEST_REQUIRED

## 13. Super Cancel

Ruta especialmente importante:

Close/Crouch C → Oniyaki C (cancelar durante impactos iniciales) → Ya Otome

Esta debe almacenarse como una secuencia con ventana temporal, no simplemente como una cadena de
botones. Ejemplo conceptual:

```json
{
  "combo_id": "iori_sc_01",
  "starter": "close_or_crouch_C",
  "sequence": ["oniyaki_C", "ya_otome"],
  "cancel": "SUPER_CANCEL",
  "timing": "cancel Oniyaki C during validated early-hit window",
  "rom_validation_required": true
}
```

## 14. MAX Mode

La guía de KOF 2002 confirma que Iori dispone de muchas rutas MAX; documenta solo una muestra.

Patrones útiles para entrenar inicialmente:

- Close C → Yami Barai A → Yami Barai A → Kototsuki B/D
- Close C → Kototsuki (primer impacto) → Oniyaki C (segmentos iniciales) → repetir cancelaciones dentro de la ruta permitida
- Close C → Kototsuki → Aoihana

No conviene enseñar al agente desde el inicio una ruta MAX gigantesca. Primero debe dominar:
1. activación; 2. confirmación; 3. dos cancelaciones; 4. final seguro; 5. optimización de daño.

## 15. Estrategia que debe aprender la IA

**Neutral.** Objetivos: medir distancia; detectar salto; usar movimiento y normales; Yami Barai
cuando sea razonablemente seguro; no gastar barra sin motivo.

**Antiaéreo.** Candidato principal: Oniyaki. Variables: distancia horizontal; altura rival;
trayectoria; estado actual de Iori; tiempo disponible; riesgo de whiff.

**Presión.** Opciones: normales rápidos; Yumebiki; Goufu In; Aoihana; Kuzukaze; esperar/bait. La IA
no debe repetir siempre la misma opción.

**Rival defensivo.** Incrementar gradualmente probabilidad de: Kuzukaze; overhead; retrasar ataque;
caminar/ajustar distancia; bait.

**Punish.** Cuando el rival queda en recovery: sin barra → combo seguro; con barra → evaluar Ya
Otome; con MAX/recursos → evaluar ruta de mayor daño; poca vida rival → priorizar kill confirm sobre
ahorro de barra.

**Esquina.** Aumentar prioridad de: mantener al rival encerrado; presión segura; throw/command grab;
conversiones de alto daño; evitar saltos/rolls de escape.

## 16. Impredecibilidad controlada

No utilizar aleatoriedad pura. Utilizar una distribución condicionada por estado. Ejemplo
conceptual:

```
Si rival bloquea bajo repetidamente:
  35% overhead
  25% Kuzukaze
  20% presión con normal
  10% pausa/bait
  10% reposicionamiento
```

Los porcentajes deben ser aprendidos/ajustados, no fijados como estrategia definitiva.

El agente debe poder cambiar tendencias durante una pelea sin tener acceso a inputs futuros del
rival.

## 17. Modelo de acción recomendado para Claude

Cada acción debe convertirse a un objeto similar a:

```json
{
  "character": "Iori Yagami",
  "move_id": "iori_oniyaki_c",
  "name": "100 Shiki: Oniyaki",
  "category": "SPECIAL",
  "input": ["F", "D", "DF", "C"],
  "relative_directions": true,
  "primary_roles": ["ANTI_AIR", "COMBO", "SUPER_CANCEL_START"],
  "meter_cost": 0,
  "range": "CLOSE_TO_MID",
  "requires_airborne": false,
  "requires_close": false,
  "cancel_properties": ["SUPER_CANCEL_EARLY_HITS"],
  "version": "KOF2002_BASE",
  "magic_plus_validation": "REQUIRED",
  "confidence": "HIGH"
}
```

## 18. Esquema de combos recomendado

```json
{
  "combo_id": "iori_basic_aoihana",
  "character": "Iori Yagami",
  "starter_conditions": {
    "range": "CLOSE",
    "opponent_state": "HIT_CONFIRMED",
    "corner_required": false
  },
  "sequence": ["close_C", "aoihana_1", "aoihana_2", "aoihana_3"],
  "meter_required": 0,
  "difficulty": "BASIC",
  "purpose": ["DAMAGE", "PUNISH"],
  "version": "KOF2002_BASE",
  "magic_plus_validation": "REQUIRED"
}
```

## 19. Datos que NO deben inventarse

Claude no debe completar por inferencia: startup frames; active frames; recovery frames; hit
advantage; block advantage; invulnerabilidad exacta; hurtboxes/hitboxes; daño exacto en Magic Plus;
stun exacto; distancia exacta en píxeles; ventanas exactas de cancelación; consumo de barra
específico si difiere en la ROM; atajos exclusivos de Magic Plus no comprobados.

Usar UNKNOWN o NEEDS_VALIDATION.

## 20. Protocolo de validación en Fightcade / Training

Para cada movimiento: seleccionar Iori; confirmar orientación P1 a la izquierda; ejecutar input
lentamente; ejecutar input a velocidad real; repetir 20 veces; medir éxitos; cambiar de lado;
invertir direcciones relativas; repetir; probar versión débil/fuerte; probar cancelación; probar
contra rival de pie/agachado/saltando; probar centro y esquina; registrar video/log; marcar
VALIDATED_MAGIC_PLUS solo después de confirmarlo.

Para combos: mínimo 20 ejecuciones consecutivas; registrar si depende del personaje rival;
registrar esquina/centro; registrar barras; registrar lado; registrar hit count; registrar daño
observado; registrar timing sensible.

## 21. Niveles de confianza

- **HIGH:** confirmado por documentación técnica sólida del KOF 2002 base.
- **MEDIUM:** confirmado por material comunitario o tutorial, pero necesita contraste.
- **LOW:** dato aislado o ambiguo.
- **VALIDATED_MAGIC_PLUS:** probado directamente en la ROM Magic Plus concreta del proyecto.

Esta última etiqueta debe tener prioridad sobre todas las demás para el bot.

## 22. Orden recomendado de implementación

- **IORI-01 — locomoción:** caminar, correr, agacharse, saltar, bloquear, rodar.
- **IORI-02 — normales:** A/B/C/D en estados de pie, crouch y jump.
- **IORI-03 — especiales:** Yami Barai, Aoihana, Kototsuki, Oniyaki y Kuzukaze.
- **IORI-04 — supers:** Ya Otome y follow-up.
- **IORI-05 — combos básicos:** confirmaciones desde Close/Crouch C.
- **IORI-06 — percepción:** distancia, lado, aire/suelo, esquina, hit/block, barras.
- **IORI-07 — decisiones:** neutral, anti-air, pressure, punish.
- **IORI-08 — MAX:** cancelaciones y rutas MAX.
- **IORI-09 — adaptación:** aprender hábitos del rival y ajustar probabilidades.

## 23. Prompt recomendado para Claude

Lee este documento como la especificación inicial de Iori Yagami para el proyecto KOF AI Lab.

Tu tarea es convertir la información en una base de datos estructurada para el agente. No inventes
frame data, daño, hitboxes, ventanas temporales ni propiedades que el documento marque como
desconocidas o pendientes de validación.

Genera: 1. iori_moves.json 2. iori_combos.json 3. iori_strategy.json 4. modelos/clases necesarios
para representar movimientos y combos; 5. un sistema de etiquetas de versión y confianza; 6. pruebas
unitarias de validación de inputs; 7. una lista magic_plus_validation_queue.json con todo dato que
deba probarse en nuestra ROM.

Las direcciones deben ser relativas a la posición del personaje. La implementación debe poder
invertir automáticamente izquierda/derecha cuando Iori cambia de lado.

No programes decisiones imposibles para un humano basadas en información futura del rival. Mantén
separadas: ejecución del movimiento; percepción del estado; selección de acción;
aprendizaje/adaptación.

Antes de implementar una propiedad no presente en la documentación, márcala como UNKNOWN y solicita
validación.

## 24. Fuentes y trazabilidad

- **Fuente A — Kao Megura, KOF 2002 Move List and Guide.** GameFAQs. Lista técnica de Iori,
  comandos, cancelaciones, notas de Yumebiki, Goufu In, Yuri Ori, Aoihana, Kuzukaze y Saika.
  https://gamefaqs.gamespot.com/pc/293564-the-king-of-fighters-2002/faqs/20796
- **Fuente B — Fabian Davy, Basic Game Combos FAQ: KOF 2002.** GameFAQs. Combos de Iori, Super
  Cancels, buffer y ejemplos MAX.
  https://gamefaqs.gamespot.com/neo/914531-the-king-of-fighters-2002/faqs/29140
- **Fuente C — VARPGAMER, especial de Iori — KOF 2002 Magic Plus.** Tutorial audiovisual
  específicamente etiquetado como Magic Plus; útil para contrastar secuencias de entrada con la
  modificación. https://www.youtube.com/watch?v=YUb7RYWNf4c
- **Fuente D — Manual comunitario KOF 2002 / Magic Plus.** Material comunitario que documenta
  sistema Magic Plus y lista movimientos/especial oculto de Iori. Debe considerarse fuente
  secundaria y verificarse en la ROM.
  https://es.scribd.com/document/426621294/72738104-KoF-2002-Manual-de-Instrucciones-doc

## 25. Estado de esta documentación

Esta versión es una base técnica inicial, no frame data definitiva.

La prioridad del proyecto debe ser:

documentación → representación estructurada → validación en ROM → timings medidos → agente

Cuando un movimiento o combo haya sido probado directamente en la ROM de Fightcade usada por el
proyecto, actualizar `magic_plus_validation: REQUIRED` a `magic_plus_validation: VALIDATED` y
registrar fecha, número de pruebas, lado P1/P2 y porcentaje de ejecución correcta.

**Siguiente documento recomendado:** IORI_MAGIC_PLUS_VALIDATION_LOG.md, que debe llenarse durante
las pruebas reales del juego y convertirse en la fuente de verdad de la implementación.
