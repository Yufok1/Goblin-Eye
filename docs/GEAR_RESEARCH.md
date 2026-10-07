# Reliable gear research

Goblin Eye uses existing data addons. WoWAI carries conversation and does not
retrieve equipment, item stats or quest completion.

## Exact item variants

At dashboard startup, Goblin Eye installs its small, owned
`integrations/alts-forever/GoblinEyeExport.lua` extension into the existing
Alts Forever folder and appends it to both supported manifests when present:
`AltsForever_Camelot.toc` (Forever's edition-specific manifest) and
`AltsForever.toc` (the generic manifest). It checks the inspected
Forever interface and scanner contracts first. Original files are backed up
under `data/addon-backups`. Setup errors appear in source health. No additional
addon, external catalog, or model download is required.

The changed manifest is discovered on the next normal WoW launch. Equipped
and bag items are captured automatically during Alts' normal scans; hovering
each item, opening its tooltip, or issuing a manual rescan is not required.
WoW persists SavedVariables on logout or `/reload`; those ordinary saves
import automatically while the dashboard runs. CurseForge may replace the TOC
on an update; the next dashboard startup checks and restores the extension.
If Alts' scanner contract changes, setup refuses the patch until reviewed.

The extension observes links already encountered through Alts' gear scans,
container scans, item scoring, or ordinary item tooltips. It uses the client
item-stat API and `C_TooltipInfo.GetHyperlink` to read numeric stats and tooltip
details directly for those links. Missing cached data is requested once per
item ID; a batch performs at most four timed attempts and can resume on the
matching item-data event. Lockdown defers observation work until it ends.
Passive tooltip callbacks also enrich ordinary previews. Secret-value guards,
bounded queues and a tooltip cooldown keep the work limited. It sends no game inputs and
does not query unseen item links, track combat, or read game memory.

It saves up to 1,000 full item-link variants, with numeric API keys, capture
time, client build, locale and available tooltip text. Unequipped variants
count too. Oldest saved observations are evicted at the bound; imported history
remains in the local database. Empty slots are recorded explicitly only after
Alts reports a complete gear scan. NPC/loot previews need an ordinary tooltip
to contribute client-observed details.

This is an observed-variant library, **not a universal numeric suffix catalog**.
The installed static datasets do not provide every modern bonus combination.
Unseen combinations remain unknown. A suffix name never supplies a numeric
bonus by itself. API stat rows do not guarantee complete proc/effect coverage.
Tooltip-only effects retain their text, without invented stat conversions.

## Character sheet and quest freshness

The same Alts extension automatically records the current character's maximum
health/mana, effective attributes, available school spell-damage/crit values,
regen, separate hit modifiers, selected talent-node ranks/spell IDs and helpful
buffs. It reads public addon APIs outside lockdown on normal login/equipment,
trait/stat/aura events, with a debounce. Unsupported or secret fields remain
absent. It does not sample current health/power, damage events, movement or
combat logs. Race, realm and build are client observations; they do not set an
auction region or ruleset.

Completed quest IDs are queried automatically on entering the world and quest
changes, then saved by Alts with a capture timestamp. The quest tool chooses
between this exact-character observation and the existing Questie cache by
freshness, exposing the timestamp basis. It never treats an absent quest as
proof of eligibility. Neither the client nor these tools supplies a universal
current quest-eligibility catalog.

Goblin Eye's Python/MCP backend reads these saved addon files and its database.
It does not access the game process, screenshot gameplay, issue game inputs,
or call game APIs. The separately authorized WoWAI transport screenshots only
the addon-generated chat strip and writes reply addon files. It carries chat;
it is not a research data provider.

## Tools and evidence

1. Use `list_characters`, then the intended `get_character_snapshot`.
2. Read `research_preflight`: missing exact stats, tooltip coverage, enchants,
   unrecorded slots and static catalog conflicts are explicit. If audit_readiness
   is blocked, diagnose capture/source health before launching a full upgrade
   hunt. Read character_stats for observed totals and unknown fields.
   Its talent records page through talent_limit/talent_offset on this same tool.
3. Follow `equipment_next_offset` with `get_character_equipment`; inventory is
   separately paged through `get_character_inventory`.
4. Use `get_item_variants(item_id, item_link=full_link)` for observed numeric
   rows and tooltip text. Keep exact links, account namespace and build separate.
   The character's observed client build selects matching full-link values;
   old builds remain available through get_item_variants(game_build=...).
   Without a known build, conflicting observed builds remain unresolved.
5. Use `get_enchant_evidence` for ProfessionDB's applied-enchant catalog and
   recipe assertions. Verify slot/build. Do not double-count enchants against
   full-link API stats without establishing the API's inclusion semantics.
6. Use `get_character_quests` for client-observed completion and Questie fallback.
   Matching uses the exact account and full character name. File save time is
   not completion time. Absence does not prove quest eligibility or zero quests.
7. Page `get_research_datasets`, `search_evidence`, acquisition and world tools
   using their returned `next_offset`. A partial page cannot establish absence.
8. Read get_recipe_evidence(fact_id, snapshot_id=...) for learning_plan: dynamic
   pattern acquisition associations, trainer claims, skill disagreements,
   saved profession/known-recipe coverage and material follow-ups. Page pattern
   acquisition rather than treating its first five sources as exhaustive.

Static Forever Guide catalog, gear and tooltip views remain separate. Raw stat
keys survive import; normalized fields cover the installed renderer's keys.
Shadow resistance is not Shadow damage. Generic hit/crit ratings are not
spell-only or percentages. Classic fallback views retain their labels.
Stat conflicts are explicit. Only subtract the same normalized stat key at a
comparable scope/build; spell_damage and spell_power equivalence has not been
established by these sources. Missing keys cannot be substituted with zero.

Dungeon searches accept sourced dungeon names, keys and slugs. Membership comes
from Forever Guide's explicit boss and quest associations and can join other
sources by entity ID. It is incomplete membership, especially for trash mobs.
Entrance coordinates are never used to place nearby outdoor mobs inside a
dungeon. Ambiguous names require a more specific label.

Compact MCP responses share provenance and summarize large coordinate arrays.
Focused world queries provide labeled coordinate samples; cached source
documents preserve full arrays. Oversized full item aggregations return an
explicit summary with focused follow-up tools rather than failing as missing
data. The HTTP item detail remains available.

## Report standards

Resolve actionable gaps with focused tools before ranking upgrades. Report
unresolved gaps and conflicting sources separately. Never substitute zeros,
infer suffix amounts, claim complete loot coverage, or report definitive stat
deltas from incomplete evidence. Check current source health around saves and
preserve capture time separately from import time.
