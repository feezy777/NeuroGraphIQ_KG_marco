"""诊断:Evidence Center 关键接口链路。"""
import asyncio
import json

import httpx

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

API = "http://127.0.0.1:8002"


async def main():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as s:
        # 角色
        role = (
            await s.execute(text("SELECT value FROM settings WHERE key='ontology_role'"))
        ).first() if False else None
    async with httpx.AsyncClient(base_url=API, timeout=30) as c:
        # 1) 角色
        r = await c.get("/api/ontology/governance/role")
        print("1. role:", r.status_code, r.text[:80])

        # 2) 佐证任务列表
        r = await c.get("/api/ontology/evidence/batch", params={"limit": 5})
        print("2. tasks:", r.status_code, end=" ")
        if r.status_code == 200:
            items = r.json().get("items", [])
            print(f"{len(items)} tasks")
            for t in items[:3]:
                print(f"   {t['id'][:8]} {t.get('name')} status={t['status']} review={t.get('review_status')} awaiting={t.get('awaiting_review_items')}")
        else:
            print(r.text[:150])

        # 3) 论文库
        r = await c.get("/api/ontology/evidence/papers", params={"page_size": 3})
        print("3. papers:", r.status_code, end=" ")
        if r.status_code == 200:
            body = r.json()
            print(f"total={body['total']} items={len(body['items'])}")
            for p in body["items"][:2]:
                print(f"   {p.get('pmid')} {str(p.get('title'))[:40]} paragraphs={p.get('paragraph_count')}")
        else:
            print(r.text[:150])

        # 4) 任务 items(证据候选数据源)
        tasks = (await c.get("/api/ontology/evidence/batch", params={"limit": 3})).json().get("items", [])
        if tasks:
            tid = tasks[0]["id"]
            r = await c.get(f"/api/ontology/evidence/batch/{tid}/items", params={"limit": 5})
            print(f"4. task items({tid[:8]}):", r.status_code, end=" ")
            if r.status_code == 200:
                items = r.json().get("items", [])
                print(f"{len(items)} items")
                for it in items[:3]:
                    cp = it.get("candidate_papers") or []
                    print(f"   {str(it.get('label'))[:30]} status={it.get('status')} candidates={len(cp)}")
            else:
                print(r.text[:150])

        # 5) getEvidenceTarget(取一个 connection)
        async with AsyncSessionLocal() as s:
            conn = (await s.execute(text("SELECT id::text FROM mirror_region_connections LIMIT 1"))).first()
            cid = conn[0] if conn else None
        if cid:
            r = await c.get(f"/api/ontology/evidence/target/connection/{cid}")
            print("5. target dto:", r.status_code, end=" ")
            if r.status_code == 200:
                d = r.json()
                print(f"claim={str(d.get('claim_text'))[:50]} components={len(d.get('claim_components') or [])} granularity={d.get('granularity')}")
            else:
                print(r.text[:150])

        # 6) attach-preview(写操作,查权限)
        if cid:
            r = await c.post("/api/ontology/evidence/attach-preview", json={
                "target_type": "connection", "target_id": cid,
                "pmid": "12345678",
                "direction": "supports", "reviewer_confidence": 0.8,
                "passages": [{"source_scope": "abstract", "passage": "test passage", "direction": "supports", "confidence": 0.5}],
            })
            print("6. attach-preview:", r.status_code, r.text[:120])

        # 7) extract-selected(写操作,查权限)
        if cid:
            r = await c.post("/api/ontology/evidence/extract-selected", json={
                "target_type": "connection", "target_id": cid,
                "papers": [{"pmid": "12345678", "title": "t"}], "mode": "existence",
            })
            print("7. extract-selected:", r.status_code, r.text[:120])


asyncio.run(main())
