-- Idempotent deployment script for server-owned authentication profiles.
-- Run with a database owner/Supabase migration role; do not grant profile writes
-- to browser roles. This setup is also included in schema.sql for fresh installs.
BEGIN;

CREATE TABLE IF NOT EXISTS public.perfiles (
    id         uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email      text,
    role       text NOT NULL DEFAULT 'docente'
               CHECK (role IN ('admin', 'docente')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION public.create_default_profile_for_auth_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.perfiles (id, email, role)
    VALUES (NEW.id, NEW.email, 'docente')
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.create_default_profile_for_auth_user()
    FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS trg_auth_user_create_profile ON auth.users;
CREATE TRIGGER trg_auth_user_create_profile
AFTER INSERT ON auth.users
FOR EACH ROW
EXECUTE FUNCTION public.create_default_profile_for_auth_user();

-- Preserve trusted server metadata and the historical admin identities.
-- raw_user_meta_data is intentionally excluded because users can edit it.
INSERT INTO public.perfiles (id, email, role)
SELECT u.id,
       u.email,
       CASE
           WHEN u.raw_app_meta_data ->> 'role' IN ('admin', 'docente')
               THEN u.raw_app_meta_data ->> 'role'
           WHEN lower(btrim(coalesce(u.email, ''))) IN (
               'dannayarlinramirez0827@gmail.com',
               'dannayarlinramirez27@gmail.com'
           ) THEN 'admin'
           WHEN docente_match.match_count = 1 THEN 'docente'
           ELSE 'docente'
       END
  FROM auth.users AS u
  LEFT JOIN LATERAL (
      SELECT count(*) AS match_count
        FROM public.docentes AS d
       WHERE u.email IS NOT NULL
         AND lower(d.email) = lower(u.email)
  ) AS docente_match ON true
ON CONFLICT (id) DO NOTHING;

ALTER TABLE public.perfiles ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.perfiles FROM PUBLIC, anon, authenticated;

COMMIT;
