# TCGate — Cyberpunk TCG Database

Independent Cyberpunk TCG data package. Catalogue entries, canonical gameplay
cards, and visual printings are counted independently; a gallery total is never
used as a hard-coded canonical expectation.

## Identity model

- `cardId` is TCGate's stable logical card identity.
- `officialCardId` is the official `cb-*` identity.
- `printingId` is TCGate's stable physical-printing identity.
- `officialPrintingId` is the official printing UUID.
- `visualIdentityId` describes an intrinsic artwork/face reference. It does
  not claim that a particular matcher can distinguish a physical printing.
- `recognitionProfileId` versions the audited Vision engine and descriptor.
- `recognitionGroupId` records which printings that profile can safely return
  exactly or must expose as candidates of a shared result.

Official source images are provenance (`sourceImageUrl`). Runtime consumers use
relative `displayAssetPath` and `visionAssetPath` values, resolved against the
database package base URL. No printing embeds a GitHub/CDN distribution URL.
The current snapshot contains 444 stable display assets and 444 stable Vision
derivatives.

## Data and runtime

Canonical data lives in `data/`. Generated consumer files live in `runtime/`:

- `runtime/cards.min.json`
- `runtime/printings.min.json`
- `runtime/vision-index.json`
- `runtime/canonical-vision-index.json` (stage 1: `cardId`)
- `runtime/printing-recognition-index.json` (stage 2: candidates within one `cardId`)
- `runtime/recognition-groups.json`
- `runtime/asset-manifest.json`

Goro Hands Unclean S002 is retained as a documented legacy alias of official
printing `cpp-509f743f75700687`; it does not create a 437th printing. Lucyna
PRM-N001 remains `historical_out_of_snapshot` in
`data/unresolved-printings.json` and is excluded from the active official snapshot.

## Asset direction

Display assets and Vision references remain independent from recognition
groups. An ambiguous group never replaces each printing's own future image.
`sourceImageUrl` remains provenance and may require a temporary official
signature. Signed URLs are never persisted. Historical punksim URLs may remain
in source data as provenance only; no runtime JSON depends on punksim.

### Asset ingestion

Asset ingestion is an explicit online maintenance operation and is never part
of the normal build or CI:

```bash
python scripts/ingest_assets.py
```

Display files preserve the official WEBP bytes. Vision files are generated
deterministically with Pillow 12.3.0: RGB conversion, no crop, aspect-ratio
preserving Lanczos resize into a maximum 512×716 box, then lossy WEBP quality
80, method 6, `exact=True`. Current 733×1024 sources produce 512×715 Vision
files. Re-running the local derivation must reproduce identical SHA-256 values:

```bash
python scripts/ingest_assets.py --offline-verify-vision
```

Existing official bytes are never overwritten silently. A changed source
raises `SOURCE_ASSET_CHANGED`; accepting it requires the explicit
`--replace-existing` maintenance option and a reviewed snapshot/asset update.

## Rebuild and validation

```bash
python scripts/validate_db.py
python scripts/build_runtime.py
python scripts/validate_db.py
python scripts/report_status.py
```

Synchronization is staging-only and derives live counts from the official
sitemap and card pages:

```bash
python source/sync.py
python scripts/promote_staging.py --check-only
```

Promotion is a separate, explicit operation:

```bash
python scripts/promote_staging.py
python scripts/ingest_assets.py
python scripts/build_runtime.py
python scripts/validate_db.py
```

Expected counts belong only to the dated snapshot metadata. Official data has
priority over the secondary Punksim discovery feed and historical local data.
