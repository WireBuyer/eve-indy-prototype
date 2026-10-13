# Production job fees

Calculate the estimated item value of a print using runs per print and that print's base quantities from its recipe (`baseQty`, from db) and adjusted price (from API). Material savings do not reduce this value.

```text
SCC_BASE_RATE = 0.04 // 4% base SCC fee
estimatedValue = runs * sum(baseQty * adjustedPrice)

sccFee = prints * ceil(estimatedValue * SCC_BASE_RATE)
systemFee = prints * ceil(estimatedValue * systemIndex * costModifier)
facilityTax = prints * ceil(estimatedValue * taxRate)
```

Use the activity's index for the job's solar system, taking the selected structure's system when specified. The [job-cost modifier](structures.md), `costModifier`, affects only `systemFee`; `taxRate` is the facility's tax rate. Round each component per print before multiplying.
