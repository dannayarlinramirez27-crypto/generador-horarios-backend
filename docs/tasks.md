# Desglose de Tareas por Sprint — Sistema Generador de Horarios

Formato: `T-xxx` · **Horas estimadas** · Sprint · Dependencias (`← T-ooo`). DoD común: código revisado, pruebas verdes, sin secretos en el repo. Totales aproximados según `sprint-plan.md`.

## S1 — Entorno, datos y CRUD (~45 h)

| ID | Tarea | Horas | Dependencias |
|----|-------|:-----:|--------------|
| T-001 | Crear los dos proyectos: `horarios-backend` (FastAPI) y `horarios-frontend` (Next.js), con README base | 3 | — |
| T-002 | Crear proyecto Supabase y aplicar `schema.sql` (con `horarios.usuario_id`) | 3 | ← T-001 |
| T-003 | Aplicar `rls.sql` (owner-based) y verificar acceso por rol (anon/authenticated/service_role) | 2 | ← T-002 |
| T-004 | Esqueleto FastAPI: `main.py`, `config.py`, `db.py`, CORS, manejo de errores | 4 | ← T-001 |
| T-005 | Modelos Pydantic de todas las entidades (`models/`) | 5 | ← T-004 |
| T-006 | CRUD `/docentes` + disponibilidades | 4 | ← T-004, T-005 |
| T-007 | CRUD `/cursos` | 2 | ← T-006 |
| T-008 | CRUD `/materias` | 2 | ← T-006 |
| T-009 | CRUD `/salones` | 2 | ← T-006 |
| T-010 | CRUD `/configs` (jornada/políticas; transición de config activa) | 2 | ← T-006 |
| T-011 | Endpoints de asignación `docente_materia` / `docente_curso` | 4 | ← T-006 |
| T-012 | Datos semilla (seed) representativos | 2 | ← T-010 |
| T-013 | Afinar validación Pydantic y mensajes de error claros | 3 | ← T-005 |
| T-014 | Pruebas de CRUD e integridad (triggers §11) en verde | 5 | ← toda la serie |

**Totales S1: 45 h** — Historias: HU-01…HU-07.

## S2 — Motor generador (CSP ~43 h)

| ID | Tarea | Horas | Dependencias |
|----|------|:-----:|--------------|
| T-015 | Módulo `scheduler/`: carga de datos y modelo de asignación | 5 | ← T-014 |
| T-016 | Asignación de intensidad: elegir horas por materia dentro de `[min,max]` con suma = `horas_semanales` por curso | 5 | ← T-015 |
| T-017 | Ordenamiento por restricción (menos disponible, más horas, espacios limitados) | 4 | ← T-015 |
| T-018 | Backtracking con restricciones PLAN §5 (choques, disponibilidad, espacio, última hora, jornada, carga) | 8 | ← T-016, T-017 |
| T-019 | Celdas `bloqueadas` tratadas como fijas en el backtracking | 2 | ← T-018 |
| T-020 | Reporte de conflictos sin resolver y estado `parcial` | 3 | ← T-018 |
| T-021 | `POST /horarios/generar` (create horario con `usuario_id`, ejecutar y persistir) | 3 | ← T-018 |
| T-022 | `POST /horarios/validar` (revalidación del estado actual) | 3 | ← T-014, T-018 |
| T-023 | `POST /horarios/{id}/editar` (celda individual) | 4 | ← T-022 |
| T-024 | `GET /horarios` y `GET /horarios/{id}` | 2 | ← T-021 |
| T-025 | Pruebas del algoritmo: choques, última hora, salón, carga, jornada, celdas bloqueadas | 8 | ← T-018 |

**Totales S2: 43 h** — Historia: HU-08.

## S3 — Autenticación y Frontend (~48 h)

| ID | Tarea | Horas | Dependencias |
|----|------|:-----:|--------------|
| T-026 | Scaffolding Next.js + Tailwind + `lib/api.ts` (cliente HTTP) | 5 | ← T-014 |
| T-027 | Autenticación: registro, login, logout, recuperación y guardas de ruta | 6 | ← T-026 |
| T-028 | Formulario de configuración de jornada/políticas | 4 | ← T-010 |
| T-029 | CRUD Docentes + pantalla de disponibilidad (matriz días×horas) | 5 | ← T-006, T-027 |
| T-030 | CRUD Cursos | 2 | ← T-007, T-027 |
| T-031 | CRUD Materias | 3 | ← T-008, T-027 |
| T-032 | CRUD Salones | 2 | ← T-009, T-027 |
| T-033 | Pantalla de asignaciones docente → materias/cursos | 3 | ← T-029, T-011 |
| T-034 | Botón "Generar horario" + manejo de resultados/conflictos | 4 | ← T-033, T-021 |
| T-035 | Vista del horario por curso (tabla semana × bloques, colores por materia, filtro por docente) | 8 | ← T-034 |
| T-036 | Edición manual: seleccionar/arrastrar asignación, validación de carga, bloqueo de celdas | 6 | ← T-035, T-023 |

**Totales S3: 48 h** — Historias: HU-09, HU-10, HU-12.

## S4 — Integración, seguridad y entrega (~24 h)

| ID | Tarea | Horas | Dependencias |
|----|------|:-----:|--------------|
| T-037 | Suite de integración SQL: triggers + RLS (regresión) | 4 | ← T-003, T-025 |
| T-038 | Prueba E2E frontend → backend → Supabase (login → generar → editar → validar) | 6 | ← T-036 |
| T-039 | Verificación de aislamiento por usuario: usuario B no ve/edita horario de A | 3 | ← T-003, T-027 |
| T-040 | Exportación/impresión del horario (vista limpia PDF/print) | 3 | ← T-035 |
| T-041 | README final, guía de despliegue (Supabase + FastAPI + Next.js) | 2 | ← T-040 |
| T-042 | Datos demo, limpieza y regeneración de evaluaciones | 2 | ← T-041 |
| T-043 | Optimización del generador y no-regresión con horario grande | 4 | ← T-038 |

**Totales S4: 24 h** — Historias: HU-11, HU-13.

---

## Resumen

| Sprint | Objetivo | Historias | Horas |
|--------|----------|-----------|:-----:|
| S1 | Esquema + RLS + CRUD de entidades | HU-01…HU-07 | 45 |
| S2 | Motor CSP + endpoints | HU-08 | 43 |
| S3 | Auth + frontend completo | HU-09, HU-10, HU-12 | 48 |
| S4 | Aislamiento, E2E y entrega | HU-11, HU-13 | 24 |
| **Total** | | | **~160 h** |