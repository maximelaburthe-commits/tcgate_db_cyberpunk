# TCGate — Cyberpunk TCG Database

Independent Cyberpunk TCG data package. The active official snapshot is
`2026-08-28`: **147 canonical cards** and **436 official printings**.

## Identity model

- `cardId` is TCGate's stable logical card identity.
- `officialCardId` is the official `cb-*` identity.
- `printingId` is TCGate's stable physical-printing identity.
- `officialPrintingId` is the official printing UUID.
- `visualIdentityId` describes an artwork/face that Vision can actually
  distinguish. It never merges physical printings.

Official source images are provenance (`sourceImageUrl`). Only controlled,
stable assets may appear in `imageUrl`. The current snapshot deliberately has
436 source images but only 133 stable runtime/Vision assets.

## Data and runtime

Canonical data lives in `data/`. Generated consumer files live in `runtime/`:

- `runtime/cards.min.json`
- `runtime/printings.min.json`
- `runtime/vision-index.json`
- `runtime/asset-manifest.json`

Goro Hands Unclean S002 and Lucyna PRM-N001 are retained explicitly in
`data/unresolved-printings.json` and excluded from the official 436 count.

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
