# Phase1.7 V3 HISTORICAL_CONFLICT 对象级审计

VERIFIED=86  hist_conflict_exists=86
conflict_level={'SOURCE_LEVEL_SPATIAL': 45, 'G4_TO_G3': 41}
of_conflict_rows={'SOURCE_LEVEL_SPATIAL': 45, 'G4_TO_G3': 41}
g4_to_g3=41 source_level_spatial=45 direct_same_pair=0 unknown=0 not_affecting=86
demote_required=0  must_demote_ids=[]
family={'amygdala': {'SOURCE_LEVEL_SPATIAL': 22}, 'thalamic': {'G4_TO_G3': 33, 'SOURCE_LEVEL_SPATIAL': 23}, 'hippocampal': {'G4_TO_G3': 8}}

## 结论
- G4→G3 / source-level 历史记录不会因不同 relation pair 而否定当前 G4→G1 contained；
- 仅在出现 DIRECT_G1_PAIR（target==G1==current candidate）时才必须降级；
- 本审计不改动任何 classification（无降级执行）。