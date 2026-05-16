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

- `model.py` only contains constants and DB-read row models loaded from the EVE database.
- `PrintSettings` represents user print settings: blueprint type ID, blueprint/print name, ME, TE, runs, prints.
- `PrintSettings.blueprint_type_id` is required.
- The same settings record is used for root selected prints and child print overrides.
- `runs: float | None` means manual runs if provided, otherwise auto-calculate from required quantity / (prints * output_per_run), rounded up to whole runs.
- Root prints may have user-submitted runs. Child/derived prints must auto-calculate whole runs.
- `BuildPlan.root_prints` and `BuildPlan.print_overrides` are keyed by blueprint type ID.
- `BuildPlan.buy_product_type_ids` stores bought component product type IDs. UI/API/demo code may accept names, but must resolve them to type IDs before building the plan.
- `BuildPlan.plan_id` identifies a plan in the prototype. Web/API code can keep a plan-id map outside the planner and pass the selected `BuildPlan` into `BomPlanner`.
- `plan_service.py` owns plan mutation helpers such as root print updates, override updates, and buy toggles.
- `ProductionRecipe` is immutable catalog data for one blueprint activity/product.
- `BomItem` is the final BOM item for one product type ID, including quantity, max depth, group, and build fields when the item is built.
- `BomResult` is a plain result record containing roots, items keyed by product type ID, buy product IDs, and estimate flag.
- `BomPlanner._build_tree()` returns only child product depths. Duplicate tracking sets stay local inside tree building and are not returned.
- `bom_view.py` owns derived projections such as rows, depth layers, total time, item tags, and shopping lists.
- `production_math.py` owns run, material, output, time, and temporary estimate math.
- `BomPlanner(idx, use_estimate_math=True)` temporarily switches to the older fractional math. Delete that flag and the estimate branches in `ProductionMath` later without changing planner traversal.

Important Spring Boot/API direction:
The planner should keep using blueprint/product type IDs internally. UI/API code can still accept names for search/debug and resolve them to IDs before updating the plan.

Verification:

- `python -m unittest` should pass.
- `python main.py` should match `Example 2.txt`.
- ignore `utils/` as well as `.gitignore` exclusions.

Engineering preference:
Keep the code simple, DRY, and easy to port to Spring Boot. Prefer clear service/model boundaries over Python cleverness.
