#!/usr/bin/env python3
"""Attach independent deterministic and reconstruction-AI evidence to Noa's timeline.

Automated agreement is never presented as clinical ground truth. The audit records
what was independently tested, what was unavailable, and what needs adjudication.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PAIR_MAPS = {
    "2025-12-25__2026-01-19": {
        "L01": (1, 1), "L02": (2, 2), "L03": (3, 3), "L04": (5, 4),
        "L05": (6, 5), "L06": (7, 6), "L07": (8, 7), "L08": (9, 8),
        "L09": (10, 9), "L10": (12, 10), "L11": (13, 11), "L12": (11, 12),
        "L13": (4, 13), "L14": (16, 14), "L15": (14, 15), "L16": (17, 16),
    },
    "2026-01-19__2026-04-26": {
        "L01": (1, 1), "L02": (2, 2), "L03": (3, 4), "L04": (4, 5),
        "L05": (5, 7), "L07": (7, 6), "L08": (8, 9), "L09": (9, 8),
    },
    "2026-04-26__2026-08-23": {
        "L01": (1, 2), "L02": (2, 1), "L03": (4, 4), "L04": (5, 3),
        "L05": (7, 9), "L07": (6, 6), "L08": (9, 10), "L09": (8, 8),
    },
}

PAIR_LIVER_DICE = {
    "2025-12-25__2026-01-19": 0.915,
    "2026-01-19__2026-04-26": 0.920,
    "2026-04-26__2026-08-23": 0.903,
}

# Compact immutable output of the independent registration audit:
# lesion -> (Dice, overlap relative to the smaller mask, centroid distance mm).
PAIR_EVIDENCE = {
    "2025-12-25__2026-01-19": {
        "L01": (0.789, 0.829, 7.9), "L02": (0.803, 0.830, 5.2),
        "L03": (0.551, 0.557, 8.3), "L04": (0.312, 0.315, 7.1),
        "L05": (0.537, 0.598, 4.9), "L06": (0.237, 0.244, 8.8),
        "L07": (0.238, 0.269, 6.8), "L08": (0.356, 0.357, 5.9),
        "L09": (0.442, 0.460, 4.8), "L10": (0.240, 0.256, 5.9),
        "L11": (0.576, 0.616, 3.1), "L12": (0.338, 0.346, 5.2),
        "L13": (0.042, 0.173, 13.2), "L14": (0.266, 0.323, 3.9),
        "L15": (0.164, 0.184, 5.2), "L16": (0.000, 0.000, 7.8),
    },
    "2026-01-19__2026-04-26": {
        "L01": (0.625, 0.982, 7.0), "L02": (0.838, 0.884, 1.9),
        "L03": (0.473, 0.899, 5.9), "L04": (0.468, 0.866, 6.2),
        "L05": (0.307, 0.753, 5.2), "L07": (0.496, 0.670, 3.8),
        "L08": (0.058, 0.155, 7.6), "L09": (0.353, 0.680, 4.2),
    },
    "2026-04-26__2026-08-23": {
        "L01": (0.485, 0.943, 7.9), "L02": (0.388, 0.500, 12.9),
        "L03": (0.562, 0.943, 2.9), "L04": (0.086, 0.121, 9.9),
        "L05": (0.000, 0.000, 12.3), "L07": (0.000, 0.000, 9.9),
        "L08": (0.017, 0.030, 5.6), "L09": (0.324, 0.411, 3.3),
    },
}

OVERRIDES = {
    ("2025-12-25__2026-01-19", "L13"): ("low", "Small nearby segment 4/5 candidates remain difficult to distinguish."),
    ("2025-12-25__2026-01-19", "L14"): ("low", "Sub-centimeter correspondence is contour-sensitive."),
    ("2025-12-25__2026-01-19", "L15"): ("low", "Sub-centimeter correspondence is contour-sensitive."),
    ("2025-12-25__2026-01-19", "L16"): ("low", "No voxel overlap after registration; proximity alone supports only a tentative match."),
    ("2026-01-19__2026-04-26", "L04"): ("moderate", "Primary focus is supported, but April contains an adjacent segment 8 component: possible split/merge."),
    ("2026-01-19__2026-04-26", "L08"): ("low", "Small focus with limited registered overlap."),
    ("2026-04-26__2026-08-23", "L02"): ("moderate", "Main focus is supported; August also contains a reproducible nearby segment 1 focus, treated as a possible split/satellite."),
    ("2026-04-26__2026-08-23", "L04"): ("low", "Compound segment 4/8 region with split/merge behavior; do not interpret it as an exact one-to-one lesion measurement."),
    ("2026-04-26__2026-08-23", "L05"): ("moderate", "Small focus is anatomically compatible but has no voxel overlap after global liver registration."),
    ("2026-04-26__2026-08-23", "L07"): ("moderate", "Small focus is anatomically compatible but has no voxel overlap after global liver registration."),
    ("2026-04-26__2026-08-23", "L08"): ("low", "Very small focus; identity is highly sensitive to contour and reconstruction."),
}

# August series-2 component(s) assigned to each longitudinal track.
AUGUST_TRACK_COMPONENTS = {
    "L01": [2], "L02": [1, 5], "L03": [4], "L04": [3, 7],
    "L05": [9], "L06": [11], "L07": [6], "L08": [10], "L09": [8],
}

# iMAR component -> series-2 component correspondences from the repeat audit.
AUGUST_RECON_MATCHES = {
    1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 8, 8: 9, 9: 10,
}

# series-2 component -> (Dice, smaller-mask overlap, centroid distance mm).
AUGUST_RECON_EVIDENCE = {
    1: (0.961, 0.962, 0.8), 2: (0.939, 0.962, 0.9),
    3: (0.831, 0.959, 2.3), 4: (0.892, 0.918, 0.9),
    5: (0.893, 0.914, 0.8), 6: (0.819, 0.893, 0.8),
    8: (0.845, 0.851, 0.6), 9: (0.800, 0.838, 0.7),
    10: (0.736, 0.780, 0.8),
}


def evidence_row(values: tuple[float, float, float]) -> dict:
    dice, overlap, distance = values
    return {"dice": dice, "overlap_min": overlap, "centroid_distance_mm": distance}


def default_confidence(row: dict) -> str:
    if row["overlap_min"] >= 0.5 and row["centroid_distance_mm"] <= 10:
        return "high"
    if row["centroid_distance_mm"] <= 15:
        return "moderate"
    return "low"


def anatomy_consistency(lesion: dict, first_date: str, second_date: str) -> str:
    reference = str(lesion["reference_segment"])
    first_segment = str(lesion["measurements"][first_date].get("segment") or "")
    second_segment = str(lesion["measurements"][second_date].get("segment") or "")
    if not first_segment or not second_segment:
        return "not assessable"
    if reference in first_segment and reference in second_segment:
        return "reference segment retained"
    if set(first_segment.replace("/", "")) & set(second_segment.replace("/", "")):
        return "overlapping segment assignment"
    return "segment assignment changed — review"


def august_ai_evidence(lesion_id: str) -> dict:
    components = AUGUST_TRACK_COMPONENTS.get(lesion_id, [])
    reverse = {fixed: moving for moving, fixed in AUGUST_RECON_MATCHES.items()}
    reproduced = [component for component in components if component in reverse]
    rows = [evidence_row(AUGUST_RECON_EVIDENCE[component]) for component in reproduced]
    missing = [component for component in components if component not in reverse]
    if not components:
        return {
            "status": "unavailable", "confidence": "unavailable",
            "kind": "independent reconstruction segmentation",
            "note": "No August component was assigned to this historical track.",
        }
    if missing:
        return {
            "status": "review", "confidence": "low",
            "kind": "independent reconstruction segmentation",
            "reproduced_components": len(reproduced), "expected_components": len(components),
            "missing_series2_components": missing,
            "note": "At least one very small series-2 component was not reproduced on the independent iMAR reconstruction.",
        }
    minimum_overlap = min(row["overlap_min"] for row in rows)
    confidence = "high" if minimum_overlap >= 0.8 else "moderate"
    note = "The August mask was reproduced on an independently reconstructed CT series."
    if lesion_id == "L04":
        confidence = "moderate"
        note = "The same iMAR focus overlaps two series-2 components, confirming anatomy but also reconstruction-dependent split behavior."
    elif lesion_id == "L02" and len(components) > 1:
        note = "Both August components, including the possible satellite focus, were reproduced on iMAR."
    return {
        "status": "pass" if confidence == "high" else "review",
        "confidence": confidence,
        "kind": "independent reconstruction segmentation",
        "reproduced_components": len(reproduced), "expected_components": len(components),
        "minimum_smaller_mask_overlap_pct": round(minimum_overlap * 100, 1),
        "minimum_registered_dice_pct": round(min(row["dice"] for row in rows) * 100, 1),
        "maximum_centroid_distance_mm": round(max(row["centroid_distance_mm"] for row in rows), 1),
        "note": note,
    }


def unavailable_ai_evidence() -> dict:
    return {
        "status": "unavailable", "confidence": "unavailable",
        "kind": "independent reconstruction/model repeat",
        "note": "No independent repeat segmentation was available for both studies in this pair; AI confirmation is therefore not claimed.",
    }


def overall_gate(deterministic: dict, ai: dict) -> tuple[str, str]:
    if deterministic["status"] == "not-established":
        return "not-established", "low"
    if deterministic["status"] != "pass":
        return "review", deterministic["confidence"]
    if ai["status"] == "pass":
        order = {"low": 0, "moderate": 1, "high": 2}
        return "supported", min((deterministic["confidence"], ai["confidence"]), key=order.get)
    if ai["status"] == "unavailable":
        return "provisional", "moderate"
    return "review", "moderate"


def main():
    timeline_path = ROOT / "assets" / "timeline.json"
    timeline = json.loads(timeline_path.read_text())

    pair_summaries = {}
    for pair, mapping in PAIR_MAPS.items():
        first_date, second_date = pair.split("__")
        counts = {"supported": 0, "provisional": 0, "review": 0, "not-established": 0}
        for lesion in timeline["lesions"]:
            first = lesion["measurements"][first_date]
            second = lesion["measurements"][second_date]
            if not first.get("detected") and not second.get("detected"):
                continue
            if lesion["lesion_id"] not in mapping or not first.get("detected") or not second.get("detected"):
                deterministic = {
                    "status": "not-established", "confidence": "low",
                    "method": "registered mask geometry",
                    "anatomy_consistency": anatomy_consistency(lesion, first_date, second_date),
                    "note": "No sufficiently supported one-to-one correspondence was found; absence of a separate component does not prove resolution.",
                }
            else:
                row = evidence_row(PAIR_EVIDENCE[pair][lesion["lesion_id"]])
                confidence = default_confidence(row)
                note = "Registered location and mask overlap support this correspondence."
                override = OVERRIDES.get((pair, lesion["lesion_id"]))
                if override:
                    confidence, note = override
                deterministic = {
                    "status": "pass" if confidence == "high" else "review",
                    "confidence": confidence,
                    "method": "rigid liver-mask registration plus lesion overlap and centroid",
                    "registered_dice_pct": round(row["dice"] * 100, 1),
                    "smaller_mask_overlap_pct": round(row["overlap_min"] * 100, 1),
                    "centroid_distance_mm": row["centroid_distance_mm"],
                    "anatomy_consistency": anatomy_consistency(lesion, first_date, second_date),
                    "note": note,
                }
            ai = august_ai_evidence(lesion["lesion_id"]) if second_date == "2026-08-23" else unavailable_ai_evidence()
            decision, confidence = overall_gate(deterministic, ai)
            result = {
                "decision": decision,
                "confidence": confidence,
                "deterministic": deterministic,
                "ai": ai,
                "requires_radiologist_review": decision != "supported",
                "clinical_ground_truth": False,
            }
            lesion.setdefault("match_validation", {})[pair] = result
            counts[decision] += 1
        pair_summaries[pair] = {
            "liver_registration_dice_pct": round(PAIR_LIVER_DICE[pair] * 100, 1),
            "counts": counts,
            "deterministic_method": "Independent rigid liver-mask registration plus lesion voxel overlap, centroid distance and anatomy consistency.",
            "ai_method": "Independent repeat segmentation on a second August reconstruction where available; otherwise explicitly unavailable.",
        }

    study_reconciliation = []
    for study in timeline["studies"]:
        tracked = sum(float(row["measurements"][study["date"]].get("volume_ml") or 0) for row in timeline["lesions"])
        residual = round(float(study["tumor_volume_ml"]) - tracked, 3)
        recomputed_burden = float(study["tumor_volume_ml"]) / float(study["liver_volume_ml"]) * 100
        study_reconciliation.append({
            "date": study["date"], "reported_tumor_volume_ml": study["tumor_volume_ml"],
            "tracked_volume_ml": round(tracked, 3), "untracked_or_rounding_volume_ml": residual,
            "reported_burden_pct": study["tumor_burden_pct"],
            "recomputed_burden_pct": round(recomputed_burden, 3),
            "arithmetic_check": "pass" if abs(residual) <= 0.3 and abs(recomputed_burden - float(study["tumor_burden_pct"])) <= 0.02 else "review",
        })

    timeline["validation"] = {
        "version": "dual-channel-audit-2026-08-25",
        "independent_of_radiology_report": True,
        "pair_summaries": pair_summaries,
        "measurement_reconciliation": study_reconciliation,
        "august_reconstruction_consensus": {
            "liver_dice_pct": 98.5,
            "reproduced_imar_components": 9,
            "series_2_components": 11,
            "note": "All nine iMAR components correspond to series-2 components. One series-2 component is a reconstruction-dependent split and one 0.045 mL focus was not reproduced on iMAR.",
        },
        "gate_policy": "Supported requires deterministic high-confidence correspondence plus an independent AI/reconstruction pass. Missing AI evidence is shown as provisional, never silently treated as passed.",
        "limitations": "Agreement between algorithms or reconstructions is not clinical ground truth. Every match, measurement and trend remains subject to radiologist source-image review.",
    }
    timeline_path.write_text(json.dumps(timeline, indent=2) + "\n")
    print("Added dual-channel match validation to timeline.json")


if __name__ == "__main__":
    main()
