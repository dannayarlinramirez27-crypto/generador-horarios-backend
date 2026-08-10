"""Motor de generación de horarios (CSP) — `app/scheduler/`.

Pipeline (PLAN §6.1):
  1. `loader.load_problem()`   → arma el `Problem` desde Supabase (T-015).
  2. `intensity.allocate_intensities()` → cuántos bloques por materia (T-016).
  3. `solver.solve()`  → Backtracking MRV/Degree/LCV + reporte (T-017…T-020).
  4. `validation.validate_schedule()` → chequeo de restricciones de un horario
     guardado (para `validar` y `editar`).
"""

from app.scheduler.loader import load_problem
from app.scheduler.models import Problem, ScheduleResult, ScheduleState
from app.scheduler.solver import solve
from app.scheduler.validation import (
    validate_cell_move,
    validate_schedule,
)

__all__ = [
    "load_problem",
    "Problem",
    "ScheduleResult",
    "ScheduleState",
    "solve",
    "validate_cell_move",
    "validate_schedule",
]