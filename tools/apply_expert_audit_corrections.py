#!/usr/bin/env python3
"""Apply the independent identity audit and workstation cross-check."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TIMELINE = ROOT / "assets" / "timeline.json"

WORKSTATION_ROWS = [
    ("T1", 37.17, "77.93 ± 77.93 HU"),
    ("T2", 0.38, "75.6 ± 75.6 HU"),
    ("T3", 0.10, "50.8 ± 50.8 HU"),
    ("T4", 23.80, "72.56 ± 72.56 HU"),
    ("T5", 0.24, "79.63 ± 79.63 HU"),
    ("T6", 1.25, "89.29 ± 89.29 HU"),
    ("T7", 21.26, "55.82 ± 55.82 HU"),
    ("T8", 1.63, "70.19 ± 70.19 HU"),
    ("T9", 0.19, "63 ± 63 HU"),
    ("T10", 0.07, "59.17 ± 59.17 HU"),
    ("T11", 0.93, "101.48 ± 101.48 HU"),
    ("T12", 2.34, "95.65 ± 95.65 HU"),
    ("T13", 15.33, "73.71 ± 73.71 HU"),
    ("T14", 0.21, "87.01 ± 87.01 HU"),
    ("T15", 0.87, "81.84 ± 81.84 HU"),
]


def pct(first: float, last: float) -> float:
    return round((last / first - 1) * 100, 1)


def main() -> None:
    data = json.loads(TIMELINE.read_text())
    l01 = next(row for row in data["lesions"] if row["lesion_id"] == "L01")
    l01.update({
        "kind": "hepatic",
        "reference_segment": "3/2",
        "reference_label": "Left-lobe hepatic mass (segments II/III)",
        "trend": "Marked automated decrease in the left-lobe hepatic mass since January. It was previously misclassified as a portocaval node; that label has been withdrawn.",
    })
    for row in data["lesions"]:
        row["kind"] = "hepatic"
        for date, measurement in row.get("measurements", {}).items():
            if not measurement.get("detected") and measurement.get("volume_ml") == 0:
                measurement["volume_ml"] = None
            if measurement.get("detected") and (
                measurement.get("fragment_count", 1) > 1
                or (row["lesion_id"] == "L02" and date == "2026-04-26")
            ):
                if "caliper_status" not in measurement:
                    measurement["original_automatic_long_mm"] = measurement.get("long_mm")
                    measurement["original_automatic_short_mm"] = measurement.get("short_mm")
                measurement["long_mm"] = None
                measurement["short_mm"] = None
                measurement["caliper_status"] = "withheld: split/merged axial contour cannot support one lesion diameter"

    for study in data["studies"]:
        restored = float(study["tumor_volume_ml"]) + float(study.get("extrahepatic_target_volume_ml") or 0)
        study["tumor_volume_ml"] = round(restored, 3)
        study["tumor_burden_pct"] = round(restored / float(study["liver_volume_ml"]) * 100, 3)
        study["extrahepatic_target_volume_ml"] = None
        study["automatic_hepatic_component_count"] = sum(
            1 for row in data["lesions"] if row.get("measurements", {}).get(study["date"], {}).get("detected")
        )

    timing = {"2026-01-19": 174.4, "2026-04-26": 131.8, "2026-08-23": 131.9}
    for study in data["studies"]:
        if study["date"] in timing:
            study["contrast_timing_sec"] = timing[study["date"]]

    for key, comparison in data.get("comparisons", {}).items():
        first, second = key.split("__")
        if {first, second} == {"2026-04-26", "2026-08-23"}:
            comparison["contrast_protocol_match"] = True
            comparison["explanation"] = "April and August portal-venous acquisitions were timed 131.8 and 131.9 seconds after contrast start. Internal-reference normalization still reduces residual hemodynamic differences."
        elif "2026-01-19" in (first, second):
            comparison["level"] = "moderate"
            comparison["label"] = "Timing-adjusted comparison"
            comparison["contrast_protocol_match"] = False
            comparison["explanation"] = "January was acquired 174.4 seconds after contrast start versus about 132 seconds for April/August. Size is comparable; attenuation trends require extra caution and internal-reference normalization."

    by_date = {row["date"]: row for row in data["studies"]}
    jan, april, aug = (by_date[date] for date in ("2026-01-19", "2026-04-26", "2026-08-23"))
    data["overall"].update({
        "jan_to_aug_tumor_volume_change_pct": pct(jan["tumor_volume_ml"], aug["tumor_volume_ml"]),
        "jan_to_aug_burden_change_points": round(aug["tumor_burden_pct"] - jan["tumor_burden_pct"], 2),
        "april_to_aug_tumor_volume_change_pct": pct(april["tumor_volume_ml"], aug["tumor_volume_ml"]),
        "april_to_aug_burden_change_points": round(aug["tumor_burden_pct"] - april["tumor_burden_pct"], 2),
        "best_working_inventory": "Nine automatic hepatic components on the latest CT. Expert workstation screenshots show 15 manually segmented targets on a likely April study; exact target mapping requires the original DICOM SEG/RTSTRUCT export.",
        "bottom_line": "All automatic liver components, including the left-lobe segment II/III mass formerly mislabeled as a node, are included in liver burden. Automated volume is substantially lower in August, compatible with response, but exact lesion count and whole-tumor burden remain under expert reconciliation.",
        "independent_model_tumor_volume_ml": 55.54,
        "volume_uncertainty_note": "Independent automatic pipelines differ materially. Reported volumes are model estimates, not a clinical ground-truth contour.",
        "portocaval_node_status": "A separate portocaval node is visible and described by the radiologist, but no reliable automated contour is included in the dashboard.",
    })
    data["expert_reference"] = {
        "source": "Two radiologist-workstation screenshots supplied 27 Aug 2026; identifiers and screenshots are not published.",
        "study_date": "2026-04-26",
        "study_date_confidence": "probable, not printed in the screenshot",
        "date_basis": "The 37.17 cc dominant contour closely matches the 37.621 mL April segment VIII automatic contour, and the 105.77 cc total is closest to the independent April estimate.",
        "target_count": 15,
        "total_volume_cc": 105.77,
        "targets": [
            {"label": label, "volume_cc": volume, "workstation_hu_display": hu}
            for label, volume, hu in WORKSTATION_ROWS
        ],
        "mapping_status": "The screenshots do not contain target names, DICOM coordinates, or an exported segmentation object. Individual T1–T15 contours cannot be safely assigned to longitudinal lesion IDs from screenshots alone.",
        "hu_warning": "Every displayed SD exactly repeats the mean, which is unlikely to be a valid standard deviation. These HU entries are transcribed for audit only and are not used for viability calculations.",
    }
    data.setdefault("validation", {})["independent_audit_2026_08_27"] = {
        "status": "partially accepted",
        "accepted": [
            "Former L01 is hepatic, not the portocaval node.",
            "A distinct portocaval node remains unsegmented by the automatic liver-only pipeline.",
            "The complete August MRI includes late T1, DWI and ADC.",
            "CT timing is 174.4 s in January and approximately 132 s in April/August.",
            "Zero-volume placeholders must not be interpreted as disappeared lesions.",
            "MRI automatic contour volume is not a defensible total disease burden.",
        ],
        "qualified_or_rejected": [
            "Treatment response is described as imaging-compatible, not clinically proven by software.",
            "ADC/DWI are supportive response biomarkers, not direct live/dead percentages.",
            "The screenshot's 15 target labels cannot be mapped to lesion IDs without DICOM SEG/RTSTRUCT or a labelled export.",
        ],
    }
    data["generated"] = "2026-08-27"
    data["method"] = "Automated image-only segmentation with longitudinal registration, independent reconstruction/model checks, corrected DICOM contrast timing, and a transcribed radiologist-workstation volume cross-check. Expert screenshots are validation evidence, not substitutes for source segmentation objects."
    TIMELINE.write_text(json.dumps(data, indent=2) + "\n")
    from add_april_study import generate_pair_images, write_csv, write_pdf
    generate_pair_images(data)
    write_csv(data)
    write_pdf(data)


if __name__ == "__main__":
    main()
