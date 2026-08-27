#!/usr/bin/env python3
"""Convert the complete 26 Aug 2026 MRI archive into analysis volumes."""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pydicom
import SimpleITK as sitk

from prepare_mri_studies import build_image, clean, diffusion_b_value


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "mri_longitudinal" / "2026-08-26"
ARCHIVE = Path.home() / "Downloads" / "AA026644IBP_1.2.840.113564.9.1.3037567216.90.2.4015014569642_sbwnza7df132_1e6hvV6mhEmUqt4949cZVg.zip"


def selector(ds) -> str | None:
    description = clean(getattr(ds, "SeriesDescription", ""))
    upper = description.upper()
    temporal = int(getattr(ds, "TemporalPositionIdentifier", 0) or 0)
    if "DIXON_DYN_W" in upper and temporal in {1, 2, 3, 4}:
        return f"dynamic_{temporal}"
    if "DIXON_LATE" in upper:
        return "late"
    if description == "Ax T2 MF+SPAIR":
        return "t2_fatsat"
    if description == "dADC":
        return "adc"
    if upper.startswith("REG -") and "DWI" in upper and diffusion_b_value(ds) == 800:
        return "dwi_b800"
    return None


def main() -> None:
    required = {"late", "t2_fatsat", "adc", "dwi_b800", "dynamic_1", "dynamic_2", "dynamic_3", "dynamic_4"}
    groups: dict[str, list] = defaultdict(list)
    with zipfile.ZipFile(ARCHIVE) as bundle:
        bad = bundle.testzip()
        if bad is not None:
            raise RuntimeError(f"ZIP integrity failure at {bad}")
        for member in bundle.infolist():
            if member.is_dir() or member.filename.upper().endswith("DICOMDIR"):
                continue
            try:
                with bundle.open(member) as stream:
                    ds = pydicom.dcmread(stream, force=True)
                if clean(getattr(ds, "Modality", "")) != "MR" or clean(getattr(ds, "StudyDate", "")) != "20260826":
                    continue
                name = selector(ds)
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
                groups[name].append((float(origin @ normal), int(getattr(ds, "InstanceNumber", 0) or 0), ds.pixel_array,
                                     ds, row, col, normal, origin))
            except Exception:
                continue

    missing = sorted(required - groups.keys())
    if missing:
        raise RuntimeError(f"Complete archive is still missing: {', '.join(missing)}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    metadata = {
        "date": "2026-08-26",
        "source_archive": ARCHIVE.name,
        "source_sha256": digest,
        "source_integrity": "ZIP CRC and central directory verified",
        "volumes": {},
        "availability": {},
    }
    for name in sorted(required):
        image, details = build_image(groups[name])
        sitk.WriteImage(image, str(OUTPUT / f"{name}.nii.gz"))
        metadata["volumes"][name] = details
        metadata["availability"][name] = True
        print(name, details, flush=True)
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
