# Gate 6G-A — Audit Scope

Ontology IRI: `https://neurographiq.org/ontology/human-brain`（version 0.6.2-gate6d，本轮不改）
本轮状态: **全局一致性诊断审计，不修改 TTL**

---

## 1. 范围

- 23 Class 完整性
- 26 ObjectProperty 完整性
- Class / Property hierarchy
- Domain/Range 正确性
- TBox/ABox policy
- Connection / Circuit / Function 科学语义
- Evidence / Spatial / Atlas / Granularity 边界
- Human-only scope
- Canonical vs Derived 边界
- 逻辑公理审计
- Label/definition/legacy 残留
- 推理安全
- Protégé 兼容性

## 2. 方法

TTL 实际解析 + frozen review docs 交叉确认，不手写猜测。

## 3. 问题等级

BLOCKER（冻结前必须修）/ MAJOR（应修）/ MINOR（文档一致性）/ DEFER（未来版本）。

## 4. 原则

本轮只诊断，不自动修改 TTL；发现 BLOCKER 也只输出 Minimal Fix Proposal 等人工批准。
