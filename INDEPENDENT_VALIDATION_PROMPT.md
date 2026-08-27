# Independent CT/MRI Validation Prompt

You are performing an adversarial, independent audit of a longitudinal liver CT/MRI analysis. Do not assume the existing dashboards, lesion IDs, segment labels, contours, measurements, matches, activity estimates, or conclusions are correct.

## Safety and privacy

- Work locally. Do not upload DICOM files or patient-identifying information to external services.
- This is research/quality-assurance work, not a clinical diagnosis.
- Clearly distinguish facts, estimates, uncertainties, and findings requiring radiologist review.

## Required order of operations

1. Perform a blinded analysis from the source DICOMs.
2. Freeze and save your own lesion inventory, measurements, screenshots, and conclusions.
3. Only then inspect the existing dashboards and derived reports.
4. Compare your results against the existing work and actively search for errors. Do not agree merely because an existing result looks plausible.

## Source files

MRI archives:

- `/Users/omerkolodny/Downloads/DICOM (1).zip` — 18 Dec 2025
- `/Users/omerkolodny/Downloads/DICOM (3).zip` — 22 Jan 2026
- `/Users/omerkolodny/Downloads/AA026644IBP_1.2.840.113564.9.1.3037567216.90.2.4015014369130_sbwnza7df132_vcWduzAbP0KIyM-f-X_syA.zip` — 28 Apr 2026
- `/Users/omerkolodny/Downloads/AA026644IBP_1.2.840.113564.9.1.3037567216.90.2.4015014569642_sbwnza7df132_1e6hvV6mhEmUqt4949cZVg.zip` — 26 Aug 2026 (replacement archive; ZIP integrity verified)

CT archives:

- `/Users/omerkolodny/Downloads/AA026644IBP_1.2.840.113564.9.1.3037567216.90.2.4015014273274_sbwnza7df132_s1LsuCrb406-564Whv88kg.zip` — 26 Apr 2026
- `/Users/omerkolodny/Downloads/AA026644IBP_1.2.840.113564.9.1.3037567216.90.2.4015014601003_sbwnza7df132_w2bipV9lw0K91PF9G-rAog.1.zip` — 23 Aug 2026
- `/Users/omerkolodny/Downloads/DICOM.zip` and `/Users/omerkolodny/Downloads/DICOM (2).zip` — earlier CT material

Prepared local data:

- `/Users/omerkolodny/Downloads/dicom_analysis_2026-08-24/mri_longitudinal/`
- `/Users/omerkolodny/Downloads/dicom_analysis_2026-08-24/cross_modal/`
- `/Users/omerkolodny/Downloads/dicom_analysis_2026-08-24/web_app/`

Radiologist report—read only after the blinded analysis is frozen:

- `/Users/omerkolodny/Downloads/7a3d3dee-4ece-41fc-9827-cd1be0c455ad.pdf`

Public outputs—review only after the blinded pass:

- CT: https://omer-kolodny.github.io/liver-lesion-imaging-dashboard/
- CT explicit route: https://omer-kolodny.github.io/liver-lesion-imaging-dashboard/ct/
- MRI: https://omer-kolodny.github.io/liver-lesion-imaging-dashboard/mri/

## Required analysis

1. Verify every archive and series: ZIP structure, DICOM counts, missing/duplicate slices, spacing, orientation, dates, phases, sequences, and completeness. Explicitly verify whether the August MRI export contains DWI, ADC, and a separate axial late series.
2. Build an independent lesion inventory for every date. Separate hepatic lesions from nodes, vessels, kidneys, spleen, bowel, and false positives. Report a certain count, best working count, and uncertain candidates.
3. For every target, record series/slice, segment or extrahepatic location, boundary-anchored axial longest and perpendicular diameters, craniocaudal size, and 3D volume.
4. For longitudinal measurement, report both the conventional maximum axial diameter on each examination and a baseline-locked physical axis. Explain any difference from the existing calipers.
5. Match lesions using registration, anatomy, vessel landmarks, segment, shape, and appearance—not lesion numbering alone. Report confidence and evidence for every link.
6. Register the 23 Aug CT to the 26 Aug MRI. Classify every target as confirmed match, probable match, uncertain match, CT-only candidate, MRI-only candidate, merge, or split. Quantify global registration quality and local target error.
7. Specifically test whether the dominant structure near the porta hepatis/portocaval region is hepatic or extrahepatic.
8. Compare size, volume, enhancement, T2, DWI, and ADC only where genuinely available. Do not equate low CT attenuation with necrosis or claim a live/dead percentage without a validated method. Account for contrast timing and hemodynamics.
9. Run deterministic QA plus an independent segmentation/model repeat where possible. Visually inspect every contour and reject organ false positives.
10. After freezing your independent findings, compare them against the existing JSON, CSV, screenshots, PDF, 3D models, and finally the radiologist report.

## Existing findings to challenge

The revised analysis currently claims:

- 9 automatic hepatic CT components are retained on the latest CT. The structure formerly labelled as the automatic nodal target has been corrected to a partly exophytic segment II/III hepatic mass.
- A genuinely separate portocaval node exists, but no validated automatic contour is currently claimed for it.
- Automatic MRI contour counts vary by sequence and must not be treated as lesion counts or total disease burden.
- In the current multi-sequence audit, 5 of the 9 CT-anchored hepatic targets have an automatic contour on at least one MRI sequence; the others are not called absent.
- The real nodal target is not included in the automatic MRI volume or 3D model.
- Calipers terminate on the contour and report the maximum axial diameter plus a perpendicular chord on each examination. A separate locked-axis analysis may be used for sensitivity testing but is not substituted for conventional per-scan measurement.
- CT attenuation and MRI signal are treated as proxies rather than proof of viability or necrosis.
- Two radiologist-workstation screenshots show 15 manually segmented objects totaling 105.77 cc, but do not expose DICOM coordinates or target-to-lesion labels.

Reproduce or reject each claim independently.

## Deliverables

1. One-page plain-English bottom line.
2. Per-lesion table for every date.
3. CT↔MRI correspondence table with confidence and evidence.
4. False-positive, false-negative, merge, split, and questionable-segment list.
5. Measurement-line audit with corrected screenshots.
6. Quantitative comparison with the existing dashboards.
7. Comparison with the radiologist report performed only after the blinded pass.
8. Prioritized corrections labeled Critical, Important, or Cosmetic.
9. Exact software versions, commands, model names, and reproducibility notes.
10. Reliability verdict for lesion count, identity matching, diameters, volume, burden, CT attenuation, MRI diffusion, viability/necrosis proxy, and 3D visualization.
