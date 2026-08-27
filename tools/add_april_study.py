#!/usr/bin/env python3
"""Insert the 26 Apr 2026 CT into the derived Noa timeline dashboard.

The component-to-track map below was established from registered, liver-normalized
positions plus segment and morphology. L04 is intentionally represented as a
split/merge event (two adjacent April components), not two invented stable tracks.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as PdfImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
TIMELINE_PATH = ROOT / "assets" / "timeline.json"
APRIL_ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT.parent / "april_2026_analysis"
APRIL_DATE = "2026-04-26"

# Stable longitudinal ID -> one or more 1-based April component numbers.
APRIL_COMPONENT_MAP = {
    "L01": [1],
    "L02": [2],
    "L03": [4],
    "L04": [3, 5],
    "L05": [7],
    "L07": [6],
    "L08": [9],
    "L09": [8],
}

APRIL_REFERENCES = {
    "liver": {"contrast_median_hu": 113.0, "vnc_median_hu": 60.1, "enhancement_hu": 52.4},
    "portal_vein_and_splenic_vein": {"contrast_median_hu": 181.0, "vnc_median_hu": 37.7, "enhancement_hu": 143.9},
    "aorta": {"contrast_median_hu": 177.0, "vnc_median_hu": 34.1, "enhancement_hu": 143.4},
    "spleen": {"contrast_median_hu": 118.0, "vnc_median_hu": 52.8, "enhancement_hu": 65.7},
    "inferior_vena_cava": {"contrast_median_hu": 154.0, "vnc_median_hu": 33.2, "enhancement_hu": 121.8},
}


def weighted(rows: list[dict], field: str, digits: int = 1):
    values = [(float(row[field]), float(row["volume_ml"])) for row in rows if row.get(field) is not None]
    if not values:
        return None
    total = sum(weight for _, weight in values)
    return round(sum(value * weight for value, weight in values) / total, digits)


def combine_components(rows: list[dict]) -> dict:
    primary = max(rows, key=lambda row: row["volume_ml"])
    proximity_names = {name for row in rows for name in row.get("proximity_mm", {})}
    measurement = {
        "detected": True,
        "segment": "/".join(sorted({str(row["segment"]) for row in rows})),
        "fragment_count": len(rows),
        "volume_ml": round(sum(row["volume_ml"] for row in rows), 3),
        "long_mm": max(row.get("recist_long_mm", 0) for row in rows),
        "short_mm": max(row.get("recist_short_mm", 0) for row in rows),
        "cc_mm": max(row.get("extent_CC_mm", 0) for row in rows),
        "max3d_mm": max(row.get("max3d_caliper_mm", 0) for row in rows),
        "pca_axes_mm": primary.get("pca_axes_mm"),
        "median_hu": weighted(rows, "median_hu"),
        "mean_hu": weighted(rows, "mean_hu"),
        "p10_hu": weighted(rows, "p10"),
        "p90_hu": weighted(rows, "p90"),
        "local_liver_median_hu": weighted(rows, "local_liver_median_hu"),
        "lesion_liver_ratio": weighted(rows, "lesion_liver_ratio", 3),
        "below_40hu_pct": weighted(rows, "below_40hu_pct"),
        "relative_low_attenuation_pct": None,
        "higher_attenuation_fraction_pct": round(100 - weighted(rows, "below_40hu_pct"), 1),
        "vnc_median_hu": weighted(rows, "vnc_median_hu"),
        "vnc_corrected_enhancement_hu": weighted(rows, "vnc_corrected_enhancement_hu"),
        "enhancement_vs_liver_pct": weighted(rows, "enhancement_vs_liver_pct"),
        "enhancement_vs_portal_pct": weighted(rows, "enhancement_vs_portal_pct"),
        "minimal_enhancement_pct": weighted(rows, "minimal_enhancement_pct"),
        "proximity_mm": {
            name: round(min(row["proximity_mm"][name] for row in rows if name in row.get("proximity_mm", {})), 1)
            for name in sorted(proximity_names)
        },
        # April was analyzed as a standalone series, so these assignments use
        # liver-relative anatomy but do not claim a high-confidence voxel-overlap
        # match. High confidence is reserved for registered spatial evidence.
        "confidence": "moderate",
        "match_basis": "registered liver-relative position, segment, morphology, and vessel topology",
    }
    if len(rows) > 1:
        measurement["tracking_note"] = "Two adjacent April components are treated as one historical lesion group (split/merge event)."
    return measurement


def comparability(first: dict, second: dict) -> dict:
    diffs = {}
    for name in APRIL_REFERENCES:
        a = first["hemodynamic_references"][name]["enhancement_hu"]
        b = second["hemodynamic_references"][name]["enhancement_hu"]
        diffs[name] = round(abs(a - b) / ((a + b) / 2) * 100, 1)
    ordered = sorted(diffs.values())
    median = ordered[len(ordered) // 2]
    score = round(100 - median, 1)
    return {
        "level": "high" if median <= 12 else "moderate",
        "score_pct": score,
        "median_reference_difference_pct": median,
        "maximum_reference_difference_pct": max(ordered),
        "reference_enhancement_difference_pct": diffs,
        "basis": "VNC-corrected enhancement of normal liver, portal vein, aorta, spleen, and IVC.",
        "label": "High hemodynamic comparability" if median <= 12 else "Moderate hemodynamic comparability",
        "explanation": "Both scans used matched 90-second timing and the same 80 mL iodine injection at 1.7 mL/s; VNC-corrected internal references are similar.",
        "contrast_protocol_match": True,
    }


def load_fonts():
    candidates = [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    path = next((p for p in candidates if Path(p).exists()), None)
    if not path:
        return ImageFont.load_default(), ImageFont.load_default(), ImageFont.load_default()
    return ImageFont.truetype(path, 25), ImageFont.truetype(path, 18), ImageFont.truetype(path, 15)


def remove_caliper_overlay(panel: Image.Image) -> Image.Image:
    """Remove cyan/blue baked-in calipers while preserving purple contours."""
    array = np.asarray(panel.convert("RGB")).copy()
    red, green, blue = array[..., 0], array[..., 1], array[..., 2]
    cool_line = (green > 105) & (blue > 135) & (red < 155) & ((blue.astype(int) - red.astype(int)) > 20)
    red_line = (red > 175) & (green < 145) & (blue < 175) & ((red.astype(int) - green.astype(int)) > 45)
    caliper = cool_line | red_line
    caliper = ndimage.binary_dilation(caliper, iterations=2)
    nearest = ndimage.distance_transform_edt(caliper, return_distances=False, return_indices=True)
    array[caliper] = array[tuple(nearest[:, caliper])]
    return Image.fromarray(array)


def source_half(lesion_id: str, date: str, measurement: dict | None = None) -> Image.Image:
    labels = {
        "2025-12-25": "25 Dec 2025",
        "2026-01-19": "19 Jan 2026",
        "2026-08-23": "23 Aug 2026",
    }
    if date == "2025-12-25":
        path = ROOT / "assets" / "timeline" / f"{lesion_id}_2025-12-25_2026-01-19.webp"
        panel = Image.open(path).convert("RGB").crop((0, 0, 900, 855))
    elif date == "2026-01-19":
        path = ROOT / "assets" / "timeline" / f"{lesion_id}_2025-12-25_2026-01-19.webp"
        panel = Image.open(path).convert("RGB").crop((900, 0, 1800, 855))
    elif date == "2026-08-23":
        path = ROOT / "assets" / "timeline" / f"{lesion_id}_2026-01-19_2026-08-23.webp"
        panel = Image.open(path).convert("RGB").crop((900, 0, 1800, 855))
    else:
        raise ValueError(date)
    if measurement and measurement.get("caliper_status"):
        panel = remove_caliper_overlay(panel)
    title_font, body_font, small_font = load_fonts()
    draw = ImageDraw.Draw(panel)
    draw.rectangle((0, 0, 900, 92), fill="#0d1b2d")
    draw.text((28, 20), f"{lesion_id} · {labels[date]}", font=title_font, fill="#f4f8ff")
    draw.rectangle((0, 92, 900, 192), fill="#07111f")
    if measurement and measurement.get("detected"):
        if measurement.get("caliper_status"):
            subtitle = f"{measurement['volume_ml']:.2f} mL automatic mask · caliper withheld (split/merged contour)"
        else:
            subtitle = f"{measurement['long_mm']:.1f} × {measurement['short_mm']:.1f} mm · {measurement['volume_ml']:.2f} mL"
        draw.text((250, 124), labels[date], font=body_font, fill="#f4f8ff")
        draw.text((205, 158), subtitle, font=small_font, fill="#d5dfed")
    draw.rectangle((0, 790, 900, 855), fill="#0d1b2d")
    draw.text((28, 806), "Axial measured image overlay · automated contour", font=load_fonts()[2], fill="#b9c9dc")
    return panel


def april_panel(lesion_id: str, measurement: dict) -> Image.Image:
    title_font, body_font, small_font = load_fonts()
    panel = Image.new("RGB", (900, 855), "#07111f")
    draw = ImageDraw.Draw(panel)
    draw.rectangle((0, 0, 900, 92), fill="#0d1b2d")
    draw.text((28, 20), f"{lesion_id} · 26 Apr 2026", font=title_font, fill="#f4f8ff")
    if not measurement.get("detected"):
        draw.rounded_rectangle((105, 240, 795, 640), 28, fill="#101d2d", outline="#31435a", width=2)
        draw.text((220, 365), "Not separately detected", font=title_font, fill="#d5dfed")
        draw.text((176, 420), "No distinct automated component assigned to this track.", font=body_font, fill="#8fa2b8")
        return panel

    component = APRIL_COMPONENT_MAP[lesion_id][0]
    image_path = APRIL_ROOT / "assets" / "20260426" / f"lesion_{component:02d}.png"
    image = Image.open(image_path).convert("RGB")
    # Use only the axial source panel so both comparison sides have the same
    # orientation, square viewport, panel size, and zoom treatment.
    scale_x = image.width / 4160
    scale_y = image.height / 1560
    axial_box = tuple(round(value) for value in (
        155 * scale_x, 275 * scale_y, 1275 * scale_x, 1395 * scale_y,
    ))
    axial = image.crop(axial_box).resize((598, 598), Image.Resampling.LANCZOS)
    if measurement.get("caliper_status"):
        axial = remove_caliper_overlay(axial)
    panel.paste(axial, (151, 192))
    fragments = measurement.get("fragment_count", 1)
    if measurement.get("caliper_status"):
        subtitle = f"{measurement['volume_ml']:.2f} mL automatic mask · caliper withheld (split/merged contour)"
    elif fragments > 1:
        subtitle = f"{fragments} fragments · {measurement['volume_ml']:.2f} mL · caliper requires component-level review"
    else:
        subtitle = f"{measurement['volume_ml']:.2f} mL · {measurement['long_mm']:.1f} × {measurement['short_mm']:.1f} mm"
    draw.text((260, 126), "26 Apr 2026", font=body_font, fill="#f4f8ff")
    draw.text((245, 158), subtitle, font=small_font, fill="#d5dfed")
    draw.rectangle((0, 790, 900, 855), fill="#0d1b2d")
    draw.text((28, 806), "Axial measured image overlay · automated contour", font=small_font, fill="#b9c9dc")
    return panel


def generate_pair_images(timeline: dict):
    april = {row["lesion_id"]: row["measurements"][APRIL_DATE] for row in timeline["lesions"]}
    pairs = [
        ("2025-12-25", APRIL_DATE),
        ("2026-01-19", APRIL_DATE),
        (APRIL_DATE, "2026-08-23"),
    ]
    out_dir = ROOT / "assets" / "timeline"
    tracks = {row["lesion_id"]: row for row in timeline["lesions"]}
    for lesion_id, measurement in april.items():
        track = tracks[lesion_id]
        april_image = april_panel(lesion_id, measurement)
        for first, second in pairs:
            left = april_image if first == APRIL_DATE else source_half(lesion_id, first, track["measurements"].get(first))
            right = april_image if second == APRIL_DATE else source_half(lesion_id, second, track["measurements"].get(second))
            combined = Image.new("RGB", (1800, 855), "#07111f")
            combined.paste(left, (0, 0))
            combined.paste(right, (900, 0))
            combined.save(out_dir / f"{lesion_id}_{first}_{second}.webp", "WEBP", quality=95, method=6)


def write_csv(timeline: dict):
    fields = [
        "lesion_id", "kind", "reference_label", "reference_segment", "study_date", "detected", "segment", "fragment_count",
        "volume_ml", "long_mm", "short_mm", "cc_mm", "max3d_mm", "median_hu",
        "below_40hu_pct", "vnc_median_hu", "vnc_corrected_enhancement_hu",
        "enhancement_vs_liver_pct", "enhancement_vs_portal_pct", "minimal_enhancement_pct",
        "match_confidence", "tracking_note",
    ]
    with (ROOT / "assets" / "lesion_comparison.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for lesion in timeline["lesions"]:
            for study in timeline["studies"]:
                measurement = lesion["measurements"].get(study["date"], {"detected": False})
                writer.writerow({
                    "lesion_id": lesion["lesion_id"],
                    "kind": lesion.get("kind", "hepatic"),
                    "reference_label": lesion.get("reference_label"),
                    "reference_segment": lesion["reference_segment"],
                    "study_date": study["date"],
                    "detected": measurement.get("detected", False),
                    "segment": measurement.get("segment"),
                    "fragment_count": measurement.get("fragment_count"),
                    "volume_ml": measurement.get("volume_ml"),
                    "long_mm": measurement.get("long_mm"),
                    "short_mm": measurement.get("short_mm"),
                    "cc_mm": measurement.get("cc_mm"),
                    "max3d_mm": measurement.get("max3d_mm"),
                    "median_hu": measurement.get("median_hu"),
                    "below_40hu_pct": measurement.get("below_40hu_pct"),
                    "vnc_median_hu": measurement.get("vnc_median_hu"),
                    "vnc_corrected_enhancement_hu": measurement.get("vnc_corrected_enhancement_hu"),
                    "enhancement_vs_liver_pct": measurement.get("enhancement_vs_liver_pct"),
                    "enhancement_vs_portal_pct": measurement.get("enhancement_vs_portal_pct"),
                    "minimal_enhancement_pct": measurement.get("minimal_enhancement_pct"),
                    "match_confidence": measurement.get("confidence"),
                    "tracking_note": measurement.get("tracking_note"),
                })


def write_pdf(timeline: dict):
    output = ROOT / "assets" / "Liver_Lesion_CT_Comparison.pdf"
    page = landscape(A4)
    doc = SimpleDocTemplate(str(output), pagesize=page, rightMargin=15*mm, leftMargin=15*mm, topMargin=13*mm, bottomMargin=13*mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("TitleX", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=28, leading=32, textColor=colors.HexColor("#11243d"), alignment=TA_LEFT)
    h2 = ParagraphStyle("H2X", parent=styles["Heading2"], fontSize=17, leading=21, textColor=colors.HexColor("#173f5f"))
    body = ParagraphStyle("BodyX", parent=styles["BodyText"], fontSize=9.5, leading=13, textColor=colors.HexColor("#33465c"))
    small = ParagraphStyle("SmallX", parent=body, fontSize=7.8, leading=10)
    story = [
        Paragraph("RadioLens · Longitudinal Liver CT", title),
        Paragraph("Four-study image-derived lesion analysis · dual-channel validation added 25 Aug 2026", h2),
        Spacer(1, 5*mm),
    ]
    study_rows = [["Study", "Liver volume", "Liver-lesion volume", "Liver-only burden"]]
    for study in timeline["studies"]:
        study_rows.append([
            study["label"], f"{study['liver_volume_ml']:.2f} mL",
            f"{study['tumor_volume_ml']:.2f} mL", f"{study['tumor_burden_pct']:.2f}%",
        ])
    table = Table(study_rows, colWidths=[50*mm, 48*mm, 53*mm, 48*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#173f5f")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("BACKGROUND", (0,1), (-1,-1), colors.HexColor("#eef4f8")),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#b9c9d8")),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTNAME", (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("LEADING", (0,0), (-1,-1), 14),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    story += [table, Spacer(1, 7*mm)]
    april = next(study for study in timeline["studies"] if study["date"] == APRIL_DATE)
    august = timeline["studies"][-1]
    volume_change = (august["tumor_volume_ml"] - april["tumor_volume_ml"]) / april["tumor_volume_ml"] * 100
    april_aug_validation = timeline.get("validation", {}).get("pair_summaries", {}).get(
        f"{APRIL_DATE}__2026-08-23", {}
    )
    validation_counts = april_aug_validation.get("counts", {})
    story += [
        Paragraph("April → August summary", h2),
        Paragraph(
            f"Automated liver-only segmented lesion volume changed from {april['tumor_volume_ml']:.2f} mL to {august['tumor_volume_ml']:.2f} mL ({volume_change:+.1f}%). "
            f"Burden changed from {april['tumor_burden_pct']:.2f}% to {august['tumor_burden_pct']:.2f}%. April and August contrast timing is closely matched. "
            "The former L01 nodal classification was withdrawn: L01 is a segment II/III liver mass and is included here. The true portocaval node remains a separate unsegmented specialist-review target. "
            "These outputs require radiologist confirmation and are not a diagnosis or treatment-planning measurement.", body),
        Spacer(1, 2*mm),
        Paragraph(
            f"Segmentation uncertainty: the primary August pipeline estimates {august['tumor_volume_ml']:.2f} mL, while the independent audit estimated {timeline.get('overall', {}).get('independent_model_tumor_volume_ml', 0):.2f} mL. "
            "This spread is reported explicitly; neither estimate is treated as a clinical ground-truth volume.", body),
        Spacer(1, 4*mm),
        Paragraph("Tracking safeguards", h2),
        Paragraph(
            "Tracks are assigned using registered spatial overlap/centroid, Couinaud segment, morphology and vessel topology. One-to-one assignment is preferred; ambiguous matches and split/merge events are explicitly flagged. "
            "L04 is a split/merge case in April. A missing separate component does not prove lesion resolution.", body),
        Spacer(1, 4*mm),
        Paragraph("Independent validation gate", h2),
        Paragraph(
            f"April-to-August liver-mask registration Dice was {april_aug_validation.get('liver_registration_dice_pct', 0):.1f}%. "
            f"The dual-channel gate classified {validation_counts.get('supported', 0)} tracks as supported, "
            f"{validation_counts.get('review', 0)} for review, and {validation_counts.get('not-established', 0)} as not established. "
            "The deterministic channel uses registered voxel overlap, centroid distance and anatomy consistency. The AI channel uses independent repeat segmentation on the August iMAR reconstruction. "
            "Algorithmic agreement is not clinical ground truth; all findings require radiologist source-image confirmation.", body),
        PageBreak(),
    ]
    expert = timeline.get("expert_reference")
    if expert:
        story += [
            Paragraph("Radiologist-workstation screenshot cross-check", h2),
            Paragraph(
                f"The supplied screenshots display {expert['target_count']} manually segmented targets totaling {expert['total_volume_cc']:.2f} cc. "
                f"The study is probably 26 Apr 2026, but the date is not printed in the screenshot. {expert['mapping_status']}", body),
            Spacer(1, 4*mm),
        ]
        manual_rows = [["Target", "Volume", "Workstation HU display"]] + [
            [item["label"], f"{item['volume_cc']:.2f} cc", item["workstation_hu_display"]]
            for item in expert["targets"]
        ] + [["Total", f"{expert['total_volume_cc']:.2f} cc", ""]]
        manual_table = Table(manual_rows, colWidths=[42*mm, 48*mm, 82*mm])
        manual_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#173f5f")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("BACKGROUND", (0,1), (-1,-2), colors.HexColor("#eef4f8")),
            ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#d8ecea")),
            ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#b9c9d8")),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTNAME", (0,-1), (-1,-1), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 8.5),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        story += [manual_table, Spacer(1, 4*mm), Paragraph(expert["hu_warning"], small), PageBreak()]
    for lesion in timeline["lesions"]:
        lid = lesion["lesion_id"]
        first = lesion["measurements"][APRIL_DATE]
        second = lesion["measurements"]["2026-08-23"]
        audit = lesion.get("match_validation", {}).get(f"{APRIL_DATE}__2026-08-23", {})
        deterministic = audit.get("deterministic", {})
        ai = audit.get("ai", {})
        image_path = ROOT / "assets" / "timeline" / f"{lid}_{APRIL_DATE}_2026-08-23.webp"
        target_label = lesion.get("reference_label") if lesion.get("kind") == "node" else f"reference segment {lesion['reference_segment']}"
        def dimensions_text(item):
            if not item.get("detected"):
                return "—"
            if item.get("long_mm") is None or item.get("short_mm") is None:
                return "Withheld — split/merged contour"
            return f"{item['long_mm']:.1f} × {item['short_mm']:.1f} × {item.get('cc_mm', 0):.1f} mm"
        story += [Paragraph(f"{lid} · {target_label}", h2)]
        if image_path.exists():
            story += [PdfImage(str(image_path), width=190*mm, height=90.25*mm), Spacer(1, 1*mm)]
        rows = [
            ["Metric", "26 Apr 2026", "23 Aug 2026"],
            ["Detection", "Detected" if first.get("detected") else "Not separate", "Detected" if second.get("detected") else "Not separate"],
            ["Volume", f"{first.get('volume_ml', 0):.3f} mL" if first.get("detected") else "—", f"{second.get('volume_ml', 0):.3f} mL" if second.get("detected") else "—"],
            ["Long × short × CC", dimensions_text(first), dimensions_text(second)],
            ["VNC-corrected enhancement", f"{first.get('vnc_corrected_enhancement_hu', 0):.1f} HU" if first.get("detected") else "—", f"{second.get('vnc_corrected_enhancement_hu', 0):.1f} HU" if second.get("detected") else "—"],
            ["Below 40 HU", f"{first.get('below_40hu_pct', 0):.1f}%" if first.get("detected") else "—", f"{second.get('below_40hu_pct', 0):.1f}%" if second.get("detected") else "—"],
            ["Validation decision", audit.get("decision", "not audited").replace("-", " ").title(), f"Confidence: {audit.get('confidence', 'unavailable')}"],
            ["Deterministic geometry", (
                f"Dice {deterministic.get('registered_dice_pct', 0):.1f}% · overlap {deterministic.get('smaller_mask_overlap_pct', 0):.1f}%"
                if deterministic.get("registered_dice_pct") is not None else "No one-to-one match established"
            ), (
                f"Centroid {deterministic.get('centroid_distance_mm', 0):.1f} mm · {deterministic.get('anatomy_consistency', 'not assessable')}"
                if deterministic.get("centroid_distance_mm") is not None else deterministic.get("anatomy_consistency", "not assessable")
            )],
            ["Independent AI / reconstruction", ai.get("status", "unavailable").title(), (
                f"Minimum overlap {ai.get('minimum_smaller_mask_overlap_pct', 0):.1f}%"
                if ai.get("minimum_smaller_mask_overlap_pct") is not None else "No independent repeat metric"
            )],
        ]
        lesion_table = Table(rows, colWidths=[60*mm, 75*mm, 75*mm])
        lesion_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#173f5f")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("BACKGROUND", (0,1), (-1,-1), colors.HexColor("#f5f8fb")),
            ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#c5d1dc")),
            ("FONTSIZE", (0,0), (-1,-1), 7.4),
            ("TOPPADDING", (0,0), (-1,-1), 2),
            ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ]))
        validation_note = f"Deterministic: {deterministic.get('note', 'Not audited')} AI/reconstruction: {ai.get('note', 'Not audited')}"
        story += [
            lesion_table, Spacer(1, 2*mm), Paragraph(lesion.get("trend", ""), small),
            Spacer(1, 1*mm), Paragraph(validation_note, small),
        ]
        if lid != timeline["lesions"][-1]["lesion_id"]:
            story.append(PageBreak())
    doc.build(story)


def main():
    timeline = json.loads(TIMELINE_PATH.read_text())
    april_report = json.loads((APRIL_ROOT / "report_data.json").read_text())
    source_study = april_report["studies"][0]
    components = {index: row for index, row in enumerate(source_study["lesions"], 1)}

    april_study = {
        "date": APRIL_DATE,
        "label": "26 Apr 2026",
        "liver_volume_ml": 1504.11,
        "tumor_volume_ml": 97.64,
        "tumor_burden_pct": 6.49,
        "residual_lesion_groups": 8,
        "residual_foci": 9,
        "contrast_timing_sec": 91.8,
        "contrast_volume_ml": 80.0,
        "contrast_flow_ml_s": 1.7,
        "iodine_concentration_mg_ml": 300.0,
        "reconstruction": "70 keV VMI",
        "vnc_available": True,
        "attenuation_confidence": "higher",
        "hemodynamic_references": APRIL_REFERENCES,
    }
    timeline["studies"] = [row for row in timeline["studies"] if row["date"] != APRIL_DATE]
    timeline["studies"].append(april_study)
    timeline["studies"].sort(key=lambda row: row["date"])

    for lesion in timeline["lesions"]:
        lid = lesion["lesion_id"]
        if lid in APRIL_COMPONENT_MAP:
            rows = [components[index] for index in APRIL_COMPONENT_MAP[lid]]
            lesion["measurements"][APRIL_DATE] = combine_components(rows)
        else:
            lesion["measurements"][APRIL_DATE] = {
                "detected": False,
                "confidence": "review",
                "tracking_note": "No separate April component was confidently assigned; this does not prove resolution.",
            }
        lesion["measurements"] = dict(sorted(lesion["measurements"].items()))

    january = next(row for row in timeline["studies"] if row["date"] == "2026-01-19")
    august = next(row for row in timeline["studies"] if row["date"] == "2026-08-23")
    limited = {
        "level": "limited", "score_pct": None,
        "label": "Limited attenuation comparability",
        "explanation": "The December PET-CT lacks a matched VNC series and exact contrast-start timestamp. Morphology is comparable with segmentation limitations; attenuation trends are less reliable.",
        "contrast_protocol_match": False,
    }
    timeline["comparisons"][f"2025-12-25__{APRIL_DATE}"] = limited
    timeline["comparisons"][f"2026-01-19__{APRIL_DATE}"] = comparability(january, april_study)
    timeline["comparisons"][f"{APRIL_DATE}__2026-08-23"] = comparability(april_study, august)
    timeline["comparisons"] = dict(sorted(timeline["comparisons"].items()))

    april_to_aug = (august["tumor_volume_ml"] - april_study["tumor_volume_ml"]) / april_study["tumor_volume_ml"] * 100
    timeline["overall"].update({
        "april_to_aug_tumor_volume_change_pct": round(april_to_aug, 1),
        "april_to_aug_burden_change_points": round(august["tumor_burden_pct"] - april_study["tumor_burden_pct"], 2),
        "bottom_line": "The automated models show lower segmented liver tumor volume in August than April, with the largest residual groups remaining L01 and L02. This is compatible with interval treatment response, but registration, segmentation, and protocol uncertainty require radiologist confirmation.",
    })
    timeline["generated"] = "2026-08-24"
    timeline["method"] = "Automated image-only segmentation with longitudinal registration. Matching uses spatial overlap/centroid, segment, morphology and vessel topology; split/merge and ambiguous tracks are flagged for review. Attenuation uses VNC correction and internal liver/blood-pool normalization."

    TIMELINE_PATH.write_text(json.dumps(timeline, indent=2) + "\n")
    generate_pair_images(timeline)
    write_csv(timeline)
    write_pdf(timeline)
    print(f"Updated {TIMELINE_PATH}")
    print("Generated 48 April comparison images, CSV, and PDF")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise
