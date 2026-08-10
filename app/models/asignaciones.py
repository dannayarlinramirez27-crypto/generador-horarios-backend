from pydantic import BaseModel, ConfigDict


class DocenteMateriaCreate(BaseModel):
    """Asigna una materia a un docente (tabla `docente_materia`, UNIQUE docente+materia)."""

    docente_id: int
    materia_id: int


class DocenteMateriaOut(DocenteMateriaCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class DocenteCursoCreate(BaseModel):
    """Asigna un curso a un docente (tabla `docente_curso`, UNIQUE docente+curso)."""

    docente_id: int
    curso_id: int


class DocenteCursoOut(DocenteCursoCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int