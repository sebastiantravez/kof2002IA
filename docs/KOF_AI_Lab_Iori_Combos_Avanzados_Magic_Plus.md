# KOF AI LAB — Manual de combos avanzados de Iori
## Objetivo: KOF 2002 **Magic Plus** en Fightcade 2 (NO confundir con KOF 2002 original ni Super Magic Plus)

> Fuente: documento generado por ChatGPT en la conversación compartida
> https://chatgpt.com/share/6ac6ea37-c824-83e9-84da-0d7dc86b58c0 (edición 1.0, 7 de octubre de 2026).

**Edición:** 1.0 — 7 de octubre de 2026
**Uso:** documento textual para Claude; entrenamiento y validación local.
**Objetivo operativo:** conseguir rutas de Iori que superen el 50 % de vida del rival, medidas en la ROM específica del usuario.
**Estado de la evidencia:** se encontraron descripciones escritas de combos largos para Magic Plus, pero **ninguna ruta >50 % cuenta todavía con notación completa, medición reproducible y confirmación independiente para la ROM del usuario**. No declarar 80 %, 100 % ni 28 hits como resultados comprobados.

## 1. Identidad del juego y prevención de errores

- Objetivo: **The King of Fighters 2002 Magic Plus** que corre en Fightcade 2.
- **No sustituir** por KOF 2002 original, KOF 2002 Unlimited Match ni Super Magic Plus.
- Identificar el nombre de ROM, hash/CRC, versión y configuración antes de validar inputs.
- Los documentos de internet pueden llamar "Magic Plus" a distintas modificaciones. Si una ruta falla, no asumir que el usuario ejecutó mal el comando.
- Cada movimiento/combo debe tener `origen`, `version_objetivo`, `estado_validacion` y `resultado_prueba`.

## 2. Notación inequívoca

| Notación | Significado | Joystick desde lado izquierdo |
|---|---|---|
| `f`, `b` | adelante / atrás relativo al rival | → / ← |
| `d`, `u` | abajo / arriba | ↓ / ↑ |
| `qcf` | cuarto de círculo adelante | ↓ ↘ → |
| `qcb` | cuarto de círculo atrás | ↓ ↙ ← |
| `hcb` | medio círculo atrás | → ↘ ↓ ↙ ← |
| `dp` | gancho / dragon punch | → ↓ ↘ |
| `A/B/C/D` | puño débil / patada débil / puño fuerte / patada fuerte | botones de KOF |
| `BC` | B y C simultáneos | activación MAX, según reglas de ROM |
| `AC` | A y C simultáneos | dos puños simultáneos |
| `cl.C` | C fuerte estando muy cerca | botón C |
| `(1 hit)` | cancelar tras primer impacto | requiere detección/temporización |
| `>` | continuación o cancelación que hay que comprobar | no implica combo garantizado |

**Advertencia:** los autores comunitarios utilizan expresiones como "bola atrás", "gancho", "oriuken" y "cortar". No son equivalencias suficientes para generar inputs sin probarlos.

## 3. Evidencia escrita específicamente rotulada Magic Plus

### MP-IORI-01 — Combo largo con salto, MAX y cancelaciones

**Fuente:** documento comunitario *Movimientos y Combos KOF 2002 Magic Plus* (Scribd): https://es.scribd.com/document/602042511/K

**Transcripción interpretativa, NO input validado:**

1. Iniciar con salto hacia adelante + `B`.
2. Activar/cancelar con `BC`.
3. Conectar `C` cerca.
4. Ejecutar un movimiento descrito como "bola para atrás con C". **Hipótesis:** `qcb+C` (Aoihana), pendiente de confirmar.
5. Ejecutar "gancho con C". **Hipótesis:** `dp+C` (Oniyaki), pendiente de confirmar.
6. Cancelar con "bola para atrás con B". **Ambigüedad importante:** `qcb+B` no identifica inequívocamente el movimiento de Iori; podría ser una transcripción informal incorrecta de `hcb+B` (Kototsuki In). **NO generar input automático a partir de esta frase.**
7. Continuar con otra cancelación/gancho según el relato.
8. El autor describe una continuación final con especial y "dos bolas adelante con C", pero el orden preciso no queda claro.

**Resultado declarado por fuente:** combo avanzado/largo; sin porcentaje verificable.
**Estado:** `MAGIC_PLUS_TEXT_SOURCE_UNVERIFIED`.
**Acción para Claude:** convertir cada paso ambiguo en una hipótesis independiente; probar en training; no ejecutar toda la cadena hasta validar cada transición.

### MP-IORI-02 — Combo comunitario de "28 hits" y cuatro barras

**Fuente:** mismo documento: https://es.scribd.com/document/602042511/K

**Descripción de la fuente, resumida:** se propone acercarse corriendo con cuatro barras; comenzar con salto/ataque fuerte `C`, conectar más golpes `C`, encadenar una "bola hacia atrás con B", un "gancho con C", repetir segmentos de ataques/cancelaciones y terminar con un super. El autor afirma que puede producir unos **28 hits** y, según el número de cancelaciones, derrotar al rival.

**NO SE PUEDE CONVERTIR HONESTAMENTE A UNA SECUENCIA EXACTA DE INPUTS** porque faltan detalles esenciales:
- dirección precisa de "bola atrás con B";
- en qué impacto cancelar;
- número de repeticiones de cada especial;
- cuándo activar MAX;
- comando exacto del super final;
- distancias, esquina, lado y rival;
- prueba de daño real.

**Estado:** `COMMUNITY_CLAIM_NOT_REPRODUCED`.
**Acción para Claude:** usarlo como candidato de investigación, no como combo listo para ejecutar. El número de hits y el daño son afirmaciones no verificadas.

### MP-IORI-03 — Especial oculto de Iori

**Fuentes Magic Plus:**
- https://es.scribd.com/document/367085377/Movimientos-Especiales-Kof2002-Explicado
- https://es.scribd.com/doc/72738104/KoF-2002-Manual-de-Instrucciones

Estos textos registran el especial oculto/HSDM de Iori, pero la notación de direcciones aparece simplificada, contradictoria o dañada por extracción. **No usar un supuesto shortcut como input confirmado.** Verificar primero la ROM, los requisitos y si la variante concreta habilita el movimiento.

## 4. Rutas de referencia de KOF 2002 ORIGINAL — SOLO COMO HIPÓTESIS PARA MAGIC PLUS

**Importante:** las siguientes rutas NO proceden de un manual confirmado de Magic Plus. Son patrones técnicos de referencia para diseñar pruebas. **No presentarlas como combos Magic Plus verificados.**

**Fuente original:** Fabian Davy, *The King of Fighters 2002 — Combo Guide*: https://gamefaqs.gamespot.com/arcade/562946-the-king-of-fighters-2002/faqs/29140

### BASE-IORI-A — MAX de repetición, aproximadamente 45 % según guía del original

`cl.C > [hcb+B/D (1 hit) > dp+C (2 hits)] × 3`

- La guía del original registra **11 hits y 45 %** para esta ruta.
- **No supera 50 % en la referencia**; es útil para entrenar timing y Free Cancel antes de rutas más fuertes.
- Probar activación MAX, hitstop y ventana del primer impacto.

### BASE-IORI-B — C fuerte, Oniyaki y Ya Otome

`cl.C > dp+C (cancelación temprana) > qcf,hcb+A/C`

- Ruta conceptual de Super Cancel documentada para el original; puede variar según versión y timing.
- Probarla en Magic Plus sin atribuir porcentaje hasta medirlo.

### BASE-IORI-C — Cadena MAX con Kototsuki/Oniyaki y super final

`cl.C > activar MAX > [hcb+B/D (1 hit) > dp+C (impactos iniciales)] × N > super validado`

- **Plantilla experimental, no combo confirmado.**
- `N` no es libre: depende de barra MAX restante, empuje, hitstun y reglas reales de la ROM.
- Medir daño en cada N y descartar cualquier transición que permita escape o bloqueo.

## 5. Reglas de ejecución para Claude

**No ejecutar combos avanzados como un script con `sleep` fijo entre botones.**

Construir una máquina de estados:

1. `PRECHECK`: personaje Iori, ROM correcta, orientación, distancia, barra y estado rival.
2. `STARTER`: iniciar ataque de entrada y comprobar si conectó.
3. `CONFIRM`: si hubo hit, avanzar; si hubo bloqueo, elegir salida segura; si falló, abortar.
4. `MAX_ACTIVATION`: activar MAX solo cuando sea legal y haya recursos.
5. `CANCEL_WINDOW`: observar impacto/animación o utilizar ventana calibrada de frames.
6. `NEXT_MOVE`: emitir joystick/botones en secuencia y duración verificadas.
7. `LOOP_GUARD`: repetir solo si el combo sigue conectando y hay barra suficiente.
8. `FINISHER`: ejecutar DM/SDM validado cuando sea legal.
9. `MEASURE`: registrar hits, vida antes/después, coste y porcentaje de éxito.
10. `FALLBACK`: si falla una cancelación, dejar de enviar la cadena y volver a neutral/defensa.

### Porcentaje de daño

`damage_pct = 100 * (vida_inicial_rival - vida_final_rival) / vida_maxima_rival`

- Empezar siempre con rival al 100 % de vida y misma configuración de daño.
- Diferenciar `hits` de `damage_pct`: **28 hits no equivale a 28 %, 50 % ni 100 %.**
- Repetir 20 veces cada ruta por lado; registrar `success_rate` y daño de las ejecuciones válidas.
- No clasificar una ruta como `HIGH_DAMAGE_CONFIRMED` hasta que la prueba local muestre **>50 %** de daño en condiciones registradas.

## 6. Datos estructurados propuestos

```json
{
  "id": "MP-IORI-01",
  "character": "IORI",
  "target_game": "KOF_2002_MAGIC_PLUS",
  "source_type": "COMMUNITY_TEXT",
  "source_url": "https://es.scribd.com/document/602042511/K",
  "verification_status": "UNVERIFIED",
  "sequence": [
    {"action": "jump_forward_B", "status": "SOURCE_DESCRIBED"},
    {"action": "activate_MAX_BC", "status": "SOURCE_DESCRIBED"},
    {"action": "close_C", "status": "SOURCE_DESCRIBED"},
    {"action": "qcb_C", "status": "HYPOTHESIS"},
    {"action": "dp_C", "status": "HYPOTHESIS"},
    {"action": null, "source_phrase": "bola atras con B", "status": "AMBIGUOUS"}
  ],
  "damage_pct": null,
  "hit_count": null,
  "meter_cost": null,
  "timing_frames": null,
  "ready_for_execution": false
}
```

Para cada variante probada guardar: `rom_hash`, `player_side`, `opponent`, `opponent_position`, `meter_before`, `max_active`, `input_frame_log`, `hit_count`, `damage_pct`, `attempts`, `successes`, `failure_reason`.

## 7. Plan de pruebas prioritario

1. Confirmar que el ejecutor hace `hcb+B`, `dp+C`, `qcb+C` y `qcf,hcb+P` individualmente sin errores.
2. Probar `hcb+B (1 hit) > dp+C` en MAX, por ambos lados.
3. Añadir un segundo ciclo de cancelación y medir si el rival permanece en hitstun.
4. Añadir tercero solo si la ventana y la barra lo permiten.
5. Añadir final con Ya Otome y medir daño real.
6. Contrastar MP-IORI-01 con estas piezas; resolver primero la ambigüedad de "bola atrás con B".
7. Medir qué rutas realmente pasan 50 % en esta ROM.
8. Solo entonces incorporarlas a `iori_advanced_combos.json` como acciones disponibles.

## 8. Prompt listo para pegar en Claude

> Lee este archivo completo como documentación del proyecto KOF AI Lab para **KOF 2002 Magic Plus**. NO uses automáticamente combos del KOF 2002 original ni Super Magic Plus. Nuestra meta es lograr con Iori combos que quiten **más del 50 % de vida**, pero no debes inventar que una ruta alcanza ese daño. Distingue `SOURCE_DESCRIBED`, `HYPOTHESIS`, `AMBIGUOUS` y `VALIDATED_IN_OUR_ROM`.
>
> Primero revisa la implementación actual del emisor de inputs y el sistema de cancelación. Después crea un registro de movimientos verificables, un `iori_advanced_combos.json` con solo secuencias ejecutables ya validadas, y una cola de pruebas para las rutas incompletas. Implementa las rutas progresivamente en entrenamiento local; registra hits, daño, barra, lado y errores. No hagas que el bot ejecute un combo incompleto como si estuviera confirmado. Prioriza el ciclo `Kototsuki (primer hit) > Oniyaki C`, y después la integración con Ya Otome, solo si funciona en nuestra ROM. Entrega un reporte con los combos que realmente superen el 50 % y sus tasas de éxito.

## 9. Fuentes escritas

1. **Magic Plus — comunidad:** *Movimientos y Combos KOF 2002 Magic Plus*. https://es.scribd.com/document/602042511/K
2. **Magic Plus — comandos:** *Combos y Especiales KOF 2002 Magic Plus*. https://es.scribd.com/document/367085377/Movimientos-Especiales-Kof2002-Explicado
3. **Magic Plus — guía comunitaria:** *Trucos y Combos en KOF 2002 Magic Plus*. https://es.scribd.com/doc/72738104/KoF-2002-Manual-de-Instrucciones
4. **Solo referencia del original, NO validación Magic Plus:** *KOF 2002 Combo Guide*, Fabian Davy. https://gamefaqs.gamespot.com/arcade/562946-the-king-of-fighters-2002/faqs/29140

---
**Conclusión:** existe documentación textual comunitaria específica de Magic Plus, pero es incompleta para reproducir con fiabilidad un combo de Iori de >50 %. Este manual conserva la evidencia sin inventar inputs y define cómo convertirla en combos comprobados para Claude.
