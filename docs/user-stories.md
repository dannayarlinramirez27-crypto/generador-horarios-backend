# Historias de Usuario — Sistema Generador de Horarios

Formato: `En calidad de [rol], quiero [acción], para [beneficio].` · Estimación en **puntos Fibonacci**. Sprint asignado según `sprint-plan.md`. Referencias: `PLAN.md §5` (restricciones) y `schema.sql` (tablas).

---

## HU-01 — Configuración de jornada y políticas
**Usuario:** Administrador.
**Como** administrador **quiero** definir la jornada (mañana/tarde/única), los días laborables, la hora de inicio/fin y la duración del bloque **para** que el generador respete el marco horario de la institución.
- Puntos: **3** · Sprint: **S1**

Criterios de aceptación:
- CA-01: Solo puede existir **una** configuración activa a la vez.
- CA-02: Se persiste en `configs` con `tipo_jornada ∈ {manana, tarde, unica}`, `dias_laborables ⊆ {1..7}` y `hora_fin > hora_inicio`.
- CA-03: El cambio de configuración activa desactiva automaticmente la anterior (índice único parcial).
- CA-04: Materialización: reglas `§5.4` (nada fuera de jornada/días laborables) se aplican en el trigger `sch_celda_validar`.

## HU-02 — CRUD Docentes con carga académica
**Usuario:** Administrador.
Quiero registrar, editar, consultar y desactivar docentes con su **carga horaria contractual** para conocer la disponibilidad de horas de cada profesor.
- Puntos: **3** · Sprint: **S1**

Criterios de aceptación:
- CA: `documento` es único; `carga_horaria > 0`.
- CA: Un docente desactivado no aparece en listados por defecto y no recibe asignaciones nuevas del generador.
- CA: La carga programada (suma de celdas del docente) no excede `carga_horaria` (trigger §11.1).

## HU-03 — Disponibilidad horaria del docente
Quiero marcar los días/horas en que cada docente puede dictar clase, para que el generador solo lo ubique en esas ventanas.
- Puntos: **3** · Sprint: **S1**

Criterios de aceptación:
- CA: Nueva ventana en `disponibilidades` (día + `hora_inicio` + `hora_fin`) validada contra la jornada.
- CA: No se registran ventanas duplicadas para el mismo docente/día/hora.
- CA: Toda celda programada debe estar contenida en una ventana del docente (trigger §3.1); si no, error de validación.

## HU-04 — CRUD Cursos / grados
- Quiero registrar grados (6.º, 7.º…) con `nivel` y `horas_semanales` (30 / 37) para que el generador cuadre la carga semanal de cada curso.
- Puntos: **2** · Sprint: **S1**

Criterios de aceptación:
- CA: `nombre`, `nivel` y `horas_semanales > 0` obligatorios; `nombre` único.
- CA: `§5.5`: al marcar el horario como `completo`, la suma de minutos del curso debe `= horas_semanales × 60` (trigger `sch_horario_validar`).

## HU-05 — CRUD Materias con rango de intensidad y políticas
- Quiero registrar materias con `categoría` (básica/media técnica/otras), `min_horas`/`max_horas`, `requiere_salon` (+tipo) y `no_ultima_hora`, para que el generador respete la intensidad y las políticas institucionales.
- Puntos: **3** · Sprint: **S1**

Criterios de aceptación:
- CA: `categoria ∈ {basica,media_tecnica,otras}`; `min_horas ≥ 1` y `max_horas ≥ min_horas`.
- CA: Si `requiere_salon = true`, `tipo_salon_requerido ∈ {laboratorio, sala}` es obligatorio; si false, `null` (CHECK en tabla).
- CA: `§5.2` no programar en la última hora cuando `no_ultima_hora = true`; `§5.2/§5.3` tipo de espacio respetado.
- CA: `§5.5` intensidad dentro de `[min_horas, max_horas]` por materia al `completo`.

## EU-06 — CRUD Salones
- Quiero registrar espacios `aula`/`laboratorio`/`sala` con capacidad, para asignar cada materia a su lugar correcto.
- Puntos: **1** · Sprint: **S1**

Criterios de aceptación:
- CA: `nombre` único y `tipo` válido.
- CA: Sin choque de salón: dos celdas del mismo horario no ocupan el mismo salón en el mismo `(día, bloque)` (UNIQUE en `celdas`).

## EU-07 — Asignación docente → materias y cursos
- Quiero asignarle a cada docente las materias que puede dictar y los cursos de su cargo, para que el generador solo coloque asignaciones legítimas.
- Puntos: **3** · Sprint: **S1**

Criterios de aceptación:
- CA: Sitios en `docente_materia` y `docente_curso` sin duplicados.
- CA: `§5.1`: toda celda debe tener `(docente, materia)` en `docente_materia` y `(docente, curso)` en `docente_curso` (trigger).

## HU-08 — Generación automática del horario (CSP)
**Usuario:** Administrador/Secretaria.
Quiero pulsar un botón "Generar horario" y que el sistema arme el horario completo **sin choques ni huecos de carga** respetando las restricciones de PLAN §5, para no hacerlo a mano.
- Puntos: **13** · Sprint: **S2**

Criterios de aceptación:
- CA: Asigna intensidad por materia dentro de `[min,max]` de modo que la suma por curso = `horas_semanales`.
- CA: Cero choques de docente, curso y salón en el mismo `(día, bloque)`.
- CA: Respeta disponibilidad, carga docente, `no_ultima_hora`, tipo de salón, jornada y días laborables.
- CA: Si no existe solución completa, devuelve **reporte de conflictos** (dónde falló) y marca horario `parcial`.
- CA: Persiste el horario con su `usuario_id` (dueño), ya sea `completo`/`parcial`.

## HU-09 — Vista del horario por curso y filtro por docente
- Quiero ver el horario como tabla semana × bloques por curso, con colores por materia y el docente/salón indicados, y filtrar por docente, para consultarlo fácilmente.
- Puntos: **8** · Sprint: **S3**

Criterios de aceptación:
- CA: Tabla con día en filas/columnas según jornada (config) y bloques correspondientes.
- CA: Cada celda muestra materia + docente + salón, con color distinto por materia.
- CA: Filtro por docente muestra solo los bloques donde ese docente dicta clase.
- CA: Vista según `usuario_id`: solo se accede a horarios propios (RLS).

## HU-10 — Edición manual de celdas con validación en vivo y bloqueo
- Quiero arrastrar/seleccionar una asignación y colocarla en un día/bloque, o bloquear celdas para que el generador no las toque, para ajustar el horario a mano con seguridad.
- Puntos: **8** · Sprint: **S3**

Criterios de aceptación:
- CA: Cada edición envía a `POST /horarios/{id}/editar` y devuelve la lista de avisos/errores en tiempo real.
- CA: No se guardan ediciones que violen choques (docente/curso/salón), disponibilidad, materia no autorizada, espacio o `no_ultima_hora`.
- CA: Celdas `bloqueada=true` no son modificadas por el generador automático.
- CA: Solo el dueño del horario puede editar (RLS).

## HU-11 — Persistencia, validación y exportación de horarios
- Quiero guardar, listar y consultar horarios históricos, validarlos de nuevo y exportarlos/imprimir, para mantener el registro institucional.
- Puntos: **5** · Sprint: **S4**

Criterios de aceptación:
- CA: `GET /horarios` y `GET /horarios/{id}` devuelven solo horarios del usuario.
- CA: `POST /horarios/validar` devuelve restricciones incumplidas.
- CA: Exportación visual limpia (print/PDF) de la vista del horario.
- CA: Marcar `completo` ejecuta el trigger `sch_horario_validar` (carga por curso/intensidad/carga docente).

## HU-12 — Autenticación: registro, login, logout, recuperación
- Quiero registrarme, iniciar y cerrar sesión y recuperar mi contraseña, para gestionar mis horarios de forma privada.
- Puntos: **5** · Sprint: **S3**

Criterios de aceptación:
- CA: Registro guarda el usuario y su JWT de Supabase; `auth.uid()` se usa en horarios insertados.
- CA: Sesión persistente; rutas del generador requieren sesión (guarda en el frontend).
- CA: Flujo de recuperación de contraseña vía correo (Supabase Auth).

## HU-13 — Aislamiento por usuario (RLS por dueño)
- Quiero que cada usuario vea y edite **únicamente** sus propios horarios (y sus celdas), para que los datos de una institución no se mezclen con otras.
- Puntos: **3** · Sprint: **S4**

Criterios de aceptación:
- CA: `horarios.usuario_id = auth.uid()` aplicado a SELECT/INSERT/UPDATE/DELETE por RLS.
- CA: `celdas` accesibles solo si su horario pertenece al usuario (subquery sobre `horarios`).
- CA: Un usuario `B` obtiene 0 filas y errores de insert sobre horarios de usuario `A`.
- CA: `anon` no accede a horarios/celdas; catálogos son compartidos.