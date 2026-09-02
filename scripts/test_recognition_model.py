#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


printings = load("data/printings.json")["printings"]
groups = load("data/recognition-groups.json")["recognitionGroups"]
profiles = load("data/recognition-profiles.json")["recognitionProfiles"]
aliases = load("data/id-aliases.json")
unresolved = load("data/unresolved-printings.json")["printings"]

assert len(printings) > 0
assert len(profiles) == 1
valid = {printing["printingId"]: printing for printing in printings}
covered = []
for group in groups:
    ids = group["printingIds"]
    assert ids
    assert set(ids) == set(group["candidatePrintingIds"])
    assert {valid[printing_id]["cardId"] for printing_id in ids} == {group["cardId"]}
    assert group["mode"] in {"exact", "shared"}
    if group["mode"] == "exact":
        assert len(ids) == 1
    covered.extend(ids)

assert len(covered) == len(printings)
assert len(set(covered)) == len(printings)
assert sum(group["mode"] == "exact" for group in groups) == 3
assert sum(group["mode"] == "shared" for group in groups) == len(groups) - 3
by_card = {}
for printing in printings:
    by_card.setdefault(printing["cardId"], []).append(printing)
standard_iconic = [items for items in by_card.values() if {p["variantKind"] for p in items} >= {"standard", "iconic"}]
assert standard_iconic
assert all(len({p["cardId"] for p in items}) == 1 and len({p["printingId"] for p in items}) == len(items) for items in standard_iconic)

goro = [alias for alias in aliases["printings"] if alias["from"] == "legacy-goro-hands-unclean-s002"]
assert len(goro) == 1
assert goro[0]["to"] == "cpp-509f743f75700687"
assert goro[0]["reason"] == "pixel_identical_official_match"
assert goro[0]["auditDate"] == "2026-08-28"
assert not any(item.get("number") == "S002" for item in unresolved)

lucyna = [item for item in unresolved if item.get("cardId") == "cp-lucyna-kushinada"]
assert len(lucyna) == 1
assert lucyna[0]["snapshotStatus"] == "historical_out_of_snapshot"

print(json.dumps({
    "ok": True,
    "recognitionProfiles": len(profiles),
    "recognitionGroups": len(groups),
    "exactGroups": sum(group["mode"] == "exact" for group in groups),
    "sharedGroups": sum(group["mode"] == "shared" for group in groups),
    "coveredPrintings": len(covered),
    "goroAlias": goro[0]["to"],
    "lucyna": lucyna[0]["snapshotStatus"],
}, indent=2))
