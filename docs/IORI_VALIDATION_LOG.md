# Iori — registro de validación en la ROM del proyecto

Fuente de verdad para el bot (prioridad sobre el manual, ver sección 21 del manual).
Prueba: `tools/combo_lab.py` en modo práctica, Iori P1 contra dummy quieto sin guardia, combos con
confirmación de golpe (cada parte solo si la anterior conectó), 3 intentos por combo.

## 2026-10-07

| Combo | Notación del bot | Partes que conectan | Daño medio | Estado |
|---|---|---|---|---|
| 6C → Oniyaki C → Kototsuki B → Oniyaki C (de jugadores top) | `6C>623C>63214B>623C` | 4/4 | 25,0 | VALIDATED |
| Close C → Aoi Hana C ×3 | `C>214C>214C>214C` | 4/4 | 24,3 | VALIDATED |
| Close C → Aoi Hana A ×3 | `C>214A>214A>214A` | 4/4 | 23,7 | VALIDATED |
| Close C → Oniyaki C | `C>623C` | 2/2 | 23,0 | VALIDATED |
| Close C → Yami Barai C | `C>236C` | 2/2 | 21,0 | VALIDATED |
| Close C → Oniyaki A | `C>623A` | 2/2 | 18,0 | VALIDATED |
| Close C → Kototsuki In B | `C>63214B` | 1,7/2 | 12,0 | NO FIABLE |
| Close C → Kototsuki In D | `C>63214D` | 1,3/2 | 8,3 | NO FIABLE |
| C → Aoi Hana C → Oniyaki C → Yami Barai C (repeticiones) | `C>214C>623C>236C` | 2/4 | 12,3 | NO FIABLE |
| D → C → 6C → Yami Barai C (repeticiones) | `D>C>6C>236C` | 1/4 | 12,7 | NO FIABLE |
| Yumebiki f+A, A → Yami Barai C | `6A>A>236C` | 1/3 | 3,0 | FALLA (el 2.º A no encadena) |
| Yumebiki f+A, A → Aoi Hana ×3 | `6A>A>214A>214A>214A` | 1/5 | 3,0 | FALLA |
| 2A → Yumebiki → Yami Barai C | `2A>6A>A>236C` | 1/4 | 3,0 | FALLA |

### DM (con barra) — 2026-10-07

El daño de un DM llega unos 100 frames después del comando (pausa de super + recorrido): antes el bot
dejaba de mirar a los 24 frames y parecía que no conectaban. Con ventana de 150 frames:

| Combo | Notación del bot | Daño medio | Estado |
|---|---|---|---|
| Close C → Oniyaki C → Ya Otome (super cancel, movimiento metido sin esperar) | `C>623C23663214A` | 33,5 | VALIDATED (paso 2f) |
| Close C → Ya Otome (con confirmación) | `C>23663214A` | 33,0 | solo con paso 1f |
| Ya Otome solo, de cerca | `23663214A` | 25,0 | VALIDATED |
| Close C + Ya Otome sin confirmar | `C23663214A` | 24,5 | VALIDATED |

Pendiente de validar: Kuzukaze (hcb,f + P), Goufu In como overhead real, Saika / HSDM, rutas MAX,
lado P2 (todas las pruebas con Iori a la izquierda).
