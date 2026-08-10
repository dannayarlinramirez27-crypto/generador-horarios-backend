from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CursoBase(BaseModel):
    """Campos comunes del curso/grado (tabla `cursos`)."""

    nombre: str  # ej: 6°A
    nivel: str   # ej: 6, 7, 10
    horas_semanales: int = Field(gt=0, description="30 / 37 según el nivel.")
    orden: int = Field(default=0)


class CursoCreate(CursoBase):
    pass


class CursoUpdate(BaseModel):
    nombre: Optional[str] = None
    nivel: Optional[str] = None
    horas_semanales: Optional[int] = Field(default=None, gt=0)
    orden: Optional[int] = None


class CursoOut(CursoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int