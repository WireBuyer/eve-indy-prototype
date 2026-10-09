# Structures

A structure profile is a named, reusable setup containing a structure, security region, optional rigs, and optional solar system. Multiple profiles can be made and assigned to production plans either as a default or an override for a child component in the build tree. Example: a null sec sotiyo and null sec azbel can be 2 profiles. The sotiyo can be assigned as a default, and the azbel profile can be used as an override for certain components if the user wanted to simulate a different rig set up for each structure.

| Hull    | Activity      | Material reduction | Time reduction | Job cost reduction |
| ------- | ------------- | -----------------: | -------------: | -----------------: |
| Raitaru | Manufacturing |                 1% |            15% |                 3% |
| Azbel   | Manufacturing |                 1% |            20% |                 4% |
| Sotiyo  | Manufacturing |                 1% |            30% |                 5% |
| Athanor | Reaction      |                 0% |             0% |                 0% |
| Tatara  | Reaction      |                 0% |            25% |                 0% |

| Rig tier |        Material reduction | Time reduction |
| -------- | ------------------------: | -------------: |
| T1       |                        2% |            20% |
| T2       |                      2.4% |            24% |
| Thukker  | 2%; 3.7% (groups 873/913) |            20% |

| Security factor       | Highsec | Lowsec | Nullsec / wormhole |
| --------------------- | ------: | -----: | -----------------: |
| Manufacturing T1/T2   |       1 |    1.9 |                2.1 |
| Manufacturing Thukker |      .1 |    1.9 |                 .1 |
| Reaction T1/T2        |       0 |      1 |                1.1 |

The database determines which rigs apply to various product groups and activities. There is a special case for Thukker rigs - if a Thukker rig covers product groups 873 or 913, they have a 3.7% material reduction, whereas the other groups it covers have a 2% material reduction. If a product group needs to be built but there is no rig that covers its ID, there is no rig bonus applied. Otherwise if a product group is covered by a rig, apply the rig table bonus.

Security factors scale only applicable rig bonuses. If no rig covers the item, no rig bonus applies; hull bonuses will still apply.

rigBonus = 0
effectiveRigBonus = rigBonus \* securityFactor = 0

For job fees, convert the hull's job-cost percentage with `costModifier = 1 - jobCostBonus / 100`.

Example: Thukker capital material reduction: **3.7% × 1.9 = 7.03% in lowsec**; **3.7% × 0.1 = 0.37% elsewhere**, not including hull bonuses.
