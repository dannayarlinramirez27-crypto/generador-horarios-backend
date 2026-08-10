from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class HorarioBase(BaseModel):
    """Campos comunes del horario (tabla `horarios`)."""

    configuracion_id: int
    nombre: str = "Horario"


class HorarioCreate(HorarioBase):
    """Datos para crear un horario.

    `usuario_id` se asigna en el servicio (a partir del JWT/Supabase Auth),
    no lo define el cliente. `estado` parte siempre de `borrador`.
    """


class HorarioUpdate(BaseModel):
    configuracion_id: Optional[int] = None
    nombre: Optional[str] = None
    estado: Optional[Literal["borrador", "completo", "parcial"]] = None


class HorarioOut(HorarioBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: Optional[UUID] = None
    estado: Literal["borrador", "completo", "parcial"]
    created_at: datetime