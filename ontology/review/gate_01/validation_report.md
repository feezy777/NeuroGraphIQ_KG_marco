# Gate 1 Validation Report — NeuroGraphIQ Macro96 Ontology

校验工具: rdflib 7.6.0（只读解析校验，无写入）
校验文件: `ontology/neurographiq_macro96_v1.ttl`
校验时间: 2026-08-27

| Check | Result | Detail |
|---|---|---|
| TTL Parse | **PASS** | Turtle 语法正常解析 |
| Ontology Count | **PASS** | owl:Ontology = 1 |
| Class Count | **PASS** | 业务 owl:Class = 24 |
| Missing Class | **PASS** | 0（24 个 expected 全部存在） |
| Unexpected Class | **PASS** | 0（无额外业务 Class） |
| English Label | **PASS** | 24/24 类均有 @en label |
| Chinese Label | **PASS** | 24/24 类均有 @zh label |
| Individuals | **PASS** | 0（无 Individual） |
| Object Properties | **PASS** | 0（无自定义 ObjectProperty） |
| Data Properties | **PASS** | 0（无自定义 DataProperty） |
| Imports | **PASS** | 0（owl:imports 为空） |
| Version | **PASS** | owl:versionInfo = 0.1.0-gate1 |
