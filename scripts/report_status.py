#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
c=json.loads((ROOT/'data/coverage.json').read_text(encoding='utf-8'))
print(f"Cyberpunk TCG DB snapshot: {c['snapshot_date']}")
print(f"WNTC: {c['wntc']['revealed_slots_tracked']}/{c['wntc']['mechanically_unique_slots_expected']} revealed/tracked")
print(f"WNTC runtime metadata ready: {c['wntc']['metadata_ready_for_runtime']}")
print(f"WNTC revealed metadata pending: {c['wntc']['revealed_but_metadata_pending']}")
print(f"WNTC unrevealed mechanics: {c['wntc']['mechanically_unrevealed_slots']}")
print(f"Starter uniques: {c['starter_unique_cards']} | promos tracked: {c['standalone_promo_records']}")
print(f"Runtime cards: {c['runtime_ready_cards']} | printings: {c['printings_tracked']} | Vision-ready printings: {c['vision_ready_printings']}")
