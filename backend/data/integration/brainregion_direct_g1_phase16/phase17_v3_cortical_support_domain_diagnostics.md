# Phase1.7 V3 - Brainnetome <-> FreeSurfer DK cortical support-domain compatibility audit
VERDICT: CORTICAL_CROSS_ATLAS_SUPPORT_DOMAIN_MISMATCH_CONFIRMED
BNA semantics: cortical parcel volumetric territory at 1mm in MNI space (surface-derived volumetric labels) (SEMANTICS_PARTIALLY_RESOLVED for tissue constraint)
full BNA cortical parcels = 210 (1..210); subcortical 211..246 (36). full DK cortical labels per side: lh 34 / rh 34; selected-62 per side 31; omitted DK per side {'left': ['bankssts', 'frontalpole', 'temporalpole'], 'right': ['bankssts', 'frontalpole', 'temporalpole']}.
decomposition (median over 170): outside_selected62 0.6485; inside_omitted_DK 0.0; outside_full_DK 0.6456.
tissue: BNA cortical union GM frac 0.64329; DK ribbon union GM 0.68586; selected62 GM 0.68289.
containment raw med/P25/P75 0.3217/0.2703/0.4055; GM-weighted med/P25/P75 0.3563/0.2898/0.4749; median improvement 0.0346; pearson 0.9695.
rank: raw rank1 170/170; GM-weighted rank1 170/170; rank changed 0.
outside-full-DK median GM frac 0.6086; distance median 1.732 mm P95 4.062 mm.
cross-route cortical COM delta 6.282 mm - DESCRIPTIVE ONLY, NOT a criterion: the two supports differ in thickness/extent so their COMs are not comparable.
support-domain-aware compatibility: optimal relative shift [0.0, 0.0, 0.0] mm (max 0.0 mm, tol 2.0); DK-in-BNA containment 0.9372 (min 0.9); excess-layer median distance 1.732 mm (max 2.5); dice at zero shift 0.51673 vs at optimum 0.51673 => SPATIALLY_COMPATIBLE.
support-domain offset: dilating the DK ribbon by 3 mm reproduces the BNA support at dice 0.8204 - a thickness/extent difference, not a displacement.
interpretability: raw containment DESCRIPTIVE_ONLY; outside-selected62 flag bias as reported in status.
V2 direct-spatial evidence immutable; no mapping/geometry/transform change; no registration; independent GM prior used (TemplateFlow official).

