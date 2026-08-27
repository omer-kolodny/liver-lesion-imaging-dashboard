# RadioLens competitive and clinical-readiness analysis

Research date: 27 August 2026

## Executive conclusion

RadioLens already covers an unusually broad prototype surface: DICOM ingestion, automated liver/lesion segmentation, longitudinal measurements, tumor burden, lesion-level images, interactive 3D, PDF/CSV output, and repeat-model plus registration evidence. Its presentation is ahead of many research prototypes.

It is **not yet possible to claim accuracy on par with clinical commercial systems**. The largest gap is not another visualization. It is a radiologist-in-the-loop validation workflow, standards-aware response assessment, DICOM-native interoperability, and a multi-patient benchmark that measures detection failures as well as contour overlap.

## What comparable products provide

| Product / category | Publicly described capabilities | RadioLens implication |
|---|---|---|
| [mint Lesion](https://mint-medical.com/mint-lesion) | Image viewing, AI analysis and structured reporting in one workflow; built-in assessment guidelines; longitudinal synchronization of images and prior measurements; lesion snapshots, tables and diagrams; radiomics; tumor growth-rate modeling; PACS/RIS/HIS integration. | Add formal response templates, editable longitudinal identities, growth-rate models, structured reporting and hospital integration. |
| [GE OncoQuant](https://www.gehealthcare.com/en-us/products/imaging-applications/advanced-visualization-applications/oncoquant) | CT/MR/PET/CT/3D X-ray comparison; simultaneous registration; automatic like-series selection; finding tables by date; manual link/unlink; follow-up wizard; RECIST 1.0/1.1, WHO and customizable 1D/2D/3D criteria. | The user must be able to correct matches, select target/non-target lesions, and calculate standards-based response—not only view automated volume change. |
| [Philips Multi-modality Tumor Tracking](https://www.documents.philips.com/doclib/enc/fetch/2000/4504/577242/577251/587787/Multi_Modality_Tumor_Tracking.pdf) | Side-by-side comparison of up to four datasets, automatic registration, 3D volumetric segmentation, RECIST/WHO tumor burden, longitudinal graphs, key-image reports, saved segmentations/registrations/results and PACS export. | Add synchronized diagnostic viewports, editable 3D contours, four-time-point charts, and persistence/export of the actual derived objects. |
| [Fujifilm Synapse 3D Liver Analysis](https://healthcaresolutions-us.fujifilm.com/wp-content/uploads/2023/02/Synapse-3D-Liver-Analysis-CT-MR.pdf) | CT/MR liver and nearby vessel extraction; multiphase CT/MRCP/SPECT fusion; liver, hepatic artery, portal vein, hepatic vein, IVC, bile duct and gallbladder models; Couinaud segments; vessel supply/drainage territories; hepatectomy simulation; volumetric reports; STL and interactive PDF. | Add complete vasculobiliary anatomy, territory analysis, resection/ablation simulation, future-liver-remnant calculation and exportable surgical models. |
| [OHIF Viewer](https://github.com/OHIF/Viewers) | Extensible zero-footprint viewer with 2D/3D, MPR, MIP, segmentation labelmaps/contours, DICOM Structured Reports, PDFs and access control. | Use OHIF/Cornerstone for the diagnostic image-review layer instead of relying only on pre-rendered screenshots. |
| [3D Slicer + DICOMweb](https://www.kitware.com/3d-slicer-and-dicomweb-networking/) | Open-source processing/visualization, PACS query and retrieval through DICOMweb, metadata inspection, authentication configuration and extensibility. | Adopt DICOMweb and reuse proven registration/segmentation components where appropriate. |
| [MONAI Label](https://github.com/Project-MONAI/MONAILabel) | Automated and interactive 3D segmentation, DeepEdit/DeepGrow correction, active learning, custom model bundles, local data or DICOMweb, OHIF/3D Slicer integration. | Add rapid human correction and feed approved edits into model evaluation/retraining. |
| [Quibim QP-Liver](https://quibim.com/newsroom/news-and-press-releases/quibim-launches-qp-liver/) | Automated MRI liver segmentation, simultaneous fat and iron quantification, normative comparison and structured quantitative reporting for diffuse liver disease. | A complete MRI product should eventually include PDFF, R2*/iron and possibly elastography when compatible source sequences exist. |

Vendor pages describe product capabilities and should not be read as independent evidence of diagnostic performance.

## Clinical standards RadioLens must support

1. **RECIST 1.1:** measurable non-nodal lesions generally require a longest diameter of at least 10 mm; at most five target lesions total and two per organ; the same targets are followed, while new lesions and non-target disease are handled separately. The longest axial diameter is remeasured even if its level or orientation changes. [RECIST radiologist review](https://pmc.ncbi.nlm.nih.gov/articles/PMC2872013/)
2. **mRECIST/EASL:** for appropriate hypervascular liver tumors after treatment, response is based on the enhancing viable component rather than the whole lesion. Size-only RECIST can miss treatment-induced necrosis. [Evaluation of liver tumour response by imaging](https://pmc.ncbi.nlm.nih.gov/articles/PMC7267412/)
3. **LI-RADS Treatment Response v2024:** response depends on treatment type and enhancement pattern. Diffusion restriction and mild-to-moderate T2 hyperintensity are optional ancillary features, not stand-alone proof of viability. [LI-RADS TRA 2024 review](https://pmc.ncbi.nlm.nih.gov/articles/PMC12149880/)
4. **ADC repeatability:** QIBA reports that a mean ADC change exceeding about 27% for liver lesions can represent a true change with 95% confidence when the acquisition and analysis conform to the profile. RadioLens must not apply this threshold unless protocol conformance is verified. [QIBA ADC Profile review](https://pubmed.ncbi.nlm.nih.gov/39377680/)
5. **DICOM interoperability:** derived contours and measurements should be exportable as DICOM SEG and DICOM SR/TID 1500 and retrievable through DICOMweb, rather than living only in proprietary JSON/PDF.

## Accuracy reality check

RadioLens currently uses the open-source TotalSegmentator liver lesion model. Its published multicenter evaluation reported:

- MRI lesion sensitivity 62.7%, 1.029 false positives per case, and lesion Dice 0.337.
- CT lesion sensitivity 75.8%, 0.522 false positives per case, and Dice 0.658.
- MRI liver segmentation Dice 0.847 and CT liver Dice 0.897.

Source: [Liver Segment and Lesion Segmentation on CT and MRI: An Open-Source Contribution to TotalSegmentator](https://pubmed.ncbi.nlm.nih.gov/41136714/).

That makes automatic results useful as a starting point, but not sufficient for autonomous clinical reporting. Repeat inference agreement—currently shown in RadioLens—is valuable for stability, but two runs of the same model are not independent ground truth.

For comparison, the research system SALSA reported external CT lesion-level precision 81.72%, recall 57.92%, and tumor-wise Dice 0.760, with performance falling for small lesions. It explicitly benchmarked against external cohorts and radiologist intra/inter-reader agreement. [SALSA study](https://pmc.ncbi.nlm.nih.gov/articles/PMC12047525/)

## Recommended roadmap

### P0 — required before any accuracy claim

1. **Radiologist correction and sign-off**
   - Add contour editing, accept/reject, split/merge, target/non-target selection, and manual link/unlink.
   - Preserve the original AI mask, every edit, user, timestamp, and final approved version.

2. **Formal validation harness**
   - Build a de-identified multi-patient dataset with two independent radiologist annotations and adjudication.
   - Report patient-level and lesion-level sensitivity, precision, false positives/case, Dice, surface distance, volume error, diameter error and match accuracy.
   - Stratify by lesion size, tumor type, scanner, field strength, slice thickness, contrast agent/phase and treatment type.
   - Compare AI, radiologist-AI, inter-reader and intra-reader results with confidence intervals.

3. **Standards-aware response engine**
   - Implement RECIST 1.1 target/non-target/new-lesion logic.
   - Add optional mRECIST/EASL and LI-RADS treatment-response workflows only when tumor type and treatment make them appropriate.
   - Keep 3D burden as a supplemental endpoint and never label low attenuation/signal alone as necrosis.

4. **Safer longitudinal identity**
   - Combine rigid/deformable registration, organ/segment location, lesion embeddings, overlap, distance, morphology and intensity features.
   - Produce calibrated match confidence and alternative candidates.
   - Require review when confidence is low; allow explicit link/unlink and gap-spanning matches.

5. **DICOM preflight and quantitative MRI QC**
   - Detect truncated uploads, missing instances, duplicate SOP UIDs, geometry discontinuities, compressed transfer syntaxes and absent required phases before processing.
   - Record contrast agent, injection/acquisition timing, b-values, ADC units, field strength and sequence parameters.
   - Mark comparisons non-quantitative when protocols are incompatible.

### P1 — parity with mature clinical workflow products

6. **Diagnostic viewer** using OHIF/Cornerstone: synchronized axial/coronal/sagittal MPR, linked scrolling, windowing, measurements, overlays, key images and source-series switching.
7. **DICOM-native outputs:** DICOM SEG, DICOM SR/TID 1500, optional RTSTRUCT, plus PACS/DICOMweb send/query/retrieve.
8. **Structured report templates:** lesion table, target/non-target set, response category, uncertainty, validation state, key images and addendum/version history.
9. **Complete liver planning:** portal/hepatic veins, hepatic artery, IVC, bile ducts/gallbladder, Couinaud segments, lesion-to-structure distances, ablation margins, vessel territories and future liver remnant.
10. **Longitudinal analytics:** sum of target diameters, nadir/baseline comparisons, tumor growth rate, waterfall/spider plots and event annotations for treatments.

### P2 — differentiation

11. **Multi-model consensus:** run models with genuinely different architectures/training sources, then use disagreement to drive review—not merely repeat the same model.
12. **Quantitative MRI expansion:** protocol-validated ADC change, enhancement curves, hepatobiliary-phase features, PDFF, R2*/iron and elastography when the required sequences exist.
13. **Uncertainty visualization:** show boundary uncertainty on the image and propagate it to volume/diameter confidence intervals.
14. **Cohort and trial mode:** blinded reads, dual-reader adjudication, audit trails, exportable case report forms and multi-center analytics.
15. **Performance engineering:** asynchronous GPU workers, model warm pools, cached anatomy masks, resumable uploads, progressive previews and cost-aware scheduling.

## Practical next build sequence

The highest-value sequence is:

1. OHIF-based diagnostic viewer and contour editor.
2. Manual lesion link/unlink plus target/non-target workflow.
3. DICOM SEG/SR export and audit provenance.
4. RECIST 1.1 engine, followed by indication-specific mRECIST/LI-RADS.
5. Sheba bulk-validation workspace and radiologist adjudication.
6. Only after benchmark results: public accuracy claims and regulatory planning.

This order improves trust and measurable accuracy before adding more decorative analytics.
