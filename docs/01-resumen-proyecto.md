# Generador de Horarios

## Qué es

Sistema web para construir automáticamente la **grilla semanal de clases** de un colegio secundario. A partir de cursos, docentes, materias, salones y disponibilidades, un motor CSP (Constraint Satisfaction Problem) ubica cada bloque de clase en la semana evitando choques de recursos y respetando las reglas institucionales.

El generador acepta celdas fijas (bloques ya reservados con docente, aula, día y hora), distribuye automáticamente la **intensidad horaria** de cada materia por curso y produce la malla completa de horarios.

## Estructura general

| Capa | Tecnología | Rol |
| --- | --- | --- |
| **Frontend** | Next.js (TypeScript, Tailwind) | Interfaz de consulta y visualización de horarios generados |
| **Backend** | FastAPI (Python) | API REST, motor CSP y validación de la malla |
| **Base de datos** | Supabase (PostgreSQL) | Persistencia de cursos, docentes, materias, salones, disponibilidades, configs y celdas |

### Frontend (`horarios-frontend/`)

- Next.js con `app/` router.
- `app/horarios/page.tsx`: pantalla principal que muestra los horarios.
- `lib/api.ts`: cliente HTTP hacia la API del backend.

### Backend (`horarios-backend/`)

- `app/main.py`: aplicación FastAPI y registro de routers.
- `app/routers/`: endpoints REST (`cursos`, `docentes`, `materias`, `salones`, `asignaciones`, `configs`, `horarios`).
- `app/models/`: modelos de datos (Pydantic/SQL) y esquemas de entrada/salida.
- `app/scheduler/`: motor de generación:
  - `intensity.py` — asignación de intensidad horaria por materia (T-016).
  - `solver.py` — CSP con backtracking MRV/Degree/LCV + fallback greedy (T-017…T-029).
  - `validation.py` — validación de la malla generada.
  - `loader.py` — carga del problema desde Supabase.

### Base de datos (Supabase)

PostgreSQL con tablas `cursos`, `docentes`, `materias`, `salones`, `docente_curso`, `docente_materia`, `disponibilidades`, `configs`, `celdas` y `horarios`. La semilla de ejemplo está en `horarios-backend/sql/seed.sql`.