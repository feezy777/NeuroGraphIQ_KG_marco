# Gate 7B-B Phase 0 — 环境文件改动

## 1. backend/.env

| 键 | 旧值 | 新值 |
|---|---|---|
| `POSTGRES_DB` | `neurographiq_macro96_v1` | `neurographiq_human_brain_v1` |
| `POSTGRES_DB_TEST` | `neurographiq_macro96_v1_e2e` | `neurographiq_human_brain_v1_e2e` |
| `DATABASE_URL` | `…/neurographiq_macro96_v1` | `…/neurographiq_human_brain_v1` |

> 密码、LLM key 等其余项未改动，也**不会在任何日志/文档中明文出现**。

## 2. backend/.env.example

同上三键 + 注释由 Macro96 改为 Human Brain KG。

## 3. scripts/_db_env.ps1

fallback 默认库名由 macro96 改为 human_brain（`WorkbenchDatabase` / `CandidateDatabase` 两处 fallback）。

## 4. 说明

`.env` 含真实 secret（PostgreSQL 密码、DeepSeek/Kimi API key），本轮只改库名行，未触碰 secret 行，且全程未回显任何 secret 值。
