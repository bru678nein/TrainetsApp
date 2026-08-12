# Datos de desarrollo

Esta carpeta está ignorada por git salvo este archivo.

Contiene planillas reales de entrenamiento con información personal de atletas:
nombre, peso corporal, lesiones anotadas en los comentarios de las sesiones.
Nada de acá se versiona, ni siquiera un archivo que parezca inofensivo.

## Qué va acá

| Archivo | Para qué |
|---|---|
| `planilla.xlsx` | La que usa `make seed` y los tests de API. Es el único nombre que el código busca. |
| `PLANTILLA_entrenamiento.xlsx` | La plantilla en blanco del entrenador, sin datos de nadie. Referencia para entender el formato de origen. |
| `rutina_<atleta>.html` | Salida de `gen_app.py`, generada para un atleta real. Es un artefacto, se regenera cuando haga falta. El nombre del archivo lleva el del atleta, así que no se nombra acá: `data/` está en `.gitignore` justamente para que esos datos no entren al repo, y escribirlos en el README los mete igual por la puerta de al lado. |

Los tres están ignorados por git. El tercero además lleva el nombre de una
persona en el nombre del archivo, que es exactamente el motivo por el que la
regla de esta carpeta es ignorar todo y no ir eligiendo qué parece inofensivo.

El proyecto siembra el entorno con datos reales y no con
seeds inventados: los reales traen los casos borde que los sintéticos esconden
—prescripciones compuestas en texto libre, series de más de 12 repeticiones
fuera de la tabla RPE, cargas que cambian entre series del mismo ejercicio.

## Si no tenés la planilla

Los tests del dominio corren igual, no necesitan datos. Los de API se saltan con
un mensaje explicativo. Nada revienta.

## Herramientas

El generador de la app HTML autocontenida vive en `backend/scripts/gen_app.py`,
no acá — es código y se versiona.
