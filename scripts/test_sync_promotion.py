#!/usr/bin/env python3
import json, tempfile
from pathlib import Path
from promote_staging import validate

def dump(path, value): path.write_text(json.dumps(value), encoding="utf-8")

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    card = {"officialCardId": "cb-test", "name": "Test", "sourceUrl": "https://cyberpunktcg.com/cards/test", "printings": [{"officialPrintingId": "12345678-1234-4123-8123-123456789abc", "sourceImageUrl": "https://example.test/card.webp"}]}
    report = {"mode": "staging_only", "promotionAllowed": True, "blocked": False, "sourceHealth": "HEALTHY", "warnings": [], "conflicts": [], "canonicalCards": 1, "printings": 1}
    dump(root / "official_catalog.json", {"cards": [card]}); dump(root / "sync_report.json", report)
    _, errors = validate(root); assert not errors
    report["sourceHealth"] = "UNAVAILABLE"; report["promotionAllowed"] = False; report["blocked"] = True
    dump(root / "sync_report.json", report)
    _, errors = validate(root); assert errors
    report.update(sourceHealth="HEALTHY", promotionAllowed=True, blocked=False, warnings=[{"kind": "blocking"}])
    dump(root / "sync_report.json", report)
    _, errors = validate(root); assert "unresolved staging warnings" in errors
    report["warnings"] = []; dump(root / "sync_report.json", report)
    card["printings"][0]["sourceImageUrl"] = ""
    dump(root / "official_catalog.json", {"cards": [card]})
    _, errors = validate(root); assert "invalid official image URL" in errors
sync_source = (Path(__file__).resolve().parents[1] / "source/sync.py").read_text(encoding="utf-8")
assert 'dump(ROOT / "data/' not in sync_source and "dump(ROOT/'data/" not in sync_source
print("SYNC_PROMOTION_GUARDS_OK")
