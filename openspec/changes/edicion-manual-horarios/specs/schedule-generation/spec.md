# Spec: schedule-generation

The CSP engine (`intensity.py` → `solver.py` → fallback greedy) assigns the weekly
grid so that every course receives exactly `horas_semanales`, every subject respects
its `[min_horas, max_horas]` **per course**, subjects are spread across the week
according to the plan, and different courses do not collapse onto the same temporal
pattern when valid alternatives exist.

## ADDED Requirements

### Requirement: Per-Course Intensity Allocation

The system MUST allocate the weekly hours of each `(subject, course)` so the sum of
blocks per course equals the course's `horas_semanales` and each subject stays within
`[min_horas, max_horas]`. Intensity is computed **per `(materia_id, curso_id)`**, never
aggregated globally by subject.

The DP in `allocate_intensities` MUST return a plan whose per-course sum is exact; when
no exact combination exists it MUST emit an `intensidad_imposible` aviso and the solver
reaches state `parcial`.

#### Scenario: 6 courses x 30h plan
- GIVEN a `Problem` with 6 courses each `horas_semanales=30` and subjects whose ranges admit an exact 30-block sum
- WHEN `solve(problem)` runs
- THEN the returned plan has one entry per course with `sum == 30`
- AND no `intensidad_imposible` aviso is emitted

#### Scenario: Subject with tight min/max range
- GIVEN subject `S` has `min_horas=1, max_horas=2`
- WHEN intensity is allocated for its course
- THEN the blocks assigned to `S` are 1 or 2 inclusive

### Requirement: Cross-Course Pattern Diversification (SOFT)

The system SHOULD assign distinct `(dia, bloque)` temporal patterns to the same subject
across different courses **when valid alternatives exist**. This is a soft preference
encoded as a value-ordering penalty / `soft_score` term, NOT a hard "all-different"
constraint.

The penalty for placing subject `materia` of course `c` at `(dia, bloque)` MUST increase
with the number of **other courses** that already have `materia` at that same
`(dia, bloque)`. Lower is better; it MUST only reorder candidate values and MUST never
make an otherwise feasible cell infeasible.

The solver MUST be permitted to repeat a pattern across courses when **no feasible
alternative** exists (e.g. a single feasible slot per subject due to availability /
workday / `no_ultima_hora` constraints). Repetition under no-alternatives MUST NOT raise
a hard conflict and MUST NOT be counted as a plan failure.

#### Scenario: Different patterns when alternatives exist
- GIVEN a `Problem` with two structurally identical courses (same subjects, full availability, 5 aulas) so that each subject has several feasible `(dia, bloque)` slots
- WHEN `solve(problem)` runs
- THEN the set of `(dia, bloque)` used by subject `S` in course 1 is NOT identical to the set used by `S` in course 2
- AND no hard conflict is reported

#### Scenario: Repetition permitted when no alternatives
- GIVEN a `Problem` where subject `S` has exactly one feasible `(dia, bloque)` slot per course (constrained availability)
- WHEN `solve(problem)` runs
- THEN both courses MAY place `S` at that same `(dia, bloque)`
- AND `estado` is `completo` with zero hard conflicts

### Requirement: Hard Constraints Inviolability

The solver MUST never produce a cell that violates: docente cross-book, salón clash,
course double-book, docente availability, workday/jornada window, `no_ultima_hora`,
and salon-type matching (`requiere_salon` ⇒ exact type, else `aula`). Existing DB triggers
`sch_celda_validar` / `sch_horario_validar` MUST NOT be weakened.

#### Scenario: Salon-type respected by greedy fallback
- GIVEN backtracking is truncated and `_rellenar_greedy` runs
- WHEN greedy places cells for a lab-requiring subject
- THEN every greedy cell uses a `laboratorio` salon (never `aula` / `sala`)
- AND inserting past `sch_celda_validar` succeeds

### Requirement: Soft Preferences Quantified

The `soft_score` / value ordering MUST keep these existing measurable preferences without
changing their relative weights: docent load excess (`_penal_carga`), `MAX_BLOQUES_MATERIA_DIA`
ceiling (`_penal_materia_dia`), uniform daily spread (`_penal_dia`), anti-contiguity
(`_penal_contiguos`), slot demand (LCV `demanda`), and slot saturation (`_penal_slot`).
The new cross-course pattern penalty MUST be appended as a later tiebreaker so it never
overrides an existing preference above it.

#### Scenario: Greedy fallback skips soft penalties
- GIVEN backtracking truncates and greedy completes the grid
- WHEN the final grid is inspected
- THEN greedy cells MAY violate soft preferences but hold zero hard conflicts

### Requirement: Blocked-Cell Preservation

Cells with `bloqueada=true` loaded by `loader.load_problem(conn, horario_id)` MUST be
treated as fixed: they MUST be locked into occupancy before variables are built, count
toward the subject's planned intensity, and MUST NOT be moved, reassigned, or overwritten
by the solver or the greedy fallback. Regeneration MUST delete only non-blocked cells and
re-insert the rest.

#### Scenario: Regeneration preserves blocked cells
- GIVEN an existing schedule with 2 blocked cells
- WHEN `POST /horarios/generar` regenerates over that `horario_id`
- THEN the blocked cells remain at their original `(dia, bloque)` after regeneration
- AND the regenerated grid still reaches `completo` with zero hard conflicts

### Requirement: Determinism

Given the same `Problem` and the same internal ordering (sorted iteration, MRV/Degree/LCV
keys), `solve(problem)` MUST return a reproducible result across runs. No randomness or
wall-clock-dependent tiebreakers may change the assignment.

#### Scenario: Reproducible output
- GIVEN a fixed `problem_ok` fixture
- WHEN `solve(problem_ok)` runs twice
- THEN the two results contain the same `(curso, materia, docente, salon, dia, bloque)` sets

#### Scenario: Deadline-greedy regression held
- GIVEN backtracking is force-truncated (`_backtrack` stub raises `TimeLimitReached`)
- WHEN `solve(problem)` runs
- THEN the grid still completes 60 cells (the `_deadline` is reset before greedy)
- AND a `limite_tiempo` aviso is emitted

### Requirement: Partial Schedule Reporting

When the grid cannot be completed within node/time limits, the solver MUST return its
best partial assignment plus a structured `conflictos` list (`tipo`, `curso_id`,
`materia_id`, `motivo`) and keep state `parcial`; it MUST NOT produce a fake `completo`.

#### Scenario: Partial schedule reported
- GIVEN an over-constrained `Problem` (no exact intensity match)
- WHEN `solve(problem)` runs
- THEN `estado == "parcial"` and `conflictos` lists every unresolved cell with its reason

## Out of Scope

- Redesigning the CSP engine, swapping the backtracking solver, adding constraint
  propagation beyond forward checking, or introducing a global all-different hard
  constraint. Diversification stays SOFT.
- Changing `sql/schema.sql`, `sch_celda_validar`, or `sch_horario_validar`.
- Touching `MAX_NODES`, `TIME_LIMIT_SEG`, `GREEDY_TRIGGER_SEG` constants.
- Reordering existing soft-penalty weights; the new penalty is append-only.
- Loading careers/blocks beyond the single active jornada.

## Seed Data Note

`sql/seed.sql` currently seeds 2 courses (6°A, 7°A) and `tests/conftest.py` builds a
2-course fixture. The PLAN domain targets 6 courses. Tests for the diversification
requirement MUST either build a full 6-course fixture in `conftest.py` OR extend the
seed; this decision is deferred to the design phase. Adjusting the seed to 6 courses
is NOT a schema change and carries no trigger/RLS impact.