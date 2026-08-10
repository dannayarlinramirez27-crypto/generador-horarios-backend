"""Modelos de dominio internos del generador CSP (capa `scheduler`).

No son esquemas de API: son estructuras ligeras y optimizadas con las que
trabaja el motor (carga, intensidad y búsqueda). Se construyen en `loader.py`
a partir de filas reales de Supabase/Postgres y se consumen en `intensity.py`,
`solver.py` y `validation.py`.

El "bloque" es la unidad mínima de tiempo: un `(dia, bloque)` de la jornada
definida por la configuración activa (`configs`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import Literal

# ---------------------------------------------------------------------------
# Utilidades de tiempo (minutos desde medianoche)
# ---------------------------------------------------------------------------


def _to_min(t: time) -> int:
    return t.hour * 60 + t.minute


def _from_min(m: int) -> time:
    m %= 24 * 60
    return time(m // 60, m % 60)


def diff_min(a: time, b: time) -> int:
    """Minutos entre dos `time` (b - a)."""
    return _to_min(b) - _to_min(a)


@dataclass(frozen=True)
class Slot:
    """Un espacio de tiempo concreto dentro de la jornada."""

    dia: int
    bloque: int
    hora_inicio: time
    hora_fin: time
    ultimo: bool  # True si es la última hora de la jornada (política no_ultima_hora)

    @property
    def minutos(self) -> int:
        return diff_min(self.hora_inicio, self.hora_fin)


@dataclass
class Jornada:
    """Jornada definida por la configuración activa (`configs`)."""

    config_id: int
    tipo: Literal["manana", "tarde", "unica"]
    dias: list[int]
    hora_inicio: time
    hora_fin: time
    minutos_bloque: int
    slots: list[Slot] = field(default_factory=list)

    def build_slots(self) -> None:
        """Genera la grilla `(dia, bloque)` → hora para los días laborables."""
        start = _to_min(self.hora_inicio)
        end = _to_min(self.hora_fin)
        step = self.minutos_bloque
        n = max(0, (end - start) // step)  # cantidad de bloques completos por día
        for dia in sorted(self.dias):
            for b in range(1, n + 1):
                s = start + (b - 1) * step
                e = s + step
                self.slots.append(Slot(dia, b, _from_min(s), _from_min(e), b == n))

    def slot(self, dia: int, bloque: int) -> Slot | None:
        return next((s for s in self.slots if s.dia == dia and s.bloque == bloque), None)


@dataclass
class Curso:
    id: int
    nombre: str
    nivel: str
    horas_semanales: int


@dataclass
class Materia:
    id: int
    nombre: str
    categoria: str
    min_horas: int
    max_horas: int
    requiere_salon: bool
    tipo_salon_requerido: str | None
    no_ultima_hora: bool


@dataclass
class Salon:
    id: int
    nombre: str
    tipo: Literal["aula", "laboratorio", "sala"]
    capacidad: int


@dataclass
class Docente:
    id: int
    nombre: str
    apellido: str
    carga_horaria: int
    ventanas: list[tuple[int, time, time]] = field(default_factory=list)
    materias: set[int] = field(default_factory=set)
    cursos: set[int] = field(default_factory=set)

    def cubre(self, slot: Slot) -> bool:
        """True si alguna ventana de disponibilidad contiene el slot completo."""
        for dia, ws, we in self.ventanas:
            if (
                dia == slot.dia
                and _to_min(ws) <= _to_min(slot.hora_inicio)
                and _to_min(we) >= _to_min(slot.hora_fin)
            ):
                return True
        return False


@dataclass
class CeldaFija:
    """Celda con `bloqueada = true` que el generador debe respetar e inmutable."""

    curso_id: int
    materia_id: int
    docente_id: int
    salon_id: int
    dia: int
    bloque: int
    hora_inicio: time
    hora_fin: time


@dataclass
class Problem:
    """Instancia completa del CSP: todo lo que el solver necesita."""

    jornada: Jornada
    cursos: list[Curso]
    materias: dict[int, Materia]
    salones: list[Salon]
    docentes: list[Docente]
    celdas_fijas: list[CeldaFija]

    @property
    def minutos_bloque(self) -> int:
        return self.jornada.minutos_bloque


ScheduleState = Literal["borrador", "completo", "parcial"]


@dataclass
class ScheduleResult:
    """Salida del solver: estado + celdas + reporte de conflictos + estadísticas."""

    estado: ScheduleState
    completo: bool
    celdas: list[dict]
    conflictos: list[dict]
    avisos: list[dict]
    statistics: dict