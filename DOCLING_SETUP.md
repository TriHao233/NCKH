# Docling setup on dev-teacher

This setup uses the same pinned Docling image and Vietnamese Tesseract package as dev. PDF scan pages and pages with material table/image layout go through Docling. Good plain text pages keep direct extraction. There is no silent EasyOCR fallback when Docling is selected.

The default Docker Compose configuration starts Docling and selects it for both backend and worker, using `nckh-backend:docling`. Generation code, prompts, model parameters and GPU coordination are unchanged. The old image `nckh-backend:dev` is preserved. The overlay file remains compatible with older commands but is no longer required.

## Before building

Docker images, build cache and the `docling_cache` named volume use Docker Desktop's existing storage location on C. No disk migration is required. Cache/tmp/scratch directories are initialized in the image for the non-root service account.

Keep at least 35 GiB free on C before building. The script checks this minimum; it is not a hard upper bound on build size and cannot cap ongoing cache growth.

## Validate and build manually

From the project directory in PowerShell:

```powershell
.\scripts\Build-Docling.ps1
.\scripts\Build-Docling.ps1 -Build
```

The first command validates only. The second builds images without restarting services. If Docker uses a custom disk location, pass `-DockerDiskDirectory` with that location so the free-space check uses the correct drive.

No model pre-download is run during setup. The pinned image may contain models; additional model downloads and conversion scratch files use the named volume in Docker storage.

## Start the project

Activation is separate from build and restarts backend/worker. First ensure there are no active generation jobs. Keep the same Compose project and existing data volumes.

```powershell
docker compose up -d
```

Docling healthcheck must pass before clients start. Its port is bound to localhost. The existing GPU lock around document parsing remains in place. Docling defaults to CPU with four threads and one worker, without GPU access, to avoid competing for GPU memory with question-generation models. This can be slower than dev's GPU configuration; the Docling OCR/layout/table purpose and pinned image are preserved.

The first conversion may load/download models and take longer. Successful tests with mocked API do not confirm live compatibility of the pinned image; check a separate test PDF after build before processing important material.

## Acceptance check after activation

- Upload a separate scan PDF and a PDF with a table. Confirm extraction diagnostics contain `docling`, `docling_page_count` and original page numbers.
- Check the text, Vietnamese accents, code punctuation, table structure and source page links before sending questions for review.
- Run one test generation and confirm model selection, request parameters and source evidence remain correct. Different extraction can change RAG input; identical generated wording is not guaranteed.
- Do not re-index/delete old documents automatically. Existing questions, documents and vectors remain untouched by setup.
- If Docling fails, scan pages fail the quality gate. Optional layout on pages with usable native text can retain native text with a warning; it does not run EasyOCR.

## Rebuild after source changes

```powershell
docker compose build backend
docker compose up -d
```

Backend and worker share the rebuilt image. Existing MongoDB, model cache and Docling cache volumes are reused.

Configuration reference: https://github.com/docling-project/docling-serve/blob/main/docs/configuration.md

