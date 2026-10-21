# Plánovaná vylepšení Once Human Guide

## Databáze
- Extra sloupec `extra` (JSON) pro neznámá pole z packu
- Více vazeb (source, located_at pro všechny typy)
- data_issues tabulka pro audit (již částečně v main)
- FTS5 unicode61 remove_diacritics=2
- Indexy na type, rarity, region, slot

## Systém
- User layer v oddělené once_human_user.db (favorites, notes, progress, inventory) — přežije rebuild packu
- Zabezpečení POST /update/run tokenem OHG_ADMIN_TOKEN + hmac
- Endpointy /integrity, /audit, /facets, /user/*
- Filtrování v list endpointech (již částečně)

## Aplikace
- Search bez diakritiky (normalize)
- Export/import user dat (JSON)
- Badge DB status z /integrity
- Panel kvality

Všechny změny: pack kanonický, user layer odděleně, pouze PR.
