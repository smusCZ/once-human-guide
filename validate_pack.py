#!/usr/bin/env python3
"""Check module JSON: unique ids, required name, unknown alias targets."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
MODULES = {
    "deviations": "deviations.json",
    "weapons": "weapons.json",
    "armor": "armor.json",
    "mods": "mods.json",
    "bosses": "bosses.json",
    "locations": "map_locations.json",
    "recipes": "recipes.json",
    "materials": "materials.json",
    "scenarios": "scenarios.json",
    "quests": "quests.json",
    "events": "events.json",
    "creatures": "creatures.json",
    "npcs": "npcs.json",
    "plants": "plants.json",
    "fish": "fish.json",
    "animals": "animals.json",
    "flowers": "flowers.json",
}

def main() -> int:
    issues = []
    index = {}
    total = 0
    for table, filename in MODULES.items():
        rows = json.loads((BASE / filename).read_text(encoding="utf-8"))
        seen = set()
        for row in rows:
            total += 1
            eid = row.get("id")
            if not eid:
                issues.append(f"{table}: row without id")
                continue
            if eid in seen:
                issues.append(f"{table}: duplicate id {eid}")
            seen.add(eid)
            index[(table, eid)] = row.get("name")
            if not (row.get("name") or "").strip():
                issues.append(f"{table}/{eid}: empty name")
    aliases = json.loads((BASE / "aliases.json").read_text(encoding="utf-8"))
    for row in aliases:
        if (row.get("table"), row.get("id")) not in index:
            issues.append(f"alias {row.get('alias')} -> missing {row.get('table')}/{row.get('id')}")
    print(json.dumps({"records": total, "aliases": len(aliases), "issues": issues, "ok": not issues}, ensure_ascii=False, indent=2))
    return 1 if issues else 0

if __name__ == "__main__":
    sys.exit(main())
