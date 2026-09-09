# Phase1.7 V3 - BNST geometry authority selection / precedence audit

Role A (ENTITY AUTHORITY): canonical admission already ADMIT_AS_CANONICAL_BRAINREGION (human identity, BNST_CANONICAL_ENTITY_ADMISSION_V1).

Role B (ANATOMICAL GEOMETRY AUTHORITY): PRIMARY_ANATOMICAL_GEOMETRY_AUTHORITY = Brandstetter/Juellich human cytoarchitectonic BST family; current repo representation = Julich-Brain v3.1 whole-BST L/R probability maps on MNI152NLin2009cAsym (dataset_doi 10.25493/KNSN-XB4).

Role C (CORROBORATING / CLINICAL GEOMETRY ASSET): CORROBORATING_CLINICAL_MRI_GEOMETRY = Theiss/Blackford 2017 (in-vivo MRI whole-BNST, n~10, MNI152NLin6Asym).

Provenance caveat: stored Julich-Brain v3.1 whole-BST (10.25493/KNSN-XB4) and Brandstetter 2026 BSTC/D/M/P (10.1162/IMAG.a.1260) are both in the Julich cytoarchitectonic BST family, but equivalence is NOT assumed; the 2026 subdivision set is NOT_ACQUIRED (metadata only).
Sibbach 2024 dBNST/vBNST: subdivision evidence only (NOT_ACQUIRED).

Guards: geometry construction NOT_STARTED; no NIfTI; no transform; no DB write; no Phase1.7 reclassification; no Basal Forebrain relation; no NGIQ-BR allocation; admission verdict unchanged; prior frozen Thalamus/Amygdala/Hippocampus outputs untouched.

