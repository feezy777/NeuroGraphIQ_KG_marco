# Gate 6G-A — Connection Semantics Audit

---

## 结果：PASS（0 issue）

- StructuralConnection：真实解剖通路，不要求单突触，多跳不压成单条。
- Projection：StructuralConnection 特殊类型，需 source+target+axonal projection 语义；DTI 不能单独判向。
- FunctionalConnectivity：统计依赖，V1 non-directional，不隐含结构。
- EffectiveConnectivity：模型依赖有向影响，≠ Projection/StructuralConnection。
- Connection ObjectProperty：hasSourceRegion/hasTargetRegion ⊑ hasEndpointRegion；projectsTo ⊑ structurallyConnectedTo 正确。
- 无错误 subclass（如 Projection ⊑ EffectiveConnectivity 未出现）。
