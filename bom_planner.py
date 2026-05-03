from __future__ import annotations

from industry_index import IndustryIndex
from model import (
    MANUFACTURING_ACTIVITY,
    BlueprintProduct,
    BlueprintSettings,
    BomAggregate,
    BomLine,
    BomSnapshot,
    MaterialRow,
    PlanConfig,
    ProductionPlan,
)


class BomPlanner:
    def __init__(self, idx: IndustryIndex):
        self.idx = idx

    def build_snapshot(self, plan: PlanConfig) -> BomSnapshot:
        rows: list[BomLine] = []
        selected_product_type_ids: set[int] = set()
        descendant_product_type_ids: set[int] = set()

        # TODO: rename settings and settings-named functions
        for settings in plan.top_level_blueprints.values():
            production = self._production_for_settings(settings)
            if production.product_type_id in selected_product_type_ids:
                raise ValueError(
                    f"{production.blueprint_name} cannot be selected because "
                    f"{production.product_name} is already selected."
                )

            if production.product_type_id in descendant_product_type_ids:
                raise ValueError(
                    f"{production.blueprint_name} cannot be selected because "
                    f"{production.product_name} is already required by another selection."
                )

            root_start = len(rows)
            self._expand_blueprint(
                production=production,
                required_quantity=None,
                depth=0,
                plan=plan,
                rows=rows,
                active_blueprints=set(),
            )
            root_descendants = {row.type_id for row in rows[root_start + 1:]}
            conflicting_roots = selected_product_type_ids.intersection(root_descendants)
            if conflicting_roots:
                conflict_name = self.idx.type_name(next(iter(conflicting_roots)))
                raise ValueError(
                    f"{production.blueprint_name} cannot be selected because "
                    f"it requires an existing top-level selection: {conflict_name}."
                )

            selected_product_type_ids.add(production.product_type_id)
            descendant_product_type_ids.update(root_descendants)

        aggregates = self._summarize(rows)
        return BomSnapshot(
            request=plan,
            rows=rows,
            aggregates=aggregates,
        )

    def _expand_blueprint(
        self,
        production: ProductionPlan,
        required_quantity: float | None,
        depth: int,
        plan: PlanConfig,
        rows: list[BomLine],
        active_blueprints: set[int],
    ) -> BomLine:
        runs = production.runs_for(required_quantity)
        quantity = production.planned_output(runs) if required_quantity is None else float(required_quantity)
        row = BomLine(
            type_id=production.product_type_id,
            name=production.product_name,
            depth=depth,
            quantity=quantity,
            production=production,
            runs=runs,
            group_id=self._group_id(production.product_type_id),
        )
        rows.append(row)

        if production.blueprint_type_id in active_blueprints:
            return row

        # infinite recursion check in cases of old bpos like silos
        active_blueprints.add(production.blueprint_type_id)
        try:
            for material in self.idx.inputs(production.blueprint_type_id, production.activity):
                self._expand_material(production, runs, material, depth + 1, plan, rows, active_blueprints)
        finally:
            active_blueprints.remove(production.blueprint_type_id)
        return row

    def _expand_material(
        self,
        parent_production: ProductionPlan,
        parent_runs: float,
        material: MaterialRow,
        depth: int,
        plan: PlanConfig,
        rows: list[BomLine],
        active_blueprints: set[int],
    ) -> None:
        type_id = material.material_typeid
        name = self.idx.type_name(type_id)
        quantity = parent_production.material_quantity(material.quantity, parent_runs)

        blueprint_product = None if name in plan.buy_components else self.idx.production_blueprint_for(type_id)
        if blueprint_product is None:
            rows.append(
                BomLine(
                    type_id=type_id,
                    name=name,
                    depth=depth,
                    quantity=quantity,
                    group_id=self._group_id(type_id),
                )
            )
            return

        self._expand_blueprint(
            production=self._production_from_product(
                blueprint_product,
                plan.settings_for(self.idx.type_name(blueprint_product.type_id)),
            ),
            required_quantity=quantity,
            depth=depth,
            plan=plan,
            rows=rows,
            active_blueprints=active_blueprints,
        )

    # TODO: this can be combined with _production_from_product
    def _production_for_settings(self, settings: BlueprintSettings) -> ProductionPlan:
        blueprint_type_id = self.idx.find_type_id_by_name(settings.name)
        if blueprint_type_id is None:
            raise ValueError(f"Blueprint not found: {settings.name}")
        if not self.idx.is_published_type(blueprint_type_id):
            raise ValueError(f"Blueprint is not published: {settings.name}")

        activity = self.idx.activity_for(blueprint_type_id)
        outputs = self.idx.outputs(blueprint_type_id, activity)
        if not outputs:
            raise ValueError(f"Blueprint {settings.name} does not have a production activity.")
        return self._production_from_product(outputs[0], settings)
    
    # TODO: combine this with above 
    def _production_from_product(self, product: BlueprintProduct, settings: BlueprintSettings) -> ProductionPlan:
        if product.activity != MANUFACTURING_ACTIVITY:
            settings = BlueprintSettings(name=settings.name, runs=settings.runs, prints=settings.prints)

        return ProductionPlan(
            blueprint_type_id=product.type_id,
            blueprint_name=self.idx.type_name(product.type_id),
            activity=product.activity,
            product_type_id=product.product_typeid,
            product_name=self.idx.type_name(product.product_typeid),
            output_per_run=float(product.quantity),
            time_per_run=self.idx.activity_time(product.type_id, product.activity) or 0.0,
            settings=settings,
        )

    def _group_id(self, type_id: int) -> int | None:
        type_info = self.idx.get_type(type_id)
        return type_info.group_id if type_info is not None else None

    def _summarize(self, rows: list[BomLine]) -> dict[int, BomAggregate]:
        aggregates: dict[int, BomAggregate] = {}

        for row in rows:
            if row.depth == 0:
                continue

            aggregate = aggregates.get(row.type_id)
            if aggregate is None:
                aggregates[row.type_id] = BomAggregate.from_line(row)
            else:
                aggregate.absorb(row)

        return aggregates
