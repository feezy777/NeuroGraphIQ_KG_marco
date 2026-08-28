# Gate 6G-A — Function Semantics Audit

---

## 结果：PASS（0 issue）

- CognitiveFunction rdfs:subClassOf Function（TBox hierarchy 正确）。
- subFunctionOf：Function → Function，未挂 partOf 下，未误用 rdfs:subClassOf 表达具体 function。
- 无 hasSubFunction / functionPartOf；Function part_of 仍 DEFER。
- Function ≠ NeurobiologicalProcess（无 Function→Process 关系）。
- BrainRegion→Function 用 participatesIn；Circuit→Function 用 hasFunction。
