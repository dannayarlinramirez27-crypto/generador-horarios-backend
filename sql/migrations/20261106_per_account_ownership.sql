-- Per-account ownership migration. Apply only to a disposable/local database
-- during verification; this file is intentionally not executed by this change.
BEGIN;

DO $$
DECLARE mismatch_count bigint;
BEGIN
    IF to_regclass('public.horarios') IS NOT NULL
       AND EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'horarios'
                      AND column_name = 'user_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'horarios'
                      AND column_name = 'usuario_id') THEN
        EXECUTE 'SELECT count(*) FROM public.horarios
                  WHERE user_id IS NOT NULL AND usuario_id IS NOT NULL
                    AND user_id IS DISTINCT FROM usuario_id'
           INTO mismatch_count;
        IF mismatch_count > 0 THEN
            RAISE EXCEPTION 'Ownership migration stopped: % horarios rows have conflicting user_id and usuario_id values; reconcile them before retrying.', mismatch_count;
        END IF;
    END IF;

    IF to_regclass('public.disponibilidades') IS NOT NULL
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'disponibilidades' AND column_name = 'user_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'docentes' AND column_name = 'user_id') THEN
        EXECUTE 'SELECT count(*) FROM public.disponibilidades x
                  JOIN public.docentes p ON p.id = x.docente_id
                 WHERE x.user_id IS NOT NULL AND x.user_id IS DISTINCT FROM p.user_id'
           INTO mismatch_count;
        IF mismatch_count > 0 THEN
            RAISE EXCEPTION 'Ownership migration stopped: % disponibilidades rows do not match their docente owner.', mismatch_count;
        END IF;
    END IF;
    IF to_regclass('public.docente_materia') IS NOT NULL
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'docente_materia' AND column_name = 'user_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'docentes' AND column_name = 'user_id') THEN
        EXECUTE 'SELECT count(*) FROM public.docente_materia x
                  JOIN public.docentes p ON p.id = x.docente_id
                 WHERE x.user_id IS NOT NULL AND x.user_id IS DISTINCT FROM p.user_id'
           INTO mismatch_count;
        IF mismatch_count > 0 THEN
            RAISE EXCEPTION 'Ownership migration stopped: % docente_materia rows do not match their docente owner.', mismatch_count;
        END IF;
    END IF;
    IF to_regclass('public.docente_curso') IS NOT NULL
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'docente_curso' AND column_name = 'user_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'docentes' AND column_name = 'user_id') THEN
        EXECUTE 'SELECT count(*) FROM public.docente_curso x
                  JOIN public.docentes p ON p.id = x.docente_id
                 WHERE x.user_id IS NOT NULL AND x.user_id IS DISTINCT FROM p.user_id'
           INTO mismatch_count;
        IF mismatch_count > 0 THEN
            RAISE EXCEPTION 'Ownership migration stopped: % docente_curso rows do not match their docente owner.', mismatch_count;
        END IF;
    END IF;
    IF to_regclass('public.celdas') IS NOT NULL
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'celdas' AND column_name = 'user_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'horarios' AND column_name = 'user_id') THEN
        EXECUTE 'SELECT count(*) FROM public.celdas x
                  JOIN public.horarios p ON p.id = x.horario_id
                 WHERE x.user_id IS NOT NULL AND x.user_id IS DISTINCT FROM p.user_id'
           INTO mismatch_count;
        IF mismatch_count > 0 THEN
            RAISE EXCEPTION 'Ownership migration stopped: % celdas rows do not match their horario owner.', mismatch_count;
        END IF;
    END IF;
    IF to_regclass('public.horarios_celdas') IS NOT NULL
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'horarios_celdas' AND column_name = 'user_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'horarios' AND column_name = 'user_id') THEN
        EXECUTE 'SELECT count(*) FROM public.horarios_celdas x
                  JOIN public.horarios p ON p.id = x.horario_id
                 WHERE x.user_id IS NOT NULL AND x.user_id IS DISTINCT FROM p.user_id'
           INTO mismatch_count;
        IF mismatch_count > 0 THEN
            RAISE EXCEPTION 'Ownership migration stopped: % horarios_celdas rows do not match their horario owner.', mismatch_count;
        END IF;
    END IF;
END;
$$;

-- Add columns first so this migration is safe across partially updated schemas.
ALTER TABLE public.configs           ADD COLUMN IF NOT EXISTS user_id uuid;
ALTER TABLE public.docentes          ADD COLUMN IF NOT EXISTS user_id uuid;
ALTER TABLE public.cursos            ADD COLUMN IF NOT EXISTS user_id uuid;
ALTER TABLE public.materias          ADD COLUMN IF NOT EXISTS user_id uuid;
ALTER TABLE public.salones           ADD COLUMN IF NOT EXISTS user_id uuid;
ALTER TABLE public.disponibilidades  ADD COLUMN IF NOT EXISTS user_id uuid;
ALTER TABLE public.docente_materia   ADD COLUMN IF NOT EXISTS user_id uuid;
ALTER TABLE public.docente_curso     ADD COLUMN IF NOT EXISTS user_id uuid;
ALTER TABLE public.horarios          ADD COLUMN IF NOT EXISTS user_id uuid;
ALTER TABLE public.horarios          ADD COLUMN IF NOT EXISTS usuario_id uuid;
ALTER TABLE public.celdas            ADD COLUMN IF NOT EXISTS user_id uuid;
DO $$
BEGIN
    IF to_regclass('public.horarios_celdas') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.horarios_celdas ADD COLUMN IF NOT EXISTS user_id uuid';
    END IF;
END;
$$;

-- A previous partial rollout may already have installed the guard; remove it
-- while owner values are being reconciled, then recreate it after backfill.
DO $$
DECLARE target_table text;
BEGIN
    FOREACH target_table IN ARRAY ARRAY[
        'configs', 'docentes', 'cursos', 'materias', 'salones',
        'disponibilidades', 'docente_materia', 'docente_curso', 'horarios', 'celdas'
    ] LOOP
        IF to_regclass(format('public.%I', target_table)) IS NOT NULL THEN
            EXECUTE format('DROP TRIGGER IF EXISTS trg_validate_row_ownership ON public.%I', target_table);
        END IF;
    END LOOP;
    IF to_regclass('public.horarios_celdas') IS NOT NULL THEN
        EXECUTE 'DROP TRIGGER IF EXISTS trg_validate_row_ownership ON public.horarios_celdas';
    END IF;
END;
$$;

-- Top-level NULL owners use only the specifically authorized legacy admin.
UPDATE public.configs SET user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf' WHERE user_id IS NULL;
UPDATE public.docentes SET user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf' WHERE user_id IS NULL;
UPDATE public.cursos SET user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf' WHERE user_id IS NULL;
UPDATE public.materias SET user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf' WHERE user_id IS NULL;
UPDATE public.salones SET user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf' WHERE user_id IS NULL;

-- Preserve a known legacy schedule owner; backfill only if neither alias exists.
UPDATE public.horarios
   SET user_id = COALESCE(user_id, usuario_id, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
       usuario_id = COALESCE(usuario_id, user_id, 'f66d8637-c374-4602-b748-b9b9737abfbf')
 WHERE user_id IS NULL OR usuario_id IS NULL;

-- Dependents inherit from their actual parent, not from the acting admin.
UPDATE public.disponibilidades x SET user_id = d.user_id
  FROM public.docentes d WHERE x.docente_id = d.id AND x.user_id IS NULL;
UPDATE public.disponibilidades SET user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf' WHERE user_id IS NULL;
UPDATE public.docente_materia x SET user_id = d.user_id
  FROM public.docentes d WHERE x.docente_id = d.id AND x.user_id IS NULL;
UPDATE public.docente_materia SET user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf' WHERE user_id IS NULL;
UPDATE public.docente_curso x SET user_id = d.user_id
  FROM public.docentes d WHERE x.docente_id = d.id AND x.user_id IS NULL;
UPDATE public.docente_curso SET user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf' WHERE user_id IS NULL;
UPDATE public.celdas x SET user_id = h.user_id
  FROM public.horarios h WHERE x.horario_id = h.id AND x.user_id IS NULL;
UPDATE public.celdas SET user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf' WHERE user_id IS NULL;
DO $$
BEGIN
    IF to_regclass('public.horarios_celdas') IS NOT NULL THEN
        EXECUTE 'UPDATE public.horarios_celdas x SET user_id = h.user_id
                   FROM public.horarios h WHERE x.horario_id = h.id AND x.user_id IS NULL';
        EXECUTE 'UPDATE public.horarios_celdas SET user_id = ''f66d8637-c374-4602-b748-b9b9737abfbf'' WHERE user_id IS NULL';
    END IF;
END;
$$;

-- Ensure each owner UUID is a real Auth account, without duplicating a
-- pre-existing FK that already targets auth.users(id).
DO $$
DECLARE target_table text;
        owner_attnum smallint;
BEGIN
    FOREACH target_table IN ARRAY ARRAY[
        'configs', 'docentes', 'cursos', 'materias', 'salones',
        'disponibilidades', 'docente_materia', 'docente_curso', 'horarios', 'celdas'
    ] LOOP
        SELECT attnum INTO owner_attnum FROM pg_attribute
         WHERE attrelid = format('public.%I', target_table)::regclass
           AND attname = 'user_id' AND NOT attisdropped;
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint c
             WHERE c.conrelid = format('public.%I', target_table)::regclass
               AND c.contype = 'f' AND c.confrelid = 'auth.users'::regclass
               AND c.conkey = ARRAY[owner_attnum]::smallint[]
        ) THEN
            EXECUTE format(
                'ALTER TABLE public.%I ADD CONSTRAINT %I FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE',
                target_table, target_table || '_user_id_fkey'
            );
        END IF;
    END LOOP;
    SELECT attnum INTO owner_attnum FROM pg_attribute
     WHERE attrelid = 'public.horarios'::regclass
       AND attname = 'usuario_id' AND NOT attisdropped;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
         WHERE c.conrelid = 'public.horarios'::regclass
           AND c.contype = 'f' AND c.confrelid = 'auth.users'::regclass
           AND c.conkey = ARRAY[owner_attnum]::smallint[]
    ) THEN
        ALTER TABLE public.horarios ADD CONSTRAINT horarios_usuario_id_fkey
            FOREIGN KEY (usuario_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF to_regclass('public.horarios_celdas') IS NOT NULL THEN
        SELECT attnum INTO owner_attnum FROM pg_attribute
         WHERE attrelid = 'public.horarios_celdas'::regclass
           AND attname = 'user_id' AND NOT attisdropped;
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint c
             WHERE c.conrelid = 'public.horarios_celdas'::regclass
               AND c.contype = 'f' AND c.confrelid = 'auth.users'::regclass
               AND c.conkey = ARRAY[owner_attnum]::smallint[]
        ) THEN
            ALTER TABLE public.horarios_celdas ADD CONSTRAINT horarios_celdas_user_id_fkey
                FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
        END IF;
    END IF;
END;
$$;

ALTER TABLE public.configs          ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.docentes         ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.cursos           ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.materias         ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.salones          ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.disponibilidades ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.docente_materia  ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.docente_curso    ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.horarios         ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.horarios         ALTER COLUMN usuario_id SET NOT NULL;
ALTER TABLE public.celdas           ALTER COLUMN user_id SET NOT NULL;
DO $$
BEGIN
    IF to_regclass('public.horarios_celdas') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.horarios_celdas ALTER COLUMN user_id SET NOT NULL';
    END IF;
END;
$$;

-- Remove the former cross-account catalog uniqueness constraints.
ALTER TABLE public.docentes DROP CONSTRAINT IF EXISTS docentes_documento_key;
ALTER TABLE public.docentes DROP CONSTRAINT IF EXISTS docentes_email_key;
ALTER TABLE public.cursos DROP CONSTRAINT IF EXISTS cursos_nombre_key;
ALTER TABLE public.materias DROP CONSTRAINT IF EXISTS materias_nombre_key;
ALTER TABLE public.salones DROP CONSTRAINT IF EXISTS salones_nombre_key;
DO $$
DECLARE unique_constraint record;
BEGIN
    FOR unique_constraint IN
        SELECT t.relname AS table_name, c.conname AS constraint_name
          FROM pg_constraint c
          JOIN pg_class t ON t.oid = c.conrelid
          JOIN pg_namespace n ON n.oid = t.relnamespace
          JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = c.conkey[1]
         WHERE n.nspname = 'public' AND c.contype = 'u'
           AND array_length(c.conkey, 1) = 1
           AND ((t.relname = 'configs' AND a.attname = 'activa')
             OR (t.relname = 'docentes' AND a.attname IN ('documento', 'email'))
             OR (t.relname IN ('cursos', 'materias', 'salones') AND a.attname = 'nombre'))
    LOOP
        EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT %I', unique_constraint.table_name, unique_constraint.constraint_name);
    END LOOP;
END;
$$;
DO $$
DECLARE unique_index record;
BEGIN
    FOR unique_index IN
        SELECT i.indexrelid::regclass AS index_name
          FROM pg_index i
          JOIN pg_class t ON t.oid = i.indrelid
          JOIN pg_namespace n ON n.oid = t.relnamespace
          JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = i.indkey[0]
         WHERE n.nspname = 'public'
           AND i.indisunique AND NOT i.indisprimary AND i.indnkeyatts = 1
           AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid)
           AND ((t.relname = 'configs' AND a.attname = 'activa')
             OR (t.relname = 'docentes' AND a.attname IN ('documento', 'email'))
             OR (t.relname IN ('cursos', 'materias', 'salones') AND a.attname = 'nombre'))
    LOOP
        EXECUTE format('DROP INDEX %s', unique_index.index_name);
    END LOOP;
END;
$$;
DROP INDEX IF EXISTS public.uidx_configs_activa;
DROP INDEX IF EXISTS public.uidx_docentes_user_documento;
DROP INDEX IF EXISTS public.uidx_docentes_user_email;
DROP INDEX IF EXISTS public.uidx_cursos_user_nombre;
DROP INDEX IF EXISTS public.uidx_materias_user_nombre;
DROP INDEX IF EXISTS public.uidx_salones_user_nombre;
CREATE UNIQUE INDEX uidx_configs_activa ON public.configs (user_id) WHERE activa = true;
CREATE UNIQUE INDEX uidx_docentes_user_documento ON public.docentes (user_id, documento);
CREATE UNIQUE INDEX uidx_docentes_user_email ON public.docentes (user_id, email) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX uidx_cursos_user_nombre ON public.cursos (user_id, nombre);
CREATE UNIQUE INDEX uidx_materias_user_nombre ON public.materias (user_id, nombre);
CREATE UNIQUE INDEX uidx_salones_user_nombre ON public.salones (user_id, nombre);
DROP INDEX IF EXISTS public.idx_horarios_usuario;
CREATE INDEX idx_horarios_usuario ON public.horarios (user_id);
CREATE INDEX IF NOT EXISTS idx_disponibilidades_user ON public.disponibilidades (user_id, docente_id);
CREATE INDEX IF NOT EXISTS idx_docente_materia_user ON public.docente_materia (user_id, docente_id);
CREATE INDEX IF NOT EXISTS idx_docente_curso_user ON public.docente_curso (user_id, docente_id);
CREATE INDEX IF NOT EXISTS idx_celdas_user ON public.celdas (user_id, horario_id);

-- Rebuild the owner guard after backfill; parent ownership cannot drift later.
CREATE OR REPLACE FUNCTION public.validate_row_ownership()
RETURNS trigger LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE parent_owner uuid;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.user_id IS DISTINCT FROM OLD.user_id THEN
        RAISE EXCEPTION 'user_id ownership cannot be changed';
    END IF;
    IF TG_TABLE_NAME = 'horarios' AND NEW.user_id IS DISTINCT FROM NEW.usuario_id THEN
        RAISE EXCEPTION 'horarios.user_id and horarios.usuario_id must match';
    ELSIF TG_TABLE_NAME IN ('disponibilidades', 'docente_materia', 'docente_curso') THEN
        SELECT d.user_id INTO parent_owner FROM public.docentes d WHERE d.id = NEW.docente_id;
    ELSIF TG_TABLE_NAME IN ('celdas', 'horarios_celdas') THEN
        SELECT h.user_id INTO parent_owner FROM public.horarios h WHERE h.id = NEW.horario_id;
    END IF;
    IF parent_owner IS NOT NULL AND NEW.user_id IS DISTINCT FROM parent_owner THEN
        RAISE EXCEPTION 'dependent row user_id must match its parent owner';
    END IF;
    RETURN NEW;
END;
$$;
DO $$
DECLARE target_table text;
BEGIN
    FOREACH target_table IN ARRAY ARRAY[
        'configs', 'docentes', 'cursos', 'materias', 'salones',
        'disponibilidades', 'docente_materia', 'docente_curso', 'horarios', 'celdas'
    ] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_validate_row_ownership ON public.%I', target_table);
        EXECUTE format('CREATE TRIGGER trg_validate_row_ownership BEFORE INSERT OR UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.validate_row_ownership()', target_table);
    END LOOP;
    IF to_regclass('public.horarios_celdas') IS NOT NULL THEN
        EXECUTE 'DROP TRIGGER IF EXISTS trg_validate_row_ownership ON public.horarios_celdas';
        EXECUTE 'CREATE TRIGGER trg_validate_row_ownership BEFORE INSERT OR UPDATE ON public.horarios_celdas FOR EACH ROW EXECUTE FUNCTION public.validate_row_ownership()';
    END IF;
END;
$$;

-- Completion validation must compare only the schedule owner's catalogs.
CREATE OR REPLACE FUNCTION public.sch_horario_validar()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.estado = 'completo' OR NEW.estado IS DISTINCT FROM 'completo' THEN
        RETURN NEW;
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.cursos cu
        LEFT JOIN public.celdas cc
          ON cc.curso_id = cu.id AND cc.horario_id = NEW.id AND cc.user_id = NEW.user_id
        WHERE cu.user_id = NEW.user_id
        GROUP BY cu.id, cu.nombre, cu.horas_semanales
        HAVING COALESCE(SUM(EXTRACT(EPOCH FROM (cc.hora_fin - cc.hora_inicio)) / 60), 0)
               <> cu.horas_semanales * 60
    ) THEN
        RAISE EXCEPTION 'La carga semanal de algún curso no cuadra con sus horas_semanales.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.materias m
        JOIN public.celdas c ON c.materia_id = m.id AND c.horario_id = NEW.id AND c.user_id = NEW.user_id
        WHERE m.user_id = NEW.user_id
        GROUP BY m.id, m.nombre, m.min_horas, m.max_horas, c.curso_id
        HAVING SUM(EXTRACT(EPOCH FROM (c.hora_fin - c.hora_inicio)) / 60)
               NOT BETWEEN m.min_horas * 60 AND m.max_horas * 60
    ) THEN
        RAISE EXCEPTION 'Alguna materia no cumple su intensidad horaria [min, max].';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.docentes d
        JOIN public.celdas c ON c.docente_id = d.id AND c.horario_id = NEW.id AND c.user_id = NEW.user_id
        WHERE d.user_id = NEW.user_id
        GROUP BY d.id, d.nombre, d.carga_horaria
        HAVING SUM(EXTRACT(EPOCH FROM (c.hora_fin - c.hora_inicio)) / 60) > d.carga_horaria * 60
    ) THEN
        RAISE EXCEPTION 'Algún docente supera su carga académica contractual.';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_horarios_validar ON public.horarios;
CREATE TRIGGER trg_horarios_validar BEFORE UPDATE OF estado ON public.horarios
FOR EACH ROW EXECUTE FUNCTION public.sch_horario_validar();

CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT EXISTS (SELECT 1 FROM public.perfiles p WHERE p.id = auth.uid() AND p.role = 'admin');
$$;
REVOKE ALL ON FUNCTION public.is_admin() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_admin() TO authenticated;

ALTER TABLE public.configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.docentes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cursos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.materias ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.salones ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.disponibilidades ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.docente_materia ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.docente_curso ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.horarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.celdas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.perfiles ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.perfiles FROM PUBLIC, anon, authenticated;

DO $$
DECLARE target_table text;
        policy_row record;
BEGIN
    FOREACH target_table IN ARRAY ARRAY[
        'configs', 'docentes', 'cursos', 'materias', 'salones',
        'disponibilidades', 'docente_materia', 'docente_curso', 'horarios', 'celdas'
    ] LOOP
        FOR policy_row IN SELECT policyname FROM pg_policies
            WHERE schemaname = 'public' AND tablename = target_table
        LOOP
            EXECUTE format('DROP POLICY %I ON public.%I', policy_row.policyname, target_table);
        END LOOP;
    END LOOP;
    IF to_regclass('public.horarios_celdas') IS NOT NULL THEN
        FOR policy_row IN SELECT policyname FROM pg_policies
            WHERE schemaname = 'public' AND tablename = 'horarios_celdas'
        LOOP
            EXECUTE format('DROP POLICY %I ON public.horarios_celdas', policy_row.policyname);
        END LOOP;
    END IF;
END;
$$;
DO $$
DECLARE target_table text;
BEGIN
    FOREACH target_table IN ARRAY ARRAY['configs', 'docentes', 'cursos', 'materias', 'salones'] LOOP
        EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (user_id = auth.uid() OR public.is_admin())', target_table || '_owner_select', target_table);
        EXECUTE format('CREATE POLICY %I ON public.%I FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid())', target_table || '_actor_insert', target_table);
        EXECUTE format('CREATE POLICY %I ON public.%I FOR UPDATE TO authenticated USING (user_id = auth.uid() OR public.is_admin()) WITH CHECK (user_id = auth.uid() OR public.is_admin())', target_table || '_owner_update', target_table);
        EXECUTE format('CREATE POLICY %I ON public.%I FOR DELETE TO authenticated USING (user_id = auth.uid() OR public.is_admin())', target_table || '_owner_delete', target_table);
    END LOOP;
END;
$$;

CREATE POLICY disponibilidades_owner_admin ON public.disponibilidades FOR ALL TO authenticated
    USING (user_id = auth.uid() OR public.is_admin())
    WITH CHECK ((user_id = auth.uid() AND EXISTS (SELECT 1 FROM public.docentes d WHERE d.id = disponibilidades.docente_id AND d.user_id = auth.uid()))
        OR (public.is_admin() AND EXISTS (SELECT 1 FROM public.docentes d WHERE d.id = disponibilidades.docente_id AND d.user_id = disponibilidades.user_id)));
CREATE POLICY docente_materia_owner_admin ON public.docente_materia FOR ALL TO authenticated
    USING (user_id = auth.uid() OR public.is_admin())
    WITH CHECK ((user_id = auth.uid() AND EXISTS (SELECT 1 FROM public.docentes d WHERE d.id = docente_materia.docente_id AND d.user_id = auth.uid())
        AND EXISTS (SELECT 1 FROM public.materias m WHERE m.id = docente_materia.materia_id AND m.user_id = auth.uid()))
        OR (public.is_admin() AND EXISTS (SELECT 1 FROM public.docentes d WHERE d.id = docente_materia.docente_id AND d.user_id = docente_materia.user_id)
            AND EXISTS (SELECT 1 FROM public.materias m WHERE m.id = docente_materia.materia_id AND m.user_id = docente_materia.user_id)));
CREATE POLICY docente_curso_owner_admin ON public.docente_curso FOR ALL TO authenticated
    USING (user_id = auth.uid() OR public.is_admin())
    WITH CHECK ((user_id = auth.uid() AND EXISTS (SELECT 1 FROM public.docentes d WHERE d.id = docente_curso.docente_id AND d.user_id = auth.uid())
        AND EXISTS (SELECT 1 FROM public.cursos c WHERE c.id = docente_curso.curso_id AND c.user_id = auth.uid()))
        OR (public.is_admin() AND EXISTS (SELECT 1 FROM public.docentes d WHERE d.id = docente_curso.docente_id AND d.user_id = docente_curso.user_id)
            AND EXISTS (SELECT 1 FROM public.cursos c WHERE c.id = docente_curso.curso_id AND c.user_id = docente_curso.user_id)));
CREATE POLICY horarios_owner_select ON public.horarios FOR SELECT TO authenticated USING (user_id = auth.uid() OR public.is_admin());
CREATE POLICY horarios_actor_insert ON public.horarios FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid() AND usuario_id = auth.uid());
CREATE POLICY horarios_owner_update ON public.horarios FOR UPDATE TO authenticated
    USING (user_id = auth.uid() OR public.is_admin())
    WITH CHECK ((user_id = auth.uid() AND usuario_id = auth.uid()) OR public.is_admin());
CREATE POLICY horarios_owner_delete ON public.horarios FOR DELETE TO authenticated USING (user_id = auth.uid() OR public.is_admin());
CREATE POLICY celdas_owner_admin ON public.celdas FOR ALL TO authenticated
    USING ((user_id = auth.uid() AND EXISTS (SELECT 1 FROM public.horarios h WHERE h.id = celdas.horario_id AND h.user_id = auth.uid())) OR public.is_admin())
    WITH CHECK ((user_id = auth.uid() AND EXISTS (SELECT 1 FROM public.horarios h WHERE h.id = celdas.horario_id AND h.user_id = auth.uid())
        AND EXISTS (SELECT 1 FROM public.cursos cu WHERE cu.id = celdas.curso_id AND cu.user_id = auth.uid())
        AND EXISTS (SELECT 1 FROM public.materias m WHERE m.id = celdas.materia_id AND m.user_id = auth.uid())
        AND EXISTS (SELECT 1 FROM public.docentes d WHERE d.id = celdas.docente_id AND d.user_id = auth.uid())
        AND EXISTS (SELECT 1 FROM public.salones s WHERE s.id = celdas.salon_id AND s.user_id = auth.uid()))
        OR (public.is_admin() AND EXISTS (SELECT 1 FROM public.horarios h WHERE h.id = celdas.horario_id AND h.user_id = celdas.user_id)
        AND EXISTS (SELECT 1 FROM public.cursos cu WHERE cu.id = celdas.curso_id AND cu.user_id = celdas.user_id)
        AND EXISTS (SELECT 1 FROM public.materias m WHERE m.id = celdas.materia_id AND m.user_id = celdas.user_id)
        AND EXISTS (SELECT 1 FROM public.docentes d WHERE d.id = celdas.docente_id AND d.user_id = celdas.user_id)
        AND EXISTS (SELECT 1 FROM public.salones s WHERE s.id = celdas.salon_id AND s.user_id = celdas.user_id)));

DO $$
BEGIN
    IF to_regclass('public.horarios_celdas') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.horarios_celdas ENABLE ROW LEVEL SECURITY';
        EXECUTE 'DROP POLICY IF EXISTS horarios_celdas_owner_admin ON public.horarios_celdas';
        EXECUTE $policy$
            CREATE POLICY horarios_celdas_owner_admin ON public.horarios_celdas FOR ALL TO authenticated
            USING ((user_id = auth.uid() AND EXISTS (SELECT 1 FROM public.horarios h WHERE h.id = horarios_celdas.horario_id AND h.user_id = auth.uid())) OR public.is_admin())
            WITH CHECK ((user_id = auth.uid() AND EXISTS (SELECT 1 FROM public.horarios h WHERE h.id = horarios_celdas.horario_id AND h.user_id = auth.uid()))
                OR (public.is_admin() AND EXISTS (SELECT 1 FROM public.horarios h WHERE h.id = horarios_celdas.horario_id AND h.user_id = horarios_celdas.user_id)))
        $policy$;
    END IF;
END;
$$;

COMMIT;
