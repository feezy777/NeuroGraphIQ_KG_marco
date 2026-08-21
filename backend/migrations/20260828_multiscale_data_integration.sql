-- 20260828_multiscale_data_integration.sql
-- BR4: external data integration (Brainnetome BNA246 / HCP-MMP / Winterburn /
-- Allen Cell Types / GTEx brain). Adds laterality to canonical brain regions
-- (hemisphere info lives in the laterality field — no left_*/right_* entities)
-- and registers the two remaining atlas resources.
--
-- Must sort AFTER 20260822_canonical_brain_region.sql / 20260827_multiscale_atlas_layer.sql.

ALTER TABLE canonical_brain_regions
    ADD COLUMN IF NOT EXISTS laterality VARCHAR(32) NOT NULL DEFAULT 'bilateral';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_canonical_region_laterality'
    ) THEN
        ALTER TABLE canonical_brain_regions
            ADD CONSTRAINT chk_canonical_region_laterality
            CHECK (laterality IN ('bilateral', 'left', 'right', 'midline_unpaired', 'unknown'));
    END IF;
END $$;

-- Atlas resource registrations (data source registry; see docs/MULTISCALE_BRAIN_ONTOLOGY_DATA_SOURCES.md)
INSERT INTO atlas_resources (
    resource_code, source_atlas, source_version, resource_type, species,
    granularity_level, granularity_family, template_space,
    cn_name, en_name, description, remark, status
) VALUES
('hcp_mmp_glasser',
 'HCP MMP1.0 (Glasser 2016)', 'MMP1.0 360-parcel', 'label_table', 'human',
 'meso', 'meso_anatomical', 'MNI152',
 'HCP 多模态脑分区 1.0 (Glasser 2016)',
 'Human Connectome Project Multi-Modal Parcellation 1.0',
 '360 cortical parcels (180 bilateral areas; glasser360NodeNames.txt from the official MMP1.0 release). No gyrus/parent info in the name file — hierarchy attaches parcels to cerebrum (honest limitation, see data sources doc).',
 'Region names contain hyphens (e.g. 9-46d) — canonical region_code normalizes hyphen to underscore (ng:br:mmp_9_46d_l).', 'active'),
('gtex_brain_expression',
 'GTEx Brain', 'v10 bulk-gex TPM', 'atlas', 'human',
 'molecular', 'molecular_attr', 'native',
 'GTEx 脑组织基因表达 (v10)',
 'GTEx Brain tissue gene expression (v10 TPM)',
 '13 brain tissues from the GTEx v10 bulk-gex TPM release (adult-gtex storage bucket). Top expressed genes per tissue become molecular entities + region_molecular_alignment (evidence_type=expression).',
 'Only tissues with a clear 1:1 canonical region are aligned; others are documented as unaligned.', 'active')
ON CONFLICT (resource_code) DO NOTHING;
