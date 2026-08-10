from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class DocenteBase(BaseModel):
    """Campos comunes del docente (tabla `docentes`)."""

    nombre: str
    apellido: str
    documento: str
    telefono: Optional[str] = None
    email: Optional[EmailStr] = None
    carga_horaria: int = Field(gt=0, description="Horas de contrato semanales.")
    activo: bool = True


class DocenteCreate(DocenteBase):
    """Datos para registrar un docente."""


class DocenteUpdate(BaseModel):
    """Campos opcionales para editar un docente."""

    nombre: Optional[str] = None
    apellido: Optional[str] = None
    documento: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[EmailStr] = None
    carga_horaria: Optional[int] = Field(default=None, gt=0)
    activo: Optional[bool] = None


class DocenteOut(DocenteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime