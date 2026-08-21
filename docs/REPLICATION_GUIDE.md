# 整机复刻指南（新电脑部署）

本文档说明如何在**另一台电脑**上复刻本机 NeuroGraphIQ KG V3 的完整功能与数据。

复刻需要三样东西：

| 组件 | 来源 | 传输方式 |
|------|------|----------|
| ① 代码（含 atlas 数据、前端） | GitHub 仓库 `feezy777/NeuroGraphIQ_KG` | `git clone` |
| ② 数据库数据（PostgreSQL） | 本机 `D:\Tool\kg_backup\` 下的 `.dump` 文件 | 手动拷贝（U盘/网盘/局域网），不进 git |
| ③ 密钥配置（`.env`） | 本机 `backend/.env` | 手动拷贝或按示例自行填写 |

> **为什么不把数据库放进 git？** 主库 dump 为 232MB，超过 GitHub 100MB 单文件限制，且数据库含业务数据、不适合版本管理。代码 + 数据库 dump + .env 三者齐备即可完整复刻。

---

## 一、目标电脑准备（一次性）

### 1. 安装依赖

| 软件 | 版本 | 说明 |
|------|------|------|
| Python | 3.11+ | 后端 |
| Node.js | 18+ | 前端 |
| PostgreSQL | 15+ | 数据库（需含 `pg_restore`，装 bin 目录进 PATH） |
| Git | 任意 | 拉代码 |

### 2. 克隆代码

```powershell
git clone git@github.com:feezy777/NeuroGraphIQ_KG.git
cd NeuroGraphIQ_KG
git checkout main   # 默认即 main（最新代码已在此分支）
```

### 3. 创建数据库

```powershell
# 用 psql 以 postgres 超级用户创建两个库（库名必须与 .env 一致）
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE neurographiq_kg_v3_mvp1_e2e;"
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE neurographiq_kg_v3_candidate;"
```

### 4. 恢复数据库数据

将本机 `D:\Tool\kg_backup\` 下的两个 dump 文件拷贝到目标电脑，然后：

```powershell
# 主库（232MB，需 1-3 分钟）
pg_restore -U postgres -h 127.0.0.1 -d neurographiq_kg_v3_mvp1_e2e --no-owner --role=postgres "kg_v3_main.dump"

# 候选库（127KB）
pg_restore -U postgres -h 127.0.0.1 -d neurographiq_kg_v3_candidate --no-owner --role=postgres "kg_v3_candidate.dump"
```

> 若本机 PostgreSQL 密码不是 `postgres`，需在命令中加 `PGPASSWORD=你的密码` 前缀。
> 恢复后可用 `psql -U postgres -d neurographiq_kg_v3_mvp1_e2e -c "\dt"` 验证表是否齐全。

### 5. 配置 .env

```powershell
cd backend
Copy-Item .env.example .env
# 用编辑器打开 .env，填入：
#  - DEEPSEEK_API_KEY / KIMI_API_KEY（从本机 backend/.env 复制，或直接拷贝整个 .env 文件）
#  - POSTGRES_PASSWORD（若与你本机不同，同步修改 DATABASE_URL 等三行 URL 中的密码）
```

> 最简单方式：直接把本机 `backend/.env` 整个文件拷贝覆盖到目标电脑（内含全部密钥与库名），无需修改任何内容。

### 6. 启动

```powershell
# 后端
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_server.py
# → http://127.0.0.1:8002/api/health

# 前端（另开终端）
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

---

## 二、复刻本机流程（需在本机执行，仅在下次数据有变化时）

```powershell
# 1. 代码推送到 GitHub（本仓库已配置好远程）
git add -A
git commit -m "sync"
git push origin main

# 2. 备份数据库（本机已安装 PostgreSQL bin，路径可调整）
mkdir D:\Tool\kg_backup
cd D:\Tool\kg_backup
pg_dump -U postgres -h 127.0.0.1 -d neurographiq_kg_v3_mvp1_e2e -Fc -f kg_v3_main.dump
pg_dump -U postgres -h 127.0.0.1 -d neurographiq_kg_v3_candidate -Fc -f kg_v3_candidate.dump

# 3. 将 D:\Tool\kg_backup\ 拷贝到目标电脑（U盘/网盘）
```

---

## 三、已验证的备份记录（2026-08-21）

| 库 | 库名 | dump 文件 | 大小 |
|----|------|-----------|------|
| 主库（工作台 schema） | `neurographiq_kg_v3_mvp1_e2e` | `kg_v3_main.dump` | 232MB |
| 候选/最终库 | `neurographiq_kg_v3_candidate` | `kg_v3_candidate.dump` | 127KB |

仓库内 `backend/data/atlases/`、`backend/data/uploads/`、`backend/data/ontology_seed_candidates.json` 等数据资产已随 git 提交，克隆即得。
