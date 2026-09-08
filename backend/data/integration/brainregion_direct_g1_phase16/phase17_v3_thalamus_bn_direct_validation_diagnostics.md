# Phase1.7 V3 - Thalamus Brainnetome G3 direct spatial validation (DIAGNOSTIC)

EVIDENCE TYPE: DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME
NOT authoritative nonlinear-registration evidence; NOT proof of exact local
anatomical correspondence; NOT sufficient for automatic promotion.

G1 left sha  = bd431608fcea3c5f0f7387b1b0e1010582fa2e39dae95a300b3bba976a10cc87
G1 right sha = 73e4242b581f2420c316593f6cd85183ea7f99c29e2b817b0257cdf267c5bd3b
superseded G1 SHAs rejected: 37a82b65d86d... / 1c9b8b8de910...
spatial_bridge_id = SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1
registration_applied = FALSE; resampling_applied = TRUE
template_variant_uncertainty = PRESENT
residual limitation = TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED

HEMISPHERE left: total G1=9080.456mm3 BN-covered=8883.511mm3 uncovered=196.944mm3 union coverage=0.9783 top parcel=Tha_L_8_6 (G1 coverage 0.1716) nonzero-overlap parcels=8 contralateral=0.033276
HEMISPHERE right: total G1=9080.571mm3 BN-covered=8805.5mm3 uncovered=275.07mm3 union coverage=0.9697 top parcel=Tha_R_8_5 (G1 coverage 0.1798) nonzero-overlap parcels=8 contralateral=0.000327

Ranked parcels per hemisphere (by G1 coverage; continuous, no threshold band):
  left:
    1. Tha_L_8_6 vsG1=0.1716 vsBN=0.7167 dice=0.3475 dist=5.683
    2. Tha_L_8_1 vsG1=0.1637 vsBN=0.7466 dice=0.3321 dist=4.853
    3. Tha_L_8_5 vsG1=0.1561 vsBN=0.6840 dice=0.3146 dist=5.787
    4. Tha_L_8_4 vsG1=0.1225 vsBN=0.5384 dice=0.2419 dist=4.475
    5. Tha_L_8_8 vsG1=0.1222 vsBN=0.5252 dice=0.2408 dist=5.128
    6. Tha_L_8_7 vsG1=0.1206 vsBN=0.5959 dice=0.2505 dist=3.42
    7. Tha_L_8_3 vsG1=0.0774 vsBN=0.4682 dice=0.1603 dist=6.288
    8. Tha_L_8_2 vsG1=0.0191 vsBN=0.1232 dice=0.0394 dist=8.224
  right:
    1. Tha_R_8_5 vsG1=0.1798 vsBN=0.8150 dice=0.3628 dist=4.53
    2. Tha_R_8_1 vsG1=0.1608 vsBN=0.8098 dice=0.3214 dist=7.015
    3. Tha_R_8_8 vsG1=0.1525 vsBN=0.7834 dice=0.3124 dist=1.919
    4. Tha_R_8_6 vsG1=0.1318 vsBN=0.7280 dice=0.2762 dist=3.017
    5. Tha_R_8_2 vsG1=0.1032 vsBN=0.5191 dice=0.2050 dist=5.806
    6. Tha_R_8_7 vsG1=0.0862 vsBN=0.4691 dice=0.1781 dist=6.502
    7. Tha_R_8_3 vsG1=0.0833 vsBN=0.5754 dice=0.1724 dist=4.85
    8. Tha_R_8_4 vsG1=0.0558 vsBN=0.3042 dice=0.1126 dist=8.12

INTERPRETATION (SUPPORTIVE BUT NON-DECISIVE): all 16 corresponding Brainnetome thalamic parcels show non-zero/substantial spatial overlap with the whole-thalamus G1 geometry. overlap_ratio_vs_BN ranges from 0.30 to 0.82, with 7/16 parcels reaching >=0.70. Each parcel occupies only a fraction of G1 (overlap_ratio_vs_G1 0.02-0.18; union coverage 0.97-0.98), consistent with G1 being the whole thalami and the 8 connectivity zones tiling it.
Limitation explicitly preserved: TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED. This is DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME evidence only.
No categorical overlap bands / no new threshold; no DB write; no lifecycle/classification change; no promotion; no commit; diagnostic only.

