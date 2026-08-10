"""Schemas Pydantic de las entidades del Sistema Generador de Horarios.

Cada módulo expone:
  - <Entidad>Create  → datos requeridos al insertar.
  - <Entidad>Update  → campos opcionales al editar.
  - <Entidad>Out     → representación de salida (id + timestamps), con
                       `from_attributes=True` para serializar filas de psycopg.

Mapeo exacto a `sql/schema.sql` (10 tablas): configs, docentes, cursos,
materias, salones, disponibilidades, docente_materia, docente_curso, horarios
y celdas.
"""

from app.models.asignaciones import (
    DocenteCursoCreate,
    DocenteCursoOut,
    DocenteMateriaCreate,
    DocenteMateriaOut,
)
from app.models.celdas import CeldaCreate, CeldaOut, CeldaUpdate
from app.models.configs import ConfigCreate, ConfigOut, ConfigUpdate
from app.models.cursos import CursoCreate, CursoOut, CursoUpdate
from app.models.disponibilidades import (
    DisponibilidadCreate,
    DisponibilidadOut,
    DisponibilidadUpdate,
)
from app.models.docentes import DocenteCreate, DocenteOut, DocenteUpdate
from app.models.horarios import HorarioCreate, HorarioOut, HorarioUpdate
from app.models.materias import MateriaCreate, MateriaOut, MateriaUpdate
from app.models.salones import SalonCreate, SalonOut, SalonUpdate

__all__ = [
    "ConfigCreate",
    "ConfigUpdate",
    "ConfigOut",
    "DocenteCreate",
    "DocenteUpdate",
    "DocenteOut",
    "CursoCreate",
    "CursoUpdate",
    "CursoOut",
    "MateriaCreate",
    "MateriaUpdate",
    "MateriaOut",
    "SalonCreate",
    "SalonUpdate",
    "SalonOut",
    "DisponibilidadCreate",
    "DisponibilidadUpdate",
    "DisponibilidadOut",
    "DocenteMateriaCreate",
    "DocenteMateriaOut",
    "DocenteCursoCreate",
    "DocenteCursoOut",
    "HorarioCreate",
    "HorarioUpdate",
    "HorarioOut",
    "CeldaCreate",
    "CeldaUpdate",
    "CeldaOut",
]