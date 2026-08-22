-- Mock del schema auth de Supabase para tests en CI (Postgres vanilla).
-- Supabase tiene este schema pre-instalado; en CI local lo creamos.
-- auth.uid() lee el sub del JWT actual (request.jwt.claims).
-- auth.users es una tabla simple que simula los usuarios de Supabase Auth.

CREATE SCHEMA IF NOT EXISTS auth;

-- Tabla de usuarios (simplificada)
CREATE TABLE IF NOT EXISTS auth.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text,
    created_at timestamptz DEFAULT now()
);

-- auth.uid(): devuelve el UUID del usuario actual desde request.jwt.claims
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(
        (current_setting('request.jwt.claims', true)::json ->> 'sub'),
        ''
    )::uuid;
$$;
