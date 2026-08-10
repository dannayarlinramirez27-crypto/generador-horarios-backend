from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class SalonBase(BaseModel):
    """Campos comunes del salón (tabla `salones`)."""

    nombre: str
    tipo: Literal["aula", "laboratorio", "sala"]
    capacidad: int = Field(default=0, ge=0)
    activo: bool = True


class SalonCreate(SalonBase):
    pass


class SalonUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[Literal["aula", "laboratorio", "sala"]] = None
    capacidad: Optional[int] = Field(default=None, ge=0)
    activo: Optional[bool] = None


class SalonOut(SalonBase):
    model_config = ConfigDict(from_attributes=True)

    id: int