"""Europe PMC OA XML → Section → Paragraph parser.

Rules:
  * Never flatten the whole article into one text blob.
  * Paragraph is the minimal verification unit.
  * paragraph_id prefers the XML node id; otherwise a stable composite
    ``section_slug_p{index:03d}_{text_hash_prefix}`` so re-parsing the same
    article yields identical ids.
  * Section titles are kept raw and also lightly normalized for priors.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET


SECTION_PRIORS = {
    "abstract": 0.08,
    "results": 0.15,
    "discussion": 0.10,
    "conclusion": 0.08,
    "introduction": 0.02,
    "methods": 0.05,
    "supplementary": 0.01,
    "other": 0.0,
}


def normalize_section_title(raw: str) -> str:
    title = re.sub(r"\s+", " ", raw or "").strip()
    lower = title.lower()
    if "abstract" in lower:
        return "Abstract"
    if "introduction" in lower or lower in ("background",):
        return "Introduction"
    if "method" in lower or "materials" in lower:
        return "Methods"
    if "result" in lower:
        return "Results"
    if "discussion" in lower:
        return "Discussion"
    if "conclusion" in lower or "summary" in lower:
        return "Conclusion"
    if "supplement" in lower or "appendix" in lower:
        return "Supplementary"
    return title or "Other"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return slug or "untitled"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _node_text(node: ET.Element) -> str:
    parts = [node.text or ""]
    for child in node:
        if _local(child.tag) not in ("sec", "title", "table-wrap", "fig"):
            parts.append(child.text or "")
            parts.append(child.tail or "")
        else:
            parts.append(child.tail or "")
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _text_hash_prefix(text: str, length: int = 8) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:length]


def _walk_sections(node: ET.Element, parent_section: str) -> list[tuple[str, str, ET.Element]]:
    """Return (raw_title, normalized_title, element) for every <p> inside sections."""
    found: list[tuple[str, str, ET.Element]] = []
    for child in list(node):
        tag = _local(child.tag)
        if tag == "p":
            found.append((parent_section, normalize_section_title(parent_section), child))
        elif tag == "sec":
            title_el = next((c for c in list(child) if _local(c.tag) == "title"), None)
            raw_title = "".join(title_el.itertext()).strip() if title_el is not None else ""
            nested = _walk_sections(child, raw_title or parent_section)
            found.extend(nested)
        elif tag == "body":
            found.extend(_walk_sections(child, parent_section))
        elif tag == "abstract":
            found.extend(_walk_sections(child, "Abstract"))
    return found


def parse_oa_xml(xml_text: str) -> list[dict]:
    """Parse OA XML into structured paragraphs (section-aware)."""
    paragraphs: list[dict] = []
    if not (xml_text or "").strip():
        return paragraphs
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = _walk_sections(root, "Other")
    char_offset = 0
    section_counts: dict[str, int] = {}
    for raw_title, norm_title, node in items:
        text_value = _node_text(node)
        if not text_value:
            continue
        node_id = (node.get("id") or "").strip()
        section_counts[norm_title] = section_counts.get(norm_title, 0) + 1
        idx = section_counts[norm_title] - 1
        if node_id:
            paragraph_id = node_id
        else:
            paragraph_id = f"{_slug(norm_title)}_p{idx + 1:03d}_{_text_hash_prefix(text_value)}"
        start = char_offset
        char_offset += len(text_value) + 1
        paragraphs.append(
            {
                "source_scope": "fulltext",
                "section_title": norm_title,
                "section_title_raw": raw_title,
                "paragraph_id": paragraph_id,
                "paragraph_index": len(paragraphs),
                "passage_text": text_value,
                "text_hash": hashlib.sha256(text_value.encode("utf-8")).hexdigest(),
                "locator": f"{_slug(norm_title)}:paragraph:{idx}",
                "char_start": start,
                "char_end": start + len(text_value),
            }
        )
    return paragraphs
