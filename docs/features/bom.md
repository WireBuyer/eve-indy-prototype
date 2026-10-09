# BOM

## Plan and dependencies

A plan is a set of items the user wants to build (roots), selected through their blueprints/formulas, together with production settings, buy decisions, and assigned [structure profiles](structures.md). Required components are derived from these roots.

Assign profiles to a plan as separate manufacturing and reaction defaults. Within the plan, a blueprint-specific profile overrides its activity's default.

- Changes affect only the selected plan. Recalculate plan for each change applied.
- Respects blueprint outputs when satisfying parent requirements. Example: two parents need 4 units each; output is 10 per run. With one print, plan one child run for the combined demand of 8.
- Aggregate demand by product ID before calculating child builds. Assign each component its maximum depth across expanded paths (roots are depth 0); calculate from shallow to deep so parent demand accumulates first. Production dependencies are satisfied deepest first.
- Build components with published manufacturing/reaction recipes. Buying a component stops its expansion in the tree so its materials needed are not calculated, otherwise they are accumulated downwards like normal.
- Validate every new root before adding it. Reject new roots if it is a component (parent or child) of existing roots, at any depth. Check complete recipe trees, including descendants beneath bought components. Keep existing selections and reject the new addition if it fails the check. Shared components between otherwise unrelated roots are allowed.
  - Example: A Buzzard has a Heron as a build requirement - Heron added first blocks a Buzzard addition; Buzzard added first blocks a Heron addition.
  - Phoenix added first blocks a Genetic Safeguard Filter; Genetic Safeguard Filter added first blocks a Phoenix.

## Calculations

- Roots: users adjust both runs per print and print count; each defaults to one.
- Children: users adjust print count (default one); runs per print are calculated from aggregated demand and cannot be manually overridden.
- Runs and print counts must be positive whole numbers. Every print for a given blueprint uses the same run count.
- Root and child manufacturing settings support material efficiency (ME) and time efficiency (TE), defaulting to zero and clamped to 0–10 / 0–20 respectively.

`runs` means runs per print; `prints` is the print count. To calculate runs for children:

```text
runs = ceil(demand / (prints × outputPerRun))
output = runs × prints × outputPerRun
```

Example: the demand is 16, but the print only outputs in units of 10. That means it still needs 2 runs to satisfy requirements for all parent builds. It will output 20 and have an excess of 4 units.

For each input, enforce at least one unit per run, then multiply by runs. Round the per-print quantity to two decimals, then up to a whole unit, before multiplying by print count.

`baseInput` and `baseTime` are recipe quantities and seconds per run:

```text
inputPerPrint = runs * max(1, baseInput * materialFactor)
totalInput = prints * ceil(round(inputPerPrint, 2))
time = baseTime × runs × prints × timeFactor
```

`materialFactor` and `timeFactor` combine blueprint and [structure multipliers](structures.md). Reaction formulas have no ME/TE modifiers on the prints themselves. They only get structure-related bonuses.

## Results

Keep required and produced quantities separate to expose surplus. Built entries include settings, output, time, structure, and [fees](job-fees.md). Bought entries are explicitly selected purchases; base materials have no production recipe. Shopping lists contain all unbuilt inputs that need to be bought, as well as base materials. Example: mineral (group 18) is shown as a group and gas (group 711). Offers a filtered view as well for any specific group type.
