# System 5.5

Branch: `labs/system-5.5` on fork `smusCZ/once-human-guide`.
Canonical repo `smus-rgb/once-human-guide` is not writable by the connected GitHub account (403). Merge only via PR after access.

## Database
- Pack DB `once_human.db` is rebuilt from JSON. Count target stays 372.
- User DB `once_human_user.db` holds favorites and notes and is not deleted on rebuild.
- New tables: `aliases`, `unresolved_refs`, `duplicate_names`.
- Indexes on name, type, region. Schema tag `5.5-aliases-userlayer`.

## API
- `/catalog` filter by table, kind, rarity
- `/suggest` prefix search
- `/compare?a=table:id&b=table:id`
- `/user/favorites` get/post/delete — never writes pack
- `/search` quotes FTS tokens and falls back to LIKE
- `/integrity` reports unresolved ingredient names and duplicate names

## App
- `modules/ohg_user.js` stores favorites in localStorage and syncs to the API when it is up.
- Offline HTML still works if the script is included; pack files are unchanged.
