# Datos de desarrollo

Esta carpeta está ignorada por git salvo este archivo.

Contiene planillas reales de entrenamiento con información personal de atletas:
nombre, peso corporal, lesiones anotadas en los comentarios de las sesiones.
Nada de acá se versiona, ni siquiera un archivo que parezca inofensivo.

## Qué va acá

| Archivo | Para qué |
|---|---|
| `planilla.xlsx` | La que usa `make seed` y los tests de API |

La constitución (artículo IX) exige sembrar el entorno con datos reales y no con
seeds inventados: los reales traen los casos borde que los sintéticos esconden
—prescripciones compuestas en texto libre, series de más de 12 repeticiones
fuera de la tabla RPE, cargas que cambian entre series del mismo ejercicio.

## Si no tenés la planilla

Los tests del dominio corren igual, no necesitan datos. Los de API se saltan con
un mensaje explicativo. Nada revienta.

## Herramientas

El generador de la app HTML autocontenida vive en `backend/scripts/gen_app.py`,
no acá — es código y se versiona.
