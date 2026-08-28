#!/usr/bin/env python3
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "db-manifest.json").read_text(encoding="utf-8"))
snapshot = manifest["activeSnapshot"]
meta = json.loads((root / "sources" / "official" / snapshot / "metadata.json").read_text(encoding="utf-8"))
cards = json.loads((root / "data/cards.json").read_text(encoding="utf-8"))["cards"]
printings = json.loads((root / "data/printings.json").read_text(encoding="utf-8"))["printings"]
visuals = json.loads((root / "data/visual-identities.json").read_text(encoding="utf-8"))["visualIdentities"]
profiles = json.loads((root / "data/recognition-profiles.json").read_text(encoding="utf-8"))["recognitionProfiles"]
groups = json.loads((root / "data/recognition-groups.json").read_text(encoding="utf-8"))["recognitionGroups"]
print(f"Cyberpunk TCG DB snapshot: {snapshot}")
print(f"Canonical cards: {len(cards)}/{meta['expectedCanonicalCards']}")
print(f"Official printings: {len(printings)}/{meta['expectedOfficialPrintings']}")
print(f"Visual identities: {len(visuals)}")
print(f"Recognition profiles: {len(profiles)}")
print(f"Recognition groups: {len(groups)} ({sum(g['mode'] == 'exact' for g in groups)} exact, {sum(g['mode'] == 'shared' for g in groups)} shared)")
print(f"Stable local display/Vision assets: {sum(bool(p['image']['displayAssetPath'] and p['image']['visionAssetPath']) for p in printings)}")
