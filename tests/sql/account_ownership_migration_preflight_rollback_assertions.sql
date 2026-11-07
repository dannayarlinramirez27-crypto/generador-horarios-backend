DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.horarios
         WHERE id = 910009
           AND user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf'
           AND usuario_id = 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'
    ) THEN
        RAISE EXCEPTION 'Failed preflight changed the conflicting horario fixture';
    END IF;
    IF (SELECT user_id FROM public.configs WHERE id = 910011) IS NOT NULL THEN
        RAISE EXCEPTION 'Failed preflight partially backfilled a top-level owner';
    END IF;
    IF (SELECT attnotnull FROM pg_attribute
         WHERE attrelid = 'public.configs'::regclass AND attname = 'user_id') THEN
        RAISE EXCEPTION 'Failed preflight partially changed the legacy schema';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'public.configs'::regclass
           AND conname = 'configs_user_id_fkey'
    ) THEN
        RAISE EXCEPTION 'Failed preflight partially installed an owner foreign key';
    END IF;
END;
$$;
