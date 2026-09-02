"""Phase 1F-B: documented e2e-only schema divergence for parity tests.

brain_region_aggregation_mappings gains a review lifecycle in E2E only
(gate7b_010). Production schema is frozen this round. Parity tests strip
these documented e2e-only additions before comparing, and a dedicated test
asserts the divergence is exactly this set.
"""

AGG_REVIEW_LIFECYCLE_E2E_ONLY = {
    "columns": {"review_status", "reviewed_by", "reviewed_at"},
    # the NOT NULL review_status column also auto-creates a not-null constraint
    "constraints": {
        "ck_agg_review_status",
        "ck_agg_rollup_requires_contained_in",
        "brain_region_aggregation_mappings_review_status_not_null",
    },
    "indexes": {"uq_agg_primary_rollup_active_approved"},
}


def strip_agg_review_divergence(sig):
    """Return a copy of a schema-signature dict with the documented e2e-only
    aggregation-mapping review-lifecycle additions removed (for prod<->e2e parity)."""
    out = dict(sig)
    meta = out.get("brain_region_aggregation_mappings")
    if meta is None:
        return out
    meta = dict(meta)
    meta["columns"] = [c for c in meta["columns"] if c[0] not in AGG_REVIEW_LIFECYCLE_E2E_ONLY["columns"]]
    meta["constraints"] = [c for c in meta["constraints"] if c[1] not in AGG_REVIEW_LIFECYCLE_E2E_ONLY["constraints"]]
    meta["indexes"] = [i for i in meta["indexes"] if i[0] not in AGG_REVIEW_LIFECYCLE_E2E_ONLY["indexes"]]
    out["brain_region_aggregation_mappings"] = meta
    return out
