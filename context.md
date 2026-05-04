Project: EVE Online industry/BOM calculator prototype in Python. Will later be ported to spring boot.

Long-term goal:
This Python prototype will later be ported to Spring Boot, so model boundaries should stay API/DB-friendly. Avoid clever Python-only designs that would map poorly to Java entities, DTOs, service classes, and database tables.

Core behavior:
The app builds bill-of-materials requirements from selected EVE blueprints/prints. It recursively expands buildable components unless the user marks a component as “buy.” If bought, recursion stops there and child materials are not included.

Materials/components are aggregated and displayed at their maximum depth. If an item appears at depth 2 and depth 4, it appears once at depth 4 with the summed quantity. This ensures deeper requirements are satisfied before higher-level builds.

Blueprint ME/TE, runs, prints, and output-per-run must be respected. Reactions/formulas ignore ME/TE. Some prints output multiple product units per run, so output quantity matters.

If a component shows up in a selected print it is added to a set to track. These prints can not show up in the top level for future prints. This is to maintain the depth logic from before.

Current design:

- `BlueprintSettings` represents user print settings: blueprint/print name, ME, TE, runs, prints.
- The same `BlueprintSettings` model is used for top-level selected prints and child print overrides.
- `runs: float | None` means manual runs if provided, otherwise auto-calculate from required quantity / (prints \* output_per_run), rounded up to whole runs.
- Top-level prints have a user-submitted values for runs. Child/derived prints should auto-calculate whole runs.
- `PlanConfig.top_level_blueprints` and `PlanConfig.blueprint_settings` are keyed by blueprint name for now. This keeps root and child updates direct while preserving name-based debugging.
- `PlanConfig.plan_id` identifies a plan in the prototype. Web/API code can keep a plan-id map outside the planner and pass the selected `PlanConfig` into `BomPlanner`.
- `PlanConfig.update_blueprints` accepts a dict keyed by blueprint name. Each value is a plain dict of fields to update, so one request can update one print or many prints with different values.
- `BomPlanner` emits flat BOM rows and aggregates those rows for display. Recursive expansion is only used to follow dependencies, not as the output model.
- `BomSnapshot.rows` is the source for roots, total build time, depth aggregation, and printable output.
- Top-level runs can be manually edited. Child/derived blueprint updates keep runs automatic.
- The default production math uses EVE-style whole-run material rounding. `BomPlanner(idx, use_estimate_math=True)` temporarily switches to the older fractional math; delete that flag and the estimate helpers later without changing planner traversal.

Important Spring Boot/API direction:
The eventual design should probably key blueprint settings/overrides by blueprint type ID rather than name. Current prototype still uses print names in places, but avoid deepening that dependency if changing code. Prefer explicit IDs and DTO-like structures where practical.

Verification:

- `python -m unittest` should pass.
- `python main.py` should match `Example 2.txt`.
- ignore `utils/` as well as `.gitignore` exclusions.

Engineering preference:
Keep the code simple, DRY, and easy to port to Spring Boot. Prefer clear service/model boundaries over Python cleverness.
