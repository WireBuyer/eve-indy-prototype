Project: EVE Online industry/BOM calculator prototype in Python. Will later be ported to spring boot.

Long-term goal:
This Python prototype will later be ported to Spring Boot, so model boundaries should stay API/DB-friendly. Avoid clever Python-only designs that would map poorly to Java entities, DTOs, service classes, and database tables.

Core behavior:
The app builds a bill-of-materials tree from selected EVE blueprints/prints. It recursively expands buildable components unless the user marks a component as “buy.” If bought, recursion stops there and child materials are not included.

Materials/components are aggregated and displayed at their maximum depth. If an item appears at depth 2 and depth 4, it appears once at depth 4 with the summed quantity. This ensures deeper requirements are satisfied before higher-level builds.

Blueprint ME/TE, runs, prints, and output-per-run must be respected. Reactions/formulas ignore ME/TE. Some prints output multiple product units per run, so output quantity matters.

If a component shows up in a selected print it is added to a set to track. These prints can not show up in the top level for future prints. This is to maintain the depth logic from before.

Current design:

- `BlueprintSettings` represents user print settings: blueprint/print name, ME, TE, runs, prints.
- The same `BlueprintSettings` model is used for top-level selected prints and child print overrides.
- `runs: float | None` means manual runs if provided, otherwise auto-calculate from required quantity / (prints \* output_per_run).
- Top-level prints have a user-submitted values for runs. Child/derived prints should only have use auto runs.

Important Spring Boot/API direction:
The eventual design should probably key blueprint settings/overrides by blueprint type ID rather than name. Current prototype still uses print names in places, but avoid deepening that dependency if changing code. Prefer explicit IDs and DTO-like structures where practical.

Verification:

- `python -m unittest` should pass.
- `python main.py` should match `Example 2.txt` except for an existing leading blank line.
- ignore `utils/` as well as `.gitignore` exclusions.

Engineering preference:
Keep the code simple, DRY, and easy to port to Spring Boot. Prefer clear service/model boundaries over Python cleverness.
