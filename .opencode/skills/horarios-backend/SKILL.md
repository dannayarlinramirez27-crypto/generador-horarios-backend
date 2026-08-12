---
name: horarios-backend
description: Trigger: cambios en horarios-backend, scheduler, solver, intensity, SQL schema/seed/rls, Supabase, FastAPI, generación de horarios, horario parcial. Use ONLY cuando se trabaja en el backend generador de horarios (FastAPI + Supabase). Convenciones y gotchas críticas del proyecto: cómo arrancar, verificar el solver, trampas conocidas y por qué no romperlas.
license: Apache-2.0
metadata:
  author: "project-team"
  version: "1.0"
---

# horarios-backend — Convenciones y gotchas

Guía operativa del backend FastAPI generador de horarios. Léela ANTES de tocar
código, SQL o el scheduler.

## Arranque y verificación

- Backend: `python -m uvicorn app.main:app --reload` (venv `\.venv\Scripts\python.exe`). Swagger: `http://127.0.0.1:8000/docs`. Health: `/api/v1/health`.
- No modifiques `.env` para probar: `DATABASE_URL` es un `SecretStr` de pydantic; en scripts propios usa `settings.database_url.get_secret_value()` (y jamás `conn.cursor(row_factory=...)` si replicas la configuración del pool — ver gotchas).

## Gotchas críticas (NO romper)

1. **Pool sin `row_factory`** (app/db.py): `_load_asignaciones` y `_load_disponibilidades` leen tuplas con `conn.cursor()`. Si conectas con `dict_row`, `for docente_id, materia_id in ...` itera las **claves** del dict y el loader cree que no hay asignaciones → `curso_sin_materias` falso. Nunca agregues `row_factory` al pool ni a esas lecturas.
2. **Greedy y deadline** (app/scheduler/solver.py): `_rellenar_greedy()` comparte `_deadline` con el backtracking; en `solve()` se debe reiniciar `solver._deadline = time.time() + GREEDY_TRIGGER_SEG` antes de llamarlo, o la grilla queda vacía.
3. **Tipo de salón**: el trigger `sch_celda_validar` rechaza materias en salón equivocado — materia sin `requiere_salon` solo admite `tipo='aula'`; con requerimiento, el tipo exacto. `_valores_greedy` debe filtrar por tipo igual que `_constructor_dominio`.
4. **Regeneración** (app/routers/horarios.py POST /generar): al regenerar sobre `horario_id` existente, primero se borran celdas, luego se insertan, y SOLO DESPUÉS se transita el estado a `completo`. Si el estado cambia antes, `sch_horario_validar` valida con 0 celdas y rechaza.
5. **Intensidad por curso** (trigger `sch_horario_validar`): agrupar SIEMPRE por `(materia_id, curso_id)`. Si se agrupa solo por materia en todo el horario, 6 cursos × 5 h = 30 h supera `max_horas` y rechaza un horario correcto (ya corregido en schema.sql y BD — no revertir).

## Contexto del problema

- Jornada: 6 bloques/día × 5 días = 30 slots/curso; 6 cursos (6°A–11°A) × 30 h = 180 celdas → 30 por curso, 30 por bloque.
- Parque actual: 8 salones (5 aulas + 2 laboratorios + 1 sala). Capacidad: 5 aulas × 30 = 150 ≥ 132 (aula); 2 labs × 30 = 60 ≥ 48 (lab). La Sala Múltiple (tipo `sala`) NO sirve para clases regulares.
- Horario válido: estado `completo`, 180 celdas, 0 conflictos, 0 avisos.

## Flujo del motor

1. `loader.load_problem()` → `Problem` (config, cursos, materias, salones, docentes, celdas fijas).
2. `intensity.allocate_intensities()` → bloques por materia dentro de `[min_horas, max_horas]`.
3. `solver.solve()` → backtracking MRV/Degree/LCV + forward checking (ventana `GREEDY_TRIGGER_SEG`) → greedy de completado → `Resultado`.

## Commits

- Conventional commits; nunca Co-Authored-By ni atribución de IA (regla del usuario).