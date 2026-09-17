-- Gate 7B P0-5A — durable forensic metadata for a Discovery response
--
-- Closes DISCOVERY_FAILED_RAW_RESPONSE_AUDIT_GAP.
--
-- WHY THIS EXISTS
--   Round 21 failed with an envelope-shape parse error and the response that
--   caused it was not kept: the run retained error_code and a 500-character
--   error_message and nothing else. Whether the model really emitted a bare
--   RegionCandidate, or the extractor handed one back in place of the document,
--   is STILL unprovable — the evidence never reached storage. A failure nobody
--   can look at afterwards is a failure that will happen again.
--
-- WHAT IS STORED
--   Bounded provider-response evidence, on BOTH terminal paths: what came back
--   (bounded preview + SHA-256 of the FULL text), how it ended (finish_reason),
--   what it cost (prompt/completion/total tokens), how long it took, and whether
--   the text was a fallback raw-body dump rather than model content. "Did we see
--   this exact response before?" is then a GROUP BY on response_sha256.
--
-- WHAT IS DELIBERATELY NOT STORED
--   The full response. This is a diagnostic breadcrumb, not a second candidate
--   store, and not an archive. The preview bound is enforced HERE as well as in
--   code: a future caller cannot widen it by forgetting to truncate.
--   No request payload, header, credential or environment value has a column.
--
-- NULL SEMANTICS (load-bearing)
--   Every column is nullable and NULL means "there is nothing truthful to
--   record". response_sha256 is NULL — NOT the hash of an empty string — when
--   the provider produced no content, because "said nothing" and "said the empty
--   string" are different facts. Historical rows keep NULL: the Round-21
--   response does not exist, and back-filling it from the truncated
--   error_message would manufacture evidence.
--
-- Idempotent: every statement is re-runnable (ADD COLUMN IF NOT EXISTS, DROP
-- CONSTRAINT IF EXISTS before ADD CONSTRAINT).

-- ===========================================================================
-- 1. the columns
-- ===========================================================================
ALTER TABLE knowledge_discovery_runs
    ADD COLUMN IF NOT EXISTS response_sha256 VARCHAR(64);
ALTER TABLE knowledge_discovery_runs
    ADD COLUMN IF NOT EXISTS raw_response_preview TEXT;
ALTER TABLE knowledge_discovery_runs
    ADD COLUMN IF NOT EXISTS finish_reason VARCHAR(32);
ALTER TABLE knowledge_discovery_runs
    ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER;
ALTER TABLE knowledge_discovery_runs
    ADD COLUMN IF NOT EXISTS completion_tokens INTEGER;
ALTER TABLE knowledge_discovery_runs
    ADD COLUMN IF NOT EXISTS total_tokens INTEGER;
ALTER TABLE knowledge_discovery_runs
    ADD COLUMN IF NOT EXISTS provider_latency_ms INTEGER;
ALTER TABLE knowledge_discovery_runs
    ADD COLUMN IF NOT EXISTS fallback_raw_response_used BOOLEAN;

-- ===========================================================================
-- 2. the invariants storage refuses to break
-- ===========================================================================
-- A SHA-256 is 64 lowercase hex characters or it is not a SHA-256. The column
-- is a fingerprint other rows are compared against, so a malformed value would
-- silently poison every "same response?" comparison built on it.
ALTER TABLE knowledge_discovery_runs
    DROP CONSTRAINT IF EXISTS ck_kdr_response_sha256_format;
ALTER TABLE knowledge_discovery_runs
    ADD CONSTRAINT ck_kdr_response_sha256_format
        CHECK (response_sha256 IS NULL OR response_sha256 ~ '^[0-9a-f]{64}$');

-- The preview bound lives in storage too. 2048 = the 2000-character preview
-- limit plus the longest truncation marker the shared helper appends
-- ("…[truncated N chars]"), so the code can use the existing helper unchanged
-- while the column still cannot grow without bound.
ALTER TABLE knowledge_discovery_runs
    DROP CONSTRAINT IF EXISTS ck_kdr_raw_preview_bounded;
ALTER TABLE knowledge_discovery_runs
    ADD CONSTRAINT ck_kdr_raw_preview_bounded
        CHECK (raw_response_preview IS NULL OR length(raw_response_preview) <= 2048);

ALTER TABLE knowledge_discovery_runs
    DROP CONSTRAINT IF EXISTS ck_kdr_token_counts_non_negative;
ALTER TABLE knowledge_discovery_runs
    ADD CONSTRAINT ck_kdr_token_counts_non_negative
        CHECK (
            (prompt_tokens IS NULL OR prompt_tokens >= 0)
            AND (completion_tokens IS NULL OR completion_tokens >= 0)
            AND (total_tokens IS NULL OR total_tokens >= 0)
        );

ALTER TABLE knowledge_discovery_runs
    DROP CONSTRAINT IF EXISTS ck_kdr_provider_latency_non_negative;
ALTER TABLE knowledge_discovery_runs
    ADD CONSTRAINT ck_kdr_provider_latency_non_negative
        CHECK (provider_latency_ms IS NULL OR provider_latency_ms >= 0);

-- ===========================================================================
-- 3. what each column means
-- ===========================================================================
COMMENT ON COLUMN knowledge_discovery_runs.response_sha256 IS
    'SHA-256 of the COMPLETE raw provider text, lowercase hex. NULL when the provider produced no '
    'content (never the hash of the empty string). Two runs with the same value had byte-identical '
    'responses — the one comparison a bounded preview cannot make.';

COMMENT ON COLUMN knowledge_discovery_runs.raw_response_preview IS
    'Bounded prefix (<=2000 data characters, plus a truncation marker) of what the provider returned. '
    'Diagnostic only: never a candidate store, never an archive, never request secrets.';

COMMENT ON COLUMN knowledge_discovery_runs.finish_reason IS
    'The provider''s own stop reason for this call, e.g. "length" when the output budget ran out. '
    'This is what distinguishes a truncated answer from an empty one.';

COMMENT ON COLUMN knowledge_discovery_runs.provider_latency_ms IS
    'Provider call duration in milliseconds, as reported by the provider layer.';

COMMENT ON COLUMN knowledge_discovery_runs.fallback_raw_response_used IS
    'TRUE when the stored text is a salvaged raw HTTP body rather than assistant content. A raw-body '
    'dump is never parsed as a discovery result, so this flag is how a future reader tells them apart.';
