# Spec: schedule-manual-editing

Manual editing of a saved schedule on top of the generated/auto grid: per-course grid
view, cell edit/delete/move, blank start, blocked-cell guard, and live state
recalculation. Hard constraints are enforced by the backend; the frontend only
optimistic-UIs.

## ADDED Requirements

### Requirement: Per-Course Grid View

The frontend MUST render the schedule scoped to ONE selected course, showing exactly the
`bloques_por_dia * dias_laborables` cells (30 for the seed jornada), so that a cell never
collapses across courses as in the old joint view.

#### Scenario: 30 cells for one course
- GIVEN a stored `completo` schedule of a 6-course x 30h school under the seed jornada
- WHEN the user selects course `7°A`
- THEN the grid shows exactly 30 cells for that course, one per `(dia, bloque)`

### Requirement: Cell Edit / Delete / Move

A user MUST be able to create, move, and delete a single cell. After each operation the
backend MUST run `validate_cell_move` (or `validate_schedule` for full-state) and return
the list of violations attributable to that move. Saving a valid edit MUST NOT be
rejected by `sch_celda_validar`.

#### Scenario: Move that produces a clash is rejected
- GIVEN a `completo` schedule
- WHEN the user moves a cell to a `(dia, bloque)` already occupied in its course
- THEN the backend returns a non-empty violations list with `tipo` starting with `choque`
- AND the move is not persisted

#### Scenario: Blank start builds from empty
- GIVEN a fresh schedule in state `borrador` with no cells
- WHEN the user places a valid cell via `editar`
- THEN `validate_cell_move` returns no hard violations
- AND the schedule stays `borrador` until the user marks it complete

### Requirement: Blocked-Cell Guard (409)

The backend MUST reject any move/delete/overwrite of a cell with `bloqueada=true` with
HTTP 409, independent of the client guard, so a bypassable frontend guard cannot corrupt
fixed cells. Unblocking MUST happen via an explicit payload flag before the mutation.

#### Scenario: Delete of blocked cell returns 409
- GIVEN a schedule with a blocked cell
- WHEN the user requests `DELETE /horarios/{id}` on that cell
- THEN the response status is 409
- AND the blocked cell remains in the DB

#### Scenario: Move over blocked cell returns 409
- GIVEN a blocked cell at `(1, 3)`
- WHEN the user attempts `editar` to overwrite `(1, 3)` without unblocking
- THEN the response status is 409 and the blocked cell is unchanged

### Requirement: State Recalculation After Edit

After each persisted edit, the schedule state (`borrador` / `completo` / `parcial`) MUST
be recomputed within the same transaction, mirroring `sch_horario_validar`: completeness,
per-course `horas_semanales`, per-`(materia, curso)` intensity, and docent load. The
transition to `completo` MUST happen AFTER cells are inserted/updated, never before, so
the trigger sees the final cell set.

#### Scenario: Valid edit reaches completo
- GIVEN a `parcial` schedule missing one cell
- WHEN the user adds that valid cell
- THEN the recalculation transitions the schedule to `completo` with zero violations
- AND the UPDATE of `estado` follows the cell INSERT in the SQL operation log

#### Scenario: Edit that breaks intensity keeps parcial
- GIVEN a `completo` schedule
- WHEN the user deletes a cell so a subject now has fewer than `min_horas` blocks
- THEN the schedule stays/becomes `parcial` with an intensity aviso
- AND no `completo` state is persisted

## Out of Scope

- Undo/redo, concurrency locks, bulk cell operations, drag-multiselect, copy/paste between
  courses — not part of this change.
- Frontend optimistic-edit conflict resolution beyond surfacing the backend 4xx.