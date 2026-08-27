"""Generate Function hierarchy candidate edges (O1.3-A batch runner).

Usage:
    python -m scripts.generate_function_hierarchy_candidates [--dry-run] [--top-k 10]

Runs the deterministic candidate generation on ALL function terms in
ontology_terms, writes results to ontology_hierarchy_candidates, and
outputs a statistics report.

--dry-run:  build index + compute candidates but do NOT persist to DB
--top-k N:  max parent candidates per child term (default 10)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure backend root is on sys.path for imports
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from app.database import AsyncSessionLocal
from app.services import function_hierarchy_candidate_service as fhcs


async def main(*, dry_run: bool = False, top_k: int = 10) -> None:
    print("=" * 60)
    print("Function Hierarchy Candidate Generation (O1.3-A)")
    print("=" * 60)

    async with AsyncSessionLocal() as session:
        print("\n[1/4] Loading term index ...")
        idx = await fhcs.load_term_index(session, include_proposed=True)
        print(f"  Loaded {len(idx.terms)} function terms")
        print(f"  Terms with usage data: {len(idx.usage_subjects)}")
        print(f"  Synonym mappings: {len(idx.synonym_keys)}")

        # Category distribution
        by_category: dict[str, int] = {}
        by_domain: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for t in idx.terms.values():
            cat = t.category or "(none)"
            dom = t.domain or "(none)"
            by_category[cat] = by_category.get(cat, 0) + 1
            by_domain[dom] = by_domain.get(dom, 0) + 1
            by_status[t.status] = by_status.get(t.status, 0) + 1

        print(f"\n  Status distribution: {dict(by_status)}")
        print(f"  Top categories: {dict(list(sorted(by_category.items(), key=lambda x: -x[1]))[:10])}")
        print(f"  Top domains: {dict(list(sorted(by_domain.items(), key=lambda x: -x[1]))[:10])}")

        # Category grouping
        print("\n[2/4] Building category-group parents ...")
        cat_parents = fhcs._category_group_parents(idx)
        print(f"  Category-group hubs: {len(set(cat_parents.values()))}")
        print(f"  Category-group members: {len(cat_parents)}")

        if dry_run:
            print("\n[DRY RUN] Skipping DB writes.")
            # Quick sample: generate for first 100 terms
            sample = list(idx.terms.keys())[:100]
            total_cands = 0
            no_reason: dict[str, int] = {}
            for tid in sample:
                child = idx.terms[tid]
                cands, reason = fhcs.generate_candidates_for_term(
                    child, idx, top_k=top_k, _category_parents=cat_parents,
                )
                total_cands += len(cands)
                if reason:
                    no_reason[reason] = no_reason.get(reason, 0) + 1
            print(f"\n  Sample (100 terms): {total_cands} candidates generated")
            print(f"  No-candidate reasons: {no_reason}")
            return

        print("\n[3/4] Generating candidates for ALL terms ...")
        result = await fhcs.generate_all_candidates(
            session,
            top_k=top_k,
            include_proposed=True,
            created_by="batch_script",
        )
        await session.commit()

        print(f"\n[4/4] Results:")
        print(f"  Generation version: {result['generation_version']}")
        print(f"  Total function terms: {result['total_function_terms']}")
        print(f"  Term status: {result['term_status_distribution']}")
        print(f"  Total candidates generated: {result['total_candidates_generated']}")
        print(f"  Children with candidates: {result['children_with_candidates']}")
        print(f"  Children without candidates: {result['children_without_candidates']}")
        print(f"  Category-group hubs: {result['category_group_hubs']}")
        print(f"  Category-group members: {result['category_group_members']}")

        print(f"\n  Method distribution:")
        for method, count in sorted(result["method_distribution"].items(), key=lambda x: -x[1]):
            print(f"    {method}: {count}")

        print(f"\n  Score histogram:")
        for bucket, count in result["score_histogram"].items():
            bar = "#" * min(count // 10, 60)
            print(f"    {bucket:>8s}: {count:>5d} {bar}")

        print(f"\n  No-candidate reasons:")
        for reason, count in sorted(result["no_candidate_reasons"].items(), key=lambda x: -x[1]):
            print(f"    {reason}: {count}")

        print(f"\n  Top categories (terms):")
        for cat, count in list(result["term_category_distribution"].items())[:15]:
            print(f"    {cat}: {count}")

        print(f"\n  Top domains (terms):")
        for dom, count in list(result["term_domain_distribution"].items())[:10]:
            print(f"    {dom}: {count}")

        integrity = result["integrity"]
        print(f"\n  Integrity audit:")
        issues = []
        for k, v in integrity.items():
            if k != "total" and v > 0:
                issues.append(f"{k}={v}")
        if issues:
            print(f"    ISSUES: {', '.join(issues)}")
        else:
            print(f"    All clean (total={integrity['total']})")

        # Write JSON report
        report_dir = Path(_backend) / "data" / "exports" / "hierarchy_candidates"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "function_hierarchy_candidate_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str, ensure_ascii=False)
        print(f"\n  Report written to: {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate function hierarchy candidates")
    parser.add_argument("--dry-run", action="store_true", help="Don't persist to DB")
    parser.add_argument("--top-k", type=int, default=10, help="Max parents per term")
    args = parser.parse_args()

    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(dry_run=args.dry_run, top_k=args.top_k))
