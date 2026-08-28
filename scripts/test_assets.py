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

assert len(printings) == 436
assert len(metadata) == 436
assert len(manifest["displayAssets"]) == 436
assert len(manifest["visionAssets"]) == 436
assert len({item["path"] for item in manifest["displayAssets"]}) == 436
assert len({item["path"] for item in manifest["visionAssets"]}) == 436
assert all((ROOT / item["path"]).is_file() for item in manifest["displayAssets"] + manifest["visionAssets"])

assert len(canonical) == 147
assert all(item["visionAssetPath"].startswith("assets/vision/") for item in canonical)
assert all(item["assetStatus"] == "stable_local_assets" for item in canonical)

indexed_refs = [
    reference
    for card in printing_index
    for group in card["recognitionGroups"]
    for reference in group["references"]
]
assert len(printing_index) == 147
assert len(indexed_refs) == 436
assert all(reference["visionAssetPath"].startswith("assets/vision/") for reference in indexed_refs)
assert all(reference["assetStatus"] == "stable_local_assets" for reference in indexed_refs)

assert len(legacy) == 133
assert {entry["recognitionMode"] for entry in legacy} == {"legacy_reference"}
assert all(entry["visionAssetPath"].startswith("assets/vision/") for entry in legacy)

runtime_text = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "runtime").glob("*.json"))
assert "punksim.net" not in runtime_text.lower()
for marker in ("Signature=", "Policy=", "Key-Pair-Id=", "X-Amz-Signature="):
    assert marker.lower() not in runtime_text.lower()

print(json.dumps({
    "ok": True,
    "displayAssets": 436,
    "visionAssets": 436,
    "canonicalVisionAssets": 147,
    "printingRecognitionAssets": len(indexed_refs),
    "legacyReferences": len(legacy),
    "runtimePunksimOccurrences": 0,
    "runtimeSignedUrlOccurrences": 0,
}, indent=2))
