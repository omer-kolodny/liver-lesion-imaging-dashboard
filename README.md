# RadioLens

Public site: https://omer-kolodny.github.io/liver-lesion-imaging-dashboard/

MRI dashboard: https://omer-kolodny.github.io/liver-lesion-imaging-dashboard/mri/

The dashboard includes selectable CT comparisons for 25 Dec 2025, 19 Jan 2026, 26 Apr 2026, and 23 Aug 2026, plus a latest-scan 3D anatomy model with optional vessel, segment, and organ layers.

The separate MRI dashboard includes 18 Dec 2025, 22 Jan 2026, 28 Apr 2026, and 26 Aug 2026. It provides conservative registered lesion tracking, locked-axis measurements, ADC/DWI/T2 and dynamic signal features, repeat-AI validation, a latest-study 3D liver model, and downloadable PDF/CSV output. The recovered 26 Aug archive is truncated; the dashboard explicitly marks unavailable DWI/ADC data and uses the latest complete axial dynamic phase for morphology.

Responsive static web application containing:

- Touch-controlled interactive GLB liver model
- Switchable liver segments, hepatic vessels, portal vein, IVC, aorta, gallbladder, pancreas, spleen, kidneys, and duodenum
- Per-lesion distance estimates to selected vessels and nearby organs
- Liver and tumor-volume summary
- Selectable comparisons across all four CT dates
- VNC-corrected lesion enhancement normalized to local liver and portal-vein enhancement for January, April, and August
- Pair-specific attenuation comparability indicators based on contrast protocol and internal blood-pool references
- Searchable and filterable lesion explorer
- Full-resolution comparison images and measurements
- Downloadable designed PDF report and CSV data
- Custom iPhone/Home Screen application icon

## Preview locally

From this folder, run:

```bash
python3 -m http.server 8765
```

Then open `http://localhost:8765`.

## Deployment

This is a static site and can be deployed directly to GitHub Pages, Netlify, Vercel, Cloudflare Pages, or any ordinary web server. No build step is required.

Only derived imaging assets are included. Original DICOM files and identifying report metadata are not published.

This application is an automated visualization and not a diagnostic or treatment-planning system.
