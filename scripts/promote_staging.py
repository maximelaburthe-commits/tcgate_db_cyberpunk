#!/usr/bin/env python3
"""Explicitly promote a reviewed official staging snapshot into production data."""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

def load(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def dump(path, value): Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def validate(staging):
    report = load(staging / "sync_report.json")
    catalog = load(staging / "official_catalog.json")["cards"]
    errors = []
    if report.get("mode") != "staging_only": errors.append("sync mode is not staging_only")
    if not report.get("promotionAllowed") or report.get("blocked"): errors.append("staging report blocks promotion")
    if report.get("sourceHealth") != "HEALTHY": errors.append("official source is unhealthy")
    if report.get("warnings"): errors.append("unresolved staging warnings")
    if report.get("conflicts"): errors.append("unresolved staging conflicts")
    if len(catalog) != report.get("canonicalCards"): errors.append("canonical count mismatch")
    card_ids = [card.get("officialCardId") for card in catalog]
    printings = [printing for card in catalog for printing in card.get("printings", [])]
    printing_ids = [printing.get("officialPrintingId") for printing in printings]
    if len(set(card_ids)) != len(card_ids) or any(not item for item in card_ids): errors.append("duplicate or missing official card ID")
    if len(set(printing_ids)) != len(printing_ids) or any(not item for item in printing_ids): errors.append("duplicate or missing official printing ID")
    if len(printings) != report.get("printings"): errors.append("printing count mismatch")
    if any(not re.fullmatch(r"[0-9a-f-]{36}", item or "", re.I) for item in printing_ids): errors.append("invalid official printing UUID")
    for card in catalog:
        if not card.get("officialCardId") or not card.get("name") or not card.get("sourceUrl"): errors.append("incomplete canonical record")
        for printing in card.get("printings", []):
            image = printing.get("sourceImageUrl")
            if not image or urlparse(image).scheme != "https": errors.append("invalid official image URL")
    return report, errors

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-dir", default=str(ROOT / "staging/latest"))
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    staging = Path(args.staging_dir)
    report, errors = validate(staging)
    if errors:
        print(json.dumps({"promotionAllowed": False, "errors": sorted(set(errors))}, indent=2))
        raise SystemExit(4)
    if args.check_only:
        print(json.dumps({"promotionAllowed": True, "canonicalCards": report["canonicalCards"], "printings": report["printings"]}, indent=2))
        return
    command = [sys.executable, str(ROOT / "scripts/import_official_snapshot.py"),
        "--snapshot-date", report["snapshotDate"], "--expected-cards", str(report["canonicalCards"]),
        "--expected-printings", str(report["printings"]), "--catalog-file", str(staging / "official_catalog.json")]
    subprocess.run(command, cwd=ROOT, check=True)
    manifest = load(ROOT / "manifest.json")
    manifest["database_version"] = "1.0.0"
    dump(ROOT / "manifest.json", manifest)
    db_manifest = load(ROOT / "db-manifest.json")
    db_manifest["databaseVersion"] = "1.0.0"
    db_manifest["status"] = "production-reviewed"
    db_manifest["activeSnapshot"] = report["snapshotDate"]
    dump(ROOT / "db-manifest.json", db_manifest)
    dump(ROOT / "sources" / "official" / report["snapshotDate"] / "reconciliation.json", report)
    dump(ROOT / "data/pending_unrevealed.json", {"snapshotDate": report["snapshotDate"], "slots": [], "note": "No official catalogue entry is represented as an unrevealed placeholder."})
    dump(ROOT / "data/revealed_metadata_pending.json", {"snapshotDate": report["snapshotDate"], "slots": [], "note": f"All {report['canonicalCards']} canonical cards have resolved official identities."})
    print(json.dumps({"promoted": True, "snapshot": report["snapshotDate"], "canonicalCards": report["canonicalCards"], "printings": report["printings"]}, indent=2))

if __name__ == "__main__": main()
