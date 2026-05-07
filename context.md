Project: EVE Online industry/BOM calculator prototype in Python. Will later be ported to Spring Boot.

Long-term goal:
This Python prototype will later be ported to Spring Boot, so model boundaries should stay API/DB-friendly. Avoid clever Python-only designs that would map poorly to Java entities, DTOs, service classes, and database tables.

Core behavior:
The app builds bill-of-materials requirements from selected EVE blueprints/prints. It expands buildable components unless the user marks a component as "buy." If bought, expansion stops there and child materials are not included.

Materials/components are aggregated by product type ID and displayed at their maximum depth. If an item appears at depth 2 and depth 4, it appears once at depth 4 with the summed quantity. This ensures deeper requirements are satisfied before higher-level builds.

Duplicate component demand is aggregated before child builds are calculated. If two parents each need 4 units of a component whose print outputs 10 per run, the child build is planned once for 8 total units, not twice for 4 units each.

Blueprint ME/TE, runs, prints, and output-per-run must be respected. Reactions/formulas ignore ME/TE. Some prints output multiple product units per run, so output quantity matters.

If a component shows up in a selected print it is tracked as a descendant. That component's blueprint cannot also be selected as a top-level blueprint, because doing so would break the depth logic.

Current design:

- `BlueprintSettings` represents user print settings: blueprint type ID, blueprint/print name, ME, TE, runs, prints.
- `BlueprintSettings.blueprint_type_id` is required.
- The same settings model is used for top-level selected prints and child print overrides.
- `runs: float | None` means manual runs if provided, otherwise auto-calculate from required quantity / (prints * output_per_run), rounded up to whole runs.
- Top-level prints may have user-submitted runs. Child/derived prints must auto-calculate whole runs.
- `PlanConfig.top_level_blueprints` and `PlanConfig.blueprint_settings` are keyed by blueprint type ID.
- `PlanConfig.buy_component_type_ids` stores bought component product type IDs. UI/API/demo code may accept names, but must resolve them to type IDs before building the plan.
- `PlanConfig.plan_id` identifies a plan in the prototype. Web/API code can keep a plan-id map outside the planner and pass the selected `PlanConfig` into `BomPlanner`.
- `PlanConfig.update_blueprints` accepts a dict keyed by blueprint type ID. Each value is a plain dict of fields to update, so one request can update one print or many prints with different values.
- `ProductionRecipe` is immutable catalog data for one blueprint activity/product.
- `BomEntry` is the final BOM item for one product type ID, including quantity, max depth, group, optional recipe/settings/runs for built items, and a `bought` flag for buy stops.
- `BomResult` is the planner output and source of truth. It exposes roots, entries keyed by product type ID, depth layers, total time, and shopping-list helpers.
- `BomResult.rows` is only a display/test convenience projection.
- `ProductionMath` owns run, material, output, time, and temporary estimate math.
- `BomPlanner(idx, use_estimate_math=True)` temporarily switches to the older fractional math. Delete that flag and the estimate branches in `ProductionMath` later without changing planner traversal.

Important Spring Boot/API direction:
The planner should keep using blueprint/product type IDs internally. UI/API code can still accept names for search/debug and resolve them to IDs before updating the plan.

Verification:

- `python -m unittest` should pass.
- `python main.py` should match `Example 2.txt`.
- ignore `utils/` as well as `.gitignore` exclusions.

Engineering preference:
Keep the code simple, DRY, and easy to port to Spring Boot. Prefer clear service/model boundaries over Python cleverness.
