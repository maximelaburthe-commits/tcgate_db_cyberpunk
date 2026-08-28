#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def dump(path, value):
    (ROOT / path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


cards = load("data/cards.json")["cards"]
printings = load("data/printings.json")["printings"]
visuals = load("data/visual-identities.json")["visualIdentities"]
sets = load("data/sets.json")

runtime_cards = []
for card in cards:
    runtime_cards.append({
        **card,
        "id": card["cardId"],
        "catalog_number": None,
        "source_url": card["sourceUrl"],
    })

runtime_printings = []
asset_manifest = []
for printing in printings:
    image = printing["image"]
    runtime_printings.append({
        "printingId": printing["printingId"],
        "officialPrintingId": printing["officialPrintingId"],
        "cardId": printing["cardId"],
        "setId": printing["setId"],
        "number": printing["number"],
        "catalogNumber": printing["catalogNumber"],
        "variantKind": printing["variantKind"],
        "imageUrl": image["imageUrl"],
        "imageSource": image["imageSource"],
        "recognition": printing["recognition"],
    })
    asset_manifest.append({
        "printingId": printing["printingId"],
        "cardId": printing["cardId"],
        "sourceImageUrl": image["sourceImageUrl"],
        "imageUrl": image["imageUrl"],
        "imageSource": image["imageSource"],
        "mimeType": image["mimeType"],
        "sha256": image["sha256"],
        "width": image["width"],
        "height": image["height"],
        "status": image["status"],
    })

by_printing = {p["printingId"]: p for p in printings}
card_names = {c["cardId"]: c["name"] for c in cards}
vision = []
for identity in visuals:
    candidates = identity["candidatePrintingIds"]
    first = by_printing[candidates[0]]
    exact = identity["mode"] == "exact_printing" and len(candidates) == 1
    vision.append({
        "visualIdentityId": identity["visualIdentityId"],
        "cardId": identity["cardId"],
        "printingId": candidates[0] if exact else None,
        "candidatePrintingIds": candidates,
        "recognitionMode": "exact_printing" if exact else "shared_visual_identity",
        "referenceImageUrl": identity["referenceImageUrl"],
        "printing_id": candidates[0] if exact else identity["visualIdentityId"],
        "card_id": identity["cardId"],
        "name": card_names[identity["cardId"]],
        "set_id": first["setId"],
        "number": first["number"],
        "variant_kind": first["variantKind"],
        "image_url": identity["referenceImageUrl"],
        "image_source": first["image"]["imageSource"],
    })

dump("runtime/cards.min.json", runtime_cards)
dump("runtime/printings.min.json", runtime_printings)
dump("runtime/vision-index.json", vision)
dump("runtime/asset-manifest.json", {"assets": asset_manifest})
dump("sets.json", sets)
print(json.dumps({
    "runtimeCards": len(runtime_cards),
    "runtimePrintings": len(runtime_printings),
    "visionEntries": len(vision),
    "stableRuntimeAssets": sum(bool(a["imageUrl"]) for a in asset_manifest),
}, indent=2))
