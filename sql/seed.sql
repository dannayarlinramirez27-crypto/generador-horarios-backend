-- ============================================================================
-- Datos de muestra — Sistema Generador de Horarios
-- Diseñados para que el solver CSP (jornada única 07:00-13:00, lun-vie,
-- bloques de 60 min = 30 slots semanales) pueda completar 2 cursos de 30 h.
-- Idempotente: seguro de ejecutar repetidas veces.
-- ============================================================================
BEGIN;

-- 1. Configuración de jornada activa (una sola)
INSERT INTO configs (nombre, tipo_jornada, dias_laborables, hora_inicio, hora_fin, minutos_bloque, activa)
SELECT 'Jornada Única', 'unica', ARRAY[1,2,3,4,5]::smallint[], '07:00', '13:00', 60, true
WHERE NOT EXISTS (SELECT 1 FROM configs);

-- 2. Cursos (6°A y 7°A, 30 h semanales cada uno)
INSERT INTO cursos (nombre, nivel, horas_semanales, orden) VALUES
    ('6°A', '6', 30, 1),
    ('7°A', '7', 30, 2)
ON CONFLICT (nombre) DO NOTHING;

-- 3. Materias (los máximos de cada rango suman 30 h por curso)
INSERT INTO materias (nombre, categoria, min_horas, max_horas, requiere_salon, tipo_salon_requerido, no_ultima_hora) VALUES
    ('Matemáticas',        'basica',        3, 5, false, NULL,            false),
    ('Lengua',             'basica',        3, 5, false, NULL,            false),
    ('Ciencias Naturales', 'basica',        3, 5, true,  'laboratorio',   false),
    ('Historia',           'basica',        3, 5, false, NULL,            false),
    ('Inglés',             'basica',        3, 5, false, NULL,            false),
    ('Ed. Física',         'otras',         1, 2, false, NULL,            false),
    ('Informática',        'media_tecnica', 2, 3, true,  'laboratorio',   false)
ON CONFLICT (nombre) DO NOTHING;

-- 4. Salones
INSERT INTO salones (nombre, tipo, capacidad, activo) VALUES
    ('Aula 102',        'aula',        30, true),
    ('Aula 103',        'aula',        30, true),
    ('Lab. Ciencias',   'laboratorio', 25, true),
    ('Lab. Informática','laboratorio', 25, true),
    ('Sala Múltiple',   'sala',        40, true)
ON CONFLICT (nombre) DO NOTHING;

-- 5. Docentes (uno por materia; carga 30 h)
INSERT INTO docentes (nombre, apellido, documento, telefono, email, carga_horaria, activo) VALUES
    ('María', 'González', '111', '300111', 'maria.gonzalez@instituto.edu', 30, true),
    ('Carlos', 'Pérez',   '222', '300222', 'carlos.perez@instituto.edu',   30, true),
    ('Lucía', 'Ramírez',  '333', '300333', 'lucia.ramirez@instituto.edu',  30, true),
    ('Jorge', 'Torres',   '444', '300444', 'jorge.torres@instituto.edu',   30, true),
    ('Ana',   'Flores',   '555', '300555', 'ana.flores@instituto.edu',     30, true),
    ('Pedro', 'Castro',   '666', '300666', 'pedro.castro@instituto.edu',   30, true),
    ('Sofía', 'Mendoza',  '777', '300777', 'sofia.mendoza@instituto.edu',  30, true)
ON CONFLICT (documento) DO NOTHING;

-- 6. Disponibilidad: todos los docentes, jornada completa 07:00-13:00 (Lun-Vie)
INSERT INTO disponibilidades (docente_id, dia, hora_inicio, hora_fin)
SELECT d.id, gs, '07:00', '13:00'
  FROM docentes d
  CROSS JOIN LATERAL generate_series(1, 5) AS gs
 WHERE NOT EXISTS (
     SELECT 1 FROM disponibilidades x
      WHERE x.docente_id = d.id AND x.dia = gs
        AND x.hora_inicio = '07:00' AND x.hora_fin = '13:00'
 );

-- 7. Materias que puede dictar cada docente
INSERT INTO docente_materia (docente_id, materia_id)
SELECT d.id, m.id
  FROM docentes d
  JOIN materias m ON (
      (d.documento = '111' AND m.nombre = 'Matemáticas')
   OR (d.documento = '222' AND m.nombre = 'Lengua')
   OR (d.documento = '333' AND m.nombre = 'Ciencias Naturales')
   OR (d.documento = '444' AND m.nombre = 'Historia')
   OR (d.documento = '555' AND m.nombre = 'Inglés')
   OR (d.documento = '666' AND m.nombre = 'Ed. Física')
   OR (d.documento = '777' AND m.nombre = 'Informática')
  )
WHERE NOT EXISTS (
    SELECT 1 FROM docente_materia dm
     WHERE dm.docente_id = d.id AND dm.materia_id = m.id
 );

-- 8. Cursos que le corresponden a cada docente (todos dictan en 6°A y 7°A)
INSERT INTO docente_curso (docente_id, curso_id)
SELECT d.id, c.id
  FROM docentes d CROSS JOIN cursos c
 WHERE NOT EXISTS (
     SELECT 1 FROM docente_curso dc
      WHERE dc.docente_id = d.id AND dc.curso_id = c.id
 );

COMMIT;