#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def duplicates(values):
    seen = set()
    repeated = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return sorted(repeated)


manifest = load("db-manifest.json")
active = manifest["activeSnapshot"]
meta = load(f"sources/official/{active}/metadata.json")
snapshot_catalog = load(f"sources/official/{active}/catalog.json")["cards"]
cards = load("data/cards.json")["cards"]
printings = load("data/printings.json")["printings"]
sets = load("data/sets.json")["sets"]
visuals = load("data/visual-identities.json")["visualIdentities"]
unresolved = load("data/unresolved-printings.json")["printings"]
aliases = load("data/id-aliases.json")
errors = []

card_ids = [c.get("cardId") for c in cards]
official_card_ids = [c.get("officialCardId") for c in cards]
printing_ids = [p.get("printingId") for p in printings]
official_printing_ids = [p.get("officialPrintingId") for p in printings]
set_ids = {s["setId"] for s in sets}

if len(cards) != meta["expectedCanonicalCards"]:
    errors.append(f"canonical count {len(cards)} != {meta['expectedCanonicalCards']}")
if len(printings) != meta["expectedOfficialPrintings"]:
    errors.append(f"official printing count {len(printings)} != {meta['expectedOfficialPrintings']}")
if duplicates(card_ids): errors.append("duplicate cardId")
if duplicates(official_card_ids): errors.append("duplicate officialCardId")
if duplicates(printing_ids): errors.append("duplicate printingId")
if duplicates(official_printing_ids): errors.append("duplicate officialPrintingId")
if any(not value for value in official_card_ids): errors.append("missing officialCardId")
if any(not value for value in official_printing_ids): errors.append("missing officialPrintingId")
if any((card.get("cardId") or "").endswith("-pending") for card in cards): errors.append("pending cardId remains")
required_card_fields = {"cardId", "officialCardId", "name", "slug", "type", "color", "tags", "cost", "power", "ram", "rulesText", "status", "sourceUrl", "primaryPrintingId", "provenance"}
for card in cards:
    missing = required_card_fields - set(card)
    if missing:
        errors.append(f"missing card fields {card.get('cardId')}: {sorted(missing)}")

cards_by_official = {card["officialCardId"]: card for card in cards}
printings_by_official = {printing["officialPrintingId"]: printing for printing in printings}
snapshot_card_ids = {card["officialCardId"] for card in snapshot_catalog}
if snapshot_card_ids != set(official_card_ids):
    errors.append("officialCardId set differs from active snapshot")
snapshot_printing_ids = {
    printing["officialPrintingId"]
    for card in snapshot_catalog for printing in card["printings"]
}
if snapshot_printing_ids != set(official_printing_ids):
    errors.append("officialPrintingId set differs from active snapshot")
for snapshot_card in snapshot_catalog:
    database_card = cards_by_official.get(snapshot_card["officialCardId"])
    if not database_card:
        continue
    for snapshot_printing in snapshot_card["printings"]:
        database_printing = printings_by_official.get(snapshot_printing["officialPrintingId"])
        if database_printing and database_printing["cardId"] != database_card["cardId"]:
            errors.append(f"wrong cardId for official printing {snapshot_printing['officialPrintingId']}")

valid_cards = set(card_ids)
valid_printings = set(printing_ids)
printings_by_id = {printing["printingId"]: printing for printing in printings}
for card in cards:
    primary = printings_by_id.get(card["primaryPrintingId"])
    if not primary or primary["cardId"] != card["cardId"]:
        errors.append(f"invalid primaryPrintingId for {card['cardId']}")
for printing in printings:
    required_printing_fields = {"printingId", "officialPrintingId", "official", "cardId", "setId", "number", "catalogNumber", "variantKind", "rarity", "finish", "artist", "sourceUrl", "image", "recognition", "provenance"}
    missing = required_printing_fields - set(printing)
    if missing:
        errors.append(f"missing printing fields {printing.get('printingId')}: {sorted(missing)}")
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", printing["officialPrintingId"], re.I):
        errors.append(f"invalid officialPrintingId UUID {printing['printingId']}")
    if printing["cardId"] not in valid_cards:
        errors.append(f"orphan printing {printing['printingId']}")
    if printing["setId"] not in set_ids:
        errors.append(f"unknown set {printing['setId']} in {printing['printingId']}")
    image = printing["image"]
    if not image.get("sourceImageUrl"):
        errors.append(f"missing sourceImageUrl {printing['printingId']}")
    runtime_url = image.get("imageUrl")
    if runtime_url:
        query = {key.lower() for key in parse_qs(urlparse(runtime_url).query)}
        signed = {"expires", "signature", "key-pair-id", "x-amz-signature", "x-amz-expires"}
        if query & signed:
            errors.append(f"temporary signed imageUrl {printing['printingId']}")
    recognition = printing["recognition"]
    if recognition["enabled"] and not runtime_url:
        errors.append(f"recognition without stable image {printing['printingId']}")

for identity in visuals:
    candidates = identity.get("candidatePrintingIds") or []
    if not candidates:
        errors.append(f"empty visual identity {identity.get('visualIdentityId')}")
    if any(pid not in valid_printings for pid in candidates):
        errors.append(f"invalid printing in visual identity {identity.get('visualIdentityId')}")
    if identity["cardId"] not in valid_cards:
        errors.append(f"invalid card in visual identity {identity.get('visualIdentityId')}")
    if identity["mode"] == "exact_printing" and len(candidates) != 1:
        errors.append(f"exact visual identity has {len(candidates)} candidates")
    if identity["mode"] == "shared_visual_identity" and len(candidates) < 2:
        errors.append("shared visual identity must have multiple candidates")

visual_ids = {identity["visualIdentityId"] for identity in visuals}
for printing in printings:
    recognition = printing["recognition"]
    if recognition["enabled"] and recognition.get("visualIdentityId") not in visual_ids:
        errors.append(f"missing visual identity for {printing['printingId']}")

goro = [p for p in unresolved if p.get("variantKind") == "legacy_unresolved" and p.get("number") == "S002"]
if len(goro) != 1 or goro[0].get("official") is not False or goro[0].get("officialPrintingId") is not None:
    errors.append("Goro S002 exception invalid")
lucyna = [p for p in unresolved if p.get("cardId") == "cp-lucyna-kushinada"]
if len(lucyna) != 1 or lucyna[0].get("snapshotStatus") != "historical_out_of_snapshot":
    errors.append("Lucyna exception invalid")
if len(aliases.get("cards", [])) != 5:
    errors.append("five placeholder card aliases required")
if len(aliases.get("printings", [])) != 5:
    errors.append("five placeholder printing aliases required")

result = {
    "ok": not errors,
    "snapshot": active,
    "cards": len(cards),
    "officialPrintings": len(printings),
    "visualIdentities": len(visuals),
    "exactVisualPrintings": sum(v["mode"] == "exact_printing" for v in visuals),
    "sharedVisualPrintings": sum(len(v["candidatePrintingIds"]) for v in visuals if v["mode"] == "shared_visual_identity"),
    "sourceImages": sum(bool(p["image"].get("sourceImageUrl")) for p in printings),
    "stableRuntimeAssets": sum(bool(p["image"].get("imageUrl")) for p in printings),
    "unresolved": len(unresolved),
    "errors": errors,
}
print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(1 if errors else 0)
