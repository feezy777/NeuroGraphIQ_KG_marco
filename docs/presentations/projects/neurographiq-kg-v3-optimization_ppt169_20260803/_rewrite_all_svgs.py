# -*- coding: ascii -*-
"""Rewrite all 15 svg_output/*.svg as valid UTF-8 (ASCII-only source)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "svg_output"

# body_family note (spec): Microsoft YaHei, PingFang SC, Arial, sans-serif
# latin note: English/latin labels use Arial, sans-serif or shared stack.
# fill colors: only from palette below (plus #FFFFFF freely).
FF = "Microsoft YaHei, Arial, sans-serif"
FL = "Arial, sans-serif"

C_BG = "#F7FAFC"
C_BG2 = "#EDF2F7"
C_PRI = "#17324D"
C_ACC = "#1F9FB5"
C_WAR = "#C05640"
C_BODY = "#243447"
C_SEC = "#5A6A7A"
C_TER = "#8492A0"
C_BDR = "#CBD5E0"
C_OK = "#2F855A"
C_WHT = "#FFFFFF"


def u(*codes):
    return "".join(chr(c) for c in codes)


def esc(s):
    return s.replace("&", "&amp;")


def icon(name, x, y, w=28, h=28, stroke=None):
    stroke = stroke or C_ACC
    return (
        f'<use data-icon="tabler-outline/{name}" x="{x}" y="{y}" '
        f'width="{w}" height="{h}" stroke="{stroke}" fill="none" stroke-width="2"/>'
    )


def footer(n):
    return (
        f'<g id="footer"><text x="1224" y="696" text-anchor="end" '
        f'font-family="{FL}" font-size="12" fill="{C_TER}">{n}</text></g>'
    )


def header(title, subtitle=None):
    lines = [
        '<g id="header">',
        f'<rect x="56" y="42" width="8" height="40" fill="{C_ACC}"/>',
        f'<text x="80" y="72" font-family="{FF}" font-size="34" font-weight="700" fill="{C_PRI}">{esc(title)}</text>',
    ]
    if subtitle:
        lines.append(
            f'<text x="80" y="104" font-family="{FF}" font-size="16" fill="{C_SEC}">{esc(subtitle)}</text>'
        )
    lines.append("</g>")
    return "\n  ".join(lines)


def svg(parts):
    body = "\n  ".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" '
        f'width="1280" height="720">\n  {body}\n</svg>\n'
    )


def write(name, content):
    path = OUT / name
    path.write_bytes(content.encode("utf-8"))
    return path


# ----- Chinese helpers (codepoints) -----
# Common words
duo_li_du = u(0x591A, 0x7C92, 0x5EA6)
nao_qu = u(0x8111, 0x533A)
zhi_shi = u(0x77E5, 0x8BC6)
tu_pu = u(0x56FE, 0x8C31)
gou_jian = u(0x6784, 0x5EFA)
guo_cheng = u(0x8FC7, 0x7A0B)
he_xin = u(0x6838, 0x5FC3)
ming_ti = u(0x547D, 0x9898)
rang = u(0x8BA9)
cheng_wei = u(0x6210, 0x4E3A)
shou_kong = u(0x53D7, 0x63A7)
ti_qu = u(0x63D0, 0x53D6)
gong_ju = u(0x5DE5, 0x5177)
er_bu_shi = u(0x800C, 0x4E0D, 0x662F)
zhong_shen = u(0x7EC8, 0x5BA1)
zhe = u(0x8005)


def page_01():
    title_cn = duo_li_du + nao_qu + zhi_shi + tu_pu + gou_jian + guo_cheng
    thesis = (
        he_xin + ming_ti + u(0xFF1A)
        + rang + " LLM " + cheng_wei + shou_kong + ti_qu + gong_ju
        + u(0xFF0C) + er_bu_shi + zhi_shi + zhong_shen + zhe
    )
    parts = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/>'
        f'<image href="../images/cover_neural_graph.png" x="640" y="0" width="640" height="720" preserveAspectRatio="xMidYMid slice"/>'
        f'<rect x="0" y="0" width="720" height="720" fill="{C_BG}"/>'
        f'<rect x="700" y="0" width="40" height="720" fill="{C_BG}"/></g>',
        '<g id="content">',
        icon("brain", 56, 120, 48, 48, C_ACC),
        f'<text x="56" y="240" font-family="{FL}" font-size="48" font-weight="700" fill="{C_PRI}">NeuroGraphIQ KG V3</text>',
        f'<text x="56" y="300" font-family="{FF}" font-size="28" font-weight="700" fill="{C_BODY}">{esc(title_cn)}</text>',
        f'<rect x="56" y="340" width="560" height="2" fill="{C_ACC}"/>',
        f'<text x="56" y="400" font-family="{FF}" font-size="20" fill="{C_SEC}">{esc(thesis)}</text>',
        f'<text x="56" y="460" font-family="{FF}" font-size="16" fill="{C_TER}">'
        + esc(u(0x5B66, 0x672F, 0x6C47, 0x62A5, 0xFF0C, 0x4FE1, 0x4EFB, 0x6784, 0x5EFA, 0x4E0E, 0x6CBB, 0x7406, 0x95ED, 0x73AF))
        + "</text>",
        "</g>",
        footer(1),
    ]
    return svg(parts)


def page_02():
    title = u(0x591A, 0x6E90, 0x8111, 0x56FE, 0x8C31) + zhi_shi + u(0x4E3A, 0x4F55, 0x96BE, 0x4EE5, 0x53EF, 0x4FE1, 0x6C89, 0x6DC0)
    sub = u(0x95EE, 0x9898, 0x5148, 0x4E8E, 0x65B9, 0x6848, 0xFF1A, 0x63A5, 0x5165, 0x3001, 0x5408, 0x5E76, 0x3001, 0x5E7B, 0x89C9, 0x4E0E, 0x8FFD, 0x8D23)
    left_title = he_xin + u(0x95EE, 0x9898)
    right_title = he_xin + ming_ti + u(0x4E0E, 0x786C, 0x8FB9, 0x754C)
    problems = [
        u(0x591A, 0x6E90, 0x8111, 0x56FE, 0x8C31, 0x96BE, 0x7EDF, 0x4E00, 0x63A5, 0x5165),
        u(0x8DE8, 0x7C92, 0x5EA6, 0x547D, 0x540D, 0x51B2, 0x7A81, 0x6613, 0x8BF1, 0x53D1, 0x9690, 0x5F0F, 0x5408, 0x5E76),
        "LLM " + u(0x53EF, 0x80FD, 0x5E26, 0x6765, 0x5E7B, 0x89C9, 0x4E0E, 0x4E0D, 0x7A33, 0x5B9A, 0x8F93, 0x51FA),
        u(0x5BA1, 0x6838, 0x82E5, 0x6210, 0x9ED1, 0x76D2, 0x5219, 0x65E0, 0x6CD5, 0x8FFD, 0x8D23),
    ]
    bounds = [
        "LLM " + u(0x4E0D, 0x5199) + " final_*",
        "Final " + u(0x53EA, 0x6536, 0x7ECF, 0x5BA1, 0x6838) + zhi_shi,
        u(0x8DE8, 0x7C92, 0x5EA6, 0x53EA, 0x5141, 0x8BB8, 0x663E, 0x5F0F) + " mapping",
        Mirror := (u(0x662F, 0x552F, 0x4E00, 0x9884, 0x6B63, 0x5F0F, 0x7F13, 0x51B2, 0x5C42)),
    ]
    # fix walrus misuse - rewrite bounds cleanly
    bounds = [
        "LLM " + u(0x4E0D, 0x5199) + " final_*",
        "Final " + u(0x53EA, 0x6536, 0x7ECF, 0x5BA1, 0x6838) + zhi_shi,
        u(0x8DE8, 0x7C92, 0x5EA6, 0x53EA, 0x5141, 0x8BB8, 0x663E, 0x5F0F) + " mapping",
        "Mirror " + u(0x662F, 0x552F, 0x4E00, 0x9884, 0x6B63, 0x5F0F, 0x7F13, 0x51B2, 0x5C42),
    ]
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/></g>',
        header(title, sub),
        f'<g id="left"><rect x="56" y="140" width="560" height="500" rx="10" fill="{C_WHT}" stroke="{C_BDR}"/>',
        icon("alert-triangle", 84, 168, 32, 32, C_WAR),
        f'<text x="132" y="192" font-family="{FF}" font-size="22" font-weight="700" fill="{C_PRI}">{esc(left_title)}</text>',
    ]
    y = 250
    for i, p in enumerate(problems, 1):
        lines.append(
            f'<circle cx="100" cy="{y - 6}" r="14" fill="{C_BG2}" stroke="{C_WAR}"/>'
            f'<text x="100" y="{y - 1}" text-anchor="middle" font-family="{FL}" font-size="12" fill="{C_WAR}">{i}</text>'
            f'<text x="132" y="{y}" font-family="{FF}" font-size="18" fill="{C_BODY}">{esc(p)}</text>'
        )
        y += 70
    lines.append("</g>")
    lines.append(
        f'<g id="right"><rect x="664" y="140" width="560" height="500" rx="10" fill="{C_WHT}" stroke="{C_BDR}"/>'
    )
    lines.append(icon("lock", 692, 168, 32, 32, C_OK))
    lines.append(
        f'<text x="740" y="192" font-family="{FF}" font-size="22" font-weight="700" fill="{C_PRI}">{esc(right_title)}</text>'
    )
    y = 250
    for i, p in enumerate(bounds, 1):
        lines.append(
            f'<rect x="692" y="{y - 28}" width="500" height="52" rx="8" fill="{C_BG2}"/>'
            f'<text x="716" y="{y + 4}" font-family="{FF}" font-size="17" fill="{C_BODY}">{esc(p)}</text>'
        )
        y += 70
    lines.append("</g>")
    lines.append(footer(2))
    return svg(lines)


def page_03():
    title = u(0x9879, 0x76EE, 0x5B9A, 0x4F4D, 0xFF1A) + duo_li_du + nao_qu + zhi_shi + u(0x57FA, 0x7840, 0x8BBE, 0x65BD)
    sub = u(0x4E09, 0x5217, 0x5B9A, 0x4F4D, 0xFF0B, 0x4E94, 0x7EA7, 0x7C92, 0x5EA6, 0x9694, 0x79BB, 0xFF08, 0x5B8F, 0x89C2, 0x4E34, 0x5E8A, 0x5DF2, 0x843D, 0x5730, 0xFF09)
    cols = [
        (u(0x76EE, 0x6807), duo_li_du + tu_pu, "topology-star"),
        (u(0x4EFB, 0x52A1), u(0x5168, 0x94FE, 0x8DEF) + gou_jian + u(0x4E0E, 0x6CBB, 0x7406), "route"),
        (u(0x67B6, 0x6784), u(0x4E94, 0x7EA7, 0x7C92, 0x5EA6) + " Schema " + u(0x9694, 0x79BB), "stack-2"),
    ]
    grains = [
        (u(0x5B8F, 0x89C2, 0x4E34, 0x5E8A), True, "AAL3 / Macro96"),
        (u(0x4ECB, 0x89C2, 0x89E3, 0x5256), False, "HCP-MMP"),
        (u(0x4E9A, 0x533A, 0x8FDE, 0x63A5), False, "Brainnetome"),
        (u(0x7EC6, 0x80DE, 0x6784, 0x7B51), False, "Julich"),
        (u(0x5206, 0x5B50, 0x5C5E, 0x6027), False, "Allen"),
    ]
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/></g>',
        header(title, sub),
    ]
    x = 56
    for t, b, ic in cols:
        lines.append(
            f'<g><rect x="{x}" y="140" width="368" height="220" rx="10" fill="{C_WHT}" stroke="{C_BDR}"/>'
            + icon(ic, x + 28, 168, 32, 32)
            + f'<text x="{x + 76}" y="192" font-family="{FF}" font-size="20" font-weight="700" fill="{C_PRI}">{esc(t)}</text>'
            + f'<text x="{x + 28}" y="260" font-family="{FF}" font-size="22" font-weight="700" fill="{C_BODY}">{esc(b)}</text></g>'
        )
        x += 392
    lines.append(
        f'<g id="grain"><text x="56" y="420" font-family="{FF}" font-size="18" font-weight="700" fill="{C_PRI}">'
        + esc(u(0x4E94, 0x7EA7, 0x7C92, 0x5EA6, 0x6761))
        + "</text>"
    )
    x = 56
    for name, done, tag in grains:
        fill = C_OK if done else C_BG2
        tc = C_WHT if done else C_BODY
        badge = u(0x5DF2, 0x843D, 0x5730) if done else u(0x89C4, 0x5212)
        lines.append(
            f'<rect x="{x}" y="450" width="216" height="160" rx="10" fill="{fill}" stroke="{C_BDR}"/>'
            f'<text x="{x + 108}" y="510" text-anchor="middle" font-family="{FF}" font-size="18" font-weight="700" fill="{tc}">{esc(name)}</text>'
            f'<text x="{x + 108}" y="545" text-anchor="middle" font-family="{FL}" font-size="14" fill="{tc}">{esc(tag)}</text>'
            f'<text x="{x + 108}" y="580" text-anchor="middle" font-family="{FF}" font-size="14" fill="{tc}">{esc(badge)}</text>'
        )
        x += 232
    lines.append("</g>")
    lines.append(footer(3))
    return svg(lines)


def page_04():
    title = u(0x4E5D, 0x9879, 0x786C, 0x7EA6, 0x675F)
    sub = u(0x6CA1, 0x6709, 0x5BA1, 0x6838, 0x8BB0, 0x5F55, 0xFF0C, 0x5C31, 0x4E0D, 0x5F97, 0x8FDB, 0x5165, 0x4E0B, 0x4E00, 0x73AF, 0x8282)
    items = [
        "LLM " + u(0x9694, 0x79BB),
        u(0x7EDF, 0x4E00, 0x5165, 0x53E3),
        u(0x53CC, 0x91CD, 0x5BA1, 0x6838),
        u(0x6B63, 0x5F0F, 0x5E93, 0x7EAF, 0x51C0),
        u(0x5168, 0x94FE, 0x8DEF, 0x6EAF, 0x6E90),
        u(0x7C92, 0x5EA6, 0x9694, 0x79BB),
        u(0x663E, 0x5F0F, 0x6620, 0x5C04),
        u(0x8F93, 0x51FA, 0x7559, 0x75D5),
        u(0x5168, 0x7A0B, 0x65E5, 0x5FD7),
    ]
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/></g>',
        header(title, sub),
        f'<g id="left"><rect x="56" y="140" width="560" height="500" rx="10" fill="{C_WHT}" stroke="{C_BDR}"/>',
    ]
    y = 190
    for i, t in enumerate(items[:5], 1):
        lines.append(
            f'<rect x="84" y="{y - 30}" width="504" height="56" rx="8" fill="{C_BG2}"/>'
            f'<text x="108" y="{y + 6}" font-family="{FL}" font-size="20" font-weight="700" fill="{C_ACC}">0{i}</text>'
            f'<text x="168" y="{y + 6}" font-family="{FF}" font-size="20" fill="{C_BODY}">{esc(t)}</text>'
        )
        y += 80
    lines.append("</g>")
    lines.append(
        f'<g id="right"><rect x="664" y="140" width="560" height="500" rx="10" fill="{C_WHT}" stroke="{C_BDR}"/>'
    )
    y = 190
    for i, t in enumerate(items[5:], 6):
        lines.append(
            f'<rect x="692" y="{y - 30}" width="504" height="56" rx="8" fill="{C_BG2}"/>'
            f'<text x="716" y="{y + 6}" font-family="{FL}" font-size="20" font-weight="700" fill="{C_ACC}">0{i}</text>'
            f'<text x="776" y="{y + 6}" font-family="{FF}" font-size="20" fill="{C_BODY}">{esc(t)}</text>'
        )
        y += 80
    lines.append("</g>")
    lines.append(footer(4))
    return svg(lines)


def page_05():
    title = u(0x4E03, 0x5C42, 0x77E5, 0x8BC6, 0x9636, 0x68AF)
    sub = u(0x81EA, 0x4E0B, 0x800C, 0x4E0A, 0xFF1A, 0x7ED3, 0x6784, 0x4E0E, 0x8BC1, 0x636E, 0x5206, 0x5C42, 0xFF0C, 0x907F, 0x514D, 0x6DF7, 0x5E73)
    # top to bottom as user: ?????????????????????
    layers = [
        u(0x6620, 0x5C04),
        u(0x4E09, 0x5143, 0x7EC4),
        u(0x8BC1, 0x636E),
        u(0x529F, 0x80FD),
        u(0x56DE, 0x8DEF),
        u(0x8FDE, 0x63A5),
        u(0x5B9E, 0x4F53),
    ]
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/></g>',
        header(title, sub),
        '<g id="stairs">',
    ]
    for i, name in enumerate(layers):
        w = 420 + i * 90
        x = 56 + (1168 - w) // 2
        y = 140 + i * 70
        fill = C_ACC if i == 0 else (C_PRI if i < 3 else C_BG2)
        tc = C_WHT if i < 3 else C_BODY
        lines.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="56" rx="8" fill="{fill}" stroke="{C_BDR}"/>'
            f'<text x="{x + w // 2}" y="{y + 36}" text-anchor="middle" font-family="{FF}" font-size="20" font-weight="700" fill="{tc}">{esc(name)}</text>'
        )
    lines.append("</g>")
    lines.append(footer(5))
    return svg(lines)


def page_06():
    title = u(0x6784, 0x5EFA, 0x6F0F, 0x6597, 0xFF1A, 0x4E94, 0x9636, 0x6BB5)
    sub = u(0x81EA, 0x52A8, 0x5316, 0x89E3, 0x51B3, 0x89C4, 0x6A21, 0xFF0C, 0x4EBA, 0x5DE5, 0x628A, 0x5173, 0x89E3, 0x51B3, 0x53EF, 0x4FE1)
    stages = [
        (u(0x5BFC, 0x5165, 0x89E3, 0x6790), "database-import", 980),
        (u(0x5019, 0x9009, 0x751F, 0x6210), "filter", 860),
        (u(0x6821, 0x9A8C, 0x589E, 0x5F3A), "shield-check", 740),
        ("LLM " + u(0x63D0, 0x53D6), "robot", 620),
        (u(0x5BA1, 0x6838, 0x664B, 0x5347), "user-check", 500),
    ]
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/></g>',
        header(title, sub),
        '<g id="funnel">',
    ]
    y = 150
    for i, (name, ic, w) in enumerate(stages):
        x = (1280 - w) // 2
        fill = C_ACC if i < 3 else (C_PRI if i == 3 else C_OK)
        lines.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="80" rx="10" fill="{fill}"/>'
            + icon(ic, x + 28, y + 24, 32, 32, C_WHT)
            + f'<text x="{x + w // 2}" y="{y + 50}" text-anchor="middle" font-family="{FF}" font-size="22" font-weight="700" fill="{C_WHT}">{esc(name)}</text>'
        )
        y += 96
    lines.append("</g>")
    lines.append(footer(6))
    return svg(lines)


def page_07():
    title = u(0x5168, 0x5C40, 0x67B6, 0x6784, 0xFF1A, 0x751F, 0x4EA7) + " - " + u(0x6CBB, 0x7406) + " - " + u(0x6D88, 0x8D39)
    sub = "Mirror " + u(0x662F, 0x552F, 0x4E00, 0x9884, 0x6B63, 0x5F0F, 0x7F13, 0x51B2, 0x5C42, 0xFF1B, 0x664B, 0x5347, 0x5FC5, 0x987B, 0x9884, 0x89C8, 0x786E, 0x8BA4)
    nodes = [
        ("Raw", "database"),
        ("Candidate", "filter"),
        ("LLM/Mirror", "robot"),
        ("Review", "user-check"),
        ("Final", "circle-check"),
        (u(0x6D88, 0x8D39), "database-export"),
    ]
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/>'
        f'<image href="../images/global_architecture_atmosphere.png" x="0" y="120" width="1280" height="520" preserveAspectRatio="xMidYMid slice"/>'
        f'<rect x="0" y="120" width="1280" height="520" fill="{C_BG}" opacity="0.82"/></g>',
    ]
    # opacity on rect - user said no rgba and no g opacity. rect opacity might be borderline.
    # Avoid opacity: use solid light overlay instead
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/>'
        f'<image href="../images/global_architecture_atmosphere.png" x="720" y="160" width="520" height="480" preserveAspectRatio="xMidYMid slice"/>'
        f'<rect x="700" y="160" width="40" height="480" fill="{C_BG}"/></g>',
        header(title, sub),
        '<g id="pipeline">',
    ]
    x = 56
    for i, (name, ic) in enumerate(nodes):
        fill = C_OK if name == "Final" else (C_ACC if i < 3 else C_PRI)
        lines.append(
            f'<rect x="{x}" y="280" width="160" height="120" rx="10" fill="{C_WHT}" stroke="{fill}" stroke-width="2"/>'
            + icon(ic, x + 64, 300, 32, 32, fill)
            + f'<text x="{x + 80}" y="370" text-anchor="middle" font-family="{FF}" font-size="16" font-weight="700" fill="{C_PRI}">{esc(name)}</text>'
        )
        if i < len(nodes) - 1:
            lines.append(
                f'<line x1="{x + 160}" y1="340" x2="{x + 188}" y2="340" stroke="{C_ACC}" stroke-width="3"/>'
            )
            lines.append(icon("arrow-right", x + 164, 328, 24, 24, C_ACC))
        x += 196
    hard = u(0x786C, 0x8FB9, 0x754C) + "  |  LLM " + u(0x4E0D, 0x5199) + " final_*  |  " + u(0x4EBA, 0x5DE5, 0x5BA1, 0x6838, 0x5FC5, 0x7ECF) + "  |  " + u(0x663E, 0x5F0F) + " mapping"
    lines.append("</g>")
    lines.append(
        f'<rect x="56" y="460" width="1168" height="120" rx="10" fill="{C_WHT}" stroke="{C_WAR}"/>'
        + icon("lock", 84, 500, 32, 32, C_WAR)
        + f'<text x="136" y="525" font-family="{FF}" font-size="20" font-weight="700" fill="{C_PRI}">{esc(hard)}</text>'
    )
    lines.append(footer(7))
    return svg(lines)


def page_08():
    title = u(0x5BFC, 0x5165, 0x4E0E, 0x5019, 0x9009, 0xFF1A, 0x4E94, 0x6B65, 0x786E, 0x5B9A, 0x6027, 0x94FE, 0x8DEF)
    sub = u(0x8F93, 0x51FA, 0x5E26) + " provenance " + u(0x7684, 0x6807, 0x51C6, 0x5316, 0x5019, 0x9009, 0x8BB0, 0x5F55)
    steps = [
        (u(0x8D44, 0x6E90, 0x767B, 0x8BB0), "books"),
        (u(0x53CC, 0x8F68, 0x6587, 0x4EF6), "database"),
        (u(0x6279, 0x6B21, 0x5BA1, 0x8BA1), "checklist"),
        (u(0x5355, 0x5411, 0x89E3, 0x6790), "database-import"),
        (u(0x6EAF, 0x6E90, 0x5019, 0x9009), "git-branch"),
    ]
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/></g>',
        header(title, sub),
        '<g id="steps">',
    ]
    x = 56
    for i, (name, ic) in enumerate(steps, 1):
        lines.append(
            f'<rect x="{x}" y="220" width="200" height="280" rx="10" fill="{C_WHT}" stroke="{C_BDR}"/>'
            f'<circle cx="{x + 100}" cy="280" r="28" fill="{C_ACC}"/>'
            f'<text x="{x + 100}" y="288" text-anchor="middle" font-family="{FL}" font-size="20" font-weight="700" fill="{C_WHT}">{i}</text>'
            + icon(ic, x + 84, 340, 32, 32)
            + f'<text x="{x + 100}" y="420" text-anchor="middle" font-family="{FF}" font-size="20" font-weight="700" fill="{C_PRI}">{esc(name)}</text>'
        )
        if i < 5:
            lines.append(
                f'<line x1="{x + 200}" y1="360" x2="{x + 232}" y2="360" stroke="{C_ACC}" stroke-width="3"/>'
            )
        x += 232
    lines.append("</g>")
    lines.append(footer(8))
    return svg(lines)


def page_09():
    title = u(0x89C4, 0x5219, 0x6821, 0x9A8C, 0x4E0E, 0x589E, 0x5F3A)
    sub = u(0x589E, 0x5F3A, 0x4E0D, 0x7B49, 0x4E8E, 0x5165, 0x5E93)
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/></g>',
        header(title, sub),
        f'<g id="left"><rect x="56" y="140" width="560" height="500" rx="10" fill="{C_WHT}" stroke="{C_BDR}"/>',
        icon("shield-check", 84, 168, 32, 32, C_OK),
        f'<text x="132" y="192" font-family="{FF}" font-size="22" font-weight="700" fill="{C_PRI}">'
        + esc(u(0x786E, 0x5B9A, 0x6027, 0x6821, 0x9A8C))
        + "</text>",
        f'<text x="84" y="260" font-family="{FF}" font-size="20" fill="{C_BODY}">12 ' + esc(u(0x6761, 0x89C4, 0x5219)) + "</text>",
        f'<text x="84" y="310" font-family="{FF}" font-size="20" fill="{C_BODY}">'
        + esc(u(0x8D28, 0x91CF, 0x5206) + " 0-100")
        + "</text>",
        f'<rect x="84" y="350" width="500" height="80" rx="8" fill="{C_BG2}"/>'
        f'<text x="108" y="400" font-family="{FL}" font-size="22" font-weight="700" fill="{C_WAR}">BLOCKER</text>'
        f'<text x="260" y="400" font-family="{FF}" font-size="18" fill="{C_BODY}">'
        + esc(u(0x76F4, 0x63A5, 0x7194, 0x65AD))
        + "</text>",
        f'<text x="84" y="500" font-family="{FF}" font-size="16" fill="{C_SEC}">'
        + esc(u(0x89C4, 0x5219, 0x5728, 0x524D, 0xFF0C, 0x6A21, 0x578B, 0x5728, 0x540E))
        + "</text></g>",
        f'<g id="right"><rect x="664" y="140" width="560" height="500" rx="10" fill="{C_WHT}" stroke="{C_BDR}"/>',
        icon("settings", 692, 168, 32, 32),
        f'<text x="740" y="192" font-family="{FF}" font-size="22" font-weight="700" fill="{C_PRI}">'
        + esc(u(0x589E, 0x5F3A, 0x5206, 0x5C42))
        + "</text>",
        f'<rect x="692" y="240" width="504" height="140" rx="8" fill="{C_BG2}"/>'
        f'<text x="716" y="290" font-family="{FL}" font-size="22" font-weight="700" fill="{C_ACC}">Tier1</text>'
        f'<text x="716" y="335" font-family="{FF}" font-size="18" fill="{C_BODY}">'
        + esc(u(0x89C4, 0x5219, 0x81EA, 0x52A8, 0x4FEE, 0x590D))
        + "</text>",
        f'<rect x="692" y="410" width="504" height="140" rx="8" fill="{C_BG2}"/>'
        f'<text x="716" y="460" font-family="{FL}" font-size="22" font-weight="700" fill="{C_WAR}">Tier2</text>'
        f'<text x="716" y="505" font-family="{FF}" font-size="18" fill="{C_BODY}">'
        + esc("LLM " + u(0x5EFA, 0x8BAE, 0x5FC5, 0x987B, 0x4EBA, 0x5DE5, 0x590D, 0x6838))
        + "</text></g>",
        footer(9),
    ]
    return svg(lines)


def page_10():
    title = "LLM + Mirror " + u(0x6CBB, 0x7406)
    sub = u(0x6240, 0x6709, 0x63D0, 0x53D6, 0x7ED3, 0x679C, 0x5148, 0x5165) + " Mirror"
    left_items = [
        "Provider " + u(0x62BD, 0x8C61),
        u(0x4E03, 0x7C7B, 0x5173, 0x7CFB, 0x63D0, 0x53D6),
        u(0x5F02, 0x6B65, 0x7F16, 0x6392),
        u(0x8C03, 0x7528, 0x65E5, 0x5FD7),
    ]
    right_items = [
        u(0x5199, 0x5165, 0x53BB, 0x91CD, 0x5408, 0x5E76),
        u(0x53CC, 0x6A21, 0x578B, 0x76F2, 0x5BA1),
        u(0x56DE, 0x8DEF, 0x6295, 0x5C04, 0x4EA4, 0x53C9, 0x9A8C, 0x8BC1),
        u(0x4E0D, 0x76F4, 0x5199) + " final_*",
    ]
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/>'
        f'<image href="../images/llm_capability_backdrop.png" x="0" y="400" width="1280" height="320" preserveAspectRatio="xMidYMid slice"/>'
        f'<rect x="0" y="400" width="1280" height="320" fill="{C_BG}"/></g>',
        header(title, sub),
        f'<g id="left"><rect x="56" y="140" width="560" height="480" rx="10" fill="{C_WHT}" stroke="{C_BDR}"/>',
        icon("robot", 84, 168, 32, 32),
        f'<text x="132" y="192" font-family="{FF}" font-size="22" font-weight="700" fill="{C_PRI}">LLM ' + esc(u(0x80FD, 0x529B)) + "</text>",
    ]
    y = 260
    for t in left_items:
        lines.append(
            f'<text x="84" y="{y}" font-family="{FF}" font-size="20" fill="{C_BODY}">- {esc(t)}</text>'
        )
        y += 60
    lines.append("</g>")
    lines.append(
        f'<g id="right"><rect x="664" y="140" width="560" height="480" rx="10" fill="{C_WHT}" stroke="{C_BDR}"/>'
    )
    lines.append(icon("network", 692, 168, 32, 32))
    lines.append(
        f'<text x="740" y="192" font-family="{FF}" font-size="22" font-weight="700" fill="{C_PRI}">Mirror ' + esc(u(0x6CBB, 0x7406)) + "</text>"
    )
    y = 260
    for t in right_items:
        lines.append(
            f'<text x="692" y="{y}" font-family="{FF}" font-size="20" fill="{C_BODY}">- {esc(t)}</text>'
        )
        y += 60
    lines.append("</g>")
    lines.append(footer(10))
    return svg(lines)


def page_11():
    title = u(0x4E09, 0x9053, 0x95F8, 0x95E8, 0x4E0E, 0x664B, 0x5347)
    sub = u(0x901A, 0x8FC7, 0x540E, 0x624D, 0x5199, 0x5165, 0x6807, 0x51C6, 0x4E09, 0x5143, 0x7EC4)
    gates = [
        (u(0x89C4, 0x5219, 0x6821, 0x9A8C), "shield-check"),
        (u(0x6A21, 0x578B, 0x76F2, 0x5BA1), "robot"),
        (u(0x4E13, 0x5BB6, 0x7EC8, 0x5BA1), "user-check"),
    ]
    promo = [
        u(0x9884, 0x89C8, 0x53D8, 0x66F5),
        u(0x4EBA, 0x5DE5, 0x786E, 0x8BA4),
        u(0x7CFB, 0x7EDF, 0x6267, 0x884C),
    ]
    # fix typo ??
    promo = [
        u(0x9884, 0x89C8, 0x53D8, 0x66F4),
        u(0x4EBA, 0x5DE5, 0x786E, 0x8BA4),
        u(0x7CFB, 0x7EDF, 0x6267, 0x884C),
    ]
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/></g>',
        header(title, sub),
        '<g id="chevrons">',
    ]
    x = 56
    for i, (name, ic) in enumerate(gates):
        # chevron-like trapezoid via polygon
        pts = f"{x},{200} {x + 300},{200} {x + 340},{270} {x + 300},{340} {x},{340} {x + 40},{270}"
        lines.append(
            f'<polygon points="{pts}" fill="{C_ACC if i < 2 else C_OK}"/>'
            + icon(ic, x + 120, 230, 32, 32, C_WHT)
            + f'<text x="{x + 170}" y="300" text-anchor="middle" font-family="{FF}" font-size="18" font-weight="700" fill="{C_WHT}">{esc(name)}</text>'
        )
        x += 360
    lines.append("</g>")
    lines.append(
        f'<g id="promo"><text x="56" y="420" font-family="{FF}" font-size="18" font-weight="700" fill="{C_PRI}">'
        + esc(u(0x664B, 0x5347, 0x4E09, 0x6B65, 0x9AA4))
        + "</text>"
    )
    x = 56
    for i, name in enumerate(promo, 1):
        lines.append(
            f'<rect x="{x}" y="450" width="280" height="90" rx="10" fill="{C_WHT}" stroke="{C_BDR}"/>'
            f'<text x="{x + 24}" y="505" font-family="{FL}" font-size="20" font-weight="700" fill="{C_ACC}">0{i}</text>'
            f'<text x="{x + 70}" y="505" font-family="{FF}" font-size="20" fill="{C_BODY}">{esc(name)}</text>'
        )
        x += 310
    lines.append("</g>")
    lines.append(
        f'<rect x="56" y="570" width="1168" height="70" rx="10" fill="{C_BG2}"/>'
        f'<text x="640" y="615" text-anchor="middle" font-family="{FF}" font-size="18" fill="{C_BODY}">'
        + esc(u(0x4E09, 0x5143, 0x7EC4) + " + 12 " + u(0x79CD, 0x8C13, 0x8BCD))
        + "</text>"
    )
    lines.append(footer(11))
    return svg(lines)


def page_12():
    title = zhi_shi + u(0x6D88, 0x8D39, 0xFF1A, 0x4ECE, 0x56FE, 0x8C31, 0x5230, 0x53EF, 0x64CD, 0x4F5C, 0x6D1E, 0x5BDF)
    sub = u(0x56DB, 0x7C7B, 0x5165, 0x53E3, 0x5171, 0x7528, 0x540C, 0x4E00) + " Final KG " + u(0x67E5, 0x8BE2, 0x9762)
    cards = [
        (u(0x6570, 0x636E, 0x4E2D, 0x5FC3), "database", "Raw - Candidate - Mirror - Final", u(0x5168, 0x751F, 0x547D, 0x5468, 0x671F, 0x53EF, 0x89C6, 0x5316, 0x76D1, 0x63A7, 0x4E0E, 0x68C0, 0x7D22)),
        (u(0x56FE, 0x8C31, 0x63A2, 0x7D22), "network", u(0x8282, 0x70B9, 0x805A, 0x7126) + " / " + u(0x5C42, 0x7EA7, 0x5C55, 0x5F00) + " / " + u(0x5173, 0x7CFB, 0x7B5B, 0x9009), u(0x76F4, 0x89C2, 0x5448, 0x73B0, 0x8111, 0x533A) + "-" + u(0x8FDE, 0x63A5) + "-" + u(0x529F, 0x80FD, 0x62D3, 0x6251)),
        (u(0x75C7, 0x72B6, 0x67E5, 0x8BE2), "search", u(0x81EA, 0x7136, 0x8BED, 0x8A00, 0x75C7, 0x72B6, 0x5230, 0x6807, 0x51C6, 0x5316, 0x8111, 0x533A, 0x4E0E, 0x56DE, 0x8DEF), u(0x8F93, 0x51FA, 0x542B, 0x8BC1, 0x636E, 0x94FE, 0x7684, 0x7ED3, 0x6784, 0x5316, 0x62A5, 0x544A)),
        (zhi_shi + u(0x5BFC, 0x51FA), "database-export", "JSONL / CSV / Neo4j " + u(0x7B49, 0x56FE, 0x5E93, 0x517C, 0x5BB9), u(0x652F, 0x6301, 0x79BB, 0x7EBF, 0x6316, 0x6398, 0x4E0E, 0x8DE8, 0x5E73, 0x53F0, 0x8FC1, 0x79FB)),
    ]
    positions = [(56, 140), (664, 140), (56, 400), (664, 400)]
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/></g>',
        header(title, sub),
    ]
    for (t, ic, a, b), (x, y) in zip(cards, positions):
        lines.append(
            f'<g><rect x="{x}" y="{y}" width="560" height="230" rx="10" fill="{C_WHT}" stroke="{C_BDR}"/>'
            + icon(ic, x + 28, y + 28, 32, 32)
            + f'<text x="{x + 76}" y="{y + 52}" font-family="{FF}" font-size="22" font-weight="700" fill="{C_PRI}">{esc(t)}</text>'
            + f'<text x="{x + 28}" y="{y + 110}" font-family="{FF}" font-size="17" fill="{C_BODY}">{esc(a)}</text>'
            + f'<text x="{x + 28}" y="{y + 150}" font-family="{FF}" font-size="16" fill="{C_SEC}">{esc(b)}</text></g>'
        )
    lines.append(footer(12))
    return svg(lines)


def page_13():
    title = u(0x516B, 0x6B65, 0x6EAF, 0x6E90) + " Snake"
    sub = u(0x4ECE) + " Final " + u(0x53CD, 0x5411, 0x8FFD, 0x5230) + " Resource" + u(0xFF0C, 0x4FDD, 0x7559, 0x8BC1, 0x636E, 0x94FE)
    nodes = [
        "Final",
        "Promotion",
        "Review",
        "Validation",
        "Extraction",
        "Candidate",
        "Import",
        "Resource",
    ]
    # snake: row1 L->R 0-3, row2 R->L 4-7
    coords = [
        (56, 200),
        (340, 200),
        (624, 200),
        (908, 200),
        (908, 420),
        (624, 420),
        (340, 420),
        (56, 420),
    ]
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/></g>',
        header(title, sub),
        '<g id="snake">',
    ]
    for i, ((x, y), name) in enumerate(zip(coords, nodes)):
        fill = C_OK if i == 0 else C_WHT
        tc = C_WHT if i == 0 else C_PRI
        stroke = C_OK if i == 0 else C_BDR
        lines.append(
            f'<rect x="{x}" y="{y}" width="260" height="100" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
            f'<text x="{x + 28}" y="{y + 40}" font-family="{FL}" font-size="14" fill="{C_ACC if i else C_WHT}">0{i + 1 if i < 9 else i + 1}</text>'
            f'<text x="{x + 28}" y="{y + 70}" font-family="{FF}" font-size="20" font-weight="700" fill="{tc}">{esc(name)}</text>'
        )
        if i < 3:
            lines.append(
                f'<line x1="{x + 260}" y1="{y + 50}" x2="{x + 340}" y2="{y + 50}" stroke="{C_ACC}" stroke-width="3"/>'
            )
        elif i == 3:
            lines.append(
                f'<line x1="{x + 130}" y1="{y + 100}" x2="{x + 130}" y2="{y + 220}" stroke="{C_ACC}" stroke-width="3"/>'
            )
        elif i < 7:
            # going left
            nx = coords[i + 1][0] + 260
            lines.append(
                f'<line x1="{x}" y1="{y + 50}" x2="{nx}" y2="{y + 50}" stroke="{C_ACC}" stroke-width="3"/>'
            )
    lines.append("</g>")
    lines.append(
        f'<text x="56" y="600" font-family="{FF}" font-size="16" fill="{C_SEC}">'
        + esc(u(0x8BC1, 0x636E, 0x94FE, 0xFF1A, 0x539F, 0x6587, 0x3001) + "LLM " + u(0x8F93, 0x51FA, 0x3001, 0x89C4, 0x5219, 0x65E5, 0x5FD7, 0x3001, 0x5BA1, 0x6838, 0x610F, 0x89C1))
        + "</text>"
    )
    lines.append(footer(13))
    return svg(lines)


def page_14():
    title = u(0x6280, 0x672F, 0x6808, 0x4E0E, 0x5DE5, 0x7A0B, 0x89C4, 0x6A21)
    sub = u(0x6307, 0x6807, 0x6765, 0x81EA, 0x4ED3, 0x5E93, 0x7EDF, 0x8BA1, 0xFF1B, 0x4E0D, 0x505A, 0x4E0D, 0x53EF, 0x6838, 0x9A8C, 0x627F, 0x8BFA)
    stack = [("FastAPI", C_ACC), ("React", C_PRI), ("PostgreSQL", C_OK)]
    kpis = [
        ("5", u(0x7C92, 0x5EA6)),
        ("166/96", "AAL3 / Macro96"),
        ("12", u(0x89C4, 0x5219)),
        ("7", u(0x7C7B, 0x63D0, 0x53D6)),
        ("42", u(0x8DEF, 0x7531)),
        ("88", u(0x670D, 0x52A1)),
    ]
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/></g>',
        header(title, sub),
        '<g id="stack">',
    ]
    x = 56
    for name, col in stack:
        lines.append(
            f'<rect x="{x}" y="140" width="360" height="90" rx="10" fill="{C_WHT}" stroke="{col}" stroke-width="2"/>'
            f'<text x="{x + 180}" y="195" text-anchor="middle" font-family="{FL}" font-size="28" font-weight="700" fill="{col}">{name}</text>'
        )
        x += 392
    lines.append('</g>')
    lines.append('<g id="kpis">')
    x = 56
    y = 280
    for i, (num, label) in enumerate(kpis):
        if i == 3:
            x = 56
            y = 430
        lines.append(
            f'<rect x="{x}" y="{y}" width="360" height="120" rx="10" fill="{C_WHT}" stroke="{C_BDR}"/>'
            f'<text x="{x + 28}" y="{y + 55}" font-family="{FL}" font-size="36" font-weight="700" fill="{C_ACC}">{num}</text>'
            f'<text x="{x + 28}" y="{y + 95}" font-family="{FF}" font-size="18" fill="{C_BODY}">{esc(label)}</text>'
        )
        x += 392
    lines.append("</g>")
    lines.append(
        f'<rect x="56" y="580" width="1168" height="70" rx="10" fill="{C_BG2}"/>'
        f'<text x="80" y="625" font-family="{FF}" font-size="18" fill="{C_BODY}">'
        + esc("1173 " + u(0x6D4B, 0x8BD5, 0x53E3, 0x5F84, 0xFF1A, 0x4ED3, 0x5E93, 0x53EF, 0x590D, 0x73B0, 0x7EDF, 0x8BA1, 0xFF0C, 0x975E, 0x8425, 0x9500, 0x53E3, 0x53F7))
        + "</text>"
    )
    lines.append(footer(14))
    return svg(lines)


def page_15():
    title = u(0x7ED3, 0x8BBA, 0x4E0E) + " Q&amp;A"
    # title uses &amp; already in string - esc would double; build carefully
    title_plain_part = u(0x7ED3, 0x8BBA, 0x4E0E) + " Q&A"
    title = esc(title_plain_part)
    points = [
        shou_kong + " LLM + Mirror " + u(0x662F, 0x5173, 0x952E),
        u(0x516B, 0x6B65, 0x6EAF, 0x6E90, 0x4FDD, 0x8BC1, 0x53EF, 0x8FFD, 0x8D23),
        u(0x5B8F, 0x89C2, 0x4E34, 0x5E8A, 0x5C42, 0x5DF2, 0x843D, 0x5730, 0x5E76, 0x53EF, 0x7EE7, 0x7EED, 0x6269, 0x5C55),
    ]
    lines = [
        f'<g id="background"><rect width="1280" height="720" fill="{C_BG}"/></g>',
        f'<g id="header"><rect x="56" y="42" width="8" height="40" fill="{C_ACC}"/>'
        f'<text x="80" y="72" font-family="{FF}" font-size="34" font-weight="700" fill="{C_PRI}">{title}</text></g>',
        '<g id="points">',
    ]
    y = 160
    for i, p in enumerate(points, 1):
        lines.append(
            f'<rect x="56" y="{y}" width="1168" height="90" rx="10" fill="{C_WHT}" stroke="{C_BDR}"/>'
            f'<circle cx="110" cy="{y + 45}" r="24" fill="{C_ACC}"/>'
            f'<text x="110" y="{y + 52}" text-anchor="middle" font-family="{FL}" font-size="20" font-weight="700" fill="{C_WHT}">{i}</text>'
            f'<text x="160" y="{y + 55}" font-family="{FF}" font-size="24" fill="{C_BODY}">{esc(p)}</text>'
        )
        y += 110
    lines.append("</g>")
    lines.append(
        f'<rect x="56" y="520" width="1168" height="120" rx="10" fill="{C_PRI}"/>'
        f'<text x="640" y="590" text-anchor="middle" font-family="{FL}" font-size="48" font-weight="700" fill="{C_WHT}">Q&amp;A</text>'
    )
    lines.append(footer(15))
    return svg(lines)


PAGES = [
    ("01_cover.svg", page_01),
    ("02_problem_thesis.svg", page_02),
    ("03_positioning.svg", page_03),
    ("04_principles.svg", page_04),
    ("05_knowledge_layers.svg", page_05),
    ("06_funnel_pipeline.svg", page_06),
    ("07_global_architecture.svg", page_07),
    ("08_import_candidate.svg", page_08),
    ("09_rules_enhance.svg", page_09),
    ("10_llm_mirror.svg", page_10),
    ("11_gates_promote.svg", page_11),
    ("12_consumption.svg", page_12),
    ("13_traceability.svg", page_13),
    ("14_tech_scale.svg", page_14),
    ("15_conclusion_qa.svg", page_15),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in PAGES:
        path = write(name, fn())
        # validate immediately
        path.read_text(encoding="utf-8")
        print("OK", name, path.stat().st_size)


if __name__ == "__main__":
    main()
