# Gate 6B — Circuit Property Model（回路属性模型）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.0-gate6b`

---

## 1. Circuit → BrainRegion

- `includesRegion`（Circuit → BrainRegion），Canonical。
- 逆语义：`BrainRegion participatesIn Circuit`（本 Gate 不设 owl:inverseOf）。

## 2. Circuit → Connection（reification）

Canonical detailed model：

```
Circuit ──hasConnectionMembership──> CircuitConnectionMembership ──membershipConnection──> Connection
```

- `hasConnectionMembership`（Circuit → CircuitConnectionMembership），Canonical。
- `membershipConnection`（CircuitConnectionMembership → Connection），Canonical。
- membership 未来承载 step_order / role / membership evidence / topology context（本 Gate 不加 DataProperty）。

`hasConnection`（Circuit → Connection）为 **Derived convenience relation**，由上述链派生（本 Gate 不建 property chain，仅定义 + comment 说明）。

## 3. 例子

- Circuit A hasConnectionMembership M1；M1 membershipConnection C001（step 2）。
- Circuit B hasConnectionMembership M2；M2 membershipConnection C001（step 5）。
