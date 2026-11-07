-- Owner isolation for direct Supabase clients. The backend uses Psycopg with its
-- server credential and independently applies the same owner predicates.
BEGIN;

CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1
          FROM public.perfiles p
         WHERE p.id = auth.uid()
           AND p.role = 'admin'
    );
$$;
REVOKE ALL ON FUNCTION public.is_admin() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_admin() TO authenticated;

ALTER TABLE configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE docentes ENABLE ROW LEVEL SECURITY;
ALTER TABLE cursos ENABLE ROW LEVEL SECURITY;
ALTER TABLE materias ENABLE ROW LEVEL SECURITY;
ALTER TABLE salones ENABLE ROW LEVEL SECURITY;
ALTER TABLE disponibilidades ENABLE ROW LEVEL SECURITY;
ALTER TABLE docente_materia ENABLE ROW LEVEL SECURITY;
ALTER TABLE docente_curso ENABLE ROW LEVEL SECURITY;
ALTER TABLE horarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE celdas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.perfiles ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.perfiles FROM PUBLIC, anon, authenticated;

-- Remove previous shared-catalog and schedule-only policies. Policies are
-- permissive by default, so retaining even one old global policy would bypass
-- the owner checks below.
DO $$
DECLARE target_table text;
        policy_row record;
BEGIN
    FOREACH target_table IN ARRAY ARRAY[
        'configs', 'docentes', 'cursos', 'materias', 'salones',
        'disponibilidades', 'docente_materia', 'docente_curso', 'horarios', 'celdas'
    ] LOOP
        FOR policy_row IN
            SELECT policyname FROM pg_policies
             WHERE schemaname = 'public' AND tablename = target_table
        LOOP
            EXECUTE format('DROP POLICY %I ON public.%I', policy_row.policyname, target_table);
        END LOOP;
    END LOOP;
    IF to_regclass('public.horarios_celdas') IS NOT NULL THEN
        FOR policy_row IN
            SELECT policyname FROM pg_policies
             WHERE schemaname = 'public' AND tablename = 'horarios_celdas'
        LOOP
            EXECUTE format('DROP POLICY %I ON public.horarios_celdas', policy_row.policyname);
        END LOOP;
    END IF;
END;
$$;

-- Standalone inserts always belong to the actor, including admin-created rows.
-- Admins may later manage any row; ownership itself is immutable by trigger.
DO $$
DECLARE target_table text;
BEGIN
    FOREACH target_table IN ARRAY ARRAY['configs', 'docentes', 'cursos', 'materias', 'salones'] LOOP
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (user_id = auth.uid() OR public.is_admin())',
            target_table || '_owner_select', target_table
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid())',
            target_table || '_actor_insert', target_table
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR UPDATE TO authenticated USING (user_id = auth.uid() OR public.is_admin()) WITH CHECK (user_id = auth.uid() OR public.is_admin())',
            target_table || '_owner_update', target_table
        );
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR DELETE TO authenticated USING (user_id = auth.uid() OR public.is_admin())',
            target_table || '_owner_delete', target_table
        );
    END LOOP;
END;
$$;

CREATE POLICY disponibilidades_owner_admin ON disponibilidades FOR ALL TO authenticated
    USING (user_id = auth.uid() OR public.is_admin())
    WITH CHECK (
        (user_id = auth.uid() AND EXISTS (
            SELECT 1 FROM public.docentes d
             WHERE d.id = disponibilidades.docente_id AND d.user_id = auth.uid()
        )) OR (public.is_admin() AND EXISTS (
            SELECT 1 FROM public.docentes d
             WHERE d.id = disponibilidades.docente_id
               AND d.user_id = disponibilidades.user_id
        ))
    );
CREATE POLICY docente_materia_owner_admin ON docente_materia FOR ALL TO authenticated
    USING (user_id = auth.uid() OR public.is_admin())
    WITH CHECK (
        (user_id = auth.uid() AND EXISTS (
            SELECT 1 FROM public.docentes d
             WHERE d.id = docente_materia.docente_id AND d.user_id = auth.uid()
         ) AND EXISTS (
             SELECT 1 FROM public.materias m
              WHERE m.id = docente_materia.materia_id AND m.user_id = auth.uid()
         )) OR (public.is_admin() AND EXISTS (
             SELECT 1 FROM public.docentes d
              WHERE d.id = docente_materia.docente_id
                AND d.user_id = docente_materia.user_id
         ) AND EXISTS (
             SELECT 1 FROM public.materias m
              WHERE m.id = docente_materia.materia_id
                AND m.user_id = docente_materia.user_id
         ))
    );
CREATE POLICY docente_curso_owner_admin ON docente_curso FOR ALL TO authenticated
    USING (user_id = auth.uid() OR public.is_admin())
    WITH CHECK (
        (user_id = auth.uid() AND EXISTS (
            SELECT 1 FROM public.docentes d
             WHERE d.id = docente_curso.docente_id AND d.user_id = auth.uid()
         ) AND EXISTS (
             SELECT 1 FROM public.cursos c
              WHERE c.id = docente_curso.curso_id AND c.user_id = auth.uid()
         )) OR (public.is_admin() AND EXISTS (
             SELECT 1 FROM public.docentes d
              WHERE d.id = docente_curso.docente_id
                AND d.user_id = docente_curso.user_id
         ) AND EXISTS (
             SELECT 1 FROM public.cursos c
              WHERE c.id = docente_curso.curso_id
                AND c.user_id = docente_curso.user_id
         ))
    );

-- Schedules are canonically owned by user_id. usuario_id remains a matching
-- compatibility alias. Inserts always belong to the authenticated actor.
CREATE POLICY horarios_owner_select ON horarios FOR SELECT TO authenticated
    USING (user_id = auth.uid() OR public.is_admin());
CREATE POLICY horarios_actor_insert ON horarios FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid() AND usuario_id = auth.uid());
CREATE POLICY horarios_owner_update ON horarios FOR UPDATE TO authenticated
    USING (user_id = auth.uid() OR public.is_admin())
    WITH CHECK ((user_id = auth.uid() AND usuario_id = auth.uid()) OR public.is_admin());
CREATE POLICY horarios_owner_delete ON horarios FOR DELETE TO authenticated
    USING (user_id = auth.uid() OR public.is_admin());

CREATE POLICY celdas_owner_admin ON celdas FOR ALL TO authenticated
    USING (
        (user_id = auth.uid() AND EXISTS (
            SELECT 1 FROM public.horarios h
             WHERE h.id = celdas.horario_id AND h.user_id = auth.uid()
        )) OR public.is_admin()
    )
    WITH CHECK (
        (user_id = auth.uid() AND EXISTS (
            SELECT 1 FROM public.horarios h
             WHERE h.id = celdas.horario_id AND h.user_id = auth.uid()
        ) AND EXISTS (
            SELECT 1 FROM public.cursos cu
             WHERE cu.id = celdas.curso_id AND cu.user_id = auth.uid()
        ) AND EXISTS (
            SELECT 1 FROM public.materias m
             WHERE m.id = celdas.materia_id AND m.user_id = auth.uid()
        ) AND EXISTS (
            SELECT 1 FROM public.docentes d
             WHERE d.id = celdas.docente_id AND d.user_id = auth.uid()
        ) AND EXISTS (
            SELECT 1 FROM public.salones s
             WHERE s.id = celdas.salon_id AND s.user_id = auth.uid()
        )) OR (public.is_admin() AND EXISTS (
            SELECT 1 FROM public.horarios h
             WHERE h.id = celdas.horario_id AND h.user_id = celdas.user_id
        ) AND EXISTS (
            SELECT 1 FROM public.cursos cu
             WHERE cu.id = celdas.curso_id AND cu.user_id = celdas.user_id
        ) AND EXISTS (
            SELECT 1 FROM public.materias m
             WHERE m.id = celdas.materia_id AND m.user_id = celdas.user_id
        ) AND EXISTS (
            SELECT 1 FROM public.docentes d
             WHERE d.id = celdas.docente_id AND d.user_id = celdas.user_id
        ) AND EXISTS (
            SELECT 1 FROM public.salones s
             WHERE s.id = celdas.salon_id AND s.user_id = celdas.user_id
        ))
    );

-- Existing deployments may retain the historical table name. It is private
-- and its rows inherit ownership from horarios, like celdas.
DO $$
BEGIN
    IF to_regclass('public.horarios_celdas') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.horarios_celdas ENABLE ROW LEVEL SECURITY';
        EXECUTE 'DROP POLICY IF EXISTS horarios_celdas_owner_admin ON public.horarios_celdas';
        EXECUTE $policy$
            CREATE POLICY horarios_celdas_owner_admin ON public.horarios_celdas
            FOR ALL TO authenticated
            USING ((user_id = auth.uid() AND EXISTS (
                SELECT 1 FROM public.horarios h
                 WHERE h.id = horarios_celdas.horario_id AND h.user_id = auth.uid()
            )) OR public.is_admin())
            WITH CHECK ((user_id = auth.uid() AND EXISTS (
                SELECT 1 FROM public.horarios h
                 WHERE h.id = horarios_celdas.horario_id AND h.user_id = auth.uid()
            )) OR (public.is_admin() AND EXISTS (
                SELECT 1 FROM public.horarios h
                 WHERE h.id = horarios_celdas.horario_id AND h.user_id = horarios_celdas.user_id
            )))
        $policy$;
    END IF;
END;
$$;

COMMIT;
