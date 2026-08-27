#!/usr/bin/env python3
"""Convert the two available abdominal MRI examinations to derived NIfTI volumes."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
import zipfile

import numpy as np
import pydicom
import SimpleITK as sitk


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "mri_longitudinal"
STUDIES = {
    "2025-12-18": Path.home() / "Downloads" / "DICOM (1).zip",
    "2026-01-22": Path.home() / "Downloads" / "DICOM (3).zip",
}


def clean(value) -> str:
    return "" if value is None else str(value)


def diffusion_b_value(ds) -> float | None:
    for tag in ((0x0018, 0x9087), (0x2001, 0x1003)):
        if tag in ds:
            try:
                return float(ds[tag].value)
            except (TypeError, ValueError):
                pass
    return None


def real_world_scale(ds) -> tuple[float, float, str]:
    sequence = getattr(ds, "RealWorldValueMappingSequence", None)
    if sequence:
        item = sequence[0]
        slope = float(getattr(item, "RealWorldValueSlope", 1) or 1)
        intercept = float(getattr(item, "RealWorldValueIntercept", 0) or 0)
        units = ""
        unit_sequence = getattr(item, "MeasurementUnitsCodeSequence", None)
        if unit_sequence:
            units = clean(getattr(unit_sequence[0], "CodeMeaning", ""))
        return slope, intercept, units
    return (
        float(getattr(ds, "RescaleSlope", 1) or 1),
        float(getattr(ds, "RescaleIntercept", 0) or 0),
        clean(getattr(ds, "RescaleType", "")),
    )


def selector_name(ds) -> str | None:
    description = clean(getattr(ds, "SeriesDescription", ""))
    upper = description.upper()
    temporal = int(getattr(ds, "TemporalPositionIdentifier", 0) or 0)
    if "DIXON_LATE" in upper:
        return "late"
    if description in {"Ax T2 MF+SPAIR", "Ax T2 MVXD RT+SPAIR"}:
        return "t2_fatsat"
    if description == "dADC":
        return "adc"
    if upper.startswith("REG -") and "DWI" in upper and diffusion_b_value(ds) == 800:
        return "dwi_b800"
    if "DIXON_DYN_W" in upper and temporal in {1, 2, 3, 4}:
        return f"dynamic_{temporal}"
    return None


def build_image(entries: list[tuple]) -> tuple[sitk.Image, dict]:
    entries.sort(key=lambda item: (item[0], item[1]))
    unique = []
    seen = set()
    for entry in entries:
        key = round(entry[0], 3)
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    if len(unique) < 10:
        raise ValueError(f"Only {len(unique)} uniquely positioned MRI slices were found")
    positions = np.asarray([item[0] for item in unique], dtype=float)
    spacing_z = float(np.median(np.abs(np.diff(positions))))
    arrays = []
    units = set()
    for _, _, array, ds, *_ in unique:
        slope, intercept, unit = real_world_scale(ds)
        arrays.append(array.astype(np.float32) * slope + intercept)
        if unit:
            units.add(unit)
    volume = np.stack(arrays)
    first = unique[0]
    ds, row, col, normal, origin = first[3], first[4], first[5], first[6], first[7]
    pixel_spacing = [float(value) for value in ds.PixelSpacing]
    image = sitk.GetImageFromArray(volume)
    image.SetSpacing((pixel_spacing[1], pixel_spacing[0], spacing_z))
    image.SetOrigin(tuple(float(value) for value in origin))
    image.SetDirection((
        float(row[0]), float(col[0]), float(normal[0]),
        float(row[1]), float(col[1]), float(normal[1]),
        float(row[2]), float(col[2]), float(normal[2]),
    ))
    return image, {
        "slices": len(unique),
        "size": list(image.GetSize()),
        "spacing_mm": [round(float(value), 5) for value in image.GetSpacing()],
        "units": sorted(units),
        "series_number": clean(getattr(ds, "SeriesNumber", "")),
        "series_description": clean(getattr(ds, "SeriesDescription", "")),
        "acquisition_time": clean(getattr(ds, "AcquisitionTime", "")),
    }


def convert_study(date: str, archive: Path) -> dict:
    study_dir = OUTPUT / date
    study_dir.mkdir(parents=True, exist_ok=True)
    groups = defaultdict(list)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if member.is_dir() or member.filename.upper().endswith("DICOMDIR"):
                continue
            try:
                with bundle.open(member) as stream:
                    ds = pydicom.dcmread(stream, force=True)
                if clean(getattr(ds, "Modality", "")) != "MR":
                    continue
                name = selector_name(ds)
                if not name or not hasattr(ds, "PixelData"):
                    continue
                ipp = getattr(ds, "ImagePositionPatient", None)
                iop = getattr(ds, "ImageOrientationPatient", None)
                if ipp is None or iop is None or not hasattr(ds, "PixelSpacing"):
                    continue
                row = np.asarray([float(value) for value in iop[:3]])
                col = np.asarray([float(value) for value in iop[3:]])
                normal = np.cross(row, col)
                origin = np.asarray([float(value) for value in ipp])
                position = float(origin @ normal)
                groups[name].append((
                    position,
                    int(getattr(ds, "InstanceNumber", 0) or 0),
                    ds.pixel_array,
                    ds,
                    row,
                    col,
                    normal,
                    origin,
                ))
            except Exception:
                continue
    required = {"late", "t2_fatsat", "adc", "dwi_b800", "dynamic_1", "dynamic_2", "dynamic_3", "dynamic_4"}
    missing = sorted(required - groups.keys())
    if missing:
        raise RuntimeError(f"{date}: missing MRI volumes: {', '.join(missing)}")
    metadata = {"date": date, "source_archive": archive.name, "volumes": {}}
    for name in sorted(required):
        image, details = build_image(groups[name])
        sitk.WriteImage(image, str(study_dir / f"{name}.nii.gz"))
        metadata["volumes"][name] = details
        print(date, name, details, flush=True)
    (study_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    return metadata


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    metadata = [convert_study(date, archive) for date, archive in STUDIES.items()]
    (OUTPUT / "studies.json").write_text(json.dumps(metadata, indent=2))
    print(OUTPUT)


if __name__ == "__main__":
    main()
