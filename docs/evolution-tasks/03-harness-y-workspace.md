# Tarea — Construir Harness 

## Objetivo

Partimos de que ya tenemos litman-core como una libreria (una wheel) con un comando 
que lanza analisis inicial o detallado y genera outputs. Queremos construir un harness para usar desde la Codex App por usuario que que escribe documetnos para licitaciones (Alguien de negocio no es técnico). La idea es que desarrolle con codex pidiendo modificaciones, o modificando el mismo, o pidiendo revisiones o cualquier cosa, partiendo de los docs ya generados por core. También se tiene que poder permitir sync con drive para que otros usuarios revisores puedan ver y incluso modificar (ya sea con mismo harness).

## Requisitos 
He ido poniendo puntos segun he caido, estan algunos relacionados. Hay que leerlos primero todos, entenderlos en general: 

1. Repo preparado para que simplemente usuario se lo instale y ya le pida a codex instalacion setup inicial y este todo detallado y sea muy fácil, tema de google drive y todo lo necesario para qeu funcione litman core y parametros que consideremos (skill setup o algo así.)

2. skill o flujo "nueva licitacion" (piensa como plantearlo) y ya codex pida por ejemplo folder de licitacion, descargue vea lo que hay y sugiera analisis de un tipo o de otro. cuando se tengan pues skills que consideremos (quizas de primeras sean pocas y con el uso vayamos añadiendo, hacerlo escalable), capacidad de desde codex editar estos tipos de documentos se tiene?? o verlos 

3. Parte de sync, debemos pensar una forma de bajar y subir de drive nose si editar en local y que codex sugiera subir hay que pensar la forma, usar scripts tools 

4. Cuanto mśa cosas tengamos tools comandos scripts mejor, agentes y skills, la idea es construir harness.

5. parte de docker no la usaremos solo parte local. en ese primer setup es importante dejar repo con lo minimo preparado (nose si hacer build o ya estare en repo pensar una forma)

6. Excluir todo lo posible al usuario, es de negocio y no es técnico, el sistema debe ser lo más facil de usar por él. 

7. No se si afecta en algo, pero gente de negocio usa windows. 

8. Importante aclarar diseñar implementar workspace donde esto se ejecutara, estaran documentos, pensar si drive o local, tema de sync. 

9. Pensar como quedara el repo, si release otra rama para esto, con el objetivo en mente de lo más facil para negocio y simple. 

10. Importante por ejemplo generar un context.md asociado a la licitacion (a partir de lo de litman core) que nos sirva para dar contexto, de alguna forma determinista por ej. (podria plantearse hacer cambio en litman-core)

## Lo que tienes que hacer
El objetivo abstracto es al final dar al usuario un sistema sencillo para desarrollar la oferta para una licitación mediante asistente IAcon los menos recursos posibles, con el menos trabajo sin posible (sin UI y demás) y con unicamente licencia codex. Imporatante analisis-inicial es para ver si es interesante una licitacion y cuando se pasa a tramitacion ya se pasa al detallado. Entiende lo que quiero, analiza mi planteamiento, criticalo, partes buenas, malas, que cambiarias, y busquemos al final una solución. No hay que buscar ya diseño final, analiza piensa investiga busca y discutamos. 