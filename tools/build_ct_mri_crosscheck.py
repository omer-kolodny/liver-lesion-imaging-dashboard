#!/usr/bin/env python3
"""Create a CT-anchored, multi-sequence audit of the latest MRI."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from PIL import Image
from scipy import ndimage
from skimage import measure
import SimpleITK as sitk
import trimesh


WEB_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ROOT = WEB_ROOT.parent
CROSS_ROOT = ANALYSIS_ROOT / "cross_modal"
MRI_ROOT = ANALYSIS_ROOT / "mri_longitudinal" / "2026-08-26"
CT_REPORT = ANALYSIS_ROOT / "august_2026_reanalysis" / "report_data.json"
OUTPUT = WEB_ROOT / "mri" / "assets" / "ct-mri-crosscheck.png"
AUDIT_JSON = WEB_ROOT / "mri" / "assets" / "ct_mri_audit.json"
TARGET_DIR = WEB_ROOT / "mri" / "assets" / "targets"


def components(mask: np.ndarray, image: nib.Nifti1Image, minimum_ml=.025):
    labels, count = ndimage.label(mask)
    voxel_ml = abs(np.linalg.det(image.affine[:3, :3])) / 1000
    result = []
    for label in range(1, count + 1):
        selection = labels == label
        volume = float(selection.sum() * voxel_ml)
        if volume < minimum_ml:
            continue
        center = np.asarray(ndimage.center_of_mass(selection))
        world = nib.affines.apply_affine(image.affine, center)
        result.append((label, selection, volume, center, world))
    return result


def resample_to_reference(path: Path, reference: sitk.Image) -> np.ndarray:
    image = sitk.ReadImage(str(path))
    result = sitk.Resample(image, reference, sitk.Transform(3, sitk.sitkIdentity),
                           sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8)
    return np.transpose(sitk.GetArrayFromImage(result), (2, 1, 0)) > 0


def best_match(anchor: np.ndarray, anchor_world: np.ndarray, candidates):
    scored = []
    for label, mask, volume, _, world in candidates:
        intersection = np.logical_and(anchor, mask).sum()
        overlap = float(2 * intersection / (anchor.sum() + mask.sum()))
        distance = float(np.linalg.norm(anchor_world - world))
        scored.append((overlap, distance, label, mask, volume))
    if not scored:
        return None
    match = max(scored, key=lambda row: (row[0], -row[1]))
    return match if match[0] >= .05 and match[1] <= 15 else None


def add_mesh(scene, mask, affine, name, color, step=1):
    if mask.sum() < 8:
        return
    vertices, faces, _, _ = measure.marching_cubes(mask.astype(np.uint8), .5, step_size=step, allow_degenerate=False)
    vertices = nib.affines.apply_affine(affine, vertices)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.visual.face_colors = color
    scene.add_geometry(mesh, node_name=name, geom_name=name)


def main():
    ct_path = CROSS_ROOT / "ct_2026-08-23_series2_liver_span.nii.gz"
    ct_mask_path = CROSS_ROOT / "ct_2026-08-23_liver_lesions_raw.nii.gz"
    transform_path = CROSS_ROOT / "ct_2026-08-23_to_mri_2026-08-26_affine.tfm"
    mri_path = MRI_ROOT / "late.nii.gz"

    ct_image = nib.load(ct_path)
    ct_mask = np.asarray(nib.load(ct_mask_path).dataobj) > 0
    mri_image = nib.load(mri_path)
    mri_volume = np.asarray(mri_image.dataobj)
    ct_components = components(ct_mask, ct_image)
    report = json.loads(CT_REPORT.read_text())["studies"][0]["lesions"]
    transform = sitk.ReadTransform(str(transform_path))
    fixed = sitk.ReadImage(str(mri_path))

    sequence_paths = {
        "P4": MRI_ROOT / "segmentations" / "lesions_primary" / "liver_lesions.nii.gz",
        "Late": MRI_ROOT / "segmentations" / "lesions_true_late" / "liver_lesions.nii.gz",
        "T2": MRI_ROOT / "segmentations" / "lesions_t2" / "liver_lesions.nii.gz",
        "DWI": MRI_ROOT / "segmentations" / "lesions_dwi" / "liver_lesions.nii.gz",
    }
    sequence_colors = {"P4": "#ff39ad", "Late": "#ffd166", "T2": "#55efc4", "DWI": "#ff8c42"}
    sequence_components = {
        name: components(resample_to_reference(path, fixed), mri_image)
        for name, path in sequence_paths.items()
    }
    display_volumes = {"Late T1": mri_volume}
    for label, filename in (("Phase 4", "dynamic_4.nii.gz"), ("T2 fat-sat", "t2_fatsat.nii.gz"),
                            ("DWI b=800", "dwi_b800.nii.gz"), ("ADC", "adc.nii.gz")):
        source = sitk.ReadImage(str(MRI_ROOT / filename))
        resampled = sitk.Resample(source, fixed, sitk.Transform(3, sitk.sitkIdentity), sitk.sitkLinear, 0.0, source.GetPixelID())
        display_volumes[label] = np.transpose(sitk.GetArrayFromImage(resampled), (2, 1, 0))
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    labels = {
        "L01": ("H01", "hepatic"), "L02": ("N01", "extrahepatic node"),
        "L03": ("H02", "hepatic"), "L04": ("H03", "hepatic"),
        "L05": ("H04", "hepatic"), "L06": ("H05", "hepatic"),
        "L07": ("H06", "hepatic"), "L08": ("H07", "hepatic"),
        "L09": ("H08", "hepatic"),
    }
    rows = []
    audit_targets = []
    for item in report:
        target_ras = np.asarray([-item["centroid_lps_mm"][0], -item["centroid_lps_mm"][1], item["centroid_lps_mm"][2]])
        source = min(ct_components, key=lambda value: np.linalg.norm(value[4] - target_ras))
        temp = CROSS_ROOT / "_ct_component_tmp.nii.gz"
        nib.save(nib.Nifti1Image(source[1].astype(np.uint8), ct_image.affine, ct_image.header), temp)
        resampled = sitk.Resample(sitk.ReadImage(str(temp)), fixed, transform, sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8)
        anchor = np.transpose(sitk.GetArrayFromImage(resampled), (2, 1, 0)) > 0
        center = np.asarray(ndimage.center_of_mass(anchor))
        center_world = nib.affines.apply_affine(mri_image.affine, center)
        matches = {name: best_match(anchor, center_world, candidates) for name, candidates in sequence_components.items()}
        public_id, category = labels[item["lesion_id"]]
        category_label = "extrahepatic nodal target" if category != "hepatic" else f"liver · segment {item['segment']}"
        supported_by = [name for name, match in matches.items() if match is not None]
        rows.append((public_id, category, item, anchor, center, matches))
        audit_targets.append({
            "id": public_id,
            "kind": "hepatic" if category == "hepatic" else "node",
            "ct_segment": item["segment"],
            "ct_volume_ml": item["volume_ml"],
            "supported_by_sequences": supported_by,
            "status": "multi-sequence supported" if len(supported_by) >= 2 else "single-sequence support" if supported_by else "not confidently contoured",
            "panel": f"assets/targets/{public_id}_2026-08-26.webp",
        })
        target_fig, target_axes = plt.subplots(1, 5, figsize=(15, 3.4), dpi=180, facecolor="#080813")
        radius_x = int(round(64 / mri_image.header.get_zooms()[0]))
        radius_y = int(round(64 / mri_image.header.get_zooms()[1]))
        z = int(round(center[2])); x0, x1 = max(0, int(center[0]) - radius_x), min(mri_volume.shape[0], int(center[0]) + radius_x)
        y0, y1 = max(0, int(center[1]) - radius_y), min(mri_volume.shape[1], int(center[1]) + radius_y)
        display_to_model = {"Late T1": "Late", "Phase 4": "P4", "T2 fat-sat": "T2", "DWI b=800": "DWI"}
        for axis, (sequence_label, volume) in zip(target_axes, display_volumes.items()):
            panel = volume[x0:x1, y0:y1, z]
            values = panel[np.isfinite(panel) & (panel > 0)]
            lo, hi = np.percentile(values, (2, 98)) if len(values) else (0, 1)
            axis.imshow(panel.T, origin="lower", cmap="magma" if sequence_label == "ADC" else "gray", vmin=lo, vmax=hi, interpolation="lanczos")
            anchor_slice = anchor[x0:x1, y0:y1, z]
            if anchor_slice.any():
                axis.contour(anchor_slice.T, [.5], colors=["#46e3ff"], linewidths=2)
            model_name = display_to_model.get(sequence_label)
            match = matches.get(model_name) if model_name else None
            if match is not None:
                model_slice = match[3][x0:x1, y0:y1, z]
                if model_slice.any():
                    axis.contour(model_slice.T, [.5], colors=[sequence_colors[model_name]], linewidths=1.6)
            axis.set_title(sequence_label, color="white", fontsize=10); axis.set_xticks([]); axis.set_yticks([])
            for spine in axis.spines.values(): spine.set_edgecolor("#403052")
        target_fig.suptitle(f"{public_id} · {category_label} · CT anchor {item['volume_ml']:.2f} mL · MRI support: {', '.join(supported_by) or 'none'}",
                            color="white", fontsize=13, fontweight="bold")
        target_fig.tight_layout(rect=(0, 0, 1, .91))
        target_png = TARGET_DIR / f"{public_id}_2026-08-26.png"
        target_fig.savefig(target_png, facecolor=target_fig.get_facecolor(), bbox_inches="tight")
        plt.close(target_fig)
        Image.open(target_png).convert("RGB").save(target_png.with_suffix(".webp"), "WEBP", quality=93, method=6)
    (CROSS_ROOT / "_ct_component_tmp.nii.gz").unlink(missing_ok=True)

    fig, axes = plt.subplots(3, 3, figsize=(15, 15), dpi=180, facecolor="#080813")
    for ax, (public_id, category, item, anchor, center, matches) in zip(axes.flat, rows):
        z = int(round(center[2]))
        radius_x = int(round(64 / mri_image.header.get_zooms()[0]))
        radius_y = int(round(64 / mri_image.header.get_zooms()[1]))
        x0, x1 = max(0, int(center[0]) - radius_x), min(mri_volume.shape[0], int(center[0]) + radius_x)
        y0, y1 = max(0, int(center[1]) - radius_y), min(mri_volume.shape[1], int(center[1]) + radius_y)
        panel = mri_volume[x0:x1, y0:y1, z]
        values = panel[np.isfinite(panel) & (panel > 0)]
        lo, hi = np.percentile(values, (2, 98)) if len(values) else (0, 1)
        ax.imshow(panel.T, origin="lower", cmap="gray", vmin=lo, vmax=hi, interpolation="lanczos")
        ct_slice = anchor[x0:x1, y0:y1, z]
        if ct_slice.any():
            ax.contour(ct_slice.T, [.5], colors=["#46e3ff"], linewidths=2.2)
        supported = []
        for name, match in matches.items():
            if match is None:
                continue
            mri_slice = match[3][x0:x1, y0:y1, z]
            if mri_slice.any():
                ax.contour(mri_slice.T, [.5], colors=[sequence_colors[name]], linewidths=1.5)
            supported.append(name)
        status = "MRI support: " + ", ".join(supported) if supported else "No confident automatic MRI contour"
        category_label = "extrahepatic nodal target" if category != "hepatic" else f"liver · segment {item['segment']}"
        ax.set_title(f"{public_id} · {category_label} · CT {item['volume_ml']:.2f} mL\n{status}", color="white", fontsize=9.2)
        ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_edgecolor("#403052")
    supported_hepatic = sum(row["kind"] == "hepatic" and bool(row["supported_by_sequences"]) for row in audit_targets)
    scene = trimesh.Scene()
    liver = np.asarray(nib.load(MRI_ROOT / "segmentations" / "liver_segments_multilabel.nii.gz").dataobj) > 0
    add_mesh(scene, liver, mri_image.affine, "Liver_Shell", (172, 104, 224, 92), step=2)
    palette = [(244,72,179,255),(255,113,86,255),(255,186,73,255),(126,105,255,255)]
    for index, (public_id, category, _, anchor, _, _) in enumerate(rows):
        name = f"Node_{public_id}" if category != "hepatic" else f"Lesion_{public_id}"
        color = (217, 70, 239, 255) if category != "hepatic" else palette[index % len(palette)]
        add_mesh(scene, anchor, mri_image.affine, name, color)
    scene.export(WEB_ROOT / "mri" / "assets" / "mri_liver_core.glb")
    hero = plt.figure(figsize=(10, 8), dpi=180, facecolor="#090916")
    hero_ax = hero.add_subplot(111, projection="3d", facecolor="#090916")
    liver_vertices, liver_faces, _, _ = measure.marching_cubes(liver.astype(np.uint8), .5, step_size=3)
    liver_world = nib.affines.apply_affine(mri_image.affine, liver_vertices)
    hero_ax.plot_trisurf(liver_world[:, 0], liver_world[:, 1], liver_faces, liver_world[:, 2], color="#a65ddd", alpha=.20, linewidth=0, shade=True)
    for index, (_, category, _, anchor, _, _) in enumerate(rows):
        if category != "hepatic":
            continue
        vertices, faces, _, _ = measure.marching_cubes(anchor.astype(np.uint8), .5, step_size=1)
        world = nib.affines.apply_affine(mri_image.affine, vertices)
        hero_ax.plot_trisurf(world[:, 0], world[:, 1], faces, world[:, 2], color="#f448b3" if index < 4 else "#ff825f", alpha=.96, linewidth=0, shade=True)
    liver_points = np.argwhere(liver)[::400]
    liver_points_world = nib.affines.apply_affine(mri_image.affine, liver_points)
    center = liver_points_world.mean(axis=0); span = np.ptp(liver_points_world, axis=0).max() / 2
    hero_ax.set_xlim(center[0]-span, center[0]+span); hero_ax.set_ylim(center[1]-span, center[1]+span); hero_ax.set_zlim(center[2]-span, center[2]+span)
    hero_ax.view_init(elev=18, azim=-58); hero_ax.set_axis_off(); hero_ax.set_box_aspect((1,1,.75))
    hero.text(.06,.92,"MRI",color="#b784ff",fontsize=18,fontweight="bold");hero.text(.06,.865,"8 CT-anchored liver targets",color="white",fontsize=24,fontweight="bold")
    hero.savefig(WEB_ROOT / "mri" / "assets" / "mri-hero.png", facecolor=hero.get_facecolor(), bbox_inches="tight", pad_inches=.1)
    plt.close(hero)
    fig.suptitle("23 Aug CT targets registered onto complete 26 Aug MRI\ncyan = CT anchor · pink = phase 4 · yellow = late · green = T2 · orange = DWI",
                 color="white", fontsize=18, fontweight="bold")
    fig.text(.5, .008, f"8 CT-anchored liver targets retained; {supported_hepatic} have an automatic contour on at least one MRI sequence. Lack of a contour is not disappearance.",
             ha="center", color="#d7cce6", fontsize=10)
    plt.tight_layout(rect=(0, .025, 1, .95))
    fig.savefig(OUTPUT, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    Image.open(OUTPUT).convert("RGB").save(OUTPUT.with_suffix(".webp"), "WEBP", quality=92, method=6)
    AUDIT_JSON.write_text(json.dumps({
        "ct_hepatic_targets": 8,
        "extrahepatic_targets": 1,
        "automatic_mri_supported_hepatic_targets": supported_hepatic,
        "targets": audit_targets,
    }, indent=2) + "\n")
    print(OUTPUT)


if __name__ == "__main__":
    main()
