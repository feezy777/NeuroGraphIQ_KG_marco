"""Canonical Connection Evidence 查询端点。

* GET /api/canonical-connections/evidence/by-region?region=Hippocampus
  — 按 region 查询(子串匹配 source/target),返回连接列表 + evidence 数量 + confidence
* GET /api/canonical-connections/{connection_id}/evidence
  — 单连接证据详情(标准 evidence_summary + supporting_records + confidence + quality)

只读查询,不写任何表。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.macro_connection_evidence_service import (
    CONNECTION_DETAIL_SQL,
    connection_to_summary,
    detail_from_row,
)

router = APIRouter(tags=["Canonical Connection Evidence"])


@router.get("/evidence/by-region")
async def query_by_region(
    region: str = Query(..., description="region 名(子串匹配,大小写不敏感),如 Hippocampus"),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
):
    """按 region 查询相关连接:返回 connections + evidence 数量 + confidence。"""
    if not region.strip():
        raise HTTPException(status_code=422, detail="region is required")
    rows = (await session.execute(text(
        CONNECTION_DETAIL_SQL +
        """WHERE rs.canonical_name_en ILIKE :pat OR rt.canonical_name_en ILIKE :pat
           ORDER BY c.evidence_count DESC LIMIT :lim"""),
        {"pat": f"%{region.strip()}%", "lim": limit})).all()
    return {"region": region.strip(), "total": len(rows),
            "connections": [connection_to_summary(r) for r in rows]}


@router.get("/{connection_id}/evidence")
async def get_connection_evidence(
    connection_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
):
    """单连接证据详情:source/target region、connection_type、evidence_summary、
    supporting_records、confidence、quality score。"""
    row = (await session.execute(text(
        CONNECTION_DETAIL_SQL + "WHERE c.id = :cid"),
        {"cid": connection_id})).first()
    if row is None:
        raise HTTPException(status_code=404, detail="canonical connection not found")
    return detail_from_row(row)
