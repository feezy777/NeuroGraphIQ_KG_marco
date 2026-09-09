# Phase1.7 V3 - Brainnetome <-> FreeSurfer DK cortical support-domain compatibility audit
VERDICT: CORTICAL_CROSS_ATLAS_TRANSFORM_COMPATIBILITY_FAILED
BNA semantics: cortical parcel volumetric territory at 1mm in MNI space (surface-derived volumetric labels) (SEMANTICS_PARTIALLY_RESOLVED for tissue constraint)
full BNA cortical parcels = 210 (1..210); subcortical 211..246 (36). full DK cortical labels per side: lh 34 / rh 34; selected-62 per side 31; omitted DK per side {'left': ['bankssts', 'frontalpole', 'temporalpole'], 'right': ['bankssts', 'frontalpole', 'temporalpole']}.
decomposition (median over 170): outside_selected62 0.6485; inside_omitted_DK 0.0; outside_full_DK 0.6456.
tissue: BNA cortical union GM frac 0.64329; DK ribbon union GM 0.68586; selected62 GM 0.68289.
containment raw med/P25/P75 0.3217/0.2703/0.4055; GM-weighted med/P25/P75 0.3563/0.2898/0.4749; median improvement 0.0346; pearson 0.9695.
rank: raw rank1 170/170; GM-weighted rank1 170/170; rank changed 0.
outside-full-DK median GM frac 0.6086; distance median 1.732 mm P95 4.062 mm.
cross-route COM delta 6.282 mm; systemic shift evidence True.
interpretability: raw containment INVALID_FOR_ADJUDICATION; outside-selected62 flag bias as reported in status.
V2 direct-spatial evidence immutable; no mapping/geometry/transform change; no registration; independent GM prior used (TemplateFlow official).

