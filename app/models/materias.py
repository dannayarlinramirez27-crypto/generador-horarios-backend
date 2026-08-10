from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MateriaBase(BaseModel):
    """Campos comunes de la materia (tabla `materias`).

    Refleja el CHECK de la BD: si `requiere_salon` es true, `tipo_salon_requerido`
    es obligatorio; si es false, debe ser `null`.
    """

    nombre: str
    categoria: Literal["basica", "media_tecnica", "otras"]
    min_horas: int = Field(default=3, ge=1)
    max_horas: int = Field(default=5)
    requiere_salon: bool = False
    tipo_salon_requerido: Optional[Literal["laboratorio", "sala"]] = None
    no_ultima_hora: bool = False

    @model_validator(mode="after")
    def _rango_y_salon(self) -> "MateriaBase":
        if self.max_horas < self.min_horas:
            raise ValueError("max_horas debe ser >= min_horas")
        if self.requiere_salon and self.tipo_salon_requerido is None:
            raise ValueError(
                "tipo_salon_requerido es obligatorio si requiere_salon=true"
            )
        if not self.requiere_salon and self.tipo_salon_requerido is not None:
            raise ValueError(
                "tipo_salon_requerido debe ser null si requiere_salon=false"
            )
        return self


class MateriaCreate(MateriaBase):
    pass


class MateriaUpdate(BaseModel):
    nombre: Optional[str] = None
    categoria: Optional[Literal["basica", "media_tecnica", "otras"]] = None
    min_horas: Optional[int] = Field(default=None, ge=1)
    max_horas: Optional[int] = None
    requiere_salon: Optional[bool] = None
    tipo_salon_requerido: Optional[Literal["laboratorio", "sala"]] = None
    no_ultima_hora: Optional[bool] = None


class MateriaOut(MateriaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int