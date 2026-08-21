"""Canonical 脑区别名（Phase Q1.5）— 只挂已有 canonical 脑区，绝不新增虚假脑区。

别名来源:
- manual_curated: 手工整理的常见中文表达 / 医学英文表达 / 缩写（macro+clinical 52 区）
- atlas: 从 atlas_region_mappings 已有映射自动生成的 atlas 原生名称
- ontology_synonym: 预留（本体同义词仍走 ontology_term_synonyms 实时解析）

用途: NL 查询实体解析（canonical_region_aliases 精确匹配层），见
ontology_query_service.resolve_region 的 7 级解析链。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CanonicalRegionAlias(Base):
    """一条 canonical 脑区别名（region_id, alias 唯一）。"""

    __tablename__ = "canonical_region_aliases"
    __table_args__ = (
        UniqueConstraint("region_id", "alias", name="uq_canonical_region_aliases"),
        CheckConstraint("alias_language IN ('cn', 'en', 'abbr')", name="chk_canonical_region_aliases_lang"),
        CheckConstraint(
            "source IN ('manual_curated', 'atlas', 'ontology_synonym')",
            name="chk_canonical_region_aliases_source",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="chk_canonical_region_aliases_conf",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_brain_regions.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    alias_language: Mapped[str] = mapped_column(String(16), nullable=False)  # cn / en / abbr
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual_curated")
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
