# Avances de Hoy

Registro de lo realizado en la sesión de hoy.

## Carga de 6 cursos (6°A a 11°A)

- Se incorporaron los 6 cursos del colegio: **6°A, 7°A, 8°A, 9°A, 10°A y 11°A**.
- Cada curso cursa **30 horas semanales** y ocupa los 30 slots de la jornada (5 días × 6 bloques de 60 min).
- El plan de intensidades (`allocate_intensities`, T-016) distribuye las materias por curso respetando los rangos `[min_horas, max_horas]`.
- Con 6 cursos en paralelo, el motor debe ubicar hasta 180 celdas; la infraestructura disponible (5 salones) define el techo alcanzable por slot.

## Optimización del solver con límite de tiempo (30 s)

- El backend quedó con un **límite de tiempo interno de 30 segundos** (`TIME_LIMIT_SEG`) para no bloquear el hilo del endpoint en búsquedas grandes.
- La búsqueda CSP (backtracking MRV/Degree/LCV + forward checking) se ejecuta en una **ventana acotada de 5 segundos** (`GREEDY_TRIGGER_SEG`): si no termina en ese tiempo, se abandona y se pasa al completado greedy.
- Heurísticas vigentes: MRV con desempate por Degree y **balance de llenado entre cursos** (evita que un par de cursos acapare aulas/salones; T-028).

## Fallback greedy para asegurar mallas llenas (T-029)

- Nueva etapa de **completado greedy**: rellena las celdas restantes a partir del mejor parcial guardado por el backtracking.
- El greedy respeta **únicamente las restricciones duras** (sin choques de docente, de aula ni de curso en cada `(dia, bloque)`), garantizando una grilla **sin conflictos duros**.
- Se relaja en esta etapa el tipo de salón requerido por la materia (cualquier salón sirve) y las restricciones suaves, para maximizar el llenado de la malla.
- Verificación de cambios: compilación OK (`py_compile`) y reinicio del servidor uvicorn en segundo plano (127.0.0.1:8000).

## Pendientes / observaciones

- La regla de **salida flexible para 10° y 11°** aún no está modelada (jornada diferencial por nivel).
- La malla "completa" (180 celdas, estado `completo`) depende de que existan suficientes salones para 6 clases simultáneas; con el parque actual de 5 salones, algunas celdas pueden quedar como conflictos estructurales y el estado resultante es `parcial`.