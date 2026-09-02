#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


printings = load("data/printings.json")["printings"]
metadata = load("data/asset-metadata.json")["assets"]
manifest = load("runtime/asset-manifest.json")
canonical = load("runtime/canonical-vision-index.json")["references"]
printing_index = load("runtime/printing-recognition-index.json")["cards"]
legacy = load("runtime/vision-index.json")

expected = len(printings)
assert expected > 0
assert len(metadata) == expected
assert len(manifest["displayAssets"]) == expected
assert len(manifest["visionAssets"]) == expected
assert len({item["path"] for item in manifest["displayAssets"]}) == expected
assert len({item["path"] for item in manifest["visionAssets"]}) == expected
assert all((ROOT / item["path"]).is_file() for item in manifest["displayAssets"] + manifest["visionAssets"])

assert len(canonical) == len({printing["cardId"] for printing in printings})
assert all(item["visionAssetPath"].startswith("assets/vision/") for item in canonical)
assert all(item["assetStatus"] == "stable_local_assets" for item in canonical)

indexed_refs = [
    reference
    for card in printing_index
    for group in card["recognitionGroups"]
    for reference in group["references"]
]
assert len(printing_index) == len({printing["cardId"] for printing in printings})
assert len(indexed_refs) == expected
assert all(reference["visionAssetPath"].startswith("assets/vision/") for reference in indexed_refs)
assert all(reference["assetStatus"] == "stable_local_assets" for reference in indexed_refs)

assert len(legacy) == expected
assert {entry["recognitionMode"] for entry in legacy} <= {"exact", "shared"}
assert all(entry["refId"] and entry["printingId"] and entry["cardId"] and entry["imageUrl"] and entry["variantKind"] and entry["recognition"]["eligible"] for entry in legacy)
assert all(entry["visionAssetPath"].startswith("assets/vision/") for entry in legacy)

runtime_text = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "runtime").glob("*.json"))
assert "punksim.net" not in runtime_text.lower()
for marker in ("Signature=", "Policy=", "Key-Pair-Id=", "X-Amz-Signature="):
    assert marker.lower() not in runtime_text.lower()

print(json.dumps({
    "ok": True,
    "displayAssets": expected,
    "visionAssets": expected,
    "canonicalVisionAssets": len(canonical),
    "printingRecognitionAssets": len(indexed_refs),
    "visionReferences": len(legacy),
    "runtimePunksimOccurrences": 0,
    "runtimeSignedUrlOccurrences": 0,
}, indent=2))
