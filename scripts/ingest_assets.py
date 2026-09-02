#!/usr/bin/env python3
"""Explicitly ingest official display assets and deterministic Vision derivatives.

This maintenance command is intentionally separate from the database build.
Signed delivery URLs only exist in memory and are never serialized.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import html
import io
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PROFILE = {
    "format": "WEBP",
    "maxWidth": 512,
    "maxHeight": 716,
    "resizeAlgorithm": "Pillow LANCZOS",
    "colorMode": "RGB",
    "crop": False,
    "webpLossless": False,
    "webpQuality": 80,
    "webpMethod": 6,
    "webpExact": True,
    "pillowVersion": Image.__version__,
}
UA = {"User-Agent": "TCGateCyberpunkDB/1.0 asset maintenance"}
SIGNED_KEYS = ("Signature=", "Policy=", "Key-Pair-Id=", "X-Amz-Signature=")


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, attempts: int = 5) -> tuple[bytes, str | None]:
    for attempt in range(attempts):
        try:
            request = Request(url, headers=UA)
            with urlopen(request, timeout=45) as response:
                return response.read(), response.headers.get_content_type()
        except Exception:
            if attempt + 1 == attempts:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise AssertionError("unreachable")


def signed_urls(page_url: str) -> dict[str, str]:
    raw, _ = fetch(page_url)
    page = html.unescape(raw.decode("utf-8", "replace")).replace("\\/", "/").replace("\\u0026", "&")
    pattern = re.compile(
        r'(https://dstcynss47vun\.cloudfront\.net/prod/cyberpunk/portal/'
        r'([0-9a-f-]{36})/[^"<\\ ]+?\.webp\?[^"<\\ ]+)',
        re.I,
    )
    result = {}
    for url, official_printing_id in pattern.findall(page):
        if any(key in url for key in SIGNED_KEYS):
            result[official_printing_id.lower()] = url
    return result


def inspect_webp(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "WEBP":
            raise ValueError(f"Expected WEBP, got {image.format}")
        image.load()
        return image.size


def vision_bytes(display: bytes) -> tuple[bytes, int, int]:
    with Image.open(io.BytesIO(display)) as image:
        image = image.convert(PROFILE["colorMode"])
        width, height = image.size
        scale = min(PROFILE["maxWidth"] / width, PROFILE["maxHeight"] / height, 1.0)
        output_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        resized = image.resize(output_size, Image.Resampling.LANCZOS) if output_size != image.size else image.copy()
        output = io.BytesIO()
        resized.save(
            output,
            format="WEBP",
            lossless=PROFILE["webpLossless"],
            quality=PROFILE["webpQuality"],
            method=PROFILE["webpMethod"],
            exact=PROFILE["webpExact"],
        )
        return output.getvalue(), output_size[0], output_size[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace-existing", action="store_true", help="Explicitly accept changed official display bytes")
    parser.add_argument("--replace-vision", action="store_true", help="Explicitly replace changed deterministic derivatives")
    parser.add_argument("--verify-existing", action="store_true", help="Download and compare without writing")
    parser.add_argument("--offline-verify-vision", action="store_true", help="Regenerate Vision bytes locally without network")
    args = parser.parse_args()

    manifest = load("db-manifest.json")
    snapshot = manifest["activeSnapshot"]
    catalog = load(f"sources/official/{snapshot}/catalog.json")["cards"]
    printings = load("data/printings.json")["printings"]
    by_official = {printing["officialPrintingId"]: printing for printing in printings}
    existing_metadata_path = ROOT / "data/asset-metadata.json"
    existing_entries = {}
    if existing_metadata_path.exists():
        existing_entries = {
            entry["printingId"]: entry
            for entry in json.loads(existing_metadata_path.read_text(encoding="utf-8")).get("assets", [])
        }

    if len(by_official) != len(printings):
        raise SystemExit("Asset ingestion requires unique official printing IDs")

    display_dir = ROOT / "assets/display"
    vision_dir = ROOT / "assets/vision"
    display_dir.mkdir(parents=True, exist_ok=True)
    vision_dir.mkdir(parents=True, exist_ok=True)

    if args.offline_verify_vision:
        failures = []
        for printing in printings:
            display_path = display_dir / f"{printing['printingId']}.webp"
            vision_path = vision_dir / f"{printing['printingId']}.webp"
            generated, _, _ = vision_bytes(display_path.read_bytes())
            if not vision_path.exists() or sha256(generated) != sha256(vision_path.read_bytes()):
                failures.append(printing["printingId"])
        if failures:
            raise SystemExit(f"VISION_ASSET_CHANGED: {failures[:10]} ({len(failures)} total)")
        print(json.dumps({"offlineVisionReproducible": len(printings), "profile": PROFILE}, indent=2))
        return

    pending = []
    reusable = {}
    for printing in printings:
        prior = existing_entries.get(printing["printingId"])
        if (prior and (ROOT / prior["display"]["path"]).is_file()
                and (ROOT / prior["vision"]["path"]).is_file()
                and not args.verify_existing and not args.replace_existing and not args.replace_vision):
            reusable[printing["printingId"]] = prior
        else:
            pending.append(printing)
    pending_official = {printing["officialPrintingId"] for printing in pending}
    page_urls = sorted({card["sourceUrl"] for card in catalog if any(p["officialPrintingId"] in pending_official for p in card["printings"])})
    current_signed = {}
    with futures.ThreadPoolExecutor(max_workers=4) as executor:
        for result in executor.map(signed_urls, page_urls):
            current_signed.update(result)
    missing_signed = sorted(pending_official - set(current_signed))
    if missing_signed:
        raise SystemExit(f"Missing signed URLs for {len(missing_signed)} printings: {missing_signed[:10]}")

    source_by_official = {
        printing["officialPrintingId"]: (card, printing)
        for card in catalog for printing in card["printings"]
    }

    def download(item):
        official_id = item["officialPrintingId"]
        url = current_signed[official_id]
        if f"/portal/{official_id}/" not in url:
            raise ValueError(f"Signed URL UUID mismatch for {official_id}")
        body, mime = fetch(url)
        return item, body, mime, source_by_official[official_id]

    results = []
    with futures.ThreadPoolExecutor(max_workers=6) as executor:
        for index, downloaded in enumerate(executor.map(download, pending), 1):
            results.append(downloaded)
            if index % 50 == 0:
                print(f"downloaded {index}/{len(pending)}", flush=True)

    metadata = []
    for printing in printings:
        prior = reusable.get(printing["printingId"])
        if prior:
            prior = {**prior, "officialPrintingId": printing["officialPrintingId"], "cardId": printing["cardId"]}
            prior["provenance"] = {**prior["provenance"], "snapshot": snapshot}
            metadata.append(prior)
    anomalies = []
    for printing, display, response_mime, (source_card, source_printing) in results:
        printing_id = printing["printingId"]
        official_id = printing["officialPrintingId"]
        display_rel = f"assets/display/{printing_id}.webp"
        vision_rel = f"assets/vision/{printing_id}.webp"
        display_path = ROOT / display_rel
        vision_path = ROOT / vision_rel
        width, height = inspect_webp(display)
        if (width, height) != (733, 1024):
            anomalies.append({"printingId": printing_id, "dimensions": [width, height]})
        display_hash = sha256(display)
        prior = existing_entries.get(printing_id)
        if display_path.exists() and sha256(display_path.read_bytes()) != display_hash and not args.replace_existing:
            raise SystemExit(f"SOURCE_ASSET_CHANGED {printing_id}")
        if prior and prior["display"]["sha256"] != display_hash and not args.replace_existing:
            raise SystemExit(f"SOURCE_ASSET_CHANGED {printing_id}")

        vision, vision_width, vision_height = vision_bytes(display)
        vision_hash = sha256(vision)
        if vision_path.exists() and sha256(vision_path.read_bytes()) != vision_hash and not args.replace_vision:
            raise SystemExit(f"VISION_ASSET_CHANGED {printing_id}")
        if prior and prior["vision"]["sha256"] != vision_hash and not args.replace_vision:
            raise SystemExit(f"VISION_ASSET_CHANGED {printing_id}")

        if not args.verify_existing:
            if not display_path.exists() or args.replace_existing:
                display_path.write_bytes(display)
            if not vision_path.exists() or args.replace_vision or args.replace_existing:
                vision_path.write_bytes(vision)

        metadata.append({
            "printingId": printing_id,
            "officialPrintingId": official_id,
            "cardId": printing["cardId"],
            "provenance": {
                "authority": "official_cyberpunk_tcg",
                "sourcePageUrl": source_card["sourceUrl"],
                "sourceImageUrl": source_printing["sourceImageUrl"],
                "snapshot": snapshot,
            },
            "display": {
                "path": display_rel,
                "sha256": display_hash,
                "mimeType": "image/webp",
                "width": width,
                "height": height,
                "bytes": len(display),
                "preservedOfficialBytes": True,
            },
            "vision": {
                "path": vision_rel,
                "sha256": vision_hash,
                "mimeType": "image/webp",
                "width": vision_width,
                "height": vision_height,
                "bytes": len(vision),
                "sourceDisplaySha256": display_hash,
                "generation": PROFILE,
            },
        })

    metadata.sort(key=lambda entry: entry["printingId"])
    if not args.verify_existing:
        existing_metadata_path.write_text(
            json.dumps({"assetProfileVersion": "1.0.0", "assets": metadata}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        metadata_by_printing = {entry["printingId"]: entry for entry in metadata}
        for printing in printings:
            asset = metadata_by_printing[printing["printingId"]]
            printing["image"].update({
                "displayAssetPath": asset["display"]["path"], "visionAssetPath": asset["vision"]["path"],
                "displaySha256": asset["display"]["sha256"], "visionSha256": asset["vision"]["sha256"],
                "displayWidth": asset["display"]["width"], "displayHeight": asset["display"]["height"],
                "visionWidth": asset["vision"]["width"], "visionHeight": asset["vision"]["height"],
                "status": "stable_local_assets",
            })
            printing["recognition"].update({
                "enabled": True, "visualIdentityId": "cpvi-" + printing["printingId"][4:],
                "referenceImageUrl": asset["vision"]["path"], "status": "reference_available",
            })
        (ROOT / "data/printings.json").write_text(json.dumps({"printings": printings}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "displayAssets": len(metadata),
        "visionAssets": len(metadata),
        "displayBytes": sum(entry["display"]["bytes"] for entry in metadata),
        "visionBytes": sum(entry["vision"]["bytes"] for entry in metadata),
        "dimensionAnomalies": anomalies,
        "verifyOnly": args.verify_existing,
        "signedUrlsPersisted": False,
    }, indent=2))


if __name__ == "__main__":
    main()
