# RadioLens Upload Platform — Free MVP Architecture

## Product flow

1. A user opens the public web app and uploads one or more DICOM ZIP files.
2. The browser uploads directly to object storage using a short-lived signed URL.
3. A background job is queued; the user can close the page.
4. A backend imaging worker downloads the job and runs the existing image-only pipeline.
5. The worker publishes the derived dashboard, PDF, CSV, screenshots, and GLB models.
6. The user receives a random result URL and can compare all detected study dates.

The user's computer only performs the upload. Segmentation and report generation happen asynchronously on a worker.

## Free deployment stack

- **Frontend:** Cloudflare Pages. Static HTML/CSS/JavaScript and the Three.js viewer.
- **API:** Cloudflare Workers free tier. Creates upload sessions, reports job state, and returns result URLs.
- **Metadata:** Cloudflare D1 free tier. Stores job IDs, timestamps, status, study dates, and result locations.
- **Temporary files/results:** Cloudflare R2 free allowance. Raw DICOM archives are deleted after processing; compact derived assets are retained.
- **Queue:** Cloudflare Queues free allowance, or D1 job polling for the first MVP.
- **Imaging compute:** A self-hosted worker on the existing Mac/PC, connected outbound over HTTPS. It can run as a system service or self-hosted runner and can be duplicated on additional machines later.

Cloud CPU/GPU inference is the only component that cannot be unlimited, free, and scalable simultaneously. A self-hosted worker makes the MVP genuinely deployable without a recurring cloud-compute bill. Additional workers provide horizontal scaling; managed GPU workers can be introduced later without changing the upload app.

## Processing worker

The worker claims one queued job with a lease, downloads it to a temporary directory, and runs:

1. ZIP/DICOM validation and series inventory.
2. Diagnostic-series selection and DICOM-to-NIfTI conversion.
3. Liver, lesion, vessel, organ, and segment masks.
4. Longitudinal registration and lesion matching when multiple dates are present.
5. Dimensions, volume, tumor burden, attenuation, VNC correction, internal-reference normalization, and vessel proximity.
6. Annotated comparison images, interactive GLB models, JSON/CSV, and the designed PDF.
7. Upload of derived outputs and deletion of the local temporary job.

The existing RadioLens viewer becomes a reusable template that loads a job-specific `timeline.json`.

## Storage strategy

- Upload directly to R2; never proxy multi-gigabyte files through the API worker.
- Use multipart/resumable uploads so a browser refresh or unstable connection does not restart the entire upload.
- Store each job under an unguessable 128-bit ID.
- Delete raw archives immediately after a successful result, or after a short failure/retry window.
- Keep only derived assets required by the dashboard. A typical derived result is far smaller than its source DICOM archive.
- Apply an automatic expiry policy to abandoned uploads and, initially, to old reports.

## MVP without accounts

The first version can avoid login entirely:

- The upload response returns a secret job URL.
- The same URL shows progress and later opens the report.
- The URL acts as a temporary capability token.
- Optional email notification can be added later.

Authentication, organizational workspaces, audit logs, and formal medical-data compliance can be added without replacing the processing pipeline.

## Scaling path

1. **Free MVP:** one self-hosted CPU/Mac worker, one job at a time.
2. **Small public beta:** several self-hosted workers sharing the same queue.
3. **Production:** burst heavy segmentation jobs to managed GPU containers; keep Pages, Workers, D1, R2, and the result format unchanged.

## Important limitation

Free-tier quotas change and are finite. The static app, API, metadata, and short-lived storage can remain inside free allowances for an MVP. Arbitrary public volume of 3D medical-image inference has a real compute cost; no hosting provider offers unlimited production GPU processing for free.
