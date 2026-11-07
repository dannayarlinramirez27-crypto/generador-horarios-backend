-- Legacy-like fixtures for the forward ownership migration. Runs only against
-- the dedicated disposable PostgreSQL service in the ownership CI job.
INSERT INTO auth.users (
    id, instance_id, aud, role, email, email_confirmed_at,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at
)
VALUES (
    'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02',
    '00000000-0000-0000-0000-000000000000',
    'authenticated', 'authenticated', 'docente-ownership@localhost', now(),
    '{"role":"docente"}'::jsonb, '{}'::jsonb, now(), now()
);
UPDATE public.perfiles
   SET role = 'docente'
 WHERE id = 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM auth.users u JOIN public.perfiles p ON p.id = u.id
         WHERE u.id = 'f66d8637-c374-4602-b748-b9b9737abfbf'
           AND p.role = 'admin'
    ) THEN
        RAISE EXCEPTION 'Authorized admin auth/profile fixture is missing';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM auth.users u JOIN public.perfiles p ON p.id = u.id
         WHERE u.id = 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'
           AND p.role = 'docente'
    ) THEN
        RAISE EXCEPTION 'Second docente auth/profile fixture is missing';
    END IF;
END;
$$;

INSERT INTO public.configs (
    id, user_id, nombre, tipo_jornada, dias_laborables,
    hora_inicio, hora_fin, minutos_bloque, activa
) OVERRIDING SYSTEM VALUE
VALUES (
    910001, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02', 'Legacy config', 'unica',
    '{1,2,3,4,5}', '07:00', '13:00', 60, false
);

INSERT INTO public.docentes (id, user_id, nombre, apellido, documento, carga_horaria, activo)
OVERRIDING SYSTEM VALUE
VALUES (
    910002, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02',
    'Legacy', 'Docente', 'ownership-legacy-910002', 2, true
);

INSERT INTO public.cursos (id, user_id, nombre, nivel, horas_semanales)
OVERRIDING SYSTEM VALUE
VALUES (910003, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02', 'Legacy course', '1', 1);

INSERT INTO public.materias (id, user_id, nombre, categoria, min_horas, max_horas)
OVERRIDING SYSTEM VALUE
VALUES (910004, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02', 'Legacy subject', 'basica', 1, 2);

INSERT INTO public.salones (id, user_id, nombre, tipo, capacidad, activo)
OVERRIDING SYSTEM VALUE
VALUES (910005, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02', 'Legacy room', 'aula', 30, true);

INSERT INTO public.disponibilidades (id, user_id, docente_id, dia, hora_inicio, hora_fin)
OVERRIDING SYSTEM VALUE
VALUES (910006, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02', 910002, 1, '07:00', '13:00');

INSERT INTO public.docente_materia (id, user_id, docente_id, materia_id)
OVERRIDING SYSTEM VALUE
VALUES (910007, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02', 910002, 910004);

INSERT INTO public.docente_curso (id, user_id, docente_id, curso_id)
OVERRIDING SYSTEM VALUE
VALUES (910008, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02', 910002, 910003);

INSERT INTO public.horarios (
    id, user_id, configuracion_id, usuario_id, nombre, estado
) OVERRIDING SYSTEM VALUE
VALUES (
    910009, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02', 910001,
    'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02', 'Legacy schedule', 'borrador'
);

INSERT INTO public.celdas (
    id, user_id, horario_id, curso_id, materia_id, docente_id, salon_id,
    dia, bloque, hora_inicio, hora_fin, bloqueada
) OVERRIDING SYSTEM VALUE
VALUES (
    910010, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02', 910009, 910003,
    910004, 910002, 910005, 1, 1, '07:00', '08:00', false
);

-- Distinct ownerless top-level rows prove the approved legacy-admin backfill
-- without making any record referenced by the docente tenant cross-owned.
INSERT INTO public.configs (
    id, user_id, nombre, tipo_jornada, dias_laborables,
    hora_inicio, hora_fin, minutos_bloque, activa
) OVERRIDING SYSTEM VALUE
VALUES (
    910011, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02', 'Legacy ownerless config', 'unica',
    '{1,2,3,4,5}', '07:00', '13:00', 60, true
);
INSERT INTO public.cursos (id, user_id, nombre, nivel, horas_semanales)
OVERRIDING SYSTEM VALUE
VALUES (910012, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02', 'Legacy ownerless course', '1', 1);
INSERT INTO public.materias (id, user_id, nombre, categoria, min_horas, max_horas)
OVERRIDING SYSTEM VALUE
VALUES (910013, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02', 'Legacy ownerless subject', 'basica', 1, 2);
INSERT INTO public.salones (id, user_id, nombre, tipo, capacidad, activo)
OVERRIDING SYSTEM VALUE
VALUES (910014, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02', 'Legacy ownerless room', 'aula', 30, true);
INSERT INTO public.docentes (id, user_id, nombre, apellido, documento, carga_horaria, activo)
OVERRIDING SYSTEM VALUE
VALUES (
    910015, 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02',
    'Legacy', 'Ownerless', 'ownership-legacy-910015', 2, true
);

-- Exercise the migration's optional child-table path with only the legacy
-- columns it reads or protects. The migration must add and backfill user_id.
CREATE TABLE public.horarios_celdas (
    id integer PRIMARY KEY,
    horario_id integer NOT NULL REFERENCES public.horarios(id) ON DELETE CASCADE
);
INSERT INTO public.horarios_celdas (id, horario_id) VALUES (910016, 910009);

-- Restore the pre-ownership global uniqueness rules. The migration must drop
-- both single-column constraints and standalone indexes before installing
-- owner-scoped uniqueness.
ALTER TABLE public.configs
    ADD CONSTRAINT configs_activa_key UNIQUE (activa);
ALTER TABLE public.docentes
    ADD CONSTRAINT docentes_documento_key UNIQUE (documento),
    ADD CONSTRAINT docentes_email_key UNIQUE (email);
ALTER TABLE public.cursos
    ADD CONSTRAINT cursos_nombre_key UNIQUE (nombre);
ALTER TABLE public.materias
    ADD CONSTRAINT materias_nombre_key UNIQUE (nombre);
ALTER TABLE public.salones
    ADD CONSTRAINT salones_nombre_key UNIQUE (nombre);

CREATE UNIQUE INDEX legacy_configs_activa_uidx ON public.configs (activa) WHERE activa = true;
CREATE UNIQUE INDEX legacy_docentes_documento_uidx ON public.docentes (documento);
CREATE UNIQUE INDEX legacy_docentes_email_uidx ON public.docentes (email) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX legacy_cursos_nombre_uidx ON public.cursos (nombre);
CREATE UNIQUE INDEX legacy_materias_nombre_uidx ON public.materias (nombre);
CREATE UNIQUE INDEX legacy_salones_nombre_uidx ON public.salones (nombre);

-- Recreate the pre-ownership shape: no ownership guard/FKs/NOT NULL on owner
-- fields, and missing owners on legacy rows. Keep horario.usuario_id to prove
-- the migration copies its existing owner into user_id instead of replacing it.
DO $$
DECLARE target_table text;
BEGIN
    FOREACH target_table IN ARRAY ARRAY[
        'configs', 'docentes', 'cursos', 'materias', 'salones',
        'disponibilidades', 'docente_materia', 'docente_curso', 'horarios', 'celdas'
    ] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_validate_row_ownership ON public.%I', target_table);
        EXECUTE format('ALTER TABLE public.%I ALTER COLUMN user_id DROP NOT NULL', target_table);
        EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT IF EXISTS %I', target_table, target_table || '_user_id_fkey');
    END LOOP;
    ALTER TABLE public.horarios ALTER COLUMN usuario_id DROP NOT NULL;
    ALTER TABLE public.horarios DROP CONSTRAINT IF EXISTS horarios_usuario_id_fkey;
END;
$$;

UPDATE public.configs SET user_id = NULL WHERE id = 910011;
UPDATE public.cursos SET user_id = NULL WHERE id = 910012;
UPDATE public.materias SET user_id = NULL WHERE id = 910013;
UPDATE public.salones SET user_id = NULL WHERE id = 910014;
UPDATE public.docentes SET user_id = NULL WHERE id = 910015;
UPDATE public.disponibilidades SET user_id = NULL WHERE id = 910006;
UPDATE public.docente_materia SET user_id = NULL WHERE id = 910007;
UPDATE public.docente_curso SET user_id = NULL WHERE id = 910008;
UPDATE public.horarios SET user_id = NULL WHERE id = 910009;
UPDATE public.celdas SET user_id = NULL WHERE id = 910010;
