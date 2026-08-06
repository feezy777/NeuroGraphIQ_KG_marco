-- 20260806_ontology_expand_vocab.sql (idempotent)
-- Move connection/circuit/step/triple enums into ontology_vocabularies and
-- remove the corresponding hardcoded CHECK constraints.

INSERT INTO ontology_vocabularies (code, vocab_type, label_en, seq) VALUES
('structural_connection','connection_type','structural_connection',10),
('functional_connectivity','connection_type','functional_connectivity',20),
('effective_connectivity','connection_type','effective_connectivity',30),
('projection','connection_type','projection',40),
('association','connection_type','association',50),
('coactivation','connection_type','coactivation',60),
('uncertain_connection','connection_type','uncertain_connection',70),
('unknown','connection_type','unknown',80),
('directed','directionality','directed',10),
('undirected','directionality','undirected',20),
('bidirectional','directionality','bidirectional',30),
('unknown','directionality','unknown',40),
('sensory_circuit','circuit_type','sensory_circuit',10),
('motor_circuit','circuit_type','motor_circuit',20),
('limbic_circuit','circuit_type','limbic_circuit',30),
('cognitive_control_circuit','circuit_type','cognitive_control_circuit',40),
('default_mode_related','circuit_type','default_mode_related',50),
('salience_related','circuit_type','salience_related',60),
('memory_related','circuit_type','memory_related',70),
('reward_related','circuit_type','reward_related',80),
('language_related','circuit_type','language_related',90),
('attention_related','circuit_type','attention_related',100),
('uncertain_circuit','circuit_type','uncertain_circuit',110),
('unknown','circuit_type','unknown',120),
('participant','circuit_region_role','participant',10),
('source','circuit_region_role','source',20),
('target','circuit_region_role','target',30),
('hub','circuit_region_role','hub',40),
('relay','circuit_region_role','relay',50),
('modulator','circuit_region_role','modulator',60),
('unknown','circuit_region_role','unknown',70),
('region','step_type','region',10),
('region_group','step_type','region_group',20),
('relay','step_type','relay',30),
('hub','step_type','hub',40),
('modulator','step_type','modulator',50),
('functional_stage','step_type','functional_stage',60),
('unknown','step_type','unknown',70),
('source','step_role','source',10),
('target','step_role','target',20),
('relay','step_role','relay',30),
('hub','step_role','hub',40),
('modulator','step_role','modulator',50),
('participant','step_role','participant',60),
('unknown','step_role','unknown',70),
('main_path','projection_role','main_path',10),
('feedback','projection_role','feedback',20),
('feedforward','projection_role','feedforward',30),
('modulatory','projection_role','modulatory',40),
('relay','projection_role','relay',50),
('parallel_branch','projection_role','parallel_branch',60),
('unknown','projection_role','unknown',70),
('same_granularity','triple_scope','same_granularity',10),
('cross_granularity_mapping','triple_scope','cross_granularity_mapping',20),
('evidence_link','triple_scope','evidence_link',30),
('unknown','triple_scope','unknown',40),
('region_candidate','triple_subject_type','region_candidate',10),
('region_final','triple_subject_type','region_final',20),
('connection','triple_subject_type','connection',30),
('circuit','triple_subject_type','circuit',40),
('function','triple_subject_type','function',50),
('term','triple_subject_type','term',60),
('literal','triple_subject_type','literal',70),
('unknown','triple_subject_type','unknown',80),
('region_candidate','triple_object_type','region_candidate',10),
('region_final','triple_object_type','region_final',20),
('connection','triple_object_type','connection',30),
('circuit','triple_object_type','circuit',40),
('function','triple_object_type','function',50),
('term','triple_object_type','term',60),
('literal','triple_object_type','literal',70),
('unknown','triple_object_type','unknown',80)
ON CONFLICT (code, vocab_type) DO NOTHING;

UPDATE mirror_region_connections SET connection_type='unknown'
WHERE connection_type NOT IN ('structural_connection','functional_connectivity','effective_connectivity','projection','association','coactivation','uncertain_connection','unknown');
UPDATE mirror_region_connections SET directionality='unknown'
WHERE directionality NOT IN ('directed','undirected','bidirectional','unknown');
UPDATE mirror_region_circuits SET circuit_type='unknown'
WHERE circuit_type NOT IN ('sensory_circuit','motor_circuit','limbic_circuit','cognitive_control_circuit','default_mode_related','salience_related','memory_related','reward_related','language_related','attention_related','uncertain_circuit','unknown');
UPDATE mirror_circuit_regions SET role='unknown'
WHERE role NOT IN ('participant','source','target','hub','relay','modulator','unknown');
UPDATE mirror_kg_triples SET subject_type='unknown'
WHERE subject_type NOT IN ('region_candidate','region_final','connection','circuit','function','term','literal','unknown');
UPDATE mirror_kg_triples SET object_type='unknown'
WHERE object_type NOT IN ('region_candidate','region_final','connection','circuit','function','term','literal','unknown');
UPDATE mirror_kg_triples SET triple_scope='unknown'
WHERE triple_scope NOT IN ('same_granularity','cross_granularity_mapping','evidence_link','unknown');
UPDATE mirror_circuit_steps SET step_type='unknown'
WHERE step_type NOT IN ('region','region_group','relay','hub','modulator','functional_stage','unknown');
UPDATE mirror_circuit_steps SET role='unknown'
WHERE role NOT IN ('source','target','relay','hub','modulator','participant','unknown');
UPDATE mirror_circuit_projection_memberships SET role_in_circuit='unknown'
WHERE role_in_circuit NOT IN ('main_path','feedback','feedforward','modulatory','relay','parallel_branch','unknown');

ALTER TABLE mirror_region_connections DROP CONSTRAINT IF EXISTS chk_mirror_connection_type;
ALTER TABLE mirror_region_connections DROP CONSTRAINT IF EXISTS chk_mirror_connection_directionality;
ALTER TABLE mirror_region_circuits DROP CONSTRAINT IF EXISTS chk_mirror_circuit_type;
ALTER TABLE mirror_circuit_regions DROP CONSTRAINT IF EXISTS chk_mirror_circuit_region_role;
ALTER TABLE mirror_kg_triples DROP CONSTRAINT IF EXISTS chk_mirror_triple_subject_type;
ALTER TABLE mirror_kg_triples DROP CONSTRAINT IF EXISTS chk_mirror_triple_object_type;
ALTER TABLE mirror_kg_triples DROP CONSTRAINT IF EXISTS chk_mirror_triple_scope;
ALTER TABLE mirror_circuit_steps DROP CONSTRAINT IF EXISTS chk_mirror_circuit_step_type;
ALTER TABLE mirror_circuit_steps DROP CONSTRAINT IF EXISTS chk_mirror_circuit_step_role;
ALTER TABLE mirror_circuit_projection_memberships DROP CONSTRAINT IF EXISTS chk_mirror_membership_role_in_circuit;
