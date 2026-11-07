-- ============================================================================
-- Datos de muestra — Sistema Generador de Horarios
-- Diseñados para que el solver CSP (jornada única 07:00-13:00, lun-vie,
-- bloques de 60 min = 30 slots semanales) pueda completar 2 cursos de 30 h.
-- Idempotente: seguro de ejecutar repetidas veces.
-- ============================================================================
BEGIN;

-- Sample catalog rows belong to the explicitly configured legacy admin account.
-- 1. Configuración de jornada activa (una por cuenta)
INSERT INTO configs (nombre, tipo_jornada, dias_laborables, hora_inicio, hora_fin, minutos_bloque, activa, user_id)
SELECT 'Jornada Única', 'unica', ARRAY[1,2,3,4,5]::smallint[], '07:00', '13:00', 60, true,
       'f66d8637-c374-4602-b748-b9b9737abfbf'
WHERE NOT EXISTS (SELECT 1 FROM configs WHERE user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf');

-- 2. Cursos (6°A y 7°A, 30 h semanales cada uno)
INSERT INTO cursos (nombre, nivel, horas_semanales, orden, user_id) VALUES
    ('6°A', '6', 30, 1, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('7°A', '7', 30, 2, 'f66d8637-c374-4602-b748-b9b9737abfbf')
ON CONFLICT (user_id, nombre) DO NOTHING;

-- 3. Materias (los máximos de cada rango suman 30 h por curso)
INSERT INTO materias (nombre, categoria, min_horas, max_horas, requiere_salon, tipo_salon_requerido, no_ultima_hora, user_id) VALUES
    ('Matemáticas',        'basica',        3, 5, false, NULL,            false, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Lengua',             'basica',        3, 5, false, NULL,            false, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Ciencias Naturales', 'basica',        3, 5, true,  'laboratorio',   false, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Historia',           'basica',        3, 5, false, NULL,            false, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Inglés',             'basica',        3, 5, false, NULL,            false, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Ed. Física',         'otras',         1, 2, false, NULL,            false, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Informática',        'media_tecnica', 2, 3, true,  'laboratorio',   false, 'f66d8637-c374-4602-b748-b9b9737abfbf')
ON CONFLICT (user_id, nombre) DO NOTHING;

-- 4. Salones
-- Capacidad para 6 cursos de 30 h (180 bloques):
--   · 5 aulas  × 30 slots = 150  ≥ 132 bloques de aula requeridos (5 materias × 6 cursos)
--   · 2 labs   × 30 slots = 60   ≥  48 bloques de laboratorio requeridos (Ciencias 5h + Info 3h)
--   · 1 sala (multiuso, reservada) — el trigger sch_celda_validar exige 'aula'
--     para materias normales, por lo que 'sala' no es apta para clases regulares.
INSERT INTO salones (nombre, tipo, capacidad, activo, user_id) VALUES
    ('Aula 102',        'aula',        30, true, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Aula 103',        'aula',        30, true, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Aula 104',        'aula',        30, true, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Aula 105',        'aula',        30, true, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Aula 106',        'aula',        30, true, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Lab. Ciencias',   'laboratorio', 25, true, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Lab. Informática','laboratorio', 25, true, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Sala Múltiple',   'sala',        40, true, 'f66d8637-c374-4602-b748-b9b9737abfbf')
ON CONFLICT (user_id, nombre) DO NOTHING;

-- 5. Docentes (uno por materia; carga 30 h)
INSERT INTO docentes (nombre, apellido, documento, telefono, email, carga_horaria, activo, user_id) VALUES
    ('María', 'González', '111', '300111', 'maria.gonzalez@instituto.edu', 30, true, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Carlos', 'Pérez',   '222', '300222', 'carlos.perez@instituto.edu',   30, true, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Lucía', 'Ramírez',  '333', '300333', 'lucia.ramirez@instituto.edu',  30, true, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Jorge', 'Torres',   '444', '300444', 'jorge.torres@instituto.edu',   30, true, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Ana',   'Flores',   '555', '300555', 'ana.flores@instituto.edu',     30, true, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Pedro', 'Castro',   '666', '300666', 'pedro.castro@instituto.edu',   30, true, 'f66d8637-c374-4602-b748-b9b9737abfbf'),
    ('Sofía', 'Mendoza',  '777', '300777', 'sofia.mendoza@instituto.edu',  30, true, 'f66d8637-c374-4602-b748-b9b9737abfbf')
ON CONFLICT (user_id, documento) DO NOTHING;

-- 6. Disponibilidad: todos los docentes, jornada completa 07:00-13:00 (Lun-Vie)
INSERT INTO disponibilidades (docente_id, dia, hora_inicio, hora_fin, user_id)
SELECT d.id, gs, '07:00', '13:00', d.user_id
  FROM docentes d
  CROSS JOIN LATERAL generate_series(1, 5) AS gs
 WHERE d.user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf'
   AND NOT EXISTS (
     SELECT 1 FROM disponibilidades x
       WHERE x.docente_id = d.id AND x.user_id = d.user_id AND x.dia = gs
        AND x.hora_inicio = '07:00' AND x.hora_fin = '13:00'
 );

-- 7. Materias que puede dictar cada docente
INSERT INTO docente_materia (docente_id, materia_id, user_id)
SELECT d.id, m.id, d.user_id
  FROM docentes d
  JOIN materias m ON m.user_id = d.user_id AND (
      (d.documento = '111' AND m.nombre = 'Matemáticas')
   OR (d.documento = '222' AND m.nombre = 'Lengua')
   OR (d.documento = '333' AND m.nombre = 'Ciencias Naturales')
   OR (d.documento = '444' AND m.nombre = 'Historia')
   OR (d.documento = '555' AND m.nombre = 'Inglés')
   OR (d.documento = '666' AND m.nombre = 'Ed. Física')
   OR (d.documento = '777' AND m.nombre = 'Informática')
  )
 WHERE d.user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf'
   AND NOT EXISTS (
    SELECT 1 FROM docente_materia dm
      WHERE dm.docente_id = d.id AND dm.materia_id = m.id AND dm.user_id = d.user_id
 );

-- 8. Cursos que le corresponden a cada docente (todos dictan en 6°A y 7°A)
INSERT INTO docente_curso (docente_id, curso_id, user_id)
SELECT d.id, c.id, d.user_id
FROM docentes d JOIN cursos c ON c.user_id = d.user_id
 WHERE d.user_id = 'f66d8637-c374-4602-b748-b9b9737abfbf'
   AND NOT EXISTS (
     SELECT 1 FROM docente_curso dc
      WHERE dc.docente_id = d.id AND dc.curso_id = c.id AND dc.user_id = d.user_id
 );

COMMIT;
