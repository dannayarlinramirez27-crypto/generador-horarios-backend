DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.docente_materia
         WHERE id = 910007 AND user_id IS NULL AND materia_id = 910013
    ) THEN
        RAISE EXCEPTION 'Failed cross-reference preflight changed the assignment fixture';
    END IF;
    IF (SELECT user_id FROM public.materias WHERE id = 910013) IS NOT NULL THEN
        RAISE EXCEPTION 'Failed cross-reference preflight partially backfilled the foreign materia';
    END IF;
    IF (SELECT user_id FROM public.configs WHERE id = 910011) IS NOT NULL THEN
        RAISE EXCEPTION 'Failed cross-reference preflight partially backfilled a top-level owner';
    END IF;
    IF (SELECT attnotnull FROM pg_attribute
         WHERE attrelid = 'public.configs'::regclass AND attname = 'user_id') THEN
        RAISE EXCEPTION 'Failed cross-reference preflight partially changed the legacy schema';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'public.configs'::regclass
           AND conname = 'configs_user_id_fkey'
    ) THEN
        RAISE EXCEPTION 'Failed cross-reference preflight partially installed an owner foreign key';
    END IF;
END;
$$;
