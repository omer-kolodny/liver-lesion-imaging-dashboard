# Independent audit and workstation screenshot reconciliation

Reviewed 27 Aug 2026. This is software quality assurance, not a radiologist-signed diagnosis.

## Corrections accepted and applied

- The former `L01` extrahepatic-node label was incorrect. The tracked structure is a partly exophytic segment II/III hepatic mass and is included in liver-lesion burden.
- The actual portocaval node is a separate target. It is not assigned an automatic volume or 3D contour because the liver-restricted model did not segment it reliably.
- CT liver-lesion totals were restored to 166.82, 170.34, 97.64 and 46.56 mL. January-to-August automated volume change is -72.7%.
- CT contrast delays were corrected to 174.4 s, 131.8 s and 131.9 s for January, April and August. January attenuation comparisons are therefore explicitly qualified.
- The complete August MRI archive is used, including late T1, DWI b=800, ADC, T2 fat-sat and all dynamic phases.
- The MRI 3D model now contains nine CT-anchored hepatic targets. Five have automatic support on at least one MRI sequence. Missing MRI contours are not interpreted as disappeared lesions.
- Zero-volume placeholders for undetected lesions were changed to missing values.
- MRI automatic contour volume is presented as quality-control output, not total disease burden.

## Claims accepted only with qualification

- The imaging direction is favorable and compatible with treatment response, but software alone cannot establish treatment success.
- DWI/ADC findings support reduced diffusion restriction in sampled regions, but cannot provide a validated percentage of living or dead tumor.
- Automated volumes are model-dependent. The primary and independent August CT pipelines estimate 46.56 and 55.54 mL respectively.

## Radiologist-workstation screenshot transcription

The screenshots display 15 segmented objects totaling 105.77 cc:

| Target | Volume (cc) | Workstation display |
|---|---:|---|
| T1 | 37.17 | 77.93 ± 77.93 HU |
| T2 | 0.38 | 75.6 ± 75.6 HU |
| T3 | 0.10 | 50.8 ± 50.8 HU |
| T4 | 23.80 | 72.56 ± 72.56 HU |
| T5 | 0.24 | 79.63 ± 79.63 HU |
| T6 | 1.25 | 89.29 ± 89.29 HU |
| T7 | 21.26 | 55.82 ± 55.82 HU |
| T8 | 1.63 | 70.19 ± 70.19 HU |
| T9 | 0.19 | 63 ± 63 HU |
| T10 | 0.07 | 59.17 ± 59.17 HU |
| T11 | 0.93 | 101.48 ± 101.48 HU |
| T12 | 2.34 | 95.65 ± 95.65 HU |
| T13 | 15.33 | 73.71 ± 73.71 HU |
| T14 | 0.21 | 87.01 ± 87.01 HU |
| T15 | 0.87 | 81.84 ± 81.84 HU |

The scan date is not visible. April 2026 is the leading inference because T1 (37.17 cc) closely matches the April automatic segment VIII contour (37.621 mL), and the total is closest to the independent April estimate. This inference is not treated as confirmed.

The repeated `mean ± SD` values are suspicious because every displayed standard deviation exactly equals its mean. They are retained as literal screenshot transcription and are not used for viability analysis.

## Still required for exact reconciliation

1. The Philips DICOM SEG, RTSTRUCT, or labelled contour export corresponding to T1–T15.
2. Confirmation of the acquisition date represented by the screenshots.
3. A target-name/segment key for T1–T15.
4. A validated contour for the true portocaval node.
5. Complete re-downloads of the remaining truncated CT/MRI archives before claiming a final lesion count or definitive volumetric trend.
