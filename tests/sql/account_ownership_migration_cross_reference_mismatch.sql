-- The assignment owner is inherited from its docente, but its materia belongs
-- to a distinct ownerless legacy row that will backfill to the authorized admin.
UPDATE public.docente_materia SET materia_id = 910013 WHERE id = 910007;
