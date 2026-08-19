"""非神经靶标分类器。

识别「脑区 → 非神经结构」(如侧脑室)这类解剖学上不可能的连接靶标。
纯函数、无 DB;未命中返回 unknown(按神经处理,不误杀)。
"""

from __future__ import annotations

# 非神经结构关键词(子串匹配,大小写不敏感;中文按原样匹配)
_NON_NEURAL_KEYWORDS: tuple[str, ...] = (
    # 脑室系统
    "ventricle", "脑室",
    # 脑脊液/蛛网膜下腔/池
    "cistern", "csf", "cerebrospinal", "subarachnoid", "脑脊液", "蛛网膜下腔", "池",
    # 脑膜
    "meninges", "dura", "pia mater", "arachnoid", "脑膜", "硬脑膜", "软脑膜",
    # 脉络丛
    "choroid plexus", "脉络丛",
    # 硬膜结构
    "falx", "tentorium", "大脑镰", "小脑幕",
)


def classify_target(region_name_cn: str | None, region_name_en: str | None) -> str:
    """判定靶标是否为非神经结构。返回 'neural' | 'non_neural' | 'unknown'。

    - 命中非神经关键词(中英任一)→ 'non_neural';
    - 未命中 → 'unknown'(按神经处理,不误杀;本版本不做神经白名单确认)。
    """
    haystacks = [region_name_en or "", region_name_cn or ""]
    for kw in _NON_NEURAL_KEYWORDS:
        lowered = kw.lower()
        for h in haystacks:
            if lowered in h.lower():
                return "non_neural"
    return "unknown"
