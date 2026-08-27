#!/usr/bin/env python3
"""Create an anonymized CT-to-MRI lesion-location audit for Noa's dashboard."""

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
import SimpleITK as sitk


WEB_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ROOT = WEB_ROOT.parent
CROSS_ROOT = ANALYSIS_ROOT / "cross_modal"
MRI_ROOT = ANALYSIS_ROOT / "mri_longitudinal" / "2026-08-26"
CT_REPORT = ANALYSIS_ROOT / "august_2026_reanalysis" / "report_data.json"
OUTPUT = WEB_ROOT / "mri" / "assets" / "ct-mri-crosscheck.png"


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


def main():
    ct_path = CROSS_ROOT / "ct_2026-08-23_series2_liver_span.nii.gz"
    ct_mask_path = CROSS_ROOT / "ct_2026-08-23_liver_lesions_raw.nii.gz"
    transform_path = CROSS_ROOT / "ct_2026-08-23_to_mri_2026-08-26_affine.tfm"
    mri_path = MRI_ROOT / "late.nii.gz"
    mri_mask_path = MRI_ROOT / "segmentations" / "lesions_primary" / "liver_lesions.nii.gz"

    ct_image = nib.load(ct_path)
    ct_mask = np.asarray(nib.load(ct_mask_path).dataobj) > 0
    mri_image = nib.load(mri_path)
    mri_volume = np.asarray(mri_image.dataobj)
    mri_mask = np.asarray(nib.load(mri_mask_path).dataobj) > 0
    ct_components = components(ct_mask, ct_image)
    mri_components = components(mri_mask, mri_image)
    report = json.loads(CT_REPORT.read_text())["studies"][0]["lesions"]
    transform = sitk.ReadTransform(str(transform_path))
    fixed = sitk.ReadImage(str(mri_path))

    labels = {
        "L01": ("H01", "hepatic"), "L02": ("N01", "extrahepatic node"),
        "L03": ("H02", "hepatic"), "L04": ("H03", "hepatic"),
        "L05": ("H04", "hepatic"), "L06": ("H05", "hepatic"),
        "L07": ("H06", "hepatic"), "L08": ("H07", "hepatic"),
        "L09": ("H08", "hepatic"),
    }
    accepted = {"L01": 3, "L02": 7, "L04": 2, "L05": 4}
    rows = []
    for item in report:
        target_ras = np.asarray([-item["centroid_lps_mm"][0], -item["centroid_lps_mm"][1], item["centroid_lps_mm"][2]])
        source = min(ct_components, key=lambda value: np.linalg.norm(value[4] - target_ras))
        temp = CROSS_ROOT / "_ct_component_tmp.nii.gz"
        nib.save(nib.Nifti1Image(source[1].astype(np.uint8), ct_image.affine, ct_image.header), temp)
        resampled = sitk.Resample(sitk.ReadImage(str(temp)), fixed, transform, sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8)
        array = np.transpose(sitk.GetArrayFromImage(resampled), (2, 1, 0)) > 0
        center = np.asarray(ndimage.center_of_mass(array))
        public_id, category = labels[item["lesion_id"]]
        match_index = accepted.get(item["lesion_id"])
        match = next((value for value in mri_components if value[0] == match_index), None)
        overlap = None
        distance = None
        if match is not None:
            overlap = 2 * np.logical_and(array, match[1]).sum() / (array.sum() + match[1].sum())
            distance = float(np.linalg.norm(nib.affines.apply_affine(mri_image.affine, center) - match[4]))
        rows.append((public_id, category, item, array, center, match, overlap, distance))
    (CROSS_ROOT / "_ct_component_tmp.nii.gz").unlink(missing_ok=True)

    fig, axes = plt.subplots(3, 3, figsize=(15, 15), dpi=180, facecolor="#080813")
    for ax, (public_id, category, item, ct_array, center, match, overlap, distance) in zip(axes.flat, rows):
        z = int(round(center[2]))
        radius_x = int(round(64 / mri_image.header.get_zooms()[0]))
        radius_y = int(round(64 / mri_image.header.get_zooms()[1]))
        x0, x1 = max(0, int(center[0]) - radius_x), min(mri_volume.shape[0], int(center[0]) + radius_x)
        y0, y1 = max(0, int(center[1]) - radius_y), min(mri_volume.shape[1], int(center[1]) + radius_y)
        panel = mri_volume[x0:x1, y0:y1, z]
        values = panel[np.isfinite(panel) & (panel > 0)]
        lo, hi = np.percentile(values, (2, 98)) if len(values) else (0, 1)
        ax.imshow(panel.T, origin="lower", cmap="gray", vmin=lo, vmax=hi, interpolation="lanczos")
        ct_slice = ct_array[x0:x1, y0:y1, z]
        if ct_slice.any():
            ax.contour(ct_slice.T, [.5], colors=["#46e3ff"], linewidths=2.2)
        if match is not None:
            mri_slice = match[1][x0:x1, y0:y1, z]
            if mri_slice.any():
                ax.contour(mri_slice.T, [.5], colors=["#ff39ad"], linewidths=2.2)
        if match is None:
            status = "No accepted MRI mask"
        else:
            status = f"MRI C{match[0]} · overlap {overlap:.2f} · {distance:.1f} mm"
        category_label = "extrahepatic nodal target" if category != "hepatic" else f"liver · segment {item['segment']}"
        ax.set_title(f"{public_id} · {category_label} · CT {item['volume_ml']:.2f} mL\n{status}", color="white", fontsize=9.5)
        ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_edgecolor("#403052")
    fig.suptitle("23 Aug CT targets registered onto 26 Aug MRI\ncyan = CT reference region · pink = accepted MRI automated contour",
                 color="white", fontsize=18, fontweight="bold")
    fig.text(.5, .008, "Five CT liver locations have no accepted automatic MRI contour. Non-detection on MRI is not proof of disappearance.",
             ha="center", color="#d7cce6", fontsize=10)
    plt.tight_layout(rect=(0, .025, 1, .955))
    fig.savefig(OUTPUT, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    Image.open(OUTPUT).convert("RGB").save(OUTPUT.with_suffix(".webp"), "WEBP", quality=92, method=6)
    print(OUTPUT)


if __name__ == "__main__":
    main()
