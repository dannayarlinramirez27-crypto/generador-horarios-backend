# Proposal: Manual Schedule Editing

## Intent

Ratify the uncommitted manual-editing implementation (~196 BE + ~1210 FE lines) and close gaps: move/edit/delete cells, blank start, block cells, manage schedules.

## Scope

### In Scope
- Ratify uncommitted backend (cell edit/delete, `vacio`, regeneration preserving blocked cells, state recalc) and frontend edit mode (assignment panel, click/drag placement, cell actions, validation panel).
- Close gaps: per-course grid (critical), `validate_schedule` intensity check, missing tests, hardening.
- New: rename/delete schedule.

### Out of Scope
- Engine changes, undo/redo, concurrency locks, bulk ops.

## Decisions (auto mode)

| Decision | Choice | Why |
|---|---|---|
| Grid scope | One course + selector | Fixes cell collapse |
| Management | Rename + delete included | User requested it |
| `completo` recalc | Kept after each edit | Current behavior; safe after fix |
| Blocked guard | Server 409 on move/delete | Client-only guard bypassable |

## Capabilities

### New Capabilities
- `schedule-manual-editing`: blank start, cell edit/delete, blocked-cell guard, state recalculation, per-course grid.
- `schedule-generation`: regeneration preserving blocked cells; delete→insert→state order.
- `schedule-validation`: conflict/warning reporting, intensity check, violation attribution.
- `schedule-management`: rename and delete schedule.

### Modified Capabilities
None — `openspec/specs/` is empty.

## Approach

- **Backend**: intensity check in `validate_schedule`; 409 blocked-cell guard unless unblocked in payload; `PATCH/DELETE /horarios/{id}`; pytest for editar/borrar/vacio/recalcular. No schema/trigger changes.
- **Frontend**: grid scoped to selected course; remove `pnpm` dep; clean types; document seed 2-vs-6 gap.

## Review Forecast

~1400 lines > 400 budget (3.5×).
Decision needed before apply: Yes · Chained PRs recommended: Yes · 400-line budget risk: High

- **PR1** backend ratification + tests
- **PR2** frontend edit-mode ratification (may need exception)
- **PR3** grid fix + hardening (guard, intensity, management)

## Affected Areas

| Area | Impact |
|---|---|
| `app/routers/horarios.py` | Modified: guard, rename/delete |
| `app/scheduler/validation.py` | Modified: intensity check |
| `tests/` | New tests |
| `../horarios-frontend/` (`page.tsx`, `lib/api.ts`, `package.json`) | Modified: grid scope, deps, types |

## Risks

| Risk | L | Mitigation |
|---|---|---|
| Python state vs DB trigger mismatch | Med | Intensity in `validate_schedule`; same-transaction recalc |
| Regeneration order regression | Low | Existing test; delete→insert→state kept |
| PR2 over budget | High | ask-on-risk user decision; split if needed |

## Rollback Plan

Additive endpoints/checks — revert per-PR commits. No schema/trigger/migration → no DB rollback.

## Dependencies

None; requires uncommitted working-tree code.

## Success Criteria

- [ ] Grid shows the 30 cells of the selected course
- [ ] pytest green incl. new editar/borrar/vacio/recalcular tests
- [ ] 409 on move/delete of blocked cell
- [ ] Valid edit reaches `completo` without DB rejection
- [ ] Rename/delete works end-to-end
