# Tarea

Analiza el expediente completo para preparar una propuesta inicial editable.

Devuelve: cabecera de oportunidad, contexto técnico, objetivos, alcance,
trabajos, fases, entregables contractuales, documentos a presentar con la
oferta, equipo exigido, tecnologías, requisitos concretos, criterios de
adjudicación, contrato del simulador económico, estructura sugerida del documento técnico,
pendientes del usuario y evidencias.

Extrae además el contrato de la memoria técnica: si es obligatoria, su nombre,
idioma, índice o estructura en el orden exacto del pliego, apartados
obligatorios, puntuación asociada, límites globales o por apartado, requisitos
formales (páginas, fuente, tamaño, interlineado y márgenes), prohibiciones y
consecuencias de incumplimiento. Indica también, cuando conste, si portada,
índice y anexos computan en el límite. Usa `null` cuando no esté indicado; no
conviertas una ausencia de información en libertad confirmada.

En `cabecera.nombre` conserva la denominación oficial completa del contrato y
en `cabecera.expediente` la referencia oficial. No confundas el título de la
licitación con la denominación del documento exigido (por ejemplo, «Memoria
técnica») ni dupliques un expediente ya incluido en el nombre. Añade evidencias
localizables para ambos datos. Cuando el pliego imponga subapartados de una
sección de la memoria, extráelos en `memoria_tecnica.secciones[].subapartados`
con título, nivel, orden implícito, descripción, requisitos y evidencias; no
inventes subapartados que el pliego no imponga.

No mezcles los entregables que se producirán durante el contrato con los
documentos que se presentan para licitar. Tampoco mezcles criterios de
adjudicación con requisitos obligatorios.

Para `simulador_economico`, extrae el presupuesto máximo sin IVA, moneda,
puntuación total, todos los criterios no económicos, la fórmula de puntuación
del precio y las reglas de ofertas anormalmente bajas. Conserva por separado la
expresión literal y su interpretación estructurada. Usa
`inversa_oferta_minima` solo si la fórmula equivale a «oferta mínima × puntos
máximos / oferta evaluada» y `lineal_baja` solo cuando esa estructura sea
inequívoca; cualquier otra fórmula debe ser `otra_no_soportada`. No escribas
fórmulas de Excel ni código ejecutable.

Para cada criterio indica si es automático cuantitativo, automático binario o
juicio de valor, su máximo, rango y unidad cuando consten. Para cada regla de
baja anormal indica a cuántos licitadores se aplica, su base numérica, si usa la
media de ofertas o el presupuesto máximo, el peso de calidad y el comparador.
No resuelvas contradicciones del pliego: consérvalas en `advertencias` con sus
evidencias. No inventes precio de la empresa, puntuaciones esperadas, número de
competidores ni ofertas rivales; regístralos como pendientes económicos.

No redactes una oferta final. Las recomendaciones deben marcarse como tales y
los datos no presentes en el expediente deben quedar como pendientes.
