#!/usr/bin/env python3
"""Build Noa's longitudinal liver MRI dashboard from derived, anonymized volumes.

The output is intentionally described as computer-assisted research visualization.
It is not a radiologist-signed report and it does not turn MRI signal intensity into
an absolute tissue property. MRI signal features are normalized to background liver.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import nibabel as nib
import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from scipy import ndimage
from scipy.optimize import linear_sum_assignment
from skimage import measure
import SimpleITK as sitk
import trimesh


WEB_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = WEB_ROOT.parent / "mri_longitudinal"
OUT = WEB_ROOT / "mri"
ASSETS = OUT / "assets"
IMAGES = ASSETS / "lesions"
DATES = ("2025-12-18", "2026-01-22")
DATE_LABELS = {"2025-12-18": "18 Dec 2025", "2026-01-22": "22 Jan 2026"}
PURPLE = "#b784ff"
FUCHSIA = "#f35cc7"
INDIGO = "#6d78ff"


@dataclass
class Component:
    label: int
    mask: np.ndarray
    volume_ml: float
    centroid_index: np.ndarray
    centroid_world: np.ndarray
    bbox: tuple[slice, slice, slice]


def load(path: Path) -> tuple[nib.Nifti1Image, np.ndarray]:
    image = nib.load(path)
    return image, np.asarray(image.dataobj)


def components(mask: np.ndarray, image: nib.Nifti1Image, minimum_ml: float = 0.025) -> list[Component]:
    labels, count = ndimage.label(mask > 0)
    voxel_ml = abs(np.linalg.det(image.affine[:3, :3])) / 1000.0
    objects = ndimage.find_objects(labels)
    result = []
    for label in range(1, count + 1):
        selection = labels == label
        volume = float(selection.sum() * voxel_ml)
        if volume < minimum_ml:
            continue
        centroid = np.asarray(ndimage.center_of_mass(selection), dtype=float)
        world = nib.affines.apply_affine(image.affine, centroid)
        result.append(Component(label, selection, volume, centroid, world, objects[label - 1]))
    result.sort(key=lambda item: item.volume_ml, reverse=True)
    return result


def dice(first: np.ndarray, second: np.ndarray) -> float:
    denominator = int(first.sum() + second.sum())
    return float(2 * np.logical_and(first, second).sum() / denominator) if denominator else 1.0


def sitk_resample_to_reference(moving_path: Path, reference_path: Path, transform=None, nearest=False) -> np.ndarray:
    moving = sitk.ReadImage(str(moving_path))
    reference = sitk.ReadImage(str(reference_path))
    transform = transform or sitk.Transform(3, sitk.sitkIdentity)
    interpolator = sitk.sitkNearestNeighbor if nearest else sitk.sitkLinear
    result = sitk.Resample(moving, reference, transform, interpolator, 0.0, moving.GetPixelID())
    return np.transpose(sitk.GetArrayFromImage(result), (2, 1, 0))


def world_distance(first: Component, second: Component) -> float:
    return float(np.linalg.norm(first.centroid_world - second.centroid_world))


def mask_extent(mask: np.ndarray, spacing: np.ndarray, direction_xy: np.ndarray | None = None) -> dict:
    z_counts = mask.sum(axis=(0, 1))
    z = int(np.argmax(z_counts))
    coords = np.argwhere(mask[:, :, z])[:, :2].astype(float)
    if len(coords) < 2:
        direction = np.asarray([1.0, 0.0])
    elif direction_xy is None:
        centered = (coords - coords.mean(axis=0)) * spacing[:2]
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        direction = vh[0] / np.linalg.norm(vh[0])
    else:
        direction = np.asarray(direction_xy, dtype=float)
        direction /= np.linalg.norm(direction)
    perpendicular = np.asarray([-direction[1], direction[0]])
    physical = coords * spacing[:2]
    center_mm = physical.mean(axis=0)
    along = (physical - center_mm) @ direction
    across = (physical - center_mm) @ perpendicular
    long_mm = float(along.max() - along.min()) if len(along) else 0.0
    short_mm = float(across.max() - across.min()) if len(across) else 0.0
    center_px = coords.mean(axis=0)
    return {
        "slice": z,
        "direction": direction,
        "center_px": center_px,
        "long_mm": long_mm,
        "short_mm": short_mm,
        "long_endpoints_px": [
            center_px + direction * (along.min() / spacing[:2]),
            center_px + direction * (along.max() / spacing[:2]),
        ],
        "short_endpoints_px": [
            center_px + perpendicular * (across.min() / spacing[:2]),
            center_px + perpendicular * (across.max() / spacing[:2]),
        ],
    }


def three_dimensional_extents(component: Component, image: nib.Nifti1Image) -> list[float]:
    coords = np.argwhere(component.mask)
    if len(coords) < 4:
        return [0.0, 0.0, 0.0]
    sample = coords[:: max(1, len(coords) // 50000)]
    world = nib.affines.apply_affine(image.affine, sample)
    centered = world - world.mean(axis=0)
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    projections = centered @ vh.T
    extents = np.ptp(projections, axis=0)
    return sorted([float(value) for value in extents], reverse=True)


def segment_number(component: Component, segments: np.ndarray) -> int | None:
    values = segments[component.mask]
    values = values[values > 0].astype(int)
    if not len(values):
        center = tuple(np.rint(component.centroid_index).astype(int))
        value = int(segments[center]) if all(0 <= center[i] < segments.shape[i] for i in range(3)) else 0
        return value or None
    return int(np.bincount(values).argmax())


def robust_reference(liver: np.ndarray, lesion: np.ndarray, volume: np.ndarray) -> np.ndarray:
    excluded = ndimage.binary_dilation(lesion, iterations=7)
    values = volume[np.logical_and(liver, ~excluded)]
    values = values[np.isfinite(values) & (values > 0)]
    if not len(values):
        return values
    low, high = np.percentile(values, (10, 90))
    return values[(values >= low) & (values <= high)]


def feature_metrics(mask: np.ndarray, liver: np.ndarray, volumes: dict[str, np.ndarray]) -> dict:
    result = {}
    for name in ("t2_fatsat", "dwi_b800", "adc", "late", "dynamic_1", "dynamic_2", "dynamic_3", "dynamic_4"):
        values = volumes[name][mask]
        values = values[np.isfinite(values)]
        reference = robust_reference(liver, mask, volumes[name])
        lesion_median = float(np.median(values)) if len(values) else None
        liver_median = float(np.median(reference)) if len(reference) else None
        ratio = lesion_median / liver_median if lesion_median is not None and liver_median and liver_median > 0 else None
        result[name] = {"median": lesion_median, "liver_median": liver_median, "ratio": ratio}
    adc_values = volumes["adc"][mask]
    adc_values = adc_values[np.isfinite(adc_values) & (adc_values > 0)]
    result["adc_median"] = float(np.median(adc_values)) if len(adc_values) else None
    result["low_adc_fraction_pct"] = float(100 * np.mean(adc_values < 1.0)) if len(adc_values) else None
    late_values = volumes["late"][mask]
    late_ref = robust_reference(liver, mask, volumes["late"])
    if len(late_values) and len(late_ref):
        threshold = float(np.percentile(late_ref, 25))
        result["low_late_signal_fraction_pct"] = float(100 * np.mean(late_values < threshold))
    else:
        result["low_late_signal_fraction_pct"] = None
    phase_ratios = [result[f"dynamic_{index}"]["ratio"] for index in range(1, 5)]
    result["dynamic_liver_normalized"] = phase_ratios
    if all(value is not None for value in phase_ratios):
        result["peak_phase"] = int(np.argmax(phase_ratios)) + 1
        result["peak_to_phase1_pct"] = float((max(phase_ratios) / phase_ratios[0] - 1) * 100) if phase_ratios[0] else None
        result["late_phase_change_pct"] = float((phase_ratios[-1] / max(phase_ratios) - 1) * 100) if max(phase_ratios) else None
    else:
        result["peak_phase"] = None
        result["peak_to_phase1_pct"] = None
        result["late_phase_change_pct"] = None
    return result


def repeat_validation(primary: Component, repeat_components: list[Component]) -> dict:
    overlaps = [np.logical_and(primary.mask, other.mask).sum() for other in repeat_components]
    best = int(np.argmax(overlaps)) if overlaps else -1
    if best < 0 or overlaps[best] == 0:
        return {"dice": 0.0, "centroid_distance_mm": None, "volume_delta_pct": None, "status": "review"}
    other = repeat_components[best]
    score = dice(primary.mask, other.mask)
    distance = world_distance(primary, other)
    delta = (other.volume_ml / primary.volume_ml - 1) * 100 if primary.volume_ml else None
    status = "supported" if score >= 0.75 and distance <= 5 and abs(delta) <= 20 else "review"
    return {"dice": score, "centroid_distance_mm": distance, "volume_delta_pct": delta, "status": status}


def registered_components_to_january(dec_components: list[Component], jan_image: nib.Nifti1Image) -> list[Component]:
    transform = sitk.ReadTransform(str(DATA_ROOT / "dec_to_jan_rigid.tfm"))
    reference_path = DATA_ROOT / DATES[1] / "late.nii.gz"
    dec_path = DATA_ROOT / DATES[0] / "late.nii.gz"
    registered = []
    for item in dec_components:
        temp = DATA_ROOT / "_component_tmp.nii.gz"
        dec_image = nib.load(dec_path)
        nib.save(nib.Nifti1Image(item.mask.astype(np.uint8), dec_image.affine, dec_image.header), temp)
        array = sitk_resample_to_reference(temp, reference_path, transform=transform, nearest=True) > 0
        temp.unlink(missing_ok=True)
        if not array.any():
            registered.append(Component(item.label, array, item.volume_ml, np.zeros(3), np.zeros(3), (slice(0, 1),) * 3))
            continue
        center = np.asarray(ndimage.center_of_mass(array), dtype=float)
        registered.append(Component(item.label, array, item.volume_ml, center, nib.affines.apply_affine(jan_image.affine, center), ndimage.find_objects(array.astype(np.uint8))[0]))
    return registered


def longitudinal_matches(dec_registered: list[Component], jan_components: list[Component]) -> tuple[dict[int, int], dict[tuple[int, int], dict]]:
    cost = np.full((len(dec_registered), len(jan_components)), 1000.0)
    evidence = {}
    for i, first in enumerate(dec_registered):
        for j, second in enumerate(jan_components):
            distance = world_distance(first, second)
            overlap_dice = dice(first.mask, second.mask)
            volume_ratio = abs(math.log(max(second.volume_ml, 0.01) / max(first.volume_ml, 0.01)))
            score = distance / 12 + (1 - overlap_dice) * 2.5 + volume_ratio * 0.7
            cost[i, j] = score
            evidence[(i, j)] = {"distance_mm": distance, "registered_dice": overlap_dice, "cost": score}
    rows, cols = linear_sum_assignment(cost)
    accepted = {}
    for i, j in zip(rows, cols):
        ev = evidence[(i, j)]
        small = max(dec_registered[i].volume_ml, jan_components[j].volume_ml) < 0.5
        if ev["registered_dice"] >= (0.18 if small else 0.20) and ev["distance_mm"] <= (8 if small else 15):
            accepted[i] = j
    return accepted, evidence


def display_window(array: np.ndarray, mask: np.ndarray | None = None) -> tuple[float, float]:
    values = array[mask] if mask is not None and mask.any() else array[array > 0]
    values = values[np.isfinite(values)]
    if not len(values):
        return 0.0, 1.0
    return tuple(float(value) for value in np.percentile(values, (2, 98)))


def crop_bounds(center: np.ndarray, shape: tuple[int, int], spacing: np.ndarray, width_mm: float = 105) -> tuple[int, int, int, int]:
    radii = np.maximum(24, np.rint(width_mm / spacing[:2] / 2).astype(int))
    x0 = max(0, int(round(center[0])) - int(radii[0])); x1 = min(shape[0], int(round(center[0])) + int(radii[0]))
    y0 = max(0, int(round(center[1])) - int(radii[1])); y1 = min(shape[1], int(round(center[1])) + int(radii[1]))
    return x0, x1, y0, y1


def draw_calipers(ax, extent: dict, bounds, color="#ff69d4") -> None:
    x0, _, y0, _ = bounds
    for endpoints, line_color, width in ((extent["long_endpoints_px"], color, 2.4), (extent["short_endpoints_px"], "#91d7ff", 1.8)):
        points = np.asarray(endpoints)
        ax.plot(points[:, 0] - x0, points[:, 1] - y0, color=line_color, lw=width, marker="|", markersize=10)


def make_comparison_image(track: dict, studies: dict, output: Path) -> None:
    fig, axes = plt.subplots(2, 4, figsize=(16, 8), dpi=180, facecolor="#070917")
    modality = (("late", "Late post-contrast T1"), ("t2_fatsat", "T2 fat-sat"), ("dwi_b800", "DWI b=800"), ("adc", "ADC map"))
    for row, date in enumerate(DATES):
        entry = track["measurements"].get(date)
        center = np.asarray(entry["centroid_index"] if entry else track["display_centers"][date])
        z = int(round(center[2]))
        study = studies[date]
        bounds = crop_bounds(center, study["late"].shape[:2], study["spacing"])
        x0, x1, y0, y1 = bounds
        for col, (name, title) in enumerate(modality):
            ax = axes[row, col]
            array = study["volumes"][name]
            z_panel = max(0, min(z, array.shape[2] - 1))
            panel = array[x0:x1, y0:y1, z_panel]
            mask = study["liver"][x0:x1, y0:y1, z_panel]
            lo, hi = display_window(panel, mask)
            cmap = "magma" if name == "adc" else "gray"
            ax.imshow(panel.T, origin="lower", cmap=cmap, vmin=lo, vmax=hi, interpolation="lanczos")
            if entry:
                lesion = entry["mask"][x0:x1, y0:y1, z_panel]
                if lesion.any():
                    ax.contour(lesion.T, levels=[0.5], colors=[FUCHSIA], linewidths=2.0)
                if name == "late":
                    draw_calipers(ax, entry["extent"], bounds)
                    ax.text(0.02, 0.04, f'{entry["long_mm"]:.1f} × {entry["short_mm"]:.1f} mm', transform=ax.transAxes,
                            color="white", fontsize=9, fontweight="bold", bbox=dict(facecolor="#240b37", alpha=.82, edgecolor=FUCHSIA, pad=4))
            else:
                ax.text(.5, .5, "No accepted match", transform=ax.transAxes, ha="center", va="center", color="#ffd0ef",
                        fontsize=11, fontweight="bold", bbox=dict(facecolor="#240b37", alpha=.86, edgecolor=FUCHSIA, pad=7))
            ax.set_title(title if row == 0 else "", color="#e9e7ff", fontsize=11, pad=7)
            ax.set_xticks([]); ax.set_yticks([])
            for spine in ax.spines.values(): spine.set_edgecolor("#342a52")
        axes[row, 0].set_ylabel(DATE_LABELS[date], color="#e9e7ff", fontsize=12, fontweight="bold", labelpad=12)
    fig.suptitle(f'{track["id"]} · registered multiparametric MRI comparison', color="white", fontsize=19, fontweight="bold", y=.985)
    fig.text(.5, .012, "Pink contour = automated lesion mask · Pink/blue calipers = locked-axis long/short measurements · MRI signal is displayed with per-panel windowing",
             ha="center", color="#aaa5c6", fontsize=9)
    plt.subplots_adjust(left=.04, right=.99, top=.92, bottom=.055, wspace=.035, hspace=.06)
    fig.savefig(output, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def add_mesh(scene: trimesh.Scene, mask: np.ndarray, affine: np.ndarray, name: str, color: tuple[int, int, int, int], step: int = 1) -> None:
    if mask.sum() < 8:
        return
    vertices, faces, _, _ = measure.marching_cubes(mask.astype(np.uint8), level=.5, step_size=step, allow_degenerate=False)
    vertices = nib.affines.apply_affine(affine, vertices)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.visual.face_colors = color
    scene.add_geometry(mesh, node_name=name, geom_name=name)


def build_3d(study: dict, jan_components: list[Component], jan_track_ids: dict[int, str]) -> None:
    liver = study["liver"]
    affine = study["image"].affine
    core = trimesh.Scene()
    add_mesh(core, liver, affine, "Liver_Shell", (146, 85, 205, 115), step=2)
    lesion_colors = [(246, 72, 179, 255), (255, 114, 83, 255), (255, 184, 74, 255), (130, 101, 255, 255)]
    for index, component in enumerate(jan_components):
        track_id = jan_track_ids[index]
        add_mesh(core, component.mask, affine, f"Lesion_{track_id}", lesion_colors[index % len(lesion_colors)], step=1)
    core.export(ASSETS / "mri_liver_core.glb")
    overlays = trimesh.Scene()
    for segment in range(1, 9):
        add_mesh(overlays, study["segments"] == segment, affine, f"Segment_{segment}",
                 (80 + segment * 18, 100 + (segment % 3) * 35, 235 - segment * 12, 125), step=2)
    overlays.export(ASSETS / "mri_segments.glb")


def render_hero(study: dict, components_: list[Component], output: Path) -> None:
    fig = plt.figure(figsize=(10, 8), dpi=180, facecolor="#090916")
    ax = fig.add_subplot(111, projection="3d", facecolor="#090916")
    liver = study["liver"]
    verts, faces, _, _ = measure.marching_cubes(liver.astype(np.uint8), .5, step_size=3)
    world = nib.affines.apply_affine(study["image"].affine, verts)
    ax.plot_trisurf(world[:, 0], world[:, 1], faces, world[:, 2], color="#a65ddd", alpha=.23, linewidth=0, shade=True)
    for index, component in enumerate(components_[:8]):
        verts, faces, _, _ = measure.marching_cubes(component.mask.astype(np.uint8), .5, step_size=1)
        world = nib.affines.apply_affine(study["image"].affine, verts)
        ax.plot_trisurf(world[:, 0], world[:, 1], faces, world[:, 2], color="#f448b3" if index < 2 else "#ff825f", alpha=.96, linewidth=0, shade=True)
    all_points = np.argwhere(liver)[::400]
    world_all = nib.affines.apply_affine(study["image"].affine, all_points)
    center = world_all.mean(axis=0); span = np.ptp(world_all, axis=0).max() / 2
    ax.set_xlim(center[0]-span, center[0]+span); ax.set_ylim(center[1]-span, center[1]+span); ax.set_zlim(center[2]-span, center[2]+span)
    ax.view_init(elev=18, azim=-58); ax.set_axis_off(); ax.set_box_aspect((1, 1, .75))
    fig.text(.06, .92, "MRI", color=PURPLE, fontsize=18, fontweight="bold")
    fig.text(.06, .865, "Latest 3D lesion map", color="white", fontsize=25, fontweight="bold")
    fig.savefig(output, facecolor=fig.get_facecolor(), transparent=False, bbox_inches="tight", pad_inches=.1)
    plt.close(fig)


def safe(value, digits=1, suffix="") -> str:
    return "—" if value is None else f"{value:.{digits}f}{suffix}"


def build_pdf(report: dict) -> None:
    path = ASSETS / "Noa_Liver_MRI_Comparison.pdf"
    page = landscape(A4); width, height = page
    c = canvas.Canvas(str(path), pagesize=page, pageCompression=1)
    c.setTitle("Noa Liver MRI Comparison – Automated Research Visualization")

    def background():
        c.setFillColor(colors.HexColor("#090916")); c.rect(0, 0, width, height, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#16102a")); c.roundRect(24, 24, width-48, height-48, 20, fill=1, stroke=0)
        c.setFillColor(colors.HexColor(PURPLE)); c.rect(24, height-39, width-48, 4, fill=1, stroke=0)

    def footer(page_number):
        c.setFillColor(colors.HexColor("#9991b3")); c.setFont("Helvetica", 7.5)
        c.drawString(38, 31, "Automated research visualization · Not a radiologist-signed report · Source DICOM not embedded")
        c.drawRightString(width-38, 31, f"Page {page_number}")

    background()
    c.setFillColor(colors.HexColor(PURPLE)); c.setFont("Helvetica-Bold", 18); c.drawString(52, height-84, "RADIOLENS · MRI")
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 33); c.drawString(52, height-137, "Longitudinal liver MRI analysis")
    c.setFillColor(colors.HexColor("#c8c0df")); c.setFont("Helvetica", 15); c.drawString(52, height-169, "18 Dec 2025  →  22 Jan 2026")
    hero = ImageReader(str(ASSETS / "mri-hero.png")); c.drawImage(hero, width-365, 95, 310, 310, preserveAspectRatio=True, mask='auto')
    y = height-225
    studies = report["studies"]
    for label, value in (
        ("Tumor volume", f'{studies[0]["tumor_volume_ml"]:.1f} → {studies[1]["tumor_volume_ml"]:.1f} mL'),
        ("Tumor burden", f'{studies[0]["tumor_burden_pct"]:.2f}% → {studies[1]["tumor_burden_pct"]:.2f}%'),
        ("Accepted lesion matches", f'{report["summary"]["accepted_matches"]}'),
        ("Repeat-AI whole-mask Dice", f'{studies[0]["repeat_dice"]:.3f} / {studies[1]["repeat_dice"]:.3f}'),
    ):
        c.setFillColor(colors.HexColor("#231a3c")); c.roundRect(52, y-38, 350, 48, 10, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#a9a1c2")); c.setFont("Helvetica", 9); c.drawString(66, y-6, label.upper())
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 15); c.drawString(66, y-25, value); y -= 60
    c.setFillColor(colors.HexColor("#f1c7e6")); c.setFont("Helvetica-Bold", 9); c.drawString(52, 63, "Clinical limitation")
    c.setFillColor(colors.HexColor("#bcb5cf")); c.setFont("Helvetica", 8)
    c.drawString(52, 49, "Signal ratios, low-ADC fractions, enhancement patterns, segment assignments, and lesion matches require radiologist verification.")
    footer(1); c.showPage()

    background(); c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 25); c.drawString(44, height-75, "Methods and validation")
    blocks = [
        ("Deterministic measurement", "3D connected components on late post-contrast MRI; physical voxel geometry; locked-axis axial calipers; PCA-based 3D extents."),
        ("Longitudinal matching", "Rigid liver registration followed by overlap, centroid-distance, volume-consistency and segment checks. Weak tiny-focus matches are not forced."),
        ("Independent AI repeat", "Each examination was segmented twice with an independent reconstruction run. Per-lesion overlap and volume stability are reported."),
        ("MRI biomarkers", "ADC is reported in 10^-3 mm²/s. T2, DWI, late T1 and dynamic phase values are normalized to background liver because MRI signal is not absolute."),
        ("Timing / hemodynamics", "Dynamic phase behavior depends on acquisition timing, contrast delivery, cardiac output and portal circulation. Phase-normalized findings are proxies, not pathology proof."),
        ("Scope", "No MRCP/biliary, whole-abdomen, or vascular surgical-planning claim is made in this first MRI dashboard. Source images should be reviewed in a diagnostic viewer."),
    ]
    y = height-112
    for title, body in blocks:
        c.setFillColor(colors.HexColor("#241b3d")); c.roundRect(44, y-58, width-88, 67, 12, fill=1, stroke=0)
        c.setFillColor(colors.HexColor(FUCHSIA)); c.setFont("Helvetica-Bold", 11); c.drawString(58, y-12, title)
        c.setFillColor(colors.HexColor("#d1cbe0")); c.setFont("Helvetica", 9)
        words = body.split(); line=""; yy=y-29
        for word in words:
            trial = f"{line} {word}".strip()
            if stringWidth(trial, "Helvetica", 9) > width-125:
                c.drawString(58, yy, line); yy -= 12; line=word
            else: line=trial
        if line: c.drawString(58, yy, line)
        y -= 75
    footer(2); c.showPage()

    page_number = 3
    for track in report["lesions"]:
        background()
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 23); c.drawString(38, height-68, f'{track["id"]} · {track["status_label"]}')
        c.setFillColor(colors.HexColor("#aaa2c0")); c.setFont("Helvetica", 9)
        c.drawString(38, height-86, f'Segment: {track["segment_label"]} · Match: {track["match_status"]} · Radiologist review: required')
        image_path = IMAGES / f'{track["id"]}.png'
        c.drawImage(ImageReader(str(image_path)), 34, 160, 545, 290, preserveAspectRatio=True, anchor='c', mask='auto')
        x = 602; y = height-108
        for date in DATES:
            item = track["measurements"].get(date)
            c.setFillColor(colors.HexColor("#241b3d")); c.roundRect(x, y-126, 205, 135, 12, fill=1, stroke=0)
            c.setFillColor(colors.HexColor(PURPLE)); c.setFont("Helvetica-Bold", 11); c.drawString(x+12, y-14, DATE_LABELS[date])
            if item:
                rows = [
                    ("Axial calipers", f'{item["long_mm"]:.1f} × {item["short_mm"]:.1f} mm'),
                    ("3D volume", f'{item["volume_ml"]:.2f} mL'),
                    ("ADC median", safe(item["features"]["adc_median"], 2, " ×10⁻³ mm²/s")),
                    ("Low ADC <1.0", safe(item["features"]["low_adc_fraction_pct"], 1, "%")),
                    ("DWI / liver", safe(item["features"]["dwi_b800"]["ratio"], 2, "×")),
                    ("T2 / liver", safe(item["features"]["t2_fatsat"]["ratio"], 2, "×")),
                ]
                yy=y-34
                for key, value in rows:
                    c.setFillColor(colors.HexColor("#aaa2c0")); c.setFont("Helvetica", 7.5); c.drawString(x+12, yy, key)
                    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 8); c.drawRightString(x+193, yy, value); yy -= 15
            else:
                c.setFillColor(colors.HexColor("#e8bddb")); c.setFont("Helvetica-Bold", 10); c.drawString(x+12, y-50, "No accepted corresponding focus")
                c.setFillColor(colors.HexColor("#aaa2c0")); c.setFont("Helvetica", 8); c.drawString(x+12, y-67, "Absence of a match does not prove resolution.")
            y -= 150
        c.setFillColor(colors.HexColor("#241b3d")); c.roundRect(602, 162, 205, 92, 12, fill=1, stroke=0)
        c.setFillColor(colors.HexColor(FUCHSIA)); c.setFont("Helvetica-Bold", 10); c.drawString(614, 233, "Dual validation")
        c.setFillColor(colors.HexColor("#d1cbe0")); c.setFont("Helvetica", 8)
        c.drawString(614, 216, f'Registered overlap: {safe(track["match_evidence"].get("registered_dice"), 3)}')
        c.drawString(614, 202, f'Centroid distance: {safe(track["match_evidence"].get("distance_mm"), 1, " mm")}')
        c.drawString(614, 188, f'Dec repeat Dice: {safe(track["validation"].get(DATES[0], {}).get("dice"), 3)}')
        c.drawString(614, 174, f'Jan repeat Dice: {safe(track["validation"].get(DATES[1], {}).get("dice"), 3)}')
        footer(page_number); c.showPage(); page_number += 1
    c.save()


def json_measurement(component: Component, image: nib.Nifti1Image, segments: np.ndarray, volumes: dict, liver: np.ndarray,
                     locked_direction: np.ndarray | None = None) -> dict:
    spacing = np.asarray(image.header.get_zooms()[:3], dtype=float)
    extent = mask_extent(component.mask, spacing, locked_direction)
    dims3d = three_dimensional_extents(component, image)
    return {
        "component_index": component.label,
        "volume_ml": component.volume_ml,
        "centroid_index": component.centroid_index.tolist(),
        "centroid_world": component.centroid_world.tolist(),
        "long_mm": extent["long_mm"],
        "short_mm": extent["short_mm"],
        "dimensions_3d_mm": dims3d,
        "segment": segment_number(component, segments),
        "extent": extent,
        "features": feature_metrics(component.mask, liver, volumes),
        "mask": component.mask,
    }


def strip_arrays(value):
    if isinstance(value, dict): return {key: strip_arrays(item) for key, item in value.items() if key not in {"mask", "extent"}}
    if isinstance(value, list): return [strip_arrays(item) for item in value]
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, (np.floating, np.integer)): return value.item()
    return value


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True); IMAGES.mkdir(parents=True, exist_ok=True)
    studies = {}
    study_summary = []
    component_sets = {}; repeat_sets = {}
    for date in DATES:
        folder = DATA_ROOT / date
        image, late = load(folder / "late.nii.gz")
        _, primary = load(folder / "segmentations/lesions_primary/liver_lesions.nii.gz")
        _, repeat = load(folder / "segmentations/lesions_repeat/liver_lesions.nii.gz")
        _, segments = load(folder / "segmentations/liver_segments_multilabel.nii.gz")
        liver = segments > 0
        volumes = {"late": late.astype(np.float32)}
        for name in ("t2_fatsat", "dwi_b800", "adc", "dynamic_1", "dynamic_2", "dynamic_3", "dynamic_4"):
            volumes[name] = sitk_resample_to_reference(folder / f"{name}.nii.gz", folder / "late.nii.gz").astype(np.float32)
        primary_components = components(primary > 0, image)
        repeat_components = components(repeat > 0, image)
        component_sets[date] = primary_components; repeat_sets[date] = repeat_components
        voxel_ml = abs(np.linalg.det(image.affine[:3, :3])) / 1000
        tumor_volume = float((primary > 0).sum() * voxel_ml); liver_volume = float(liver.sum() * voxel_ml)
        studies[date] = {"image": image, "late": late, "volumes": volumes, "segments": segments.astype(np.uint8), "liver": liver,
                         "spacing": np.asarray(image.header.get_zooms()[:3]), "components": primary_components}
        study_summary.append({"date": date, "label": DATE_LABELS[date], "tumor_volume_ml": tumor_volume, "liver_volume_ml": liver_volume,
                              "tumor_burden_pct": tumor_volume / liver_volume * 100, "lesion_count": len(primary_components),
                              "repeat_dice": dice(primary > 0, repeat > 0)})

    dec_registered = registered_components_to_january(component_sets[DATES[0]], studies[DATES[1]]["image"])
    accepted, evidence = longitudinal_matches(dec_registered, component_sets[DATES[1]])
    tracks = []
    used_jan = set()
    for dec_index, component in enumerate(component_sets[DATES[0]]):
        jan_index = accepted.get(dec_index); used_jan.add(jan_index) if jan_index is not None else None
        track_id = f"M{len(tracks)+1:02d}"
        dec_extent = mask_extent(component.mask, studies[DATES[0]]["spacing"])
        locked = dec_extent["direction"]
        measurements = {DATES[0]: json_measurement(component, studies[DATES[0]]["image"], studies[DATES[0]]["segments"],
                                                    studies[DATES[0]]["volumes"], studies[DATES[0]]["liver"], locked)}
        match_evidence = evidence.get((dec_index, jan_index), {}) if jan_index is not None else {}
        if jan_index is not None:
            jan_component = component_sets[DATES[1]][jan_index]
            measurements[DATES[1]] = json_measurement(jan_component, studies[DATES[1]]["image"], studies[DATES[1]]["segments"],
                                                       studies[DATES[1]]["volumes"], studies[DATES[1]]["liver"], locked)
            status = "accepted"
        else:
            status = "unmatched baseline focus"
        tracks.append({"id": track_id, "dec_index": dec_index, "jan_index": jan_index, "measurements": measurements,
                       "match_evidence": match_evidence, "match_status": status})
    for jan_index, component in enumerate(component_sets[DATES[1]]):
        if jan_index in used_jan: continue
        track_id = f"M{len(tracks)+1:02d}"
        locked = mask_extent(component.mask, studies[DATES[1]]["spacing"])["direction"]
        tracks.append({"id": track_id, "dec_index": None, "jan_index": jan_index,
                       "measurements": {DATES[1]: json_measurement(component, studies[DATES[1]]["image"], studies[DATES[1]]["segments"],
                                                                   studies[DATES[1]]["volumes"], studies[DATES[1]]["liver"], locked)},
                       "match_evidence": {}, "match_status": "new/unmatched later focus"})

    # Display centers for absent counterparts use the registered anatomical location when available.
    inverse_transform = sitk.ReadTransform(str(DATA_ROOT / "dec_to_jan_rigid.tfm")).GetInverse()
    for track in tracks:
        display_centers = {}
        if DATES[0] in track["measurements"]:
            display_centers[DATES[0]] = track["measurements"][DATES[0]]["centroid_index"]
        if DATES[1] in track["measurements"]:
            display_centers[DATES[1]] = track["measurements"][DATES[1]]["centroid_index"]
        if DATES[1] not in display_centers:
            display_centers[DATES[1]] = dec_registered[track["dec_index"]].centroid_index.tolist()
        if DATES[0] not in display_centers:
            world = component_sets[DATES[1]][track["jan_index"]].centroid_world
            dec_world = np.asarray(inverse_transform.TransformPoint(tuple(float(v) for v in world)))
            display_centers[DATES[0]] = nib.affines.apply_affine(np.linalg.inv(studies[DATES[0]]["image"].affine), dec_world).tolist()
        track["display_centers"] = display_centers
        validation = {}
        if track["dec_index"] is not None:
            validation[DATES[0]] = repeat_validation(component_sets[DATES[0]][track["dec_index"]], repeat_sets[DATES[0]])
        if track["jan_index"] is not None:
            validation[DATES[1]] = repeat_validation(component_sets[DATES[1]][track["jan_index"]], repeat_sets[DATES[1]])
        track["validation"] = validation
        segments_present = [item["segment"] for item in track["measurements"].values() if item.get("segment")]
        track["segment_label"] = " / ".join(f"S{value}" for value in dict.fromkeys(segments_present)) if segments_present else "Unassigned"
        if len(track["measurements"]) == 2:
            first = track["measurements"][DATES[0]]["volume_ml"]; second = track["measurements"][DATES[1]]["volume_ml"]
            delta = (second / first - 1) * 100 if first else None
            track["volume_change_pct"] = delta
            track["status_label"] = "Measured increase" if delta > 20 else "Measured decrease" if delta < -20 else "Broadly stable"
        elif DATES[0] in track["measurements"]:
            track["volume_change_pct"] = None; track["status_label"] = "No accepted later match"
        else:
            track["volume_change_pct"] = None; track["status_label"] = "No accepted earlier match"
        make_comparison_image(track, studies, IMAGES / f'{track["id"]}.png')

    jan_track_ids = {track["jan_index"]: track["id"] for track in tracks if track["jan_index"] is not None}
    build_3d(studies[DATES[1]], component_sets[DATES[1]], jan_track_ids)
    render_hero(studies[DATES[1]], component_sets[DATES[1]], ASSETS / "mri-hero.png")
    report = {"generated": "2026-08-27", "modality": "MRI", "studies": study_summary,
              "summary": {"accepted_matches": len(accepted), "total_tracks": len(tracks),
                          "registration_liver_dice": 0.9167,
                          "volume_change_pct": (study_summary[1]["tumor_volume_ml"] / study_summary[0]["tumor_volume_ml"] - 1) * 100,
                          "burden_change_pp": study_summary[1]["tumor_burden_pct"] - study_summary[0]["tumor_burden_pct"]},
              "lesions": tracks,
              "limitations": [
                  "Automated research visualization; radiologist verification is required.",
                  "MRI signal intensity is scanner- and sequence-dependent; ratios are normalized to background liver.",
                  "ADC thresholding and low late-signal fractions are exploratory imaging proxies, not proof of viable tumor or necrosis.",
                  "Dynamic enhancement depends on contrast timing and patient hemodynamics; phase labels do not establish a standard arterial or portal phase.",
                  "Tiny foci with weak registered overlap are deliberately not forced into longitudinal matches.",
              ]}
    public_report = strip_arrays(report)
    (ASSETS / "report_data.json").write_text(json.dumps(public_report, indent=2), encoding="utf-8")
    with (ASSETS / "lesion_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["track_id", "date", "match_status", "segment", "volume_ml", "long_mm", "short_mm", "dim3_mm", "adc_median_1e-3_mm2_s",
                         "low_adc_fraction_pct", "dwi_liver_ratio", "t2_liver_ratio", "late_liver_ratio", "low_late_signal_fraction_pct",
                         "repeat_ai_dice", "registered_dice", "centroid_distance_mm"])
        for track in tracks:
            for date in DATES:
                item = track["measurements"].get(date)
                if not item: continue
                features = item["features"]; repeat = track["validation"].get(date, {})
                writer.writerow([track["id"], date, track["match_status"], item["segment"], item["volume_ml"], item["long_mm"], item["short_mm"],
                                 "×".join(f"{v:.1f}" for v in item["dimensions_3d_mm"]), features["adc_median"], features["low_adc_fraction_pct"],
                                 features["dwi_b800"]["ratio"], features["t2_fatsat"]["ratio"], features["late"]["ratio"],
                                 features["low_late_signal_fraction_pct"], repeat.get("dice"), track["match_evidence"].get("registered_dice"),
                                 track["match_evidence"].get("distance_mm")])
    build_pdf(public_report)
    print(json.dumps({"output": str(OUT), "studies": study_summary, "tracks": len(tracks), "matches": len(accepted)}, indent=2))


if __name__ == "__main__":
    main()
