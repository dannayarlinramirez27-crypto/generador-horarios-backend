from datetime import time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DisponibilidadBase(BaseModel):
    """Campos comunes de la ventana horaria del docente (tabla `disponibilidades`)."""

    docente_id: int
    dia: int = Field(ge=1, le=7, description="1=Lun … 7=Dom.")
    hora_inicio: time
    hora_fin: time

    @model_validator(mode="after")
    def _hora_fin_mayor(self) -> "DisponibilidadBase":
        if self.hora_fin <= self.hora_inicio:
            raise ValueError("hora_fin debe ser mayor que hora_inicio")
        return self


class DisponibilidadCreate(DisponibilidadBase):
    pass


class DisponibilidadUpdate(BaseModel):
    dia: Optional[int] = Field(default=None, ge=1, le=7)
    hora_inicio: Optional[time] = None
    hora_fin: Optional[time] = None


class DisponibilidadOut(DisponibilidadBase):
    model_config = ConfigDict(from_attributes=True)

    id: int