# Phase1.7 V3 - Thalamus probability semantics + aggregation rule audit

verdict = GEOMETRY_RULE_BLOCKED_BY_ONTOLOGY_SCOPE
probability_aggregation_semantics = RESOLVED
probability_aggregation_operator = SUM
aggregation_rule_status = FROZEN_AT_PROBABILITY_LAYER
g1_scope_status = ONTOLOGY_SCOPE_INCOMPLETE
geometry_construction_status = BLOCKED_BY_ONTOLOGY_SCOPE
construction_allowed = False
sum_applicability: SUM applies only to the mutually-exclusive nucleus channels included in the same G1 Thalamus once INCLUDED_CHANNELS is frozen: P_G1(x)=sum_i P_i(x), i in INCLUDED_CHANNELS. MAX: not applicable. PROBABILISTIC_UNION: not applicable (not independent Bernoulli). CLIPPED_SUM: numerically == SUM here; not a separate operator.
semantics = MUTUALLY_EXCLUSIVE_CATEGORICAL_NORMALIZED_POSTERIOR
channels = 53 (expected 53)  L=26 R=26 bg=1
raw sha256 = 640377ae93cf0782365a698573970c2a429a775c6f64dcf9ac02536156b51f22  freeze_match=True
Iglesias DOI (corrected) = 10.1016/j.neuroimage.2018.08.012
Julich reference shape = 193 x 229 x 193 (1 mm)
sum(all 53 channels): min/median/max = 0.9999999469146132/1.0/1.0000000521540642
frac S_nuc >1 = 0.00000  frac S_nuc ==1 = 0.05459
frac S_nuc ==0 = 0.79362
background==1-sum(nuc) frac = 1.00000
laterality QC ok = True
no geometry constructed; construction BLOCKED by ontology scope (INCLUDED_CHANNELS not frozen); SUM is the frozen probability-layer operator

provenance:
- Iglesias 2018 official paper (26 nuclei, Bayesian)
- FS wiki ThalamicNuclei / SubfieldAtlasesICBMspace
- raw sha256 640377ae93cf0782365a698573970c2a429a775c6f64dcf9ac02536156b51f22
- names.txt channel metadata (same release zip)
- data-verified categorical posterior (sum==1)
- inclusion/exclusion per channel table
- aggregation operator audit (SUM/MAX/UNION/CLIP)
- verdict = GEOMETRY_RULE_BLOCKED_BY_ONTOLOGY_SCOPE (probability layer RESOLVED / SUM; ontology scope INCOMPLETE)

DOI correction:
- old=10.1016/j.neuroimage.2018.06.012 -> new=10.1016/j.neuroimage.2018.08.012 (2018.06.012 is not the Iglesias thalamic-nuclei atlas DOI; the correct DOI for Iglesias et al., 'A probabilistic atlas of the human thalamic nuclei combining ex vivo MRI and histology', NeuroImage 183 (2018):314-326 is 2018.08.012)

