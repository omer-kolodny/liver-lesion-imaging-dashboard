#!/usr/bin/env python3
"""Keep the portocaval nodal target visible but exclude it from liver burden."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TIMELINE = ROOT / "assets" / "timeline.json"


def main() -> None:
    data = json.loads(TIMELINE.read_text())
    node = next(row for row in data["lesions"] if row["lesion_id"] == "L01")
    node.update({
        "kind": "node",
        "reference_segment": None,
        "reference_label": "Portocaval nodal target",
        "trend": "Marked automated decrease in the separate portocaval nodal target since January.",
    })
    for row in data["lesions"]:
        if row is not node:
            row["kind"] = "hepatic"

    for study in data["studies"]:
        node_measurement = node["measurements"][study["date"]]
        node_volume = float(node_measurement.get("volume_ml") or 0)
        original_total = float(study["tumor_volume_ml"]) + float(study.get("extrahepatic_target_volume_ml") or 0)
        liver_only = max(0.0, original_total - node_volume)
        study["extrahepatic_target_volume_ml"] = round(node_volume, 3)
        study["tumor_volume_ml"] = round(liver_only, 3)
        study["tumor_burden_pct"] = round(liver_only / float(study["liver_volume_ml"]) * 100, 3)
        study["liver_lesion_groups"] = 8

    by_date = {row["date"]: row for row in data["studies"]}
    jan, april, aug = (by_date[date] for date in ("2026-01-19", "2026-04-26", "2026-08-23"))
    pct = lambda a, b: round((b / a - 1) * 100, 1)
    data["overall"].update({
        "jan_to_aug_tumor_volume_change_pct": pct(jan["tumor_volume_ml"], aug["tumor_volume_ml"]),
        "jan_to_aug_burden_change_points": round(aug["tumor_burden_pct"] - jan["tumor_burden_pct"], 2),
        "april_to_aug_tumor_volume_change_pct": pct(april["tumor_volume_ml"], aug["tumor_volume_ml"]),
        "april_to_aug_burden_change_points": round(aug["tumor_burden_pct"] - april["tumor_burden_pct"], 2),
        "best_working_inventory": "8 hepatic lesion groups plus 1 separate portocaval nodal target",
        "bottom_line": "Liver-only segmented lesion volume is lower in August than January and April. The portocaval nodal target also decreased markedly but is reported separately and is not included in liver burden.",
    })
    TIMELINE.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main()
