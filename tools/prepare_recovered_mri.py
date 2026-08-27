#!/usr/bin/env python3
"""Prepare the complete DICOM instances recovered from truncated MRI ZIPs."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pydicom
import SimpleITK as sitk

from prepare_mri_studies import build_image, clean, diffusion_b_value


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "mri_longitudinal"
SOURCES = {
    "2026-04-28": Path("/tmp/noa-new-mri.GnTnlS/3"),
    "2026-08-26": Path("/tmp/noa-new-mri.GnTnlS/4"),
}


def selector(date: str, ds) -> str | None:
    description = clean(getattr(ds, "SeriesDescription", ""))
    upper = description.upper()
    temporal = int(getattr(ds, "TemporalPositionIdentifier", 0) or 0)
    if "DIXON_DYN_W" in upper and temporal in {1, 2, 3, 4}:
        return f"dynamic_{temporal}"
    if date == "2026-04-28" and "DIXON_LATE" in upper:
        return "late"
    if date == "2026-04-28" and description == "PI_Ax_T2_SPAIR_TSE__BH":
        return "t2_fatsat"
    if date == "2026-08-26" and description == "MF_T2_HR_RT":
        return "t2_fatsat"
    if date == "2026-04-28" and description == "CS_Ax DWI_3b_RTV":
        b_value = diffusion_b_value(ds)
        if b_value == 0:
            return "dwi_b0"
        if b_value == 800:
            return "dwi_b800"
    return None


def entries(source: Path, date: str) -> dict[str, list]:
    groups = defaultdict(list)
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        try:
            ds = pydicom.dcmread(path, force=True)
            if clean(getattr(ds, "Modality", "")) != "MR" or clean(getattr(ds, "StudyDate", "")) != date.replace("-", ""):
                continue
            name = selector(date, ds)
            if not name or not hasattr(ds, "PixelData"):
                continue
            ipp = getattr(ds, "ImagePositionPatient", None); iop = getattr(ds, "ImageOrientationPatient", None)
            if ipp is None or iop is None or not hasattr(ds, "PixelSpacing"):
                continue
            row = np.asarray([float(value) for value in iop[:3]])
            col = np.asarray([float(value) for value in iop[3:]])
            normal = np.cross(row, col)
            origin = np.asarray([float(value) for value in ipp])
            groups[name].append((float(origin @ normal), int(getattr(ds, "InstanceNumber", 0) or 0), ds.pixel_array,
                                 ds, row, col, normal, origin))
        except Exception:
            continue
    return groups


def main() -> None:
    for date, source in SOURCES.items():
        groups = entries(source, date)
        folder = OUTPUT / date; folder.mkdir(parents=True, exist_ok=True)
        metadata = {"date": date, "source": "complete instances recovered from truncated portal ZIP", "volumes": {}, "availability": {}}
        for name in ("dynamic_1", "dynamic_2", "dynamic_3", "dynamic_4", "late", "t2_fatsat", "dwi_b0", "dwi_b800"):
            if name not in groups:
                continue
            image, details = build_image(groups[name])
            sitk.WriteImage(image, str(folder / f"{name}.nii.gz"))
            metadata["volumes"][name] = details; metadata["availability"][name] = True
            print(date, name, details, flush=True)
        if date == "2026-08-26":
            # The incomplete archive contains four complete axial dynamic phases but
            # not the separate axial late series. Phase 4 is the latest complete
            # axial post-contrast volume and is used transparently as the morphology reference.
            image = sitk.ReadImage(str(folder / "dynamic_4.nii.gz"))
            sitk.WriteImage(image, str(folder / "late.nii.gz"))
            metadata["volumes"]["late"] = dict(metadata["volumes"]["dynamic_4"], derived_from="dynamic_4")
            metadata["availability"]["late"] = True
            metadata["availability"]["dwi_b800"] = False
            metadata["availability"]["adc"] = False
            zero = sitk.Image(image.GetSize(), sitk.sitkFloat32)
            zero.CopyInformation(image)
            sitk.WriteImage(zero, str(folder / "dwi_b800.nii.gz")); sitk.WriteImage(zero, str(folder / "adc.nii.gz"))
        else:
            b0 = sitk.ReadImage(str(folder / "dwi_b0.nii.gz")); b800 = sitk.ReadImage(str(folder / "dwi_b800.nii.gz"))
            a0 = sitk.GetArrayFromImage(b0).astype(np.float32); a800 = sitk.GetArrayFromImage(b800).astype(np.float32)
            adc = np.log(np.maximum(a0, 1) / np.maximum(a800, 1)) / 800.0 * 1000.0
            adc = np.clip(adc, 0, 4)
            adc_image = sitk.GetImageFromArray(adc); adc_image.CopyInformation(b0)
            sitk.WriteImage(adc_image, str(folder / "adc.nii.gz"))
            metadata["availability"]["adc"] = True; metadata["availability"]["dwi_b800"] = True
            metadata["volumes"]["adc"] = {"derived_from": "DWI b=0 and b=800", "units": ["10^-3 mm²/s"]}
        metadata["availability"]["t2_fatsat"] = True
        (folder / "metadata.json").write_text(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
