# Phase1.7 V3 - cortical target transform topology + inverse consistency re-audit

VERDICT: CORTICAL_TARGET_TRANSFORM_INTEGRITY_CONFIRMED
transform (immutable): TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1 | affine ff95a9fc7b843806... | forward 8bf90f3efdf7281b... | inverse 46366de37776c599...
Reporting correction: mean 0.7716 mm (correct); median 0.0175 mm (correct); any textual 'median 0.77 mm' was the mean -> REPORTING_CORRECTION_V1; history not edited.
Jacobian method A (ANTs official): full-field negative fraction 0.0, min 0.14194320142269135; brain-mask negative fraction 0.0, in-brain min 0.14194320142269135, median 0.874474287033081.
Jacobian method B (application finite-difference, 6000 brain points): negative fraction 0.0, min 0.31758448481559753, median 1.0548334121704102. methods consistent: True.
Earlier negative-Jacobian numbers (-2.51 min, 0.13%) were a raw-array numpy-gradient axis/component artifact (gate C), resolved: authoritative methods agree -> SyN warp is topology-preserving (diffeomorphic) with no brain-domain folding.
Displacement full-field mean/median/P95/max = 0.7715565392816398 / 0.01748558984068652 / 3.209405449145695 / 11.584011975037585 mm; fixed-brain mean/median/P95/max = 2.5472176683086745 / 2.1207851445607004 / 6.426571662010739 / 11.584011975037585 mm.
Nonpositive-Jacobian voxels: method A grid 0 (in-brain 0); method B sample 0.
Point roundtrip moving->fixed->moving P95 0.01357748541561625 mm (max 0.06206466988817306); fixed->moving->fixed P95 0.023203507696852633 mm.
Image roundtrip NCC (valid overlap) m->f->m 0.9995; f->m->f 0.9899.
Coverage 0.613 explanation: prior image inverse-roundtrip coverage 0.61298 is over the whole MOVING head/neck support (|moving>max*0.05| ~5.7 L) with a 20%-of-max content threshold; after two linear resamplings the low-intensity neck/CSF periphery falls below the threshold -> ~0.61 coverage over a huge denominator while the transform is geometrically accurate (point roundtrip P95 < 0.1 mm; valid-overlap NCC 0.895). It is a domain+threshold artifact of that image metric, not a transform inversion error; physical-point roundtrip is the authoritative inverse-consistency measure.
Global reflection: True (affine det sign 1.0).
NN smoke: forward moving-support nonempty True, fixed-brain coverage 1.0; inverse fixed-mask volume ratio 0.8639.
future binary ribbon = NearestNeighbor; future label application = ALLOWED (NearestNeighbor).
Guards: no registration rerun, no recipe/transform modification, no DK, no G4/Julich, no mapping results, no ribbon, no 62-target geometry, no FreeSurfer/license, no DB, no reclassification, no promotion.
route: CORTICAL_TARGET_PROJECT_DERIVED_TRANSFORM_FROZEN (c6281e8, kept) ; this round -> CORTICAL_TARGET_PROJECT_DERIVED_TRANSFORM_FROZEN + INTEGRITY_REAUDIT_PASS. c6281e8 snapshot untouched.

