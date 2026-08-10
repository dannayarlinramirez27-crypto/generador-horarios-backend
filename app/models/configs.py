from datetime import datetime, time
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConfigBase(BaseModel):
    """Campos comunes de configuración de jornada (tabla `configs`)."""

    nombre: str = "Configuración general"
    tipo_jornada: Literal["manana", "tarde", "unica"]
    dias_laborables: list[int] = Field(
        default_factory=lambda: [1, 2, 3, 4, 5],
        description="Días 1=Lun … 7=Dom (subconjunto de 1..7).",
    )
    hora_inicio: time
    hora_fin: time
    minutos_bloque: int = Field(default=60, gt=0)
    activa: bool = False

    @model_validator(mode="after")
    def _hora_fin_mayor(self) -> "ConfigBase":
        if self.hora_fin <= self.hora_inicio:
            raise ValueError("hora_fin debe ser mayor que hora_inicio")
        if not set(self.dias_laborables).issubset({1, 2, 3, 4, 5, 6, 7}):
            raise ValueError("dias_laborables debe estar dentro de 1..7")
        return self


class ConfigCreate(ConfigBase):
    """Datos requeridos para crear una configuración."""


class ConfigUpdate(BaseModel):
    """Todos los campos opcionales para actualizar una configuración."""

    nombre: Optional[str] = None
    tipo_jornada: Optional[Literal["manana", "tarde", "unica"]] = None
    dias_laborables: Optional[list[int]] = None
    hora_inicio: Optional[time] = None
    hora_fin: Optional[time] = None
    minutos_bloque: Optional[int] = Field(default=None, gt=0)
    activa: Optional[bool] = None


class ConfigOut(ConfigBase):
    """Configuración tal como sale de la API (incluye id y timestamps)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime