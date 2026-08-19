# -*- coding: utf-8 -*-
"""非神经靶标分类器:脑室/脑脊液/脑膜/脉络丛识别,正常脑区不误伤。"""

from app.services.evidence_target_classifier import classify_target


def test_lateral_ventricle_en():
    assert classify_target(None, "Lateral ventricle") == "non_neural"


def test_ventricle_cn():
    assert classify_target("侧脑室", None) == "non_neural"


def test_third_fourth_ventricle():
    assert classify_target("第三脑室", "Third ventricle") == "non_neural"


def test_cistern_cn_en():
    assert classify_target(None, "Suprasellar cistern") == "non_neural"
    assert classify_target("环池", None) == "non_neural"


def test_csf_subarachnoid():
    assert classify_target(None, "Cerebrospinal fluid") == "non_neural"
    assert classify_target(None, "Subarachnoid space") == "non_neural"


def test_meninges():
    assert classify_target(None, "Dura mater") == "non_neural"
    assert classify_target(None, "Pia mater") == "non_neural"
    assert classify_target("硬脑膜", None) == "non_neural"


def test_choroid_plexus():
    assert classify_target(None, "Choroid plexus") == "non_neural"
    assert classify_target("脉络丛", None) == "non_neural"


def test_falk_tentorium():
    assert classify_target(None, "Falx cerebri") == "non_neural"
    assert classify_target(None, "Tentorium cerebelli") == "non_neural"


def test_real_region_not_mistaken():
    assert classify_target("杏仁核", "Amygdala") == "unknown"
    assert classify_target("前扣带皮层", "Anterior cingulate cortex") == "unknown"
    assert classify_target(None, "Primary somatosensory area, layer 4") == "unknown"


def test_none_inputs():
    assert classify_target(None, None) == "unknown"


def test_all_non_neural_keywords_hit():
    """表驱动:全部非神经关键词(含未单独覆盖的 9 个)都应命中 non_neural。"""
    cases = [
        ("csf", None), ("脑脊液", None), ("蛛网膜下腔", None),
        ("meninges", None), ("arachnoid", None), ("脑膜", None), ("软脑膜", None),
        ("大脑镰", None), ("小脑幕", None),
        # 已覆盖关键词回归
        ("Lateral ventricle", None), ("侧脑室", None), ("Suprasellar cistern", None),
        ("Choroid plexus", None), ("Dura mater", None), ("Falx cerebri", None),
        ("Tentorium cerebelli", None),
    ]
    for cn, en in cases:
        assert classify_target(cn, en) == "non_neural", f"missed: {cn or en}"
