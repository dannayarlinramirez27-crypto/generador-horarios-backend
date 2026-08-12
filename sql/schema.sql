-- ============================================================================
-- Esquema de Base de Datos — Sistema Generador de Horarios
-- Motor: PostgreSQL (Supabase) · Convención: snake_case, días 1=Lu a 7=Do
--
-- Las restricciones del PLAN §5 se materializan en la BD así:
--   - FKs, UNIQUE y CHECK  → FKs (integridad), CHECK (valores), UNIQUE (choques).
--   - TRIGGERS             → reglas entre tablas (autorización, disponibilidad,
--                            tipo de salón, políticas de jornada, completitud).
-- ============================================================================
BEGIN;

-- 1. JORNADA / CONFIGURACIÓN (políticas institucionales)
CREATE TABLE IF NOT EXISTS configs (
    id                integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre            text NOT NULL DEFAULT 'Configuración general',
    tipo_jornada      text NOT NULL CHECK (tipo_jornada IN ('manana','tarde','unica')),
    dias_laborables   smallint[] NOT NULL DEFAULT '{1,2,3,4,5}'
                      CHECK (dias_laborables <@ ARRAY[1,2,3,4,5,6,7]::smallint[]),
    hora_inicio       time NOT NULL,
    hora_fin          time NOT NULL CHECK (hora_fin > hora_inicio),
    minutos_bloque    smallint NOT NULL DEFAULT 60 CHECK (minutos_bloque > 0),
    activa            boolean NOT NULL DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now()
);
-- Solo una configuración activa a la vez
CREATE UNIQUE INDEX IF NOT EXISTS uidx_configs_activa ON configs (activa) WHERE activa = true;

-- 2. DOCENTES (con carga académica contractual)
CREATE TABLE IF NOT EXISTS docentes (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre        text NOT NULL,
    apellido      text NOT NULL,
    documento     text NOT NULL UNIQUE,
    telefono      text,
    email         text UNIQUE,
    carga_horaria integer NOT NULL CHECK (carga_horaria > 0),
    activo        boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- 3. CURSOS / GRADOS (nivel + carga horaria semanal)
CREATE TABLE IF NOT EXISTS cursos (
    id             integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre         text NOT NULL UNIQUE,               -- ej: 6°A
    nivel          text NOT NULL,                      -- ej: 6, 7, 10
    horas_semanales integer NOT NULL CHECK (horas_semanales > 0),  -- 30 / 37
    orden          smallint NOT NULL DEFAULT 0
);

-- 4. MATERIAS (categoría + rango de intensidad + políticas)
--    §5.5 Intensidad en rango por categoría se valida también en la API
--    (configurable por institución); aquí se garantiza min <= max.
CREATE TABLE IF NOT EXISTS materias (
    id                   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre               text NOT NULL UNIQUE,
    categoria            text NOT NULL CHECK (categoria IN ('basica','media_tecnica','otras')),
    min_horas            smallint NOT NULL DEFAULT 3 CHECK (min_horas >= 1),
    max_horas            smallint NOT NULL DEFAULT 5 CHECK (max_horas >= min_horas),
    requiere_salon       boolean NOT NULL DEFAULT false,
    tipo_salon_requerido text CHECK (tipo_salon_requerido IN ('laboratorio','sala')),
    no_ultima_hora       boolean NOT NULL DEFAULT false,   -- política "no última hora"
    -- §5.2 Espacios especiales: si requiere salón, debe indicar su tipo.
    CHECK ((requiere_salon AND tipo_salon_requerido IS NOT NULL)
        OR (NOT requiere_salon AND tipo_salon_requerido IS NULL))
);

-- 5. SALONES / LABORATORIOS
CREATE TABLE IF NOT EXISTS salones (
    id        integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre    text NOT NULL UNIQUE,
    tipo      text NOT NULL CHECK (tipo IN ('aula','laboratorio','sala')),
    capacidad integer NOT NULL DEFAULT 0 CHECK (capacidad >= 0),
    activo    boolean NOT NULL DEFAULT true
);

-- 6. DISPONIBILIDADES (ventanas horarias de cada docente)
CREATE TABLE IF NOT EXISTS disponibilidades (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    docente_id  integer NOT NULL REFERENCES docentes(id) ON DELETE CASCADE,
    dia         smallint NOT NULL CHECK (dia BETWEEN 1 AND 7),
    hora_inicio time NOT NULL,
    hora_fin    time NOT NULL CHECK (hora_fin > hora_inicio),
    UNIQUE (docente_id, dia, hora_inicio, hora_fin)
);

-- 7. MATERIAS QUE PUEDE DICTAR CADA DOCENTE  (§5.1 Materias asignadas)
CREATE TABLE IF NOT EXISTS docente_materia (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    docente_id  integer NOT NULL REFERENCES docentes(id) ON DELETE CASCADE,
    materia_id  integer NOT NULL REFERENCES materias(id) ON DELETE CASCADE,
    UNIQUE (docente_id, materia_id)
);

-- 8. CURSOS QUE LE CORRESPONDE DAR A CADA DOCENTE  (§5.1 Cursos)
CREATE TABLE IF NOT EXISTS docente_curso (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    docente_id  integer NOT NULL REFERENCES docentes(id) ON DELETE CASCADE,
    curso_id    integer NOT NULL REFERENCES cursos(id) ON DELETE CASCADE,
    UNIQUE (docente_id, curso_id)
);

-- 9. HORARIOS (una versión/generación del horario)
CREATE TABLE IF NOT EXISTS horarios (
    id                integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    configuracion_id  integer NOT NULL REFERENCES configs(id) ON DELETE RESTRICT,
    usuario_id        uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
    nombre            text NOT NULL DEFAULT 'Horario',
    estado            text NOT NULL DEFAULT 'borrador'
                      CHECK (estado IN ('borrador','completo','parcial')),
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_horarios_usuario ON horarios (usuario_id);

-- 10. CELDAS (celda (curso,materia,docente,salon,dia,bloque,...)) — modelo §6.2
CREATE TABLE IF NOT EXISTS celdas (
    id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    horario_id   integer NOT NULL REFERENCES horarios(id) ON DELETE CASCADE,
    curso_id     integer NOT NULL REFERENCES cursos(id) ON DELETE CASCADE,
    materia_id   integer NOT NULL REFERENCES materias(id) ON DELETE CASCADE,
    docente_id   integer NOT NULL REFERENCES docentes(id) ON DELETE CASCADE,
    salon_id     integer NOT NULL REFERENCES salones(id) ON DELETE CASCADE,
    dia          smallint NOT NULL CHECK (dia BETWEEN 1 AND 7),
    bloque       integer  NOT NULL CHECK (bloque >= 1),
    hora_inicio  time NOT NULL,
    hora_fin     time NOT NULL CHECK (hora_fin > hora_inicio),
    bloqueada    boolean NOT NULL DEFAULT false,   -- celda fija (no la toca el generador)
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),

    -- §5.3 Sin choque de un mismo salón en el mismo (dia,bloque)
    UNIQUE (horario_id, salon_id, dia, bloque),
    -- §5.4 Un curso no recibe dos clases en el mismo bloque
    UNIQUE (horario_id, curso_id, dia, bloque),
    -- §5.1 Un docente no tiene dos clases en el mismo (dia,bloque)
    UNIQUE (horario_id, docente_id, dia, bloque)
);

-- Índices de FK para el frontend
CREATE INDEX IF NOT EXISTS idx_disponibilidades_doc  ON disponibilidades (docente_id);
CREATE INDEX IF NOT EXISTS idx_docente_materia_mat   ON docente_materia (materia_id);
CREATE INDEX IF NOT EXISTS idx_docente_curso_curso   ON docente_curso (curso_id);
CREATE INDEX IF NOT EXISTS idx_celdas_horario        ON celdas (horario_id);
CREATE INDEX IF NOT EXISTS idx_celdas_curso_dia      ON celdas (horario_id, curso_id, dia, bloque);   -- vista por curso
CREATE INDEX IF NOT EXISTS idx_celdas_docente_dia    ON celdas (horario_id, docente_id, dia, bloque); -- vista por docente

-- ============================================================================
-- 11. RESTRICCIONES ENTRE TABLAS (TRIGGERS) — materializan PLAN §5
-- ============================================================================

-- ------------------------------------------------------------------
-- 11.1 VALIDACIÓN DE UNA CELDA (INSERT / UPDATE)
-- Aplica: disponibilidad, materias y cursos autorizados, tipo de salón,
-- política "no última hora", límite de jornada y carga académica del docente.
-- ------------------------------------------------------------------
CREATE OR REPLACE FUNCTION sch_celda_validar()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    cfg      RECORD;
    mat      RECORD;
    tipo_sal text;
    carga_h  numeric;
    minutos  numeric;
    ya_imp   numeric;
    cierre   time;
BEGIN
    -- §5.4 / §5.5: jornada y días laborables según el config del horario
    SELECT c.tipo_jornada, c.dias_laborables, c.hora_inicio, c.hora_fin, c.minutos_bloque
      INTO cfg
      FROM horarios h
      JOIN configs c ON c.id = h.configuracion_id
     WHERE h.id = NEW.horario_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El horario % no tiene configuración de jornada.', NEW.horario_id;
    END IF;

    IF NOT (NEW.dia = ANY (cfg.dias_laborables)) THEN
        RAISE EXCEPTION 'El día % no está en los días laborables de la jornada (%).',
            NEW.dia, cfg.tipo_jornada;
    END IF;

    IF NEW.hora_inicio < cfg.hora_inicio OR NEW.hora_fin > cfg.hora_fin THEN
        RAISE EXCEPTION 'La clase % a % queda fuera de la jornada % de % a %.',
            NEW.hora_inicio, NEW.hora_fin, cfg.tipo_jornada, cfg.hora_inicio, cfg.hora_fin;
    END IF;

    -- §5.1 Materias asignadas: el docente solo dicta materias designadas.
    IF NOT EXISTS (SELECT 1 FROM docente_materia dm
                    WHERE dm.docente_id = NEW.docente_id
                      AND dm.materia_id = NEW.materia_id) THEN
        RAISE EXCEPTION 'El docente no está designado para dictar la materia.';
    END IF;

    -- §5.1 Cursos: solo puede ser asignado a los cursos que le corresponden.
    IF NOT EXISTS (SELECT 1 FROM docente_curso dc
                    WHERE dc.docente_id = NEW.docente_id
                      AND dc.curso_id = NEW.curso_id) THEN
        RAISE EXCEPTION 'El docente no está asignado al curso.';
    END IF;

    -- §5.1 Disponibilidad: la celda debe estar dentro de una ventana del docente.
    IF NOT EXISTS (SELECT 1 FROM disponibilidades d
                    WHERE d.docente_id = NEW.docente_id
                      AND d.dia = NEW.dia
                      AND d.hora_inicio <= NEW.hora_inicio
                      AND d.hora_fin   >= NEW.hora_fin) THEN
        RAISE EXCEPTION 'El docente no tiene disponibilidad en ese día y hora.';
    END IF;

    -- §5.2 / §5.3 Espacios especiales: tipo de salón acorde a la materia.
    SELECT m.requiere_salon, m.tipo_salon_requerido, m.no_ultima_hora INTO mat
      FROM materias m WHERE m.id = NEW.materia_id;
    SELECT s.tipo INTO tipo_sal FROM salones s WHERE s.id = NEW.salon_id;

    IF mat.requiere_salon THEN
        IF tipo_sal IS DISTINCT FROM mat.tipo_salon_requerido THEN
            RAISE EXCEPTION 'La materia requiere un espacio de tipo % pero se le asignó uno de tipo %.',
                mat.tipo_salon_requerido, tipo_sal;
        END IF;
    ELSE
        IF tipo_sal IS DISTINCT FROM 'aula' THEN
            RAISE EXCEPTION 'La materia no requiere laboratorio/sala; solo puede usar aulas.';
        END IF;
    END IF;

    -- §5.2 Política "no última hora": no puede ocupar el último bloque del día.
    cierre := (cfg.hora_fin - (cfg.minutos_bloque || ' minutes')::interval)::time;
    IF mat.no_ultima_hora AND NEW.hora_inicio >= cierre THEN
        RAISE EXCEPTION 'La materia no puede programarse en la última hora de la jornada.';
    END IF;

    -- §5.1 Carga académica: las horas programadas del docente no superan su contrato.
    SELECT d.carga_horaria INTO carga_h FROM docentes d WHERE d.id = NEW.docente_id;
    SELECT COALESCE(SUM(EXTRACT(EPOCH FROM (hora_fin - hora_inicio)) / 60), 0)
      INTO ya_imp
      FROM celdas
     WHERE horario_id = NEW.horario_id
       AND docente_id = NEW.docente_id
       AND id IS DISTINCT FROM NEW.id;

    minutos := EXTRACT(EPOCH FROM (NEW.hora_fin - NEW.hora_inicio)) / 60;
    IF ya_imp + minutos > carga_h * 60 THEN
        RAISE EXCEPTION 'La carga programada supera la carga académica del docente (%).',
            carga_h;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_celdas_validar ON celdas;
CREATE TRIGGER trg_celdas_validar
BEFORE INSERT OR UPDATE OF horario_id, curso_id, materia_id, docente_id,
                        salon_id, dia, hora_inicio, hora_fin, bloque
ON celdas FOR EACH ROW
EXECUTE FUNCTION sch_celda_validar();

-- ------------------------------------------------------------------
-- 11.2 VALIDACIÓN DE COMPLETITUD DEL HORARIO (al marcarlo "completo")
--     §5.5 Carga semanal por curso e intensidad por materia en rango.
-- ------------------------------------------------------------------
CREATE OR REPLACE FUNCTION sch_horario_validar() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- Solo se valida al transitar a "completo".
    IF OLD.estado = 'completo' OR NEW.estado IS DISTINCT FROM 'completo' THEN
        RETURN NEW;
    END IF;

    -- §5.5 La suma de horas de todas las materias de un curso = horas_semanales.
    IF EXISTS (
        SELECT 1
          FROM cursos cu
          LEFT JOIN celdas cc
            ON cc.curso_id = cu.id AND cc.horario_id = NEW.id
         GROUP BY cu.id, cu.nombre, cu.horas_semanales
        HAVING COALESCE(SUM(EXTRACT(EPOCH FROM (cc.hora_fin - cc.hora_inicio)) / 60), 0)
               <> cu.horas_semanales * 60
    ) THEN
        RAISE EXCEPTION 'La carga semanal de algún curso no cuadra con sus horas_semanales.';
    END IF;

    -- §5.5 / §5.2 Intensidad por materia dentro de su [min_horas, max_horas].
    -- La intensidad es POR CURSO: una materia puede repetirse en varios cursos
    -- del mismo horario, y cada curso individual debe quedar dentro del rango.
    IF EXISTS (
        SELECT 1
          FROM materias m
          JOIN celdas c ON c.materia_id = m.id AND c.horario_id = NEW.id
         GROUP BY m.id, m.nombre, m.min_horas, m.max_horas, c.curso_id
        HAVING SUM(EXTRACT(EPOCH FROM (c.hora_fin - c.hora_inicio)) / 60)
               NOT BETWEEN m.min_horas * 60 AND m.max_horas * 60
    ) THEN
        RAISE EXCEPTION 'Alguna materia no cumple su intensidad horaria [min, max].';
    END IF;

    -- §5.1 El docente no supera su carga académica contractual.
    IF EXISTS (
        SELECT 1
          FROM docentes d
          JOIN celdas c ON c.docente_id = d.id AND c.horario_id = NEW.id
         GROUP BY d.id, d.nombre, d.carga_horaria
        HAVING SUM(EXTRACT(EPOCH FROM (c.hora_fin - c.hora_inicio)) / 60)
               > d.carga_horaria * 60
    ) THEN
        RAISE EXCEPTION 'Algún docente supera su carga académica contractual.';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_horarios_validar ON horarios;
CREATE TRIGGER trg_horarios_validar
BEFORE UPDATE OF estado ON horarios FOR EACH ROW
EXECUTE FUNCTION sch_horario_validar();

COMMIT;