# Liver Lesion Imaging Dashboard

Public site: https://omer-kolodny.github.io/liver-lesion-imaging-dashboard/

Responsive static web application containing:

- Touch-controlled interactive GLB liver model
- Liver and tumor-volume summary
- December 2025 versus January 2026 comparison
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
