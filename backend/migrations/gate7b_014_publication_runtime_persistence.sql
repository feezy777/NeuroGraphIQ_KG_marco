-- Gate 7B Phase 3E.1B — Publication Discovery RUNTIME persistence
--
-- Three additive changes so the chain created by gate7b_013 can actually run:
--
--   1. a `source` ENTITY TYPE, so literature providers can be registered
--      honestly (see the note below — this is the one change that touches a
--      frozen vocabulary, and it is additive only)
--   2. four publication-database sources (PubMed / Europe PMC / OpenAlex /
--      Semantic Scholar)
--   3. idempotency guards for hits and for external identifiers
--
-- gate7b_013 is NOT modified: its SHA-256 is already in the migration ledger.
--
-- ===========================================================================
-- Why extending ck_kg_entities_entity_type is necessary and safe
-- ===========================================================================
-- The 3 existing `sources` rows are RETROFITTED onto entities that are not
-- sources at all:
--
--   NGIQ-SRC-00000001  -> entity NGIQ-ATL-00000001   (brain_region? no: atlas)
--   NGIQ-SRC-00000002  -> entity NGIQ-XREG-00000001  (external_region)
--   NGIQ-SRC-00000003  -> entity NGIQ-BR-00000001    (brain_region!)
--
-- That is not a modelling choice, it is the only thing the CHECK allowed:
-- `'source'` is absent from ck_kg_entities_entity_type, even though
-- `infra.next_ngiq_id` has carried a `'source' -> 'SRC'` mapping and
-- `infra.ngiq_src_seq` has existed since gate7b_002. The vocabulary was
-- designed for source entities and the constraint was never extended to match.
--
-- This migration therefore ADDS one value. Additive widening cannot invalidate
-- an existing row: all 2144 entities keep their type. It does not re-type the
-- three retrofitted rows (that is a data-migration decision, not this phase's).

ALTER TABLE kg_entities
    DROP CONSTRAINT IF EXISTS ck_kg_entities_entity_type;

ALTER TABLE kg_entities
    ADD CONSTRAINT ck_kg_entities_entity_type CHECK (entity_type IN (
        'brain_region', 'cellular_neural_structure', 'neurobiological_process',
        'connection', 'circuit', 'function', 'neurotransmitter', 'receptor',
        'gene', 'disease', 'symptom', 'research_study', 'publication',
        'evidence', 'atlas', 'external_region', 'region_mapping',
        'circuit_connection_membership',
        -- gate7b_014: a registry source (database / literature provider) is a
        -- first-class entity in its own right. Without this, registering one
        -- honestly is impossible and it gets retrofitted onto a brain region.
        'source'
    ));

-- ===========================================================================
-- Publication-database sources
-- ===========================================================================
-- source_type 'publication_database' is already in ck_sources_source_type, so
-- no vocabulary change is needed here. `record_status='active'` requires a
-- bilingual name and explicit name sources, both of which we have.
--
-- Deterministic ids (not infra.next_ngiq_id) so re-running is idempotent
-- instead of burning sequence values.
INSERT INTO kg_entities
    (entity_id, entity_type, name_en, name_zh, name_en_source, name_zh_source,
     source_name_original, record_status)
VALUES
    ('NGIQ-SRC-00000004', 'source', 'PubMed', 'PubMed 文献数据库',
     'human_curated', 'translated_human', 'NCBI', 'active'),
    ('NGIQ-SRC-00000005', 'source', 'Europe PMC', 'Europe PMC 文献数据库',
     'human_curated', 'translated_human', 'EMBL-EBI', 'active'),
    ('NGIQ-SRC-00000006', 'source', 'OpenAlex', 'OpenAlex 学术图谱',
     'human_curated', 'translated_human', 'OurResearch', 'active'),
    ('NGIQ-SRC-00000007', 'source', 'Semantic Scholar', 'Semantic Scholar 学术图谱',
     'human_curated', 'translated_human', 'Allen Institute for AI', 'active')
ON CONFLICT (entity_id) DO NOTHING;

INSERT INTO sources
    (source_pk, source_id, name_en, name_zh, source_type, provider, url, api_url,
     record_status, description_en)
SELECT k.entity_pk, k.entity_id, k.name_en, k.name_zh, v.source_type, v.provider,
       v.url, v.api_url, 'active', v.description_en
FROM (VALUES
    ('NGIQ-SRC-00000004', 'publication_database', 'NCBI',
     'https://pubmed.ncbi.nlm.nih.gov/',
     'https://eutils.ncbi.nlm.nih.gov/entrez/eutils',
     'Biomedical literature index. Retrieval provenance source.'),
    ('NGIQ-SRC-00000005', 'publication_database', 'EMBL-EBI',
     'https://europepmc.org/',
     'https://www.ebi.ac.uk/europepmc/webservices/rest',
     'Life-science literature with abstracts and OA full text.'),
    ('NGIQ-SRC-00000006', 'publication_database', 'OurResearch',
     'https://openalex.org/',
     'https://api.openalex.org/works',
     'Scholarly works graph; identifiers also recorded via entity_xrefs.'),
    ('NGIQ-SRC-00000007', 'publication_database', 'Allen Institute for AI',
     'https://www.semanticscholar.org/',
     'https://api.semanticscholar.org/graph/v1',
     'Scholarly graph; identifiers also recorded via entity_xrefs.')
) AS v(entity_id, source_type, provider, url, api_url, description_en)
JOIN kg_entities k ON k.entity_id = v.entity_id
ON CONFLICT (source_id) DO NOTHING;

-- ===========================================================================
-- Hit idempotency (a retry must not duplicate the same retrieval provenance)
-- ===========================================================================
-- Identity of "the same hit" = which run found which publication, through
-- which source, by which query, at which rank.
--
-- NULLS NOT DISTINCT (PostgreSQL 15+) so two hits that both lack a run or a
-- source still collide instead of silently escaping the guard: with the default
-- NULLS DISTINCT every NULL would make the row unique and the index a no-op.
--
-- NOT included: query_family / query_level. Those DESCRIBE the query rather
-- than identify it; the same query_text reached under two labels is one hit.
CREATE UNIQUE INDEX IF NOT EXISTS uq_pdh_hit_identity
    ON publication_discovery_hits
       (discovery_run_pk, publication_pk, source_pk, query_text, result_rank)
    NULLS NOT DISTINCT;

-- ===========================================================================
-- External identifier idempotency (entity_xrefs)
-- ===========================================================================
-- Audited clean before adding: 0 duplicate (entity_pk, source_database,
-- external_id) groups across 246 rows.
CREATE UNIQUE INDEX IF NOT EXISTS uq_entity_xrefs_identity
    ON entity_xrefs (entity_pk, lower(btrim(source_database)), btrim(external_id))
    WHERE source_database IS NOT NULL AND external_id IS NOT NULL;
