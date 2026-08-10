# Reglas y Restricciones del Generador

> Nota de precisión: la configuración activa en `configs` es **Jornada Única**, Lunes a Viernes de 07:00 a 13:00, con bloques de 60 minutos → **6 bloques por día**. La regla institucional de "salida flexible para 10° y 11°" está contemplada como objetivo de diseño, pero aún no está modelada en la BD ni en el motor (ver sección Jornada).

## Reglas de la jornada

- **Configuración activa (`configs`)**: Jornada Única, días laborables `[1..5]`, 07:00–13:00.
- **Bloques de 60 minutos** (`minutos_bloque = 60`).
- Cálculo de bloques por día: `(13:00 − 07:00) / 60 = 6` bloques completos → **6 bloques/día × 5 días = 30 slots semanales**.
- **Política "no última hora"**: las materias con `no_ultima_hora = true` no pueden ubicarse en el último bloque del día (el solver lo filtra al construir el dominio).
- **Salida flexible para 10° y 11°** (regla institucional): los cursos superiores pueden tener una carga/jornada distinta. Pendiente de implementar como jornada diferencial por nivel.

## Restricciones Duras (Hard)

Solo se evitan **choques por recurso** en cada `(dia, bloque)`. Estas restricciones nunca se violan:

1. Un **docente** no puede estar en dos cursos al mismo tiempo.
2. Un **salón** no puede ser usado por dos cursos al mismo tiempo.
3. Un **curso** no puede tener dos clases en la misma hora.
4. Las celdas `bloqueada = true` (celdas fijas) son inmutables: se ocupan de antemano y el solver nunca las mueve ni las repite.

Además, al construir el dominio de cada celda se exige:
- El docente debe dictar esa materia **y** estar asignado al curso.
- La disponibilidad del docente (`docente_curso` + `disponibilidades`) debe **cubrir el slot completo**.
- El **tipo de salón** acorde al requerido por la materia (`aula`, `laboratorio`, `sala`).

## Restricciones Suaves (Soft)

Se ordenan y **penalizan** la elección de valores, pero **nunca bloquean** la asignación. Si no existe un horario perfecto, el solver entrega la grilla más completa posible y reporta las violaciones como avisos:

- **Carga académica del docente**: preferible no superar `floor(carga_horaria × 60 / minutos_bloque)` bloques semanales. Excederla solo penaliza el orden.
- **Dispersión de materias (§4.3)**: una materia no ocupa más de **2 bloques por día** en un mismo curso (techo suave).
- **Reparto uniforme semanal**: se prefieren los días con menos bloques ya asignados de la misma materia (reparto Lu→Vi).
- **Anti-contigüidad**: se penaliza que dos bloques de la misma materia queden adyacentes el mismo día.

## Algoritmo (resumen)

1. `allocate_intensities` (T-016) decide cuántos bloques semanales recibe cada materia por curso (DP de mochila sobre `[min_horas, max_horas]`).
2. Backtracking CSP con heurísticas **MRV** (variable con menos valores posibles), **Degree** (más interacciones) y **LCV** (valor que deja más margen), con *forward checking* (T-017…T-020).
3. Si se asignan todas las celdas → estado `completo`. Si no → se devuelve la mejor malla parcial con reporte estructurado de conflictos.
4. **Fallback greedy (T-029)**: si el backtracking supera 5 s, se rellenan las celdas restantes respetando solo las restricciones duras para maximizar el llenado de la grilla.