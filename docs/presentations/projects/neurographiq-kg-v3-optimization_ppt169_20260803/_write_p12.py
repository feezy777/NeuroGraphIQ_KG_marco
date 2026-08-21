# -*- coding: utf-8 -*-
from pathlib import Path

root = Path(__file__).resolve().parent / "svg_output"
for name in ("12_consume.svg", "12_consumption.svg", "p12.svg"):
    f = root / name
    if f.exists():
        f.unlink()

u = lambda *codes: "".join(chr(c) for c in codes)

title = u(0x77E5, 0x8BC6, 0x6D88, 0x8D39, 0xFF1A, 0x4ECE, 0x56FE, 0x8C31, 0x5230, 0x53EF, 0x64CD, 0x4F5C, 0x6D1E, 0x5BDF)
sub = u(0x56DB, 0x7C7B, 0x5165, 0x53E3, 0x5171, 0x7528, 0x540C, 0x4E00) + " Final KG " + u(0x67E5, 0x8BE2, 0x9762)
c1t = u(0x6570, 0x636E, 0x4E2D, 0x5FC3)
c1b = u(0x5168, 0x751F, 0x547D, 0x5468, 0x671F, 0x53EF, 0x89C6, 0x5316, 0x76D1, 0x63A7, 0x4E0E, 0x68C0, 0x7D22)
c2t = u(0x56FE, 0x8C31, 0x63A2, 0x7D22)
c2a = u(0x8282, 0x70B9, 0x805A, 0x7126) + " / " + u(0x5C42, 0x7EA7, 0x5C55, 0x5F00) + " / " + u(0x5173, 0x7CFB, 0x7B5B, 0x9009)
c2b = u(0x76F4, 0x89C2, 0x5448, 0x73B0, 0x8111, 0x533A) + "-" + u(0x8FDE, 0x63A5) + "-" + u(0x529F, 0x80FD, 0x62D3, 0x6251)
c3t = u(0x75C7, 0x72B6, 0x67E5, 0x8BE2)
c3a = u(0x81EA, 0x7136, 0x8BED, 0x8A00, 0x75C7, 0x72B6, 0x5230, 0x6807, 0x51C6, 0x5316, 0x8111, 0x533A, 0x4E0E, 0x56DE, 0x8DEF)
c3b = u(0x8F93, 0x51FA, 0x542B, 0x8BC1, 0x636E, 0x94FE, 0x7684, 0x7ED3, 0x6784, 0x5316, 0x62A5, 0x544A)
c4t = u(0x77E5, 0x8BC6, 0x5BFC, 0x51FA)
c4a = "JSONL / CSV / Neo4j " + u(0x7B49, 0x56FE, 0x5E93, 0x517C, 0x5BB9)
c4b = u(0x652F, 0x6301, 0x79BB, 0x7EBF, 0x6316, 0x6398, 0x4E0E, 0x8DE8, 0x5E73, 0x53F0, 0x8FC1, 0x79FB)

ff = "Microsoft YaHei, Arial, sans-serif"
parts = [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">',
    '  <g id="background"><rect width="1280" height="720" fill="#F7FAFC"/></g>',
    '  <g id="header">',
    f'    <text x="56" y="64" font-family="{ff}" font-size="34" font-weight="700" fill="#17324D">{title}</text>',
    f'    <text x="56" y="96" font-family="{ff}" font-size="16" fill="#5A6A7A">{sub}</text>',
    "  </g>",
    '  <g id="card-1">',
    '    <rect x="56" y="140" width="560" height="230" rx="10" fill="#FFFFFF" stroke="#CBD5E0"/>',
    '    <use data-icon="tabler-outline/database" x="84" y="168" width="32" height="32" stroke="#1F9FB5" fill="none" stroke-width="2"/>',
    f'    <text x="132" y="192" font-family="{ff}" font-size="22" font-weight="700" fill="#17324D">{c1t}</text>',
    f'    <text x="84" y="250" font-family="{ff}" font-size="17" fill="#243447">Raw - Candidate - Mirror - Final</text>',
    f'    <text x="84" y="290" font-family="{ff}" font-size="16" fill="#5A6A7A">{c1b}</text>',
    "  </g>",
    '  <g id="card-2">',
    '    <rect x="664" y="140" width="560" height="230" rx="10" fill="#FFFFFF" stroke="#CBD5E0"/>',
    '    <use data-icon="tabler-outline/network" x="692" y="168" width="32" height="32" stroke="#1F9FB5" fill="none" stroke-width="2"/>',
    f'    <text x="740" y="192" font-family="{ff}" font-size="22" font-weight="700" fill="#17324D">{c2t}</text>',
    f'    <text x="692" y="250" font-family="{ff}" font-size="17" fill="#243447">{c2a}</text>',
    f'    <text x="692" y="290" font-family="{ff}" font-size="16" fill="#5A6A7A">{c2b}</text>',
    "  </g>",
    '  <g id="card-3">',
    '    <rect x="56" y="400" width="560" height="230" rx="10" fill="#FFFFFF" stroke="#CBD5E0"/>',
    '    <use data-icon="tabler-outline/search" x="84" y="428" width="32" height="32" stroke="#1F9FB5" fill="none" stroke-width="2"/>',
    f'    <text x="132" y="452" font-family="{ff}" font-size="22" font-weight="700" fill="#17324D">{c3t}</text>',
    f'    <text x="84" y="510" font-family="{ff}" font-size="17" fill="#243447">{c3a}</text>',
    f'    <text x="84" y="550" font-family="{ff}" font-size="16" fill="#5A6A7A">{c3b}</text>',
    "  </g>",
    '  <g id="card-4">',
    '    <rect x="664" y="400" width="560" height="230" rx="10" fill="#FFFFFF" stroke="#CBD5E0"/>',
    '    <use data-icon="tabler-outline/database-export" x="692" y="428" width="32" height="32" stroke="#1F9FB5" fill="none" stroke-width="2"/>',
    f'    <text x="740" y="452" font-family="{ff}" font-size="22" font-weight="700" fill="#17324D">{c4t}</text>',
    f'    <text x="692" y="510" font-family="{ff}" font-size="17" fill="#243447">{c4a}</text>',
    f'    <text x="692" y="550" font-family="{ff}" font-size="16" fill="#5A6A7A">{c4b}</text>',
    "  </g>",
    '  <g id="footer"><text x="1224" y="696" text-anchor="end" font-family="Arial, sans-serif" font-size="12" fill="#8492A0">12</text></g>',
    "</svg>",
    "",
]
out = root / "12_consumption.svg"
out.write_bytes("\n".join(parts).encode("utf-8"))
print("wrote", out, out.stat().st_size)
print(out.read_text(encoding="utf-8").splitlines()[3])
