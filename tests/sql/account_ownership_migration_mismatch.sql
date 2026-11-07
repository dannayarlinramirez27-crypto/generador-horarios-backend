-- Create a known conflicting schedule-owner pair for the preflight test.
UPDATE public.horarios
   SET user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf',
       usuario_id = 'a2c33a5c-7f3d-4c22-b8e8-30a5ac7e4a02'
 WHERE id = 910009;
