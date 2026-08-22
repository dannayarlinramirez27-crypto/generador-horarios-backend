-- Grants para CI: Supabase configura estos grants automaticamente,
-- pero en Postgres vanilla debemos otorgarlos manualmente.
-- Debe ejecutarse DESPUES de schema.sql y rls.sql (necesita que las
-- tablas existan).

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO anon, authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA auth TO anon, authenticated;
