-- Mock del schema auth de Supabase para tests en CI (Postgres vanilla).
-- Supabase tiene este schema y estos roles pre-instalados; en CI local los creamos.
-- auth.uid() lee el sub del JWT actual (request.jwt.claims).
-- auth.users es una tabla simple que simula los usuarios de Supabase Auth.

-- Roles de Supabase (anon = sin login, authenticated = con JWT valido)
DO $$ BEGIN
    CREATE ROLE anon NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE ROLE authenticated NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE SCHEMA IF NOT EXISTS auth;

-- Tabla de usuarios (simplificada)
CREATE TABLE IF NOT EXISTS auth.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text,
    created_at timestamptz DEFAULT now()
);

-- auth.uid(): devuelve el UUID del usuario actual desde request.jwt.claims.
-- En CI sin JWT, devuelve un UUID fijo para que DEFAULT auth.uid() no sea NULL.
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT COALESCE(
        NULLIF(
            (current_setting('request.jwt.claims', true)::json ->> 'sub'),
            ''
        )::uuid,
        '00000000-0000-0000-0000-000000000000'::uuid
    );
$$;
