BEGIN;

DO $$
DECLARE
    required_owner_columns integer;
    owner_foreign_keys integer;
    ownership_triggers integer;
    completion_triggers integer;
    legacy_unique_constraints integer;
    legacy_standalone_unique_indexes integer;
    legacy_set_user_id_triggers integer;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM auth.users u JOIN public.perfiles p ON p.id = u.id
         WHERE u.id = 'f66d8637-c374-4602-b748-b9b9737abfbf'
           AND p.role = 'admin'
    ) OR NOT EXISTS (
        SELECT 1 FROM auth.users u JOIN public.perfiles p ON p.id = u.id
         WHERE u.id = 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'
           AND p.role = 'docente'
    ) THEN
        RAISE EXCEPTION 'Expected admin and docente auth/profile fixtures';
    END IF;

    IF (SELECT user_id FROM public.configs WHERE id = 910011)
             IS DISTINCT FROM 'f66d8637-c374-4602-b748-b9b9737abfbf'::uuid
       OR (SELECT user_id FROM public.cursos WHERE id = 910012)
             IS DISTINCT FROM 'f66d8637-c374-4602-b748-b9b9737abfbf'::uuid
       OR (SELECT user_id FROM public.materias WHERE id = 910013)
             IS DISTINCT FROM 'f66d8637-c374-4602-b748-b9b9737abfbf'::uuid
       OR (SELECT user_id FROM public.salones WHERE id = 910014)
             IS DISTINCT FROM 'f66d8637-c374-4602-b748-b9b9737abfbf'::uuid
       OR (SELECT user_id FROM public.docentes WHERE id = 910015)
             IS DISTINCT FROM 'f66d8637-c374-4602-b748-b9b9737abfbf'::uuid THEN
         RAISE EXCEPTION 'Top-level legacy rows did not receive the authorized admin owner';
    END IF;

    IF (SELECT user_id FROM public.configs WHERE id = 910001)
             IS DISTINCT FROM 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'::uuid
       OR (SELECT user_id FROM public.cursos WHERE id = 910003)
             IS DISTINCT FROM 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'::uuid
       OR (SELECT user_id FROM public.materias WHERE id = 910004)
             IS DISTINCT FROM 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'::uuid
       OR (SELECT user_id FROM public.salones WHERE id = 910005)
             IS DISTINCT FROM 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'::uuid
       OR (SELECT user_id FROM public.docentes WHERE id = 910002)
             IS DISTINCT FROM 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'::uuid
       OR (SELECT user_id FROM public.disponibilidades WHERE id = 910006)
            IS DISTINCT FROM 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'::uuid
       OR (SELECT user_id FROM public.docente_materia WHERE id = 910007)
            IS DISTINCT FROM 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'::uuid
       OR (SELECT user_id FROM public.docente_curso WHERE id = 910008)
            IS DISTINCT FROM 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'::uuid THEN
        RAISE EXCEPTION 'Docente-dependent rows did not inherit their parent owner';
    END IF;

    IF (SELECT user_id FROM public.horarios WHERE id = 910009)
            IS DISTINCT FROM 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'::uuid
       OR (SELECT usuario_id FROM public.horarios WHERE id = 910009)
            IS DISTINCT FROM 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'::uuid
       OR (SELECT user_id FROM public.celdas WHERE id = 910010)
             IS DISTINCT FROM 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'::uuid
       OR (SELECT user_id FROM public.horarios_celdas WHERE id = 910016)
             IS DISTINCT FROM 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'::uuid THEN
         RAISE EXCEPTION 'Schedule aliases or child-cell ownership were not preserved';
    END IF;

    SELECT count(*) INTO required_owner_columns
      FROM (VALUES
        ('configs', 'user_id'), ('docentes', 'user_id'), ('cursos', 'user_id'),
        ('materias', 'user_id'), ('salones', 'user_id'),
        ('disponibilidades', 'user_id'), ('docente_materia', 'user_id'),
        ('docente_curso', 'user_id'), ('horarios', 'user_id'),
        ('horarios', 'usuario_id'), ('celdas', 'user_id'),
        ('horarios_celdas', 'user_id')
      ) AS required(table_name, column_name)
      JOIN pg_attribute a
        ON a.attrelid = format('public.%I', required.table_name)::regclass
       AND a.attname = required.column_name
       AND a.attnotnull
       AND NOT a.attisdropped;
    IF required_owner_columns <> 12 THEN
        RAISE EXCEPTION 'Expected 12 required owner columns, found %', required_owner_columns;
    END IF;

    SELECT count(*) INTO owner_foreign_keys
      FROM pg_constraint c
      JOIN LATERAL unnest(c.conkey) AS key(attnum) ON true
      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = key.attnum
     WHERE c.contype = 'f'
       AND c.confrelid = 'auth.users'::regclass
       AND (a.attname = 'user_id' OR (c.conrelid = 'public.horarios'::regclass AND a.attname = 'usuario_id'))
       AND c.conrelid IN (
           'public.configs'::regclass, 'public.docentes'::regclass,
           'public.cursos'::regclass, 'public.materias'::regclass,
           'public.salones'::regclass, 'public.disponibilidades'::regclass,
           'public.docente_materia'::regclass, 'public.docente_curso'::regclass,
            'public.horarios'::regclass, 'public.celdas'::regclass,
            'public.horarios_celdas'::regclass
        );
    IF owner_foreign_keys <> 12 THEN
        RAISE EXCEPTION 'Expected 12 auth.users ownership foreign keys, found %', owner_foreign_keys;
    END IF;

    IF to_regclass('public.uidx_configs_activa') IS NULL
       OR to_regclass('public.uidx_docentes_user_documento') IS NULL
       OR to_regclass('public.uidx_docentes_user_email') IS NULL
       OR to_regclass('public.uidx_cursos_user_nombre') IS NULL
       OR to_regclass('public.uidx_materias_user_nombre') IS NULL
       OR to_regclass('public.uidx_salones_user_nombre') IS NULL
       OR to_regclass('public.idx_horarios_usuario') IS NULL
       OR to_regclass('public.idx_disponibilidades_user') IS NULL
       OR to_regclass('public.idx_docente_materia_user') IS NULL
       OR to_regclass('public.idx_docente_curso_user') IS NULL
       OR to_regclass('public.idx_celdas_user') IS NULL THEN
        RAISE EXCEPTION 'One or more ownership indexes are missing';
    END IF;

    SELECT count(*) INTO ownership_triggers
      FROM pg_trigger t
      JOIN pg_class r ON r.oid = t.tgrelid
      JOIN pg_namespace n ON n.oid = r.relnamespace
      JOIN pg_proc f ON f.oid = t.tgfoid
     WHERE n.nspname = 'public'
       AND t.tgname = 'trg_validate_row_ownership'
       AND NOT t.tgisinternal
       AND f.proname = 'validate_row_ownership'
       AND r.relname IN (
           'configs', 'docentes', 'cursos', 'materias', 'salones',
           'disponibilidades', 'docente_materia', 'docente_curso', 'horarios', 'celdas'
       );
    IF ownership_triggers <> 10 THEN
        RAISE EXCEPTION 'Expected ownership triggers on 10 tables, found %', ownership_triggers;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_class
         WHERE oid = 'public.horarios_celdas'::regclass AND relrowsecurity
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname = 'public' AND tablename = 'horarios_celdas'
           AND policyname = 'horarios_celdas_owner_admin'
    ) THEN
        RAISE EXCEPTION 'Optional horarios_celdas ownership RLS protection is missing';
    END IF;

    SELECT count(*) INTO ownership_triggers
      FROM pg_trigger t
      JOIN pg_class r ON r.oid = t.tgrelid
      JOIN pg_namespace n ON n.oid = r.relnamespace
      JOIN pg_proc f ON f.oid = t.tgfoid
     WHERE n.nspname = 'public'
       AND r.relname = 'horarios_celdas'
       AND t.tgname = 'trg_validate_row_ownership'
       AND NOT t.tgisinternal
       AND f.proname = 'validate_row_ownership';
    IF ownership_triggers <> 1 THEN
        RAISE EXCEPTION 'Expected ownership trigger on horarios_celdas, found %', ownership_triggers;
    END IF;

    SELECT count(*) INTO legacy_set_user_id_triggers
      FROM pg_trigger t
      JOIN pg_class r ON r.oid = t.tgrelid
      JOIN pg_namespace n ON n.oid = r.relnamespace
     WHERE n.nspname = 'public'
       AND r.relname IN (
           'configs', 'docentes', 'cursos', 'materias', 'salones',
           'disponibilidades', 'docente_materia', 'docente_curso',
           'horarios', 'celdas', 'horarios_celdas'
       )
       AND NOT t.tgisinternal
       AND t.tgfoid = to_regprocedure('public.set_user_id()');
    IF legacy_set_user_id_triggers <> 0 THEN
        RAISE EXCEPTION 'Expected legacy public.set_user_id() triggers to be removed, found %', legacy_set_user_id_triggers;
    END IF;
    IF to_regprocedure('public.set_user_id()') IS NULL THEN
        RAISE EXCEPTION 'Migration must leave the legacy trigger function intact';
    END IF;
    IF to_regprocedure('public.keep_docente_audit()') IS NULL OR NOT EXISTS (
        SELECT 1 FROM pg_trigger t
        JOIN pg_class r ON r.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = r.relnamespace
        WHERE n.nspname = 'public' AND r.relname = 'docentes'
          AND t.tgname = 'set_user_id_unrelated' AND NOT t.tgisinternal
          AND t.tgfoid = to_regprocedure('public.keep_docente_audit()')
    ) THEN
        RAISE EXCEPTION 'Migration removed an unrelated docentes trigger or function';
    END IF;
    IF auth.uid() IS NOT NULL THEN
        RAISE EXCEPTION 'Expected auth.uid() to remain NULL without JWT claims';
    END IF;

    SELECT count(*) INTO completion_triggers
      FROM pg_trigger t
      JOIN pg_class r ON r.oid = t.tgrelid
      JOIN pg_namespace n ON n.oid = r.relnamespace
      JOIN pg_proc f ON f.oid = t.tgfoid
     WHERE n.nspname = 'public'
       AND r.relname = 'horarios'
       AND t.tgname = 'trg_horarios_validar'
       AND NOT t.tgisinternal
       AND f.proname = 'sch_horario_validar';
    IF completion_triggers <> 1 THEN
        RAISE EXCEPTION 'Expected trg_horarios_validar on horarios, found %', completion_triggers;
    END IF;

    SELECT count(*) INTO legacy_unique_constraints
      FROM pg_constraint c
      JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
      JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = c.conkey[1]
     WHERE n.nspname = 'public' AND c.contype = 'u'
       AND array_length(c.conkey, 1) = 1
       AND ((t.relname = 'configs' AND a.attname = 'activa')
         OR (t.relname = 'docentes' AND a.attname IN ('documento', 'email'))
         OR (t.relname IN ('cursos', 'materias', 'salones') AND a.attname = 'nombre'));
    IF legacy_unique_constraints <> 0 THEN
        RAISE EXCEPTION 'Expected legacy global unique constraints to be removed, found %', legacy_unique_constraints;
    END IF;

    SELECT count(*) INTO legacy_standalone_unique_indexes
      FROM pg_index i
      JOIN pg_class t ON t.oid = i.indrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
      JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = i.indkey[0]
     WHERE n.nspname = 'public'
       AND i.indisunique AND NOT i.indisprimary AND i.indnkeyatts = 1
       AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid)
       AND ((t.relname = 'configs' AND a.attname = 'activa')
         OR (t.relname = 'docentes' AND a.attname IN ('documento', 'email'))
         OR (t.relname IN ('cursos', 'materias', 'salones') AND a.attname = 'nombre'));
    IF legacy_standalone_unique_indexes <> 0 THEN
        RAISE EXCEPTION 'Expected legacy global standalone unique indexes to be removed, found %', legacy_standalone_unique_indexes;
    END IF;
END;
$$;

-- The assertion script runs in a transaction and rolls this regression row
-- back, while proving the backend-supplied owner survives a NULL auth.uid().
DO $$
DECLARE inserted_owner public.docentes.user_id%TYPE;
BEGIN
    INSERT INTO public.docentes (
        user_id, nombre, apellido, documento, carga_horaria, activo
    ) VALUES (
        'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02',
        'Post-migration', 'Owner', 'ownership-postmigration-preserved', 2, true
    )
    RETURNING user_id INTO inserted_owner;

    IF inserted_owner IS DISTINCT FROM 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'::uuid THEN
        RAISE EXCEPTION 'A NULL auth.uid() overwrote the explicit docente owner';
    END IF;
END;
$$;

-- These writes simulate an administrator (the CI connection is the table
-- owner) attempting valid-FK but cross-owner references. Every relation must
-- still be rejected by the ownership trigger.
DO $$
DECLARE
    rejected boolean;
    rejection text;
BEGIN
    rejected := false;
    BEGIN
        UPDATE public.docente_materia SET docente_id = 910015 WHERE id = 910007;
    EXCEPTION WHEN raise_exception THEN
        rejection := SQLERRM;
        rejected := rejection = 'dependent row user_id must match its docente owner';
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'Cross-owner docente_materia docente was not rejected: %', rejection; END IF;

    rejected := false;
    BEGIN
        UPDATE public.docente_materia SET materia_id = 910013 WHERE id = 910007;
    EXCEPTION WHEN raise_exception THEN
        rejection := SQLERRM;
        rejected := rejection = 'docente_materia materia owner must match assignment owner';
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'Cross-owner docente_materia reference was not rejected: %', rejection; END IF;

    rejected := false;
    BEGIN
        UPDATE public.docente_curso SET curso_id = 910012 WHERE id = 910008;
    EXCEPTION WHEN raise_exception THEN
        rejection := SQLERRM;
        rejected := rejection = 'docente_curso curso owner must match assignment owner';
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'Cross-owner docente_curso reference was not rejected: %', rejection; END IF;

    rejected := false;
    BEGIN
        UPDATE public.horarios SET configuracion_id = 910011 WHERE id = 910009;
    EXCEPTION WHEN raise_exception THEN
        rejection := SQLERRM;
        rejected := rejection = 'horarios config owner must match schedule owner';
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'Cross-owner horarios config was not rejected: %', rejection; END IF;

    rejected := false;
    BEGIN
        UPDATE public.celdas SET salon_id = 910014 WHERE id = 910010;
    EXCEPTION WHEN raise_exception THEN
        rejection := SQLERRM;
        rejected := rejection = 'celdas salon owner must match cell owner';
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'Cross-owner celdas salon was not rejected: %', rejection; END IF;

    rejected := false;
    rejection := NULL;
    BEGIN
        INSERT INTO public.horarios_celdas (id, horario_id, user_id)
        VALUES (910017, 910009, 'f66d8637-c374-4602-b748-b9b9737abfbf');
    EXCEPTION WHEN raise_exception THEN
        rejection := SQLERRM;
        rejected := rejection = 'dependent row user_id must match its horario owner';
    END;
    IF NOT rejected THEN
        RAISE EXCEPTION 'Cross-owner horarios_celdas insert was not rejected: %', rejection;
    END IF;

    rejected := false;
    rejection := NULL;
    BEGIN
        UPDATE public.cursos SET horas_semanales = 2 WHERE id = 910003;
        UPDATE public.horarios SET estado = 'completo' WHERE id = 910009;
    EXCEPTION WHEN raise_exception THEN
        rejection := SQLERRM;
        rejected := rejection = 'La carga semanal de algún curso no cuadra con sus horas_semanales.';
    END;
    IF NOT rejected THEN
        RAISE EXCEPTION 'trg_horarios_validar did not reject an incomplete schedule: %', rejection;
    END IF;
    IF (SELECT horas_semanales FROM public.cursos WHERE id = 910003) <> 1
       OR (SELECT estado FROM public.horarios WHERE id = 910009) <> 'borrador' THEN
        RAISE EXCEPTION 'Rejected completion did not roll back its temporary fixture changes';
    END IF;

    UPDATE public.horarios SET estado = 'completo' WHERE id = 910009;
END;
$$;

ROLLBACK;
