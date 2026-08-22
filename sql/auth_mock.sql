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

-- Tabla de usuarios (simula auth.users de Supabase con las columnas
-- que usan los tests de RLS)
CREATE TABLE IF NOT EXISTS auth.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id uuid,
    aud text,
    role text,
    email text,
    email_confirmed_at timestamptz,
    raw_app_meta_data jsonb DEFAULT '{}'::jsonb,
    raw_user_meta_data jsonb DEFAULT '{}'::jsonb,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Usuario por defecto para CI (auth.uid() lo usa cuando no hay JWT)
INSERT INTO auth.users (id, instance_id, aud, role, email,
                        email_confirmed_at, raw_app_meta_data, raw_user_meta_data,
                        created_at, updated_at)
VALUES ('00000000-0000-0000-0000-000000000000',
        '00000000-0000-0000-0000-000000000000',
        'authenticated', 'authenticated', 'ci@localhost',
        now(), '{}'::jsonb, '{}'::jsonb, now(), now())
ON CONFLICT (id) DO NOTHING;

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

-- Grants que Supabase configura automaticamente pero que no existen
-- en Postgres vanilla. Sin estos, los roles anon/authenticated no pueden
-- acceder a las tablas y los tests RLS fallan con "permission denied".
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO anon, authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA auth TO anon, authenticated;
