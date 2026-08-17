# -*- coding: utf-8 -*-
"""mirror_live_display_name_parts:中英文双名解析(纯函数,不触库)。"""

from app.services.paper_evidence_service import mirror_live_display_name_parts as parts


def _get(mapping):
    return lambda c: mapping.get(c)


def test_connection_both_languages():
    get = _get({
        "source_region_name_cn": "杏仁核", "source_region_name_en": "Amygdala",
        "target_region_name_cn": "海马", "target_region_name_en": "Hippocampus",
        "connection_type": "projection",
    })
    cn, en = parts("connection", get)
    assert cn == "杏仁核 → 海马"
    assert en == "Amygdala → Hippocampus"


def test_connection_cn_missing_keeps_en():
    get = _get({
        "source_region_name_cn": None, "source_region_name_en": "Amygdala",
        "target_region_name_cn": "海马", "target_region_name_en": "Hippocampus",
    })
    cn, en = parts("connection", get)
    assert cn is None
    assert en == "Amygdala → Hippocampus"


def test_connection_en_missing_keeps_cn():
    get = _get({
        "source_region_name_cn": "杏仁核", "source_region_name_en": "Amygdala",
        "target_region_name_cn": "海马", "target_region_name_en": None,
    })
    cn, en = parts("connection", get)
    assert cn == "杏仁核 → 海马"
    assert en is None


def test_connection_all_missing():
    get = _get({"source_region_name_cn": "", "source_region_name_en": None,
                "target_region_name_cn": "", "target_region_name_en": ""})
    assert parts("connection", get) == (None, None)


def test_circuit_cn_en():
    get = _get({"name_cn": "默认模式网络", "circuit_name": "Default Mode Network"})
    assert parts("circuit", get) == ("默认模式网络", "Default Mode Network")


def test_circuit_cn_only():
    get = _get({"name_cn": "默认模式网络", "circuit_name": None})
    assert parts("circuit", get) == ("默认模式网络", None)


def test_circuit_step_en_only():
    get = _get({"step_name": "input step", "role": "relay"})
    cn, en = parts("circuit_step", get)
    assert cn is None
    assert en == "input step · relay"


def test_circuit_function_cn_en():
    get = _get({"function_term_cn": "记忆巩固", "function_term_en": "memory consolidation"})
    assert parts("circuit_function", get) == ("记忆巩固", "memory consolidation")


def test_region_function_cn_en():
    get = _get({"function_term": "memory consolidation",
                "region_name_cn": "海马", "region_name_en": "Hippocampus"})
    cn, en = parts("region_function", get)
    assert cn == "memory consolidation · 海马"
    assert en == "memory consolidation · Hippocampus"


def test_region_function_cn_missing_keeps_en_only():
    get = _get({"function_term": "memory consolidation",
                "region_name_cn": None, "region_name_en": "Hippocampus"})
    cn, en = parts("region_function", get)
    assert cn is None
    assert en == "memory consolidation · Hippocampus"


def test_region_function_en_missing_keeps_cn_only():
    get = _get({"function_term": "memory consolidation",
                "region_name_cn": "海马", "region_name_en": None})
    cn, en = parts("region_function", get)
    assert cn == "memory consolidation · 海马"
    assert en is None


def test_region_function_no_region_names():
    get = _get({"function_term": "memory consolidation",
                "region_name_cn": "", "region_name_en": ""})
    assert parts("region_function", get) == (None, None)


def test_projection_function_cn_en():
    get = _get({"function_term_cn": "恐惧消退", "function_term": "fear extinction"})
    assert parts("projection_function", get) == ("恐惧消退", "fear extinction")


def test_unknown_type_returns_none_pair():
    assert parts("unknown_type", _get({})) == (None, None)
