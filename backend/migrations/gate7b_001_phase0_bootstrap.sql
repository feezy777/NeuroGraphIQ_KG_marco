-- Gate 7B Phase 0 — database bootstrap / migration infrastructure.
--
-- NOTE: this migration does NOT create the database itself. The database
-- (neurographiq_human_brain_v1 / _e2e) is created by the admin-level bootstrap
-- script (backend/scripts/bootstrap_human_brain_v1.py) against the maintenance
-- database, because CREATE DATABASE cannot run inside an in-database migration
-- transaction against a not-yet-existing target.
--
-- This migration only sets up in-database infrastructure:
--   1. infra schema
--   2. infra.schema_migrations (migration tracking — single canonical definition)
--   3. per-type NGIQ public-ID sequences (from the frozen prefix registry)
--
-- It does NOT create any frozen scientific table (Phase 1+).

CREATE SCHEMA IF NOT EXISTS infra;

CREATE TABLE IF NOT EXISTS infra.schema_migrations (
    migration_id    TEXT PRIMARY KEY,
    filename        TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    execution_ms    BIGINT,
    status          TEXT NOT NULL,
    remark          TEXT
);

COMMENT ON TABLE infra.schema_migrations IS
    'Gate 7B migration tracking (infra schema — not a scientific table).';
COMMENT ON COLUMN infra.schema_migrations.status IS
    'APPLIED only in Phase 0.';

-- ---------------------------------------------------------------------------
-- NGIQ public-ID sequences (per-type, from frozen prefix registry:
-- ontology/review/gate_07b_a1/05_ngiq_prefix_registry.md).
-- Format: NGIQ-<TYPE>-<8 digits>; nextval() supplies the numeric part only.
-- START 1 / INCREMENT 1 / NO CYCLE; public IDs are never reused.
-- ---------------------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_br_seq    START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_cns_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_nbp_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_con_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_cob_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_cir_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_fun_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_nt_seq    START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_rcp_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_gen_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_dis_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_sym_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_stu_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_pub_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_evi_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_atl_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_xreg_seq  START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_rmap_seq  START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_ccm_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_crm_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_brh_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_fhr_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_bram_seq  START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_ast_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_pred_seq  START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_elk_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_src_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_als_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_xrf_seq   START WITH 1 INCREMENT BY 1 NO CYCLE;
