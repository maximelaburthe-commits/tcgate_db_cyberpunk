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
profiles = load("data/recognition-profiles.json")["recognitionProfiles"]
recognition_groups = load("data/recognition-groups.json")["recognitionGroups"]
asset_metadata = load("data/asset-metadata.json")
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
        "displayAssetPath": image["displayAssetPath"],
        "visionAssetPath": image["visionAssetPath"],
        "imageUrl": image["displayAssetPath"],
        "imageSource": image["imageSource"],
        "displaySha256": image["displaySha256"],
        "visionSha256": image["visionSha256"],
        "recognition": printing["recognition"],
    })

by_printing = {p["printingId"]: p for p in printings}
card_names = {c["cardId"]: c["name"] for c in cards}
group_by_printing = {
    printing_id: group
    for group in recognition_groups
    for printing_id in group["printingIds"]
}
vision = []
for identity in visuals:
    candidates = identity["candidatePrintingIds"]
    first = by_printing[candidates[0]]
    group = group_by_printing[first["printingId"]]
    vision.append({
        "refId": identity["visualIdentityId"],
        "visualIdentityId": identity["visualIdentityId"],
        "cardId": identity["cardId"],
        "printingId": first["printingId"],
        "candidatePrintingIds": group["candidatePrintingIds"],
        "recognitionMode": group["mode"],
        "recognition": {"eligible": True, "mode": group["mode"], "recognitionGroupId": group["recognitionGroupId"]},
        "referenceImageUrl": identity["referenceImageUrl"],
        "visionAssetPath": identity["referenceImageUrl"],
        "displayAssetPath": first["image"]["displayAssetPath"],
        "imageUrl": identity["referenceImageUrl"],
        "variantKind": first["variantKind"],
        "printing_id": first["printingId"],
        "card_id": identity["cardId"],
        "name": card_names[identity["cardId"]],
        "set_id": first["setId"],
        "number": first["number"],
        "variant_kind": first["variantKind"],
        "image_url": identity["referenceImageUrl"],
        "image_source": "local_db_asset",
    })

dump("runtime/cards.min.json", runtime_cards)
dump("runtime/printings.min.json", runtime_printings)
dump("runtime/vision-index.json", vision)
canonical_by_card = {}
for entry in vision:
    canonical_by_card.setdefault(entry["cardId"], {
        "cardId": entry["cardId"],
        "visualIdentityId": entry["visualIdentityId"],
        "referenceImageUrl": entry["referenceImageUrl"],
        "name": entry["name"],
        "visionAssetPath": entry["visionAssetPath"],
        "assetStatus": "stable_local_assets",
    })
for card in cards:
    if card["cardId"] in canonical_by_card:
        continue
    primary = by_printing[card["primaryPrintingId"]]
    canonical_by_card[card["cardId"]] = {
        "cardId": card["cardId"],
        "visualIdentityId": None,
        "referenceImageUrl": primary["image"]["visionAssetPath"],
        "visionAssetPath": primary["image"]["visionAssetPath"],
        "name": card["name"],
        "assetStatus": primary["image"]["status"],
    }
canonical_index = {
    "recognitionProfileId": profiles[0]["recognitionProfileId"],
    "stage": "canonical_card",
    "references": [canonical_by_card[card["cardId"]] for card in cards],
}
printing_index = {
    "recognitionProfileId": profiles[0]["recognitionProfileId"],
    "stage": "printing_within_card",
    "cards": [],
}
for card_id in sorted({group["cardId"] for group in recognition_groups}):
    groups = []
    for group in recognition_groups:
        if group["cardId"] != card_id:
            continue
        groups.append({
            **group,
            "references": [
                {
                    "printingId": printing_id,
                    "referenceImageUrl": by_printing[printing_id]["image"]["visionAssetPath"],
                    "visionAssetPath": by_printing[printing_id]["image"]["visionAssetPath"],
                    "assetStatus": by_printing[printing_id]["image"]["status"],
                }
                for printing_id in group["printingIds"]
            ],
        })
    printing_index["cards"].append({"cardId": card_id, "recognitionGroups": groups})
dump("runtime/canonical-vision-index.json", canonical_index)
dump("runtime/printing-recognition-index.json", printing_index)
dump("runtime/recognition-groups.json", {
    "recognitionProfileId": profiles[0]["recognitionProfileId"],
    "recognitionGroups": recognition_groups,
})
display_assets = []
vision_assets = []
for asset in asset_metadata["assets"]:
    common = {
        "printingId": asset["printingId"],
        "officialPrintingId": asset["officialPrintingId"],
        "cardId": asset["cardId"],
    }
    display_assets.append({**common, **asset["display"], "provenance": asset["provenance"]})
    vision_assets.append({**common, **asset["vision"]})
dump("runtime/asset-manifest.json", {
    "assetProfileVersion": asset_metadata["assetProfileVersion"],
    "displayAssets": display_assets,
    "visionAssets": vision_assets,
})
meta = load(f"sources/official/{load('db-manifest.json')['activeSnapshot']}/metadata.json")
ready = sum(bool(card.get("type") and card.get("rulesText")) for card in cards)
standard = sum(printing["variantKind"] == "standard" for printing in printings)
iconic = sum(printing["variantKind"] == "iconic" for printing in printings)
stable_assets = sum(bool(printing["image"].get("displayAssetPath") and printing["image"].get("visionAssetPath")) for printing in printings)
vision_eligible = sum(bool(printing["recognition"].get("enabled") and printing["image"].get("visionAssetPath")) for printing in printings)
dump("data/coverage.json", {
    "snapshotDate": meta["snapshotDate"],
    "officialCatalogEntries": meta.get("officialCatalogEntries", len(cards)),
    "expectedCanonicalCards": len(cards), "canonicalCards": len(cards),
    "readyCards": ready, "incompleteCards": len(cards) - ready,
    "expectedOfficialPrintings": len(printings), "officialPrintings": len(printings),
    "standardPrintings": standard, "iconicPrintings": iconic,
    "otherVariants": len(printings) - standard - iconic,
    "starterPrintings": sum("starter" in p["setId"] for p in printings),
    "promoPrintings": sum(p["variantKind"] == "promo_art" for p in printings),
    "betaPrintings": sum("beta" in p["setId"] for p in printings),
    "visualIdentities": len(visuals), "visionEligible": vision_eligible,
    "visionMissing": len(printings) - vision_eligible,
    "sourceImages": sum(bool(p["image"].get("sourceImageUrl")) for p in printings),
    "missingImages": sum(not p["image"].get("sourceImageUrl") for p in printings),
    "stableRuntimeAssets": stable_assets, "unresolvedPrintings": len(load("data/unresolved-printings.json")["printings"]),
    "complete": len(cards) == meta["expectedCanonicalCards"] and len(printings) == meta["expectedOfficialPrintings"],
    "notes": "Official catalogue entries, canonical cards, and visual printings are reported separately.",
})
dump("sets.json", sets)
print(json.dumps({
    "runtimeCards": len(runtime_cards),
    "runtimePrintings": len(runtime_printings),
    "visionEntries": len(vision),
    "canonicalVisionReferences": len(canonical_index["references"]),
    "recognitionGroups": len(recognition_groups),
    "stableRuntimeAssets": len(display_assets),
}, indent=2))
