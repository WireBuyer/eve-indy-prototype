from __future__ import annotations

from industry_index import IndustryIndex
from model import (
    MANUFACTURING_ACTIVITY,
    BuildJob,
    BlueprintProduct,
    BlueprintSettings,
    BomAggregate,
    BomLine,
    BomSnapshot,
    MaterialRow,
    PlanConfig,
)


class BomPlanner:
    # Delete the estimate param later
    def __init__(self, idx: IndustryIndex, use_estimate_math: bool = False):
        self.idx = idx
        # Temporary estimate switch: delete this parameter/field and the two branches when estimate math is removed.
        self.use_estimate_math = use_estimate_math

    def build_snapshot(self, plan: PlanConfig) -> BomSnapshot:
        rows: list[BomLine] = []
        selected_product_type_ids: set[int] = set()
        descendant_product_type_ids: set[int] = set()

        for print in plan.top_level_blueprints.values():
            # get output product and quantity of a print
            outputs = self.idx.outputs(print.blueprint_type_id)

            # convert the print to a build job
            build_job = self._build_job(outputs[0], print)

            if build_job.product_type_id in selected_product_type_ids:
                raise ValueError(
                    f"{build_job.blueprint_name} cannot be selected because "
                    f"{build_job.product_name} is already selected."
                )

            if build_job.product_type_id in descendant_product_type_ids:
                raise ValueError(
                    f"{build_job.blueprint_name} cannot be selected because "
                    f"{build_job.product_name} is already required by another selection."
                )

            root_start = len(rows)
            self._expand_blueprint(
                build_job=build_job,
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
                    f"{build_job.blueprint_name} cannot be selected because "
                    f"it requires an existing top-level selection: {conflict_name}."
                )

            selected_product_type_ids.add(build_job.product_type_id)
            descendant_product_type_ids.update(root_descendants)

        aggregates = self._summarize(rows)
        return BomSnapshot(
            request=plan,
            rows=rows,
            aggregates=aggregates,
            use_estimate_math=self.use_estimate_math,
        )

    def _expand_blueprint(
        self,
        build_job: BuildJob,
        required_quantity: float | None,
        depth: int,
        plan: PlanConfig,
        rows: list[BomLine],
        active_blueprints: set[int],
    ) -> BomLine:
        runs = None
        if self.use_estimate_math:
            runs = build_job.estimate_runs_for(required_quantity)
        else:
            runs = build_job.runs_for(required_quantity)
        quantity = build_job.planned_output(runs) if required_quantity is None else float(required_quantity)
        row = BomLine(
            type_id=build_job.product_type_id,
            name=build_job.product_name,
            depth=depth,
            quantity=quantity,
            build_job=build_job,
            runs=runs,
            group_id=self._group_id(build_job.product_type_id),
        )
        rows.append(row)

        if build_job.blueprint_type_id in active_blueprints:
            return row

        # infinite recursion check in cases of old bpos like silos
        active_blueprints.add(build_job.blueprint_type_id)
        try:
            for material in self.idx.inputs(build_job.blueprint_type_id, build_job.activity):
                self._expand_material(build_job, runs, material, depth + 1, plan, rows, active_blueprints)
        finally:
            active_blueprints.remove(build_job.blueprint_type_id)
        return row

    def _expand_material(
        self,
        parent_build_job: BuildJob,
        parent_runs: float,
        material: MaterialRow,
        depth: int,
        plan: PlanConfig,
        rows: list[BomLine],
        active_blueprints: set[int],
    ) -> None:
        type_id = material.material_typeid
        name = self.idx.type_name(type_id)
        quantity = None
        if self.use_estimate_math:
            quantity = parent_build_job.estimate_material_quantity(material.quantity, parent_runs)
        else:
            quantity = parent_build_job.material_quantity(material.quantity, parent_runs)

        blueprint_product = None if name in plan.buy_components else self.idx.build_blueprint_for(type_id)
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

        child_blueprint_name = self.idx.type_name(blueprint_product.type_id)
        self._expand_blueprint(
            build_job=self._build_job(
                blueprint_product,
                plan.settings_for(blueprint_product.type_id, child_blueprint_name),
            ),
            required_quantity=quantity,
            depth=depth,
            plan=plan,
            rows=rows,
            active_blueprints=active_blueprints,
        )

    def _build_job(self, product: BlueprintProduct, print: BlueprintSettings) -> BuildJob:
        if product.activity != MANUFACTURING_ACTIVITY:
            print = BlueprintSettings(
                name=print.name,
                runs=print.runs,
                prints=print.prints,
                blueprint_type_id=print.blueprint_type_id,
            )

        return BuildJob(
            blueprint_type_id=product.type_id,
            blueprint_name=self.idx.type_name(product.type_id),
            activity=product.activity,
            product_type_id=product.product_typeid,
            product_name=self.idx.type_name(product.product_typeid),
            output_per_run=float(product.quantity),
            time_per_run=self.idx.activity_time(product.type_id, product.activity) or 0.0,
            settings=print,
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
