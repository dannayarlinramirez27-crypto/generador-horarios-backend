# Plan de Desarrollo por Sprints — Sistema Generador de Horarios

> Documento maestro de planificación. Detalles en `user-stories.md`, `requirements.md` y `tasks.md`. Base funcional: [PLAN.md](../PLAN.md).

## 1. Visión

Sistema que **genera horarios escolares automáticos e inteligentes** (CSP/backtracking) con **ajuste manual** posterior, para instituciones educativas. Cada usuario autenticado gestiona sus propios horarios (aislamiento por `auth.uid()` vía RLS).

## 2. Alcance

### Dentro (in)
- Registro de entidades: docentes, cursos, materias, salones, jornada/configuración.
- Asignaciones: materias por docente, cursos por docente, disponibilidad horaria.
- Generación automática (satisfacción de restricciones, PLAN §6.1) + validación.
- Edición manual con validación en vivo y bloqueo de celdas (PLAN §6.2).
- Autenticación: registro, login, logout, recuperación de contraseña (Supabase Auth).
- RLS por dueño: cada usuario solo ve/edita sus horarios.
- Persistencia y consulta de horarios guardados.

### Fuera (out)
- Chat/redes sociales, importación masiva por planillas, notificaciones.
- Gestión multi-institución en una misma cuenta.
- Optimización por función objetivo avanzada (equilibrio de horas por docente, preferencias), más allá de cero choques.

## 3. Stack

| Capa | Tecnología |
|---|---|
| Frontend | Next.js (React + TypeScript) + Tailwind |
| Backend | Python + FastAPI (Pydantic) |
| Base de datos | Supabase / PostgreSQL (RLS + triggers) |
| Autenticación | Supabase Auth (JWT) |
| Algoritmo | CSP + backtracking (`horarios-backend/app/scheduler/`) |

## 4. Backlog priorizado (historias de usuario)

Ver detalle completo en `user-stories.md`. Estimación: puntos Fibonacci + horas.

| HU | Historia | Puntos | Sprint |
|----|----------|:------:|:------:|
| HU-01 | Configuración de jornada y políticas | 3 | S1 |
| HU-02 | CRUD Docentes (carga académica) | 3 | S1 |
| HU-03 | Disponibilidad del docente | 3 | S1 |
| HU-04 | CRUD Cursos / grados | 2 | S1 |
| HU-05 | CRUD Materias (rango + políticas) | 3 | S1 |
| HU-06 | CRUD Salones | 1 | S1 |
| HU-07 | Asignación docente → materias/cursos | 3 | S1 |
| HU-08 | Generación automática del horario | 13 | S2 |
| HU-09 | Vista del horario por curso y por docente | 8 | S3 |
| HU-10 | Edición manual con validación en vivo | 8 | S3 |
| HU-12 | Autenticación (registro/login/logout) | 5 | S3 |
| HU-11 | Persistencia, validación y exportación | 5 | S4 |
| HU-13 | Aislamiento por usuario (RLS owner) | 3 | S4 |
| **Total** | | **60** | |

## 5. Sprints

### S1 — Entorno, datos y CRUD (~45 h)
Objetivo: plataforma lista con esquema, RLS y API de entidades.
- Historia: HU-01…HU-07.
- Entregables: proyecto Supabase con `schema.sql` + `rls.sql` aplicados, esqueleto FastAPI, CRUD completo, datos semilla.
- DoD: CRUD probado vía Swagger con datos reales e integridad (triggers) verificada.

### S2 — Motor generador (~43 h)
Objetivo: algoritmo CSP sin choques ni conflictos.
- Historia: HU-08 (+ validación §5).
- Entregables: módulo `scheduler/`, endpoints `generar`, `validar`, `editar`, reporte de conflictos.
- DoD: suite de pruebas del algoritmo (cruces, última hora, salón, carga, jornada) en verde.

### S3 — Autenticación y Frontend (~48 h)
Objetivo: UI completa de registro, formularios, generación y vista/edición.
- Historias: HU-09, HU-10, HU-12.
- Entregables: scaffolding Next.js, auth Supabase, formularios CRUD, pantalla de generación, vista semana×bloques, edición manual.
- DoD: flujo completo usuario → generar → editar funciona de punta a punta.

### S4 — Integración, seguridad y entrega (~24 h)
Objetivo: Cerrar RLS por dueño, pruebas E2E y documentación.
- Historias: HU-11, HU-13.
- Entregables: exportación, checks de aislamiento, pruebas regresión E2E, README y guía de despliegue.
- DoD: caso E2E completo aprobado y documentación lista.

**Total estimado: ~160 h.**

## 6. Dependencias clave

- `schema.sql` + `rls.sql` deben aplicarse **antes** de cualquier CRUD (S1).
- El motor CSP (S2) requiere datos válidos del S1 (intensidad, disponibilidad, asignaciones).
- La edición manual (HU-10) consume `POST /horarios/{id}/editar` del S2.
- El aislamiento por usuario (S4) asume la columna `horarios.usuario_id` de S1.

## 7. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Problema CSP puede no tener solución completa | Alto | Reporte de conflictos para ajuste manual (PLAN §6.1). |
| Triggers RLS bloquean ediciones válidas | Medio | Suite de pruebas SQL antes del frontend. |
| Volumen de celdas grande degrada el generador | Medio | Ordenamiento por restricción + heurísticas; optimización incremental. |
| Dependencia de Supabase en pruebas locales | Medio | Plan de pruebas con Postgres local (`docker`) y Supabase en QA. |

## 8. Definición de Listo (DoD)

- Código revisado, sin comentarios muertos, estilo consistente.
- Pruebas del algoritmo/de restricciones en verde.
- Endpoint/documento validado contra el esquema real.
- Ruta del usuario cubierta en la vista correspondiente.
- No se registran cambios en tablas o RLS sin actualizar `schema.sql`/`rls.sql`.