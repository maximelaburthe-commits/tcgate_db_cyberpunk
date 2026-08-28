# TCGate — Cyberpunk TCG Database

Independent Cyberpunk TCG data package. The active official snapshot is
`2026-08-28`: **147 canonical cards** and **436 official printings**.

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

Official source images are provenance (`sourceImageUrl`). Only controlled,
stable assets may appear in `imageUrl`. The current snapshot deliberately has
436 source images but only 133 stable runtime/Vision assets.

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
`data/unresolved-printings.json` and is excluded from the 147/436 snapshot.

## Asset direction

Display assets and Vision references remain independent from recognition
groups. An ambiguous group never replaces each printing's own future image.
No official image corpus is committed yet; `sourceImageUrl` remains provenance
and `imageUrl` remains reserved for controlled, stable assets.

## Rebuild and validation

```bash
python scripts/validate_db.py
python scripts/build_runtime.py
python scripts/validate_db.py
python scripts/report_status.py
```

To create a deliberately new official snapshot:

```bash
python scripts/import_official_snapshot.py \
  --snapshot-date YYYY-MM-DD \
  --expected-cards N \
  --expected-printings M
```

The expected counts belong to the dated snapshot metadata, not to permanent
application constants. Importing a future catalogue is an explicit operation;
CI validates and rebuilds but never commits or pushes automatically.
