-- ============================================================================
-- RLS (Row Level Security) — Sistema Generador de Horarios
-- Motor: PostgreSQL / Supabase
--
-- Modelo de acceso: MULTI-USUARIO con aislamiento por dueño.
--   Catálogos compartidos (configs, docentes, cursos, materias, salones,
--   disponibilidades, docente_materia, docente_curso):
--     - anon ............ SELECT (lectura pública básica).
--     - authenticated ... acceso completo (SELECT/INSERT/UPDATE/DELETE).
--   Horarios y celdas (datos privados por usuario):
--     - anon ............ sin acceso.
--     - authenticated ... solo filas cuyo usuario_id = auth.uid().
--   service_role/owner ... bypassan RLS por defecto (generador del backend).
--
-- Requiere: horarios.usuario_id uuid DEFAULT auth.uid() (ver schema.sql).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. ACTIVAR RLS EN TODAS LAS TABLAS
-- ----------------------------------------------------------------------------
ALTER TABLE configs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE docentes         ENABLE ROW LEVEL SECURITY;
ALTER TABLE cursos           ENABLE ROW LEVEL SECURITY;
ALTER TABLE materias         ENABLE ROW LEVEL SECURITY;
ALTER TABLE salones          ENABLE ROW LEVEL SECURITY;
ALTER TABLE disponibilidades ENABLE ROW LEVEL SECURITY;
ALTER TABLE docente_materia  ENABLE ROW LEVEL SECURITY;
ALTER TABLE docente_curso    ENABLE ROW LEVEL SECURITY;
ALTER TABLE horarios         ENABLE ROW LEVEL SECURITY;
ALTER TABLE celdas           ENABLE ROW LEVEL SECURITY;

-- ----------------------------------------------------------------------------
-- 2. CATÁLOGOS GLOBALES — compartidos por todos los usuarios autenticados
-- ----------------------------------------------------------------------------

-- CONFIGS
DROP POLICY IF EXISTS configs_anon_select ON configs;
DROP POLICY IF EXISTS configs_auth_all    ON configs;
CREATE POLICY configs_anon_select ON configs FOR SELECT TO anon USING (true);
CREATE POLICY configs_auth_all    ON configs FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- DOCENTES
DROP POLICY IF EXISTS docentes_anon_select  ON docentes;
DROP POLICY IF EXISTS docentes_auth_all     ON docentes;
CREATE POLICY docentes_anon_select ON docentes FOR SELECT TO anon USING (true);
CREATE POLICY docentes_auth_all    ON docentes FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- CURSOS
DROP POLICY IF EXISTS cursos_anon_select ON cursos;
DROP POLICY IF EXISTS cursos_auth_all    ON cursos;
CREATE POLICY cursos_anon_select ON cursos FOR SELECT TO anon USING (true);
CREATE POLICY cursos_auth_all    ON cursos FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- MATERIAS
DROP POLICY IF EXISTS materias_anon_select  ON materias;
DROP POLICY IF EXISTS materias_auth_all     ON materias;
CREATE POLICY materias_anon_select ON materias FOR SELECT TO anon USING (true);
CREATE POLICY materias_auth_all    ON materias FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- SALONES
DROP POLICY IF EXISTS salones_anon_select  ON salones;
DROP POLICY IF EXISTS salones_auth_all     ON salones;
CREATE POLICY salones_anon_select ON salones FOR SELECT TO anon USING (true);
CREATE POLICY salones_auth_all    ON salones FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- DISPONIBILIDADES
DROP POLICY IF EXISTS disponibilidades_anon_select  ON disponibilidades;
DROP POLICY IF EXISTS disponibilidades_auth_all     ON disponibilidades;
CREATE POLICY disponibilidades_anon_select ON disponibilidades FOR SELECT TO anon USING (true);
CREATE POLICY disponibilidades_auth_all    ON disponibilidades FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- DOCENTE_MATERIA
DROP POLICY IF EXISTS docente_materia_anon_select  ON docente_materia;
DROP POLICY IF EXISTS docente_materia_auth_all     ON docente_materia;
CREATE POLICY docente_materia_anon_select ON docente_materia FOR SELECT TO anon USING (true);
CREATE POLICY docente_materia_auth_all    ON docente_materia FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- DOCENTE_CURSO
DROP POLICY IF EXISTS docente_curso_anon_select  ON docente_curso;
DROP POLICY IF EXISTS docente_curso_auth_all     ON docente_curso;
CREATE POLICY docente_curso_anon_select ON docente_curso FOR SELECT TO anon USING (true);
CREATE POLICY docente_curso_auth_all    ON docente_curso FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. HORARIOS — visibilidad/escritura limitada al dueño (usuario_id)
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS horarios_auth_select ON horarios;
DROP POLICY IF EXISTS horarios_auth_insert ON horarios;
DROP POLICY IF EXISTS horarios_auth_update ON horarios;
DROP POLICY IF EXISTS horarios_auth_delete ON horarios;

CREATE POLICY horarios_auth_select ON horarios
    FOR SELECT TO authenticated USING (usuario_id = auth.uid());

-- auth.uid() se asigna por defecto (columna DEFAULT), por eso el INSERT solo valida.
CREATE POLICY horarios_auth_insert ON horarios
    FOR INSERT TO authenticated
    WITH CHECK (usuario_id = auth.uid());

CREATE POLICY horarios_auth_update ON horarios
    FOR UPDATE TO authenticated
    USING (usuario_id = auth.uid())
    WITH CHECK (usuario_id = auth.uid());

CREATE POLICY horarios_auth_delete ON horarios
    FOR DELETE TO authenticated USING (usuario_id = auth.uid());

-- ----------------------------------------------------------------------------
-- 4. CELDAS — heredan la propiedad del horario al que pertenecen
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS celdas_auth_select ON celdas;
DROP POLICY IF EXISTS celdas_auth_insert ON celdas;
DROP POLICY IF EXISTS celdas_auth_update ON celdas;
DROP POLICY IF EXISTS celdas_auth_delete ON celdas;

CREATE POLICY celdas_auth_select ON celdas
    FOR SELECT TO authenticated
    USING (EXISTS (SELECT 1 FROM horarios h
                    WHERE h.id = celdas.horario_id
                      AND h.usuario_id = auth.uid()));

CREATE POLICY celdas_auth_insert ON celdas
    FOR INSERT TO authenticated
    WITH CHECK (EXISTS (SELECT 1 FROM horarios h
                        WHERE h.id = celdas.horario_id
                          AND h.usuario_id = auth.uid()));

CREATE POLICY celdas_auth_update ON celdas
    FOR UPDATE TO authenticated
    USING (EXISTS (SELECT 1 FROM horarios h
                    WHERE h.id = celdas.horario_id
                      AND h.usuario_id = auth.uid()))
    WITH CHECK (EXISTS (SELECT 1 FROM horarios h
                        WHERE h.id = celdas.horario_id
                          AND h.usuario_id = auth.uid()));

CREATE POLICY celdas_auth_delete ON celdas
    FOR DELETE TO authenticated
    USING (EXISTS (SELECT 1 FROM horarios h
                    WHERE h.id = celdas.horario_id
                      AND h.usuario_id = auth.uid()));