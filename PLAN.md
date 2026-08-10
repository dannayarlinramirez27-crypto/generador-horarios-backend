# Plan de Desarrollo — Sistema Generador de Horarios

## 1. Objetivo

Construir un sistema que genere **horarios escolares automáticos e inteligentes** a partir de los datos y restricciones de la institución, con opción de **ajuste manual** posterior.

**Entidades del dominio (colegios):**

| Entidad | Descripción |
|---------|-------------|
| **Docente** | Profesor que dicta clases; guarda su carga académica contractual y su disponibilidad. |
| **Curso / Grado** | Grupo a quien se enseña (6.º, 7.º, 8.º …) con **nivel** y **carga horaria semanal total** (ej. 6–9 → 30 h, 10–11 → 37 h, configurable). |
| **Materia / Asignatura** | Disciplina con **categoría** (básica / media técnica / otras) y **rango de intensidad** semanal (ej. Matemáticas → 3–5 h). |
| **Salón / Laboratorio** | Espacio físico; algunos son especiales según la materia. |
| **Jornada** | Mañana, Tarde o Jornada única (define horas del día y días de clase). |

**Datos que definen el horario:**

| Dato | Ejemplo |
|------|---------|
| **Carga académica del docente** | N.º de horas de clase que debe cumplir según su contrato. |
| **Disponibilidad horaria** | Horas y días en que el docente puede dictar clases. |
| **Materias asignadas** | Cada profesor solo dicta las materias para las que está capacitado/designado. |
| **Cursos o grados** | Los grupos a los que debe enseñar (6.º, 7.º, 8.º…). |
| **Intensidad horaria de cada materia** | Cantidad de horas semanales que requiere cada asignatura (dentro de un rango: básica 3–5, media técnica 3–4, otras 1–2). |
| **Jornada escolar** | Mañana, tarde o jornada única. |
| **Disponibilidad de aulas/laboratorios** | Materias que necesitan espacios específicos. |

---

## 2. Arquitectura

```
Frontend (Next.js)  ⇄  Backend (FastAPI)  ⇄  Base de datos (Supabase/Postgres)
```

### Stack

| Capa | Tecnología |
|------|------------|
| **Frontend** | Next.js (React + TypeScript) |
| **Backend** | Python + FastAPI |
| **Base de datos** | Supabase (relacional, Postgres) |
| **Comunicación** | REST + JSON (Pydantic para validación) |

---

## 3. Estructura de proyectos

El sistema se divide en **dos proyectos independientes** (cada uno con su propio repositorio, dependencias y despliegue), no en un monorepo:

```
horarios-backend/               # ★ Backend FastAPI (repo 1)
├── app/
│   ├── main.py                 # Arranque y routers
│   ├── config.py               # Credenciales y configuración
│   ├── db.py                   # Cliente de Postgres/Supabase
│   ├── models/                 # Schemas Pydantic
│   ├── routers/                # Endpoints REST
│   ├── services/               # Lógica de negocio
│   └── scheduler/              # ★ ALGORITMO generador de horarios
├── sql/                        # schema.sql, rls.sql, migraciones
├── tests/
├── requirements.txt
└── .env

horarios-frontend/              # ★ Frontend Next.js (repo 2)
├── app/                        # Páginas/rutas
├── components/                 # UI (formularios, calendario, tabla)
├── lib/api.ts                  # Cliente HTTP del backend
└── package.json
```

Los dos repos se comunican **solo vía API REST** (CORS configurado en el backend). La documentación y el esquema SQL viven en el repo del backend.

---

## 4. Base de datos (modelo)

| Tabla | Función |
|-------|---------|
| `docentes` | Profesor + **carga académica** (horas de contrato) y **disponibilidad** (días/horas). |
| `cursos` | Grupos/grados a los que se enseña (6.º, 7.º, 8.º…) con **nivel** y **horas_semanales**. |
| `materias` | Asignatura con **categoría** (básica/media técnica/otras), intensidad **en rango** (`min_horas`/`max_horas`), `requiere_salon` (si ocupa laboratorio/sala) y `no_ultima_hora`. |
| `docente_materia` | **Materias asignadas**: qué materias puede dictar cada docente. |
| `disponibilidades` | Ventanas horarias por docente (día + hora_inicio + hora_fin). |
| `salones` | Espacios físicos, con tipo (`aula` / `laboratorio` / `sala`). |
| `configs` | **Jornada**: hora inicio/fin (mañana/tarde/única), días laborables, duración de bloque. |
| `horarios` | **Resultado**: celda `(curso, materia, docente, salon, dia, bloque, hora_inicio, hora_fin)`. |

> Las restricciones imprescindibles del punto 5 se materializan como **foreign keys y checks** (desde la BD) y como **comprobaciones del algoritmo** (al generar).

---

## 5. Restricciones del sistema

El generador debe **siempre** cumplir las siguientes reglas (son el corazón del modelo):

### 5.1 Relacionadas con docentes
- **Cruces de horario**: un docente no puede estar asignado a dos cursos al mismo tiempo.
- **Disponibilidad**: debe respetarse la disponibilidad horaria (días y horas) de cada docente.
- **Materias asignadas**: un docente solo dicta las materias para las que fue designado.
- **Carga académica**: las horas programadas del docente no deben superar (y idealmente han de cumplirse acorde a) su carga contractual.
- **Cursos**: un docente solo puede ser asignado a los cursos que le corresponde dar.

### 5.2 Relacionadas con las materias
- **Intensidad horaria**: cada materia debe cumplir su número de horas semanales.
- **Última hora**: algunas materias **no deben programarse en la última hora** de la jornada (política institucional configurable).
- **Espacios especiales**: si una materia requiere laboratorio/sala, solo se asigna a esos espacios.

### 5.3 Relacionadas con los salones
- **Sin choque de salón**: dos cursos no pueden ocupar el **mismo salón a la misma hora**.
- **Tipo de espacio**: los laboratorios/salas solo se asignan a materias que los requieren.

### 5.4 Generales / Jornada
- Ninguna clase fuera de la jornada y de los días laborables.
- Un curso no recibe dos clases en el mismo bloque.

### 5.5 Carga e intensidad por nivel
- **Rango de intensidad por materia**: cada materia se programa con un número de horas dentro de su rango según su categoría:
  - Básica: **3–5 h** semanales.
  - Media técnica (7.º con división): **3–4 h** (materias intensivas).
  - Otras / apoyo: **1–2 h**.
- **Carga semanal por curso**: la suma de horas de todas las materias de un curso debe **igualar** su `horas_semanales` (p. ej. grados 6–9 → 30 h; media técnica 10–11 → 37 h; configurable por institución). El generador elige valores dentro de los rangos hasta cuadrar el total, sin pasar ni faltar.

---

## 6. Modos de generación — Automático e Inteligente + Manual

Hay **dos modos de trabajo** que se complementan:

### 6.1 Modo automático (`horarios-backend/app/scheduler/`)

Generador **automático e inteligente** mediante **satisfacción de restricciones (CSP)**:

1. **Leer datos** → docentes, cursos, materias, salones, disponibilidad, jornada.
2. **Asignar intensidad** → elegir cuántas horas se da cada materia dentro de `[min,max]` (por categoría) de modo que la suma por curso = `horas_semanales`; luego fragmentar en bloques.
3. **Ordenar** → planificar primero lo más restrictivo (menos disponibilidad / más horas / espacios limitados).
4. **Backtracking** → asignar docente+materia+curso+salón por día/bloque **respetando las restricciones del punto 5**.
5. **Imposibilidad** → si no hay solución completa, se reportan los conflictos sin resolver para ajuste manual.

**Garantías:** mínimos huecos y **cero choques** (docente, curso y salón).

### 6.2 Modo manual

Permite **editar y construir el horario a mano** sobre la misma vista:

- Rellenar/corregir celdas de forma directa (arrastrar o **seleccionar una asignación** y colocarla en un día/bloque).
- Después de cada edición, el sistema **valida el punto 3 en tiempo real** y muestra avisos/errores.
- Opciones:
  - **Generar** automáticamente y luego **ajustar** manualmente.
  - **Empezar en blanco** y construir 100 % a mano.
  - **Bloquear** celdas para que el generador automático no las toque (edición mixta).

**Modelo de estado del horario (mutable):**

```
celda = { curso_id, materia_id, docente_id, salon_id, dia, bloque,
          bloqueada, hora_inicio, hora_fin }
```

Cada operación manual dispara una validación y devuelve la lista de avisos/errores.

---

## 7. API Backend (FastAPI)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `POST` | `/horarios/generar` | Genera horario automático (CSP) |
| `POST` | `/horarios/{id}/editar` | Guarda/actualiza una celda (modo manual) |
| `POST` | `/horarios/validar` | Valida restricciones de un estado actual |
| `GET` | `/horarios` | Lista horarios guardados |
| `GET` | `/horarios/{id}` | Consulta un horario |
| CRUD | `/docentes` | Gestionar docentes (carga académica + disponibilidad) |
| CRUD | `/cursos` | Gestionar cursos/grados |
| CRUD | `/materias` | Gestionar materias (intensidad horaria) |
| CRUD | `/salones` | Gestionar salones/laboratorios |
| CRUD | `/configs` | Configurar jornada/días/bloques/políticas |

---

## 8. Frontend (Next.js)

- **Registro de entidades**: formularios para docentes, cursos, materias, salones y configuración de jornada.
- **Disponibilidad docente**: pantalla para marcar horas/días disponibles y materias asignadas.
- **Configuración**: elegir Mañana / Tarde / Jornada única, días, duración de bloque y políticas (materias que no van en la última hora).
- **Generación**: botón "Generar horario".
- **Vista del horario**: tabla semana × bloques por curso, con colores por materia, indicador de salón/docente, validación en vivo y opción de imprimir/exportar.

---

## 9. Persistencia

Todo horario generado (y sus ediciones manuales) se **guarda en Supabase** para poder consultarlo y regenerarlo más adelante.

---

## 10. Pasos de implementación

1. **Esqueleto backend** → estructura FastAPI + configuración + script SQL de tablas.
2. **Modelo de datos** → script/migración SQL para Supabase (tablas + FKs + checks del punto 3).
3. **CRUD de entidades** → endpoints de docentes, cursos, materias, salones y configs.
4. **Restricciones + algoritmo** → motor CSP que aplica el punto 3 + endpoints de generación, validación y edición.
5. **Frontend** → scaffolding Next.js + formularios → Jornada → Generar → Ver/Editar horario.
6. **Integración y pruebas** → script de pruebas del algoritmo (casos de cruce, última hora, salón, etc.) + prueba end-to-end.

---

## 11. Decisiones por confirmar

1. **Conexión con Supabase**: ¿Postgres directo (psycopg2) o SDK de Supabase en Python? → Recomendado: **Postgres directo** (simple, sin claves de servicio expuestas).
2. **Duración del bloque**: ¿Configurable por institución (45 min, 1 h, etc.)? → Asumido sí.
3. **Vista del horario**: ¿por curso (vista clásica "tengo clases") o por docente (vista "dónde dicto")? → Asumido: **por curso** como principal, con filtro por docente.