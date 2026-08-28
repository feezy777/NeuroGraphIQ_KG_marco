# Gate 6E-A — Circuit Evidence Model

本轮状态: **仅设计，不写 TTL**

---

## 1. 难点

Circuit（如 Papez Circuit）可能拥有多个 Publication / Evidence / member Connection。Evidence 支持的是：

1. Circuit 整体存在
2. Circuit 某个成员（region/connection）
3. Circuit 某个 Connection
4. Circuit hasFunction Function

四者不能混成 `Evidence supports Circuit`。

## 2. 推荐：Circuit 也是 reified scientific knowledge object

- Circuit entity 本身 = reified knowledge object，Evidence 可**直接关联 Circuit**（表示支持该 Circuit 的整体存在/组成）。
- member-level evidence 挂在 **membership / observation 层**：
  - region 成员证据 → circuit_region_memberships
  - connection 成员证据 → circuit_connection_memberships / connection_observations
  - hasFunction 证据 → 普通 assertion（Circuit hasFunction Function 走 knowledge_assertions）

## 3. Evidence 分层

| 目标 | Evidence 挂载 |
|---|---|
| Circuit 整体存在/组成 | Circuit 直接 evidence link |
| Circuit 某 region 成员 | circuit_region_memberships 的 evidence |
| Circuit 某 connection 成员 | connection_observations / membership evidence |
| Circuit hasFunction Function | knowledge_assertions（ordinary assertion）+ assertion_evidence_links |

## 4. 不新增 existence wrapper

- 不把 Circuit 包成 existence Assertion（避免无意义 wrapper）。
- Circuit 自身就是 first-class knowledge object。
