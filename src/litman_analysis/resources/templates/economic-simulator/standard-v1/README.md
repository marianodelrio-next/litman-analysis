# Simulador económico standard-v1

Plantilla interna y neutra derivada del simulador de referencia. No contiene
datos, criterios, precios ni hipótesis de una licitación concreta.

El renderizador genera las hojas `Simulador`, `Criterios y ayuda`,
`Comprobaciones` y `Pendientes`. Los hechos proceden de `economic_plan.json`;
los precios, puntuación técnica esperada y competidores proceden exclusivamente
de `economic_inputs.json`. El pliego conserva los criterios no económicos de
forma individual para su trazabilidad en `Criterios y ayuda`, pero la hoja
principal solicita una única puntuación técnica agregada por licitador. Los
precios y puntuaciones siguen siendo hipótesis internas, no hechos del expediente.

Los nuevos runs usan `economic-inputs-v2`. El rerenderizado admite
`economic-inputs-v1` de runs antiguos y deriva su puntuación técnica sumando el
desglose existente; un mismo licitador no puede mezclar ambos formatos.

Las fórmulas no reconocidas no se ejecutan: quedan señaladas como pendientes.
El libro solicita recálculo completo al abrirse en una aplicación compatible.
