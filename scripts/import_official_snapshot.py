#!/usr/bin/env python3
"""Import a dated Cyberpunk TCG official catalogue snapshot.

The importer is deliberately explicit: it reads the official sitemap and card
pages, preserves existing TCGate identifiers, and never promotes signed source
URLs to runtime asset URLs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = "https://cyberpunktcg.com"
UA = {"User-Agent": "TCGateCyberpunkDB/1.0 (+manual official snapshot import)"}
SET_IDS = {
    "welcometonightcityretail": ("wtnc-retail", "retail"),
    "welcometonightcitybeta": ("wtnc-beta", "beta"),
    "embracingpowerretailstarterdeck": ("embracing-power-retail", "starter"),
    "embracingpowerbetastarterdeck": ("embracing-power-beta", "starter"),
    "theheistretailstarterdeck": ("the-heist-retail", "starter"),
    "theheistbetastarterdeck": ("the-heist-beta", "starter"),
    "arasakademodeck": ("arasaka-demo", "demo"),
    "mercdemodeck": ("merc-demo", "demo"),
    "boxtoppersretail": ("box-toppers-retail", "box_topper"),
    "boxtoppersbeta": ("box-toppers-beta", "box_topper"),
    "prereleasebeta": ("pre-release-beta", "prerelease"),
    "PRM01": ("set-1-promos", "promo"),
}
PLACEHOLDER_BY_NUMBER = {
    "008": "cp-chrome-fang", "017": "cp-ruthless-lowlife",
    "035": "cp-shattered-memories", "047": "cp-heywood-ripperdoc",
    "080": "cp-maxtac-av",
}
PLACEHOLDER_PRINTING_IDS = {
    "008": "cpp-333ccece2b074ead", "017": "cpp-fefa880213775f50",
    "035": "cpp-30c93860388729e4", "047": "cpp-89189cddf5326537",
    "080": "cpp-6e25902a960c3aeb",
}
RECOGNITION_PROFILE_ID = "cyberpunk-v5-fast-72x108"
RECOGNITION_AUDIT_DATE = "2026-08-28"


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch(url: str) -> str:
    request = Request(url, headers=UA)
    with urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8")


def normalized(value: str | None) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    value = value.replace("’", "'").replace("—", "-").replace("–", "-")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def slugify(value: str) -> str:
    return normalized(value).replace(" ", "-")


def field(text: str, name: str):
    match = re.search(rf'{re.escape(name)}:"([^"\\]*(?:\\.[^"\\]*)*)"', text)
    if not match:
        return None
    return json.loads('"' + match.group(1) + '"')


def scalar(text: str, name: str):
    match = re.search(rf'{re.escape(name)}:(null|!0|!1|-?\d+)', text)
    if not match:
        return None
    value = match.group(1)
    if value == "null":
        return None
    if value == "!0":
        return True
    if value == "!1":
        return False
    return int(value)


def parse_card(url: str) -> dict:
    html = fetch(url)
    printing_at = html.index("printings:$R[")
    start = html.rfind('external_id:"', 0, printing_at)
    head = html[start:printing_at]
    end = html.index("],selected_printing_id", printing_at)
    printing_text = html[printing_at:end]
    printing_pattern = re.compile(
        r'\{id:"([^"]+)",collector_number:"([^"]*)",image_url:"([^"]*)",'
        r'source_image_url:"([^"]*)",set:\$R\[\d+\]=\{code:"([^"]*)",name:"([^"]*)"\},'
        r'rarity:"([^"]*)",finish:([^,}]*),artist:"([^"]*)"\}'
    )
    printings = []
    for match in printing_pattern.finditer(printing_text):
        printings.append({
            "officialPrintingId": match.group(1),
            "number": match.group(2),
            "sourceImageUrl": match.group(4),
            "officialSetCode": match.group(5),
            "setName": match.group(6),
            "rarity": match.group(7),
            "finish": None if match.group(8) == "null" else match.group(8),
            "artist": match.group(9),
        })
    if not printings:
        raise ValueError(f"No printings parsed from {url}")
    return {
        "officialCardId": field(head, "external_id"),
        "name": field(head, "name"),
        "displayName": field(head, "display_name"),
        "slug": field(head, "slug"),
        "type": field(head, "card_type"),
        "color": field(head, "color"),
        "cost": scalar(head, "cost"),
        "power": scalar(head, "power"),
        "ram": scalar(head, "ram"),
        "rulesText": field(head, "rules_text"),
        "sourceUrl": url,
        "selectedOfficialPrintingId": field(html[printing_at:], "selected_printing_id"),
        "printings": printings,
    }


def variant_kind(item: dict) -> str:
    code, number = item["officialSetCode"], item["number"]
    digits = int((re.search(r"\d+", number) or ["0"])[0])
    if code == "PRM01":
        return "promo_art"
    if code == "welcometonightcityretail" and number == "005b":
        return "alternate_art"
    if code == "welcometonightcitybeta" and digits > 140:
        return "alternate_art"
    return "standard"


def deterministic_printing_id(card_id: str, set_id: str, number: str) -> str:
    value = f"{card_id}|{set_id}:{number}".encode()
    return "cpp-" + hashlib.sha1(value).hexdigest()[:16]


def recognition_group_id(card_id: str, mode: str, printing_ids: list[str]) -> str:
    value = f"{RECOGNITION_PROFILE_ID}|{card_id}|{mode}|{'|'.join(sorted(printing_ids))}".encode()
    return "cprg-" + hashlib.sha1(value).hexdigest()[:16]


def build_recognition_groups(printings: list[dict]) -> list[dict]:
    """Materialize the conservative, versioned result of the 2026-08-28 audit."""
    by_card: dict[str, list[dict]] = {}
    for printing in printings:
        by_card.setdefault(printing["cardId"], []).append(printing)
    groups = []
    for card_id in sorted(by_card):
        exact = sorted(
            (p for p in by_card[card_id] if p["variantKind"] == "promo_art"),
            key=lambda p: p["printingId"],
        )
        exact_ids = {p["printingId"] for p in exact}
        for printing in exact:
            ids = [printing["printingId"]]
            groups.append({
                "recognitionGroupId": recognition_group_id(card_id, "exact", ids),
                "recognitionProfileId": RECOGNITION_PROFILE_ID,
                "cardId": card_id,
                "printingIds": ids,
                "candidatePrintingIds": ids,
                "mode": "exact",
                "reason": "exact_robust_in_2026_08_28_audit",
                "evidence": {
                    "auditDate": RECOGNITION_AUDIT_DATE,
                    "classification": "EXACT_ROBUST",
                    "source": "TCGate checkpoint 3C offline matcher audit",
                },
            })
        shared_ids = sorted(p["printingId"] for p in by_card[card_id] if p["printingId"] not in exact_ids)
        if shared_ids:
            groups.append({
                "recognitionGroupId": recognition_group_id(card_id, "shared", shared_ids),
                "recognitionProfileId": RECOGNITION_PROFILE_ID,
                "cardId": card_id,
                "printingIds": shared_ids,
                "candidatePrintingIds": shared_ids,
                "mode": "shared",
                "reason": "edition_details_not_robust_at_current_descriptor",
                "evidence": {
                    "auditDate": RECOGNITION_AUDIT_DATE,
                    "source": "TCGate checkpoint 3C offline matcher audit",
                    "policy": "fragile/shared remain shared; distinct artwork stays conservative until per-printing evidence is versioned",
                },
            })
    return groups


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-date", default=date.today().isoformat())
    parser.add_argument("--expected-cards", type=int, required=True)
    parser.add_argument("--expected-printings", type=int, required=True)
    args = parser.parse_args()

    old_cards = load("data/cards.json")["cards"]
    old_printings = load("data/printings.json")["printings"]
    asset_metadata = load("data/asset-metadata.json")["assets"] if (ROOT / "data/asset-metadata.json").exists() else []
    assets_by_printing = {asset["printingId"]: asset for asset in asset_metadata}
    old_unresolved = load("data/unresolved-printings.json")["printings"] if (ROOT / "data/unresolved-printings.json").exists() else []
    old_by_name = {normalized(c.get("name")): c for c in old_cards if c.get("name")}
    old_print_by_key = {
        (p.get("card_id") or p.get("cardId"), p.get("set_id") or p.get("setId"), p["number"]): p
        for p in old_printings
    }
    sitemap = fetch(f"{OFFICIAL}/sitemap.xml")
    urls = re.findall(r"<loc>(https://cyberpunktcg\.com/cards/[^<]+)</loc>", sitemap)
    if len(urls) != args.expected_cards:
        raise SystemExit(f"Expected {args.expected_cards} card URLs, found {len(urls)}")
    official_cards = [parse_card(url) for url in urls]
    if sum(len(c["printings"]) for c in official_cards) != args.expected_printings:
        raise SystemExit("Official printing count does not match requested snapshot")

    snapshot_dir = ROOT / "sources" / "official" / args.snapshot_date
    dump(snapshot_dir / "metadata.json", {
        "snapshotDate": args.snapshot_date,
        "expectedCanonicalCards": args.expected_cards,
        "expectedOfficialPrintings": args.expected_printings,
        "source": f"{OFFICIAL}/cards",
        "sitemap": f"{OFFICIAL}/sitemap.xml",
    })
    dump(snapshot_dir / "catalog.json", {"cards": official_cards})

    cards, printings, sets = [], [], {}
    aliases = {"cards": [], "printings": []}
    official_id_to_internal = {}
    for source_card in official_cards:
        old = old_by_name.get(normalized(source_card["name"]))
        primary = next(
            (p for p in source_card["printings"]
             if p["officialPrintingId"] == source_card["selectedOfficialPrintingId"]),
            source_card["printings"][0],
        )
        primary_set = SET_IDS[primary["officialSetCode"]][0]
        if old:
            card_id = old.get("id") or old["cardId"]
        elif primary_set == "wtnc-retail" and primary["number"] in PLACEHOLDER_BY_NUMBER:
            card_id = PLACEHOLDER_BY_NUMBER[primary["number"]]
        else:
            card_id = "cp-" + slugify(source_card["name"])
        official_id_to_internal[source_card["officialCardId"]] = card_id
        old_primary = old_print_by_key.get((card_id, primary_set, primary["number"]))
        primary_id = (old_primary.get("id") or old_primary["printingId"]) if old_primary else deterministic_printing_id(card_id, primary_set, primary["number"])
        tags = old.get("tags", []) if old else []
        cards.append({
            "cardId": card_id,
            "officialCardId": source_card["officialCardId"],
            "name": source_card["name"],
            "slug": source_card["slug"],
            "type": source_card["type"] or (old.get("type") if old else None),
            "color": source_card["color"] or (old.get("color") if old else None),
            "tags": tags,
            "cost": source_card["cost"] if source_card["cost"] is not None else (old.get("cost") if old else None),
            "power": source_card["power"] if source_card["power"] is not None else (old.get("power") if old else None),
            "ram": source_card["ram"] if source_card["ram"] is not None else (old.get("ram") if old else None),
            "rulesText": source_card["rulesText"] or (old.get("rules_text") if old else None),
            "status": "verified_official",
            "sourceUrl": source_card["sourceUrl"],
            "primaryPrintingId": primary_id,
            "provenance": {"authority": "official", "lastVerifiedAt": args.snapshot_date},
        })
        for item in source_card["printings"]:
            set_id, set_kind = SET_IDS[item["officialSetCode"]]
            sets[set_id] = {
                "setId": set_id, "officialCode": item["officialSetCode"],
                "name": item["setName"], "kind": set_kind,
                "source": "official_cyberpunk_tcg",
            }
            old_print = old_print_by_key.get((card_id, set_id, item["number"]))
            printing_id = (old_print.get("id") or old_print["printingId"]) if old_print else deterministic_printing_id(card_id, set_id, item["number"])
            old_image = (old_print or {}).get("image") or {}
            old_recognition = (old_print or {}).get("recognition") or {}
            historical_image = old_image.get("historicalImageUrl") or old_image.get("remote_url") or old_image.get("imageUrl")
            asset = assets_by_printing.get(printing_id)
            vision_asset_path = asset["vision"]["path"] if asset else None
            printings.append({
                "printingId": printing_id,
                "officialPrintingId": item["officialPrintingId"],
                "official": True,
                "cardId": card_id,
                "setId": set_id,
                "number": item["number"],
                "catalogNumber": f"{set_id}:{item['number']}",
                "variantKind": variant_kind(item),
                "rarity": item["rarity"], "finish": item["finish"], "artist": item["artist"],
                "sourceUrl": source_card["sourceUrl"] + "?printing=" + item["officialPrintingId"],
                "image": {
                    "displayAssetPath": asset["display"]["path"] if asset else None,
                    "visionAssetPath": vision_asset_path,
                    "sourceImageUrl": item["sourceImageUrl"],
                    "imageSource": "official_cyberpunk_tcg",
                    "historicalImageUrl": historical_image,
                    "displaySha256": asset["display"]["sha256"] if asset else None,
                    "visionSha256": asset["vision"]["sha256"] if asset else None,
                    "displayWidth": asset["display"]["width"] if asset else None,
                    "displayHeight": asset["display"]["height"] if asset else None,
                    "visionWidth": asset["vision"]["width"] if asset else None,
                    "visionHeight": asset["vision"]["height"] if asset else None,
                    "status": "stable_local_assets" if asset else "source_only",
                },
                "recognition": {
                    "enabled": bool(old_recognition.get("enabled") and vision_asset_path),
                    "visualIdentityId": ("cpvi-" + printing_id[4:]) if old_recognition.get("enabled") and vision_asset_path else None,
                    "referenceImageUrl": vision_asset_path if old_recognition.get("enabled") and vision_asset_path else None,
                    "status": "reference_available" if old_recognition.get("enabled") and vision_asset_path else "not_in_legacy_index",
                },
                "provenance": {"authority": "official", "lastVerifiedAt": args.snapshot_date},
            })

    # Explicit aliases for replaced placeholder card identities.
    for number, card_id in PLACEHOLDER_BY_NUMBER.items():
        aliases["cards"].append({"from": f"cp-wntc-{number}-pending", "to": card_id, "reason": "official_identity_resolved"})
        resolved = next(
            p for p in printings
            if p["cardId"] == card_id and p["setId"] == "wtnc-retail" and p["number"] == number
        )
        aliases["printings"].append({
            "from": PLACEHOLDER_PRINTING_IDS[number],
            "to": resolved["printingId"],
            "reason": "placeholder_card_identity_resolved",
        })

    # Historical records remain visible but outside the current official snapshot.
    lucyna_existing = next((p for p in old_unresolved if p.get("cardId") == "cp-lucyna-kushinada"), None)
    if not lucyna_existing:
        lucyna_existing = {
            "printingId": "cpp-7d2b0fc4aba70ff4", "officialPrintingId": None,
            "official": False, "snapshotStatus": "historical_out_of_snapshot",
            "cardId": "cp-lucyna-kushinada", "name": "Lucyna Kushinada — Fresh Beginnings",
            "setId": "promo-cards", "number": "N001", "variantKind": "promo_art",
            "reason": "Not present in the active official 147/436 snapshot",
        }
    # Goro S002 is a documented alias of the official EP Retail 012 printing;
    # it remains traceable without creating an unofficial 437th printing.
    unresolved = [lucyna_existing]
    goro_official = next(
        p for p in printings
        if p["printingId"] == "cpp-509f743f75700687"
        and p["officialPrintingId"] == "2ba68619-7050-44c5-b0ce-b32d48b8f40f"
    )
    aliases["printings"].append({
        "from": "legacy-goro-hands-unclean-s002",
        "to": goro_official["printingId"],
        "reason": "pixel_identical_official_match",
        "auditDate": RECOGNITION_AUDIT_DATE,
        "evidence": {
            "legacyNumber": "S002",
            "officialPrintingId": goro_official["officialPrintingId"],
            "pixelComparison": "identical",
        },
    })
    visual = []
    for item in printings:
        if item["recognition"]["enabled"]:
            visual.append({
                "visualIdentityId": item["recognition"]["visualIdentityId"],
                "cardId": item["cardId"], "mode": "intrinsic_face_reference",
                "printingId": item["printingId"],
                "candidatePrintingIds": [item["printingId"]],
                "referenceImageUrl": item["recognition"]["referenceImageUrl"],
                "evidence": "existing_stable_reference_asset",
            })
    dump(ROOT / "data/cards.json", {"cards": cards})
    dump(ROOT / "data/printings.json", {"printings": printings})
    dump(ROOT / "data/sets.json", {"sets": list(sets.values())})
    dump(ROOT / "data/visual-identities.json", {"visualIdentities": visual})
    dump(ROOT / "data/recognition-groups.json", {"recognitionGroups": build_recognition_groups(printings)})
    dump(ROOT / "data/unresolved-printings.json", {"printings": unresolved})
    dump(ROOT / "data/id-aliases.json", aliases)
    print(json.dumps({"cards": len(cards), "officialPrintings": len(printings), "visualIdentities": len(visual)}, indent=2))


if __name__ == "__main__":
    main()
