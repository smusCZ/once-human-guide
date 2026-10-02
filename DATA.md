# Once Human Guide — Data

**version:** `2026-10-02-v19.2-372`  
**app:** 5.5.0  
**schema:** `5.5-graph-integrity`  
**patch_target:** 3.0.7 live · Isles of Abyss prep  

Pack (`*.json` / `ohg_data.js`) je kanonický. SQLite se staví z packu a **nikdy ho nepřepisuje**. User layer (favorites, builds, queue) není v databázi.

## Modules on GitHub (module JSON)

| File | Role |
|------|------|
| deviations.json | Combat / Territory / Crafting deviations |
| weapons.json | Named weapons |
| armor.json | Armor sets |
| mods.json | Weapon & armor mods |
| bosses.json | Silo / monolith / raid bosses |
| map_locations.json | Regions, silos, hubs |
| recipes.json | Food, ammo, structures |
| materials.json | Craft mats & currencies |
| scenarios.json | Manibus, Winter, SCP, RaidZone, Abyss… |
| quests.json | Main / side / silo quests |
| events.json | Golden Autumn, Prime War, Abyss reservation |
| creatures.json | Bestiary |
| npcs.json | Vendors & quest NPCs |
| plants / fish / animals / flowers | Gatherables |

## Odvozené tabulky

| Tabulka | Role |
|---------|------|
| entities | Jednotný katalog pro FTS |
| entities_fts | Fulltext |
| links | Vazby podle jména (ingredient, drop, source, located_at) |
| integrity_findings | Kontrola packu při buildu |
| data_versions | data + schema verze |

## Install / update

```bash
python3 install.py --from-github
python3 db_build.py
python3 updater.py
```

Updater skládá `database_full.json` z modulů, když monolit chybí, a pak znovu postaví `once_human.db`.
