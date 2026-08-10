from datetime import datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CeldaBase(BaseModel):
    """Campos comunes de la celda del horario (tabla `celdas`).

    El modelo del PLAN §6.2: una asignación (curso, materia, docente, salón)
    colocada en un `(dia, bloque)` con `hora_inicio`/`hora_fin` y opcionalmente
    marcada como `bloqueada` (fija para el generador).
    """

    horario_id: int
    curso_id: int
    materia_id: int
    docente_id: int
    salon_id: int
    dia: int = Field(ge=1, le=7, description="1=Lun … 7=Dom.")
    bloque: int = Field(ge=1)
    hora_inicio: time
    hora_fin: time
    bloqueada: bool = False

    @model_validator(mode="after")
    def _hora_fin_mayor(self) -> "CeldaBase":
        if self.hora_fin <= self.hora_inicio:
            raise ValueError("hora_fin debe ser mayor que hora_inicio")
        return self


class CeldaCreate(CeldaBase):
    pass


class CeldaUpdate(BaseModel):
    """Edición manual de una celda: los campos que pueden moverse.

    `horario_id`/`bloqueada` no cambian en una edición normal de celda.
    """

    curso_id: Optional[int] = None
    materia_id: Optional[int] = None
    docente_id: Optional[int] = None
    salon_id: Optional[int] = None
    dia: Optional[int] = Field(default=None, ge=1, le=7)
    bloque: Optional[int] = Field(default=None, ge=1)
    hora_inicio: Optional[time] = None
    hora_fin: Optional[time] = None


class CeldaOut(CeldaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime