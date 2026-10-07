# Simulador económico standard-v1

Plantilla interna y neutra derivada del simulador de referencia. No contiene
datos, criterios, precios ni hipótesis de una licitación concreta.

El renderizador genera las hojas `Simulador`, `Criterios y ayuda`,
`Comprobaciones` y `Pendientes`. Los hechos proceden de `economic_plan.json`;
los precios, puntuaciones esperadas y competidores proceden exclusivamente de
`economic_inputs.json`.

Las fórmulas no reconocidas no se ejecutan: quedan señaladas como pendientes.
El libro solicita recálculo completo al abrirse en una aplicación compatible.
