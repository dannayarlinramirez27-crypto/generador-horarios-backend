-- Restore the legacy schedule alias state and rerun the migration successfully.
UPDATE public.horarios
   SET user_id = NULL,
       usuario_id = 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'
 WHERE id = 910009;

UPDATE public.docente_materia SET materia_id = 910004 WHERE id = 910007;
