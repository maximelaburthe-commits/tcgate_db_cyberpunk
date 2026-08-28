#!/usr/bin/env python3
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image

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
profiles = load("data/recognition-profiles.json")["recognitionProfiles"]
recognition_groups = load("data/recognition-groups.json")["recognitionGroups"]
asset_metadata = load("data/asset-metadata.json")["assets"]
unresolved = load("data/unresolved-printings.json")["printings"]
aliases = load("data/id-aliases.json")
errors = []


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_asset_path(value, expected_prefix):
    if not isinstance(value, str) or not value.startswith(expected_prefix) or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and path.suffix.lower() == ".webp"

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
    display_path = image.get("displayAssetPath")
    vision_path = image.get("visionAssetPath")
    if not valid_asset_path(display_path, "assets/display/"):
        errors.append(f"invalid displayAssetPath {printing['printingId']}")
    if not valid_asset_path(vision_path, "assets/vision/"):
        errors.append(f"invalid visionAssetPath {printing['printingId']}")
    recognition = printing["recognition"]
    if recognition["enabled"] and not vision_path:
        errors.append(f"recognition without stable image {printing['printingId']}")

asset_by_printing = {asset.get("printingId"): asset for asset in asset_metadata}
if len(asset_metadata) != 436 or len(asset_by_printing) != 436:
    errors.append("asset metadata must contain 436 unique printings")
expected_display_paths = set()
expected_vision_paths = set()
for printing_id in valid_printings:
    asset = asset_by_printing.get(printing_id)
    if not asset:
        errors.append(f"missing asset metadata {printing_id}")
        continue
    printing = printings_by_id[printing_id]
    if asset.get("officialPrintingId") != printing["officialPrintingId"] or asset.get("cardId") != printing["cardId"]:
        errors.append(f"asset identity mismatch {printing_id}")
    for kind, prefix in (("display", "assets/display/"), ("vision", "assets/vision/")):
        item = asset.get(kind) or {}
        relative = item.get("path")
        if not valid_asset_path(relative, prefix):
            errors.append(f"invalid {kind} metadata path {printing_id}")
            continue
        expected_display_paths.add(relative) if kind == "display" else expected_vision_paths.add(relative)
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing {kind} asset {printing_id}")
            continue
        if item.get("mimeType") != "image/webp":
            errors.append(f"invalid {kind} MIME {printing_id}")
        actual_hash = file_sha256(path)
        if not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256") or "") or actual_hash != item.get("sha256"):
            errors.append(f"invalid {kind} SHA-256 {printing_id}")
        if path.stat().st_size != item.get("bytes"):
            errors.append(f"invalid {kind} byte size {printing_id}")
        with Image.open(path) as image_file:
            if image_file.format != "WEBP" or list(image_file.size) != [item.get("width"), item.get("height")]:
                errors.append(f"invalid {kind} dimensions/format {printing_id}")
    if asset["vision"].get("sourceDisplaySha256") != asset["display"].get("sha256"):
        errors.append(f"vision source hash mismatch {printing_id}")
    image = printing["image"]
    if image.get("displayAssetPath") != asset["display"]["path"] or image.get("visionAssetPath") != asset["vision"]["path"]:
        errors.append(f"printing asset path mismatch {printing_id}")
    if image.get("displaySha256") != asset["display"]["sha256"] or image.get("visionSha256") != asset["vision"]["sha256"]:
        errors.append(f"printing asset hash mismatch {printing_id}")

actual_display_paths = {path.relative_to(ROOT).as_posix() for path in (ROOT / "assets/display").glob("*.webp")}
actual_vision_paths = {path.relative_to(ROOT).as_posix() for path in (ROOT / "assets/vision").glob("*.webp")}
if actual_display_paths != expected_display_paths:
    errors.append("missing or orphan display assets")
if actual_vision_paths != expected_vision_paths:
    errors.append("missing or orphan vision assets")

signed_pattern = re.compile(r"(?:Signature|Policy|Key-Pair-Id|X-Amz-Signature|X-Amz-Expires)=", re.I)
scan_paths = [ROOT / "README.md", ROOT / "manifest.json", ROOT / "db-manifest.json"]
for folder in ("data", "runtime", "sources"):
    scan_paths.extend((ROOT / folder).rglob("*.json"))
for path in scan_paths:
    text = path.read_text(encoding="utf-8")
    if signed_pattern.search(text):
        errors.append(f"signed URL persisted in {path.relative_to(ROOT)}")
for path in (ROOT / "runtime").rglob("*.json"):
    if "punksim.net" in path.read_text(encoding="utf-8").lower():
        errors.append(f"runtime punksim dependency in {path.relative_to(ROOT)}")

for identity in visuals:
    candidates = identity.get("candidatePrintingIds") or []
    if not candidates:
        errors.append(f"empty visual identity {identity.get('visualIdentityId')}")
    if any(pid not in valid_printings for pid in candidates):
        errors.append(f"invalid printing in visual identity {identity.get('visualIdentityId')}")
    if identity["cardId"] not in valid_cards:
        errors.append(f"invalid card in visual identity {identity.get('visualIdentityId')}")
    if identity["mode"] == "intrinsic_face_reference" and len(candidates) != 1:
        errors.append(f"intrinsic visual reference has {len(candidates)} candidates")
    if identity["mode"] == "shared_visual_identity" and len(candidates) < 2:
        errors.append("shared visual identity must have multiple candidates")

visual_ids = {identity["visualIdentityId"] for identity in visuals}
for printing in printings:
    recognition = printing["recognition"]
    if recognition["enabled"] and recognition.get("visualIdentityId") not in visual_ids:
        errors.append(f"missing visual identity for {printing['printingId']}")

profile_ids = [profile.get("recognitionProfileId") for profile in profiles]
if not profiles or duplicates(profile_ids):
    errors.append("recognition profiles must be non-empty and uniquely versioned")
for profile in profiles:
    if not profile.get("descriptorVersion") or not profile.get("referenceDimensions") or not profile.get("validatedAt"):
        errors.append(f"incomplete recognition profile {profile.get('recognitionProfileId')}")

group_ids = [group.get("recognitionGroupId") for group in recognition_groups]
if duplicates(group_ids): errors.append("duplicate recognitionGroupId")
assigned = set()
for group in recognition_groups:
    ids = group.get("printingIds") or []
    candidates = group.get("candidatePrintingIds") or []
    if not ids:
        errors.append(f"empty recognition group {group.get('recognitionGroupId')}")
        continue
    if group.get("recognitionProfileId") not in profile_ids:
        errors.append(f"unknown profile in {group.get('recognitionGroupId')}")
    if group.get("mode") not in {"exact", "shared"}:
        errors.append(f"invalid recognition mode {group.get('recognitionGroupId')}")
    if group.get("mode") == "exact" and len(ids) != 1:
        errors.append(f"exact recognition group is not singleton {group.get('recognitionGroupId')}")
    if set(candidates) != set(ids):
        errors.append(f"candidatePrintingIds mismatch {group.get('recognitionGroupId')}")
    if any(pid not in valid_printings for pid in ids + candidates):
        errors.append(f"unknown printing in recognition group {group.get('recognitionGroupId')}")
    card_ids_in_group = {printings_by_id[pid]["cardId"] for pid in ids if pid in printings_by_id}
    if card_ids_in_group != {group.get("cardId")}:
        errors.append(f"recognition group crosses cardId {group.get('recognitionGroupId')}")
    for pid in ids:
        key = (group.get("recognitionProfileId"), pid)
        if key in assigned:
            errors.append(f"printing assigned multiple times in profile: {pid}")
        assigned.add(key)
expected_assignments = {(profile_ids[0], pid) for pid in valid_printings} if len(profile_ids) == 1 else set()
if expected_assignments and assigned != expected_assignments:
    errors.append("recognition groups do not cover every official printing exactly once")

canonical_runtime_path = ROOT / "runtime/canonical-vision-index.json"
printing_runtime_path = ROOT / "runtime/printing-recognition-index.json"
runtime_groups_path = ROOT / "runtime/recognition-groups.json"
if canonical_runtime_path.exists() and printing_runtime_path.exists() and runtime_groups_path.exists():
    canonical_runtime = load("runtime/canonical-vision-index.json")
    printing_runtime = load("runtime/printing-recognition-index.json")
    runtime_groups = load("runtime/recognition-groups.json")
    canonical_refs = canonical_runtime.get("references") or []
    if len(canonical_refs) != len(cards) or {ref.get("cardId") for ref in canonical_refs} != valid_cards:
        errors.append("canonical runtime index must contain one entry per cardId")
    runtime_cards = printing_runtime.get("cards") or []
    if {item.get("cardId") for item in runtime_cards} != valid_cards:
        errors.append("printing recognition runtime index must be partitioned by every cardId")
    if runtime_groups.get("recognitionGroups") != recognition_groups:
        errors.append("runtime recognition groups differ from source data")

goro = [p for p in unresolved if p.get("variantKind") == "legacy_unresolved" and p.get("number") == "S002"]
if goro:
    errors.append("Goro S002 must not remain unresolved")
goro_alias = [a for a in aliases.get("printings", []) if a.get("from") == "legacy-goro-hands-unclean-s002"]
if len(goro_alias) != 1 or goro_alias[0].get("to") != "cpp-509f743f75700687" or goro_alias[0].get("reason") != "pixel_identical_official_match" or goro_alias[0].get("auditDate") != "2026-08-28":
    errors.append("Goro S002 alias invalid")
lucyna = [p for p in unresolved if p.get("cardId") == "cp-lucyna-kushinada"]
if len(lucyna) != 1 or lucyna[0].get("snapshotStatus") != "historical_out_of_snapshot":
    errors.append("Lucyna exception invalid")
if len(aliases.get("cards", [])) != 5:
    errors.append("five placeholder card aliases required")
if len(aliases.get("printings", [])) != 6:
    errors.append("five placeholder aliases plus Goro printing alias required")

result = {
    "ok": not errors,
    "snapshot": active,
    "cards": len(cards),
    "officialPrintings": len(printings),
    "visualIdentities": len(visuals),
    "recognitionProfiles": len(profiles),
    "exactRecognitionGroups": sum(g["mode"] == "exact" for g in recognition_groups),
    "sharedRecognitionGroups": sum(g["mode"] == "shared" for g in recognition_groups),
    "exactRecognitionPrintings": sum(len(g["printingIds"]) for g in recognition_groups if g["mode"] == "exact"),
    "sharedRecognitionPrintings": sum(len(g["printingIds"]) for g in recognition_groups if g["mode"] == "shared"),
    "intrinsicVisualReferences": sum(v["mode"] == "intrinsic_face_reference" for v in visuals),
    "sharedVisualPrintings": sum(len(v["candidatePrintingIds"]) for v in visuals if v["mode"] == "shared_visual_identity"),
    "sourceImages": sum(bool(p["image"].get("sourceImageUrl")) for p in printings),
    "stableRuntimeAssets": sum(bool(p["image"].get("displayAssetPath") and p["image"].get("visionAssetPath")) for p in printings),
    "displayAssets": len(actual_display_paths),
    "visionAssets": len(actual_vision_paths),
    "unresolved": len(unresolved),
    "errors": errors,
}
print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(1 if errors else 0)
