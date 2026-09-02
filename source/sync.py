#!/usr/bin/env python3
"""Synchronize official and secondary sources into staging only."""
from __future__ import annotations
import argparse, concurrent.futures, json, re, sys
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.import_official_snapshot import OFFICIAL, UA, parse_card, variant_kind  # noqa: E402
CONF = json.loads((ROOT / "source/source.json").read_text(encoding="utf-8"))

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def get(url):
    response = requests.get(url, headers=UA, timeout=45, allow_redirects=True)
    response.raise_for_status()
    return response

def official_health():
    source = CONF["sources"][0]
    result = {"source": source["id"], "url": source["url"], "ok": False}
    try:
        response = get(source["url"])
        result.update(httpStatus=response.status_code, finalUrl=response.url)
        if urlparse(response.url).netloc != urlparse(source["url"]).netloc:
            result["status"] = "CROSS_DOMAIN_REDIRECT"
            return result
        body = re.sub(r"<[^>]+>", " ", response.text)
        match = re.search(r"Showing\s+\d+[–-]\d+\s+of\s+(\d+)\s+cards", body, re.I)
        result["reportedCatalogEntries"] = int(match.group(1)) if match else None
        result["status"] = "HEALTHY" if "Card Database" in body else "STRUCTURE_CHANGED"
        result["ok"] = result["status"] == "HEALTHY"
    except Exception as error:
        result.update(status="UNAVAILABLE", error=str(error))
    return result

def official_catalog():
    sitemap = get(f"{OFFICIAL}/sitemap.xml").text
    urls = [url for url in re.findall(r"<loc>([^<]+)</loc>", sitemap) if url.startswith(f"{OFFICIAL}/cards/")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        return sorted(executor.map(parse_card, urls), key=lambda card: card["sourceUrl"])

def secondary_records():
    rows = []
    for item in get(CONF["sources"][1]["url"]).json():
        number = item.get("number") or ""
        if re.match(r"^(WNTC|EP|HEIST|PRM01)-", number):
            rows.append({key: item.get(key) for key in ["url", "name", "type", "subtype", "cost", "power", "ram", "set", "number", "illustrated_by", "eddie", "image", "color"]})
    return rows

def main():
    parser = argparse.ArgumentParser(description="Fetch sources into staging; never writes production data.")
    parser.add_argument("--output-dir", default=str(ROOT / "staging/latest"))
    parser.add_argument("--snapshot-date", default=date.today().isoformat())
    args = parser.parse_args()
    output = Path(args.output_dir)
    health, warnings, conflicts = official_health(), [], []
    try:
        official, official_error = (official_catalog() if health["ok"] else []), None
    except Exception as error:
        official, official_error = [], str(error)
        health.update(ok=False, status="UNAVAILABLE", error=official_error)
    try:
        secondary, secondary_error = secondary_records(), None
    except Exception as error:
        secondary, secondary_error = [], str(error)
    current_cards = json.loads((ROOT / "data/cards.json").read_text(encoding="utf-8"))["cards"]
    current_printings = json.loads((ROOT / "data/printings.json").read_text(encoding="utf-8"))["printings"]
    current_by_official = {card.get("officialCardId"): card for card in current_cards}
    live_by_official = {card.get("officialCardId"): card for card in official}
    current_print_ids = {printing.get("officialPrintingId") for printing in current_printings}
    live_printings = [printing for card in official for printing in card["printings"]]
    live_print_ids = {printing["officialPrintingId"] for printing in live_printings}
    if len(live_by_official) != len(official) or len(live_print_ids) != len(live_printings):
        conflicts.append({"kind": "duplicate_official_ids"})
    mechanical_fields = ("name", "type", "color", "cost", "power", "ram", "rulesText")
    changed_cards = []
    for official_id in sorted(set(current_by_official) & set(live_by_official)):
        old, new = current_by_official[official_id], live_by_official[official_id]
        changed = [field for field in mechanical_fields if old.get(field) != new.get(field)]
        if changed:
            changed_cards.append({"officialCardId": official_id, "name": new["name"], "fields": changed})
    missing = sorted(set(current_by_official) - set(live_by_official))
    drop_ratio = (len(current_cards) - len(official)) / max(len(current_cards), 1) if official else 1.0
    if missing: warnings.append({"kind": "production_cards_missing_from_official", "cardIds": missing})
    if secondary_error: warnings.append({"kind": "secondary_source_unavailable", "message": secondary_error})
    if official_error: warnings.append({"kind": "official_source_unavailable", "message": official_error})
    variants = Counter(variant_kind(printing) for printing in live_printings)
    standard, iconic = variants["standard"], variants["iconic"]
    blocking = not health["ok"] or bool(conflicts) or bool(missing) or drop_ratio > CONF["safety"]["block_large_record_drop_ratio"] or not official or any(not p.get("sourceImageUrl") for p in live_printings)
    report = {
        "mode": "staging_only", "snapshotDate": args.snapshot_date,
        "sourceHealth": health["status"], "officialHealth": health,
        "officialRecords": len(official), "officialCatalogEntries": len(official),
        "secondaryRecords": len(secondary), "canonicalCards": len(official),
        "readyCards": sum(bool(c.get("type") and c.get("rulesText")) for c in official),
        "incompleteCards": sum(not (c.get("type") and c.get("rulesText")) for c in official),
        "printings": len(live_printings), "standardPrintings": standard,
        "iconicPrintings": iconic, "otherVariants": len(live_printings) - standard - iconic,
        "starterPrintings": sum("starterdeck" in p.get("officialSetCode", "").lower() for p in live_printings),
        "promoPrintings": sum(p.get("officialSetCode") == "PRM01" for p in live_printings),
        "betaPrintings": sum("beta" in p.get("officialSetCode", "").lower() for p in live_printings),
        "visionEligible": sum(bool(p.get("sourceImageUrl")) for p in live_printings),
        "newCards": sorted(set(live_by_official) - set(current_by_official)),
        "changedCards": changed_cards, "missingFromOfficial": missing,
        "variantsAdded": sorted(live_print_ids - current_print_ids),
        "variantsRemoved": sorted(current_print_ids - live_print_ids),
        "conflicts": conflicts, "warnings": warnings, "catalogDropRatio": drop_ratio,
        "blocked": blocking, "promotionAllowed": not blocking,
    }
    dump(output / "official_catalog.json", {"cards": official})
    dump(output / "secondary_snapshot.json", {"records": secondary})
    dump(output / "sync_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(4 if blocking else 0)

if __name__ == "__main__": main()
