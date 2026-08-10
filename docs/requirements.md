# Requerimientos — Sistema Generador de Horarios

Trazabilidad: **RF-xx → HU-xx** (historias en `user-stories.md`), **RNF-xx** técnicos. Bases: `PLAN.md §5` (reglas de negocio) y `§7` (API).

## 1. Requerimientos funcionales (RF)

### RF-01 Configuración de jornada
El sistema gestiona el registro de jornada con `tipo_jornada`, `dias_laborables`, `hora_inicio/fin` y `minutos_bloque`, y garantiza **una sola configuración activa** (índice único parcial). → **HU-01**
- RF-01.1 Solo una `configs.activa = true` simultánea.

### RF-02 Gestión de docentes
CRUD de docentes con `documento` único y `carga_horaria > 0`; soporta desactivado lógico. → **HU-02**
- RF-02.1 La suma de celdas de un docente no excede su `carga_horaria` (trigger).

### RF-03 Disponibilidad horaria del docente
Mantiene ventanas `(docente, día, hora_inicio, hora_fin)` sin duplicados y valida que toda celda esté dentro de una ventana. → **HU-03**

### RF-04 Cursos / grados
CRUD con `nombre` único, `nivel` y `horas_semanales`; al completar el horario la suma por curso debe igualar `horas_semanales × 60`. → **HU-04**

### RF-05 Materias
CRUD con `categoria ∈ {basica,media_tecnica,otras}`, `min_horas/max_horas`, `requiere_salon`/`tipo_salon_requerido`, `no_ultima_hora`; CHECK coherente. → **HU-05**
- RF-05.1 Estados por categoría según PLAN §5.5 (validado en API, configurable).
- RF-05.2 Una materia con `no_ultima_hora` no queda en el último bloque (trigger).

### RF-06 Salones
CRUD de espacios `aula/laboratorio/sala`; sin choque de salón por `(día, bloque)`. → **HU-06**

### RF-07 Asignaciones docente → materia/curso
Se asignan materias (`docente_materia`) y cursos (`docente_curso`) por docente; la celda valida ambos en su trigger. → **HU-07**

### RF-08 Generación automática (CSP)
El backend arma el horario por satisfacción de restricciones: asignar intensidad por materia (suma = `horas_semanales` del curso), ordenar por restricción y hacer backtracking respetando PLAN §5. Reporta **conflictos sin resolver** si no hay solución. → **HU-08**
- RF-08.1 Cero choques de docente, curso y salón.
- RF-08.2 Mantiene celdas `bloqueadas`.
- RF-08.3 Persiste el horario con su dueño (`usuario_id`).

### RF-09 Vista del horario
Tabla semana × bloques por curso con colores por materia e indicador docente/salón; filtro por docente. → **HU-09**

### RF-10 Edición manual
Seleccionar/arrastrar asignaciones, validar en vivo y bloquear celdas (inmutable para el generador). → **HU-10**

### RF-11 Persistencia y validación
Listar, consultar, validar y exportar horarios guardados; transición a `completo` validada (carga por curso, intensidad, carga docente). → **HU-11**

### RF-12 Autenticación
Registro, login, logout y recuperación de contraseña con Supabase Auth (JWT). → **HU-12**

### RF-13 Aislamiento por usuario
RLS owner-based: `horarios` y `celdas` visibles/escriturables únicamente por `auth.uid()`; catálogos compartidos. → **HU-13**

### RF-API (Endpoints — PLAN §7)
| Endpoint | RF relacionado |
|---|---|
| `POST /horarios/generar` | RF-08 |
| `POST /horarios/{id}/editar` | RF-10 |
| `POST /horarios/validar` | RF-11 |
| `GET /horarios`, `GET /horarios/{id}` | RF-11, RF-13 |
| CRUD `/docentes`, `/cursos`, `/materias`, `/salones`, `/configs` + disponibilidad y asignaciones | RF-02…RF-07 |

## 2. Requerimientos no funcionales (RNF)

- **RNF-01 (Seguridad)**: RLS activa en todas las tablas; `anon` solo SELECT sobre catálogos; `authenticated` limitada por `auth.uid()` en `horarios`/`celdas`; `service_role` bypassa para el generador.
- **RNF-02 (Integridad)**: Reglas entre tablas materializadas por triggers (`sch_celda_validar`, `sch_horario_validar`) en el esquema `schema.sql`.
- **RNF-03 (Secreto)**: Credenciales en `.env`; nunca en repositorio ni en frontend.
- **RNF-04 (Stack)**: Frontend Next.js + TypeScript; backend FastAPI/Pydantic; BD Supabase/Postgres; comunicación REST+JSON.
- **RNF-05 (Rendimiento)**: Generación completa de un horario tipo (≈10 cursos, 30 materias) en menos de **60 s** en hardware estándar; cero choques garantizados.
- **RNF-06 (Funcionalidad en vivo)**: La edición manual valida en <1 s tras cada operación (validación por API).
- **RNF-07 (Mantenibilidad)**: Separación `models/`, `routers/`, `services/`, `scheduler/`; documentación del esquema siempre actualizada en `sql/` del repo backend.
- **RNF-08 (Pristine)**: Compatible con PostgreSQL ≥14 (identidad, `auth.users`, políticas), desplegable en Supabase sin cambios.

## 3. Matriz de trazabilidad

| | HU-01 | HU-02 | HU-03 | HU-04 | HU-05 | HU-06 | HU-07 | HU-08 | HU-09 | HU-10 | HU-11 | HU-12 | HU-13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **PLAN §5 (reglas)** | §5.4 | §5.1 | §5.1 | §5.5 | §5.2/§5.5 | §5.3 | §5.1 | Todos | — | §6.2 | §5.5 | — | RLS |
| **RF** | RF-01 | RF-02 | RF-03 | RF-04 | RF-05 | RF-06 | RF-07 | RF-08 | RF-09 | RF-10 | RF-11 | RF-12 | RF-13 |