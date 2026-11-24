# Raid intelligence: verified findings and implementation plan

Prepared October 14, 2026. Scope authorized by the user: verify the supplied Deep Research report and produce a concrete implementation plan. Subsequent clarification makes DBM's encounter modules a central proposed input. This document is a plan; no runtime feature, importer repair, addon installation or live observation was performed.

Input: [user-supplied research report](<C:/Users/Jeff Towers/.codex/attachments/ae5b9711-72f0-447d-824b-d71b9937a154/Pasted text.txt>), SHA-256 `3ad89b38744b4f6d5c68a5523d222547eb1170090e2f6508a921adbb37b90fcb`. The [earlier local audit](D:/End-Game/ended_game/codex_playground/Goblin-Eye/docs/research/2026-10-14-dynamic-data-audit.md) remains useful context. Source health was refreshed at 21:46:55 UTC; all seven active dataset summaries were paged, with no next page.

## Decision

Use DBM as a first-class source adapter for applicable encounter logic. Join that evidence to separately sourced class capabilities, item/acquisition facts and reviewed strategy. Compile the result into class/spec HTML packs. Keep the implementation incremental within the existing Python/SQLite application.

DBM already supplies an in-game live-assistance system. Goblin Eye should consume supported static module evidence for preparation and explanation, while DBM continues doing its own live work inside the game. Goblin Eye does not need its own combat-monitoring engine.

The first engineering spike must establish what DBM actually exposes for Forever before building a large generic claim framework. In particular, current DBM code delegates some encounter information to Blizzard APIs; static source inspection cannot recover values that only arrive during play.

## What was verified, and what needs correction

This is targeted verification of implementation-driving claims, not independent reproduction of the entire report's research. Its exported citation tokens cannot be resolved as sources from this text attachment. Direct URLs were followed where available; the report itself will not be imported as verified game evidence.

| Claim or recommendation | Verification result | Consequence for implementation |
| --- | --- | --- |
| November 4 launch; December 9 raid unlock | Confirmed in [Blizzard's roadmap text](https://news.blizzard.com/en-us/article/24303862/world-of-warcraft-forever-whats-next-panel-recap). It explicitly identifies Hyjal as 20-player and Barrow as 10-player. The image's Onyxia/40-player release-wave detail was inspected in the earlier audit, rather than independently fetched again in this pass. | Store a release wave with source-backed members. No invented order between simultaneous releases. |
| 13 Hyjal and eight Barrow encounters | Confirmed in [Blizzard's Legacy article](https://news.blizzard.com/en-us/article/24307383/get-to-know-the-world-of-warcraft-forever-legacy-system). | Counts are useful roster-coverage expectations; they do not establish mechanics or kill order. |
| Current boss-name rosters | Search retrieval exposed the criteria on the [Hyjal achievement](https://www.wowhead.com/forever/achievement=62034/conqueror-of-the-wilds) and [Barrow achievement](https://www.wowhead.com/forever/achievement=62035/conqueror-of-the-deeps). Direct page opens provided almost no body. | Treat this as client/community roster evidence with retrieval limitations. Obtain a reproducible structured snapshot before an automated roster importer is considered complete. Achievement order and suggested NPCScan commands do not establish encounter order or a complete multi-actor encounter identity. |
| Warlock class changes used in the example | The Bane distinction, all-magic Curse of the Elements, pet scaling, weapon imbues and named tree changes are supported by [Blizzard's Warlock article](https://news.blizzard.com/en-us/article/24310968/world-of-warcraft-forever-class-deep-dives-rogue-and-warlock). Its beta caveat remains material. | Good class-handbook inputs as official design statements. They are not observations that every runtime interaction works as described. Other class trees were not exhaustively rechecked here. |
| 70374 is the latest applicable build | The supplied tracker URL failed in this verification pass; the targeted first-party tracker search did not reproduce that conclusion. | Keep it as an unverified research lead. Select a report target from an explicitly reviewed evidence set; never hardcode this number as current. |
| Zero publishable current tactics anywhere | The report correctly qualifies its own research scope. That absence finding was not exhaustively reproduced here. | Mark sections blocked when Goblin Eye lacks adequate evidence; do not turn a partial literature search into a global absence claim. |
| Three local importer failures | All three remain in fresh MCP health. Installed files independently confirm Alts 0.12.0 and Forever Guide 1.35.1. The item file has 55 additional name assignments; the dungeon header has changed. | These are concrete repairs. The Alts error concerns installation of Goblin Eye's numeric export extension, not proof that base character imports have stopped. |
| Fixed official URL list and zone-name dictionary | Confirmed in local source. | Separate resource discovery, resource refresh and sourced label updates. |
| “READY NOW” renderer, evidence graph and class packs | These are feasible proposed deliverables, not existing verified capabilities in Goblin Eye. | Rename this category “implementable with current evidence.” Describe actual integration status separately from content readiness. |
| Source reuse policy | [Forever Guide's project page](https://www.curseforge.com/wow/addons/forever-guide) lists All Rights Reserved; [Alts source](https://github.com/KadmaiDev/AltsForever) lists MIT. DBM's inspected license is also ARR. Other provider terms were not exhaustively re-audited. | Record policy by resource/content type and intended use. Public visibility is not blanket permission to redistribute code, prose, audio or artwork. Do not assume a project label alone settles treatment of every normalized fact. |

## DBM inspection: the important addition to the research

Read the current upstream core and Vanilla raid repositories, their complete recursive file inventories, pinned source files and the Vanilla license. No DBM, BigWigs or Details directory was found in the one installed AddOns root located through the configured research addons; that is a scoped inventory, not a claim about every installation on this machine.

Pinned upstream revisions:

| Repository | Commit | Relevant source |
| --- | --- | --- |
| `DeadlyBossMods/DBM-Vanilla` | `f1c4c7b034e71235b65d25e50b0dfc0b468fef2e` | [Onyxia module](https://github.com/DeadlyBossMods/DBM-Vanilla/blob/f1c4c7b034e71235b65d25e50b0dfc0b468fef2e/DBM-Raids-Vanilla/VanillaOnyxia/Onyxia.lua), [TOC](https://github.com/DeadlyBossMods/DBM-Vanilla/blob/f1c4c7b034e71235b65d25e50b0dfc0b468fef2e/DBM-Raids-Vanilla/DBM-Raids-Vanilla.toc), [license](https://github.com/DeadlyBossMods/DBM-Vanilla/blob/f1c4c7b034e71235b65d25e50b0dfc0b468fef2e/LICENSE) |
| `DeadlyBossMods/DeadlyBossMods` | `93fac9d288b31701d8a9730c31c7d44d9c1cd5db` | [client classification](https://github.com/DeadlyBossMods/DeadlyBossMods/blob/93fac9d288b31701d8a9730c31c7d44d9c1cd5db/DBM-Core/DBM-Core.lua#L461), [encounter events](https://github.com/DeadlyBossMods/DeadlyBossMods/blob/93fac9d288b31701d8a9730c31c7d44d9c1cd5db/DBM-Core/modules/EncounterEvents.lua) |

The inventories contained 185 and 551 entries respectively and were not truncated. No filenames indicating the new Hyjal Summit or Barrow Deeps modules were found in those two trees. Other packages, branches, private work and future releases remain unsearched.

The inspected core classifies Forever under `IsRestricted()`. The inspected Onyxia module places its detailed historical event handlers, warnings and timers in the other branch; its restricted branch contains a model setting and a TODO. The core also accepts Blizzard encounter warnings and encounter timeline events during play. Therefore the old Onyxia timer block cannot be promoted into a Forever guide merely because the package TOC includes the Forever interface. This is an applicability problem, not a reason to discard DBM as a source.

### What the adapter should extract

| DBM source construct | Normalized meaning | Report use |
| --- | --- | --- |
| Module/creature/encounter identifiers and package metadata | Source-backed identity plus edition/load conditions | Boss index and source links; resolve multiple actors separately. |
| Registered events and spell identifiers | Event/spell associations scoped to the active branch | Mechanic index and observable cues. Registration alone does not establish a whole response. |
| Warning declarations and handler calls | Source-authored alert intent, target and condition | Explain the cue and recommended reaction where the full chain is supported. |
| Timer declarations, starts and replacements | Authored prediction, cast duration, variance or conditional schedule | Event-relative timeline; show ranges and prediction basis. A timer constant is not automatically an exact server rule. |
| Stage changes and their guards | Conditional phase transition logic | Phase sheet and decision tree, retaining prerequisites. |
| Role/spec/options filters | Warning audience or default filtering under that DBM API version | Class relevance hint. A “Tank” option does not itself prove an exclusive mechanic assignment. |
| Localization references | Attributable source labels and warning keys | Readable names; unsupported formatting remains unresolved. |
| Delegated Blizzard events or unresolved runtime expressions | Runtime-only or unsupported evidence | Explicit coverage gap; no synthetic static values. |

Comments, TODOs and disabled example code are not active mechanic evidence. Season, difficulty, client edition, options and role branches must survive extraction. Range warnings do not provide complete room geometry. DBM does not by itself supply conditional BiS rankings, complete item acquisition, class optimization or a historical event stream.

## Build sequence

Each work package below is a proposed reviewable change. New module names and API names are design targets, not currently callable features. Do not renumber migrations until implementation begins against the then-current checkout.

### 0. Prove the encounter source contract

Deliver a DBM inventory/extraction prototype over saved static files, without executing Lua or contacting the game. Record repository commit or installed release, file/blob hashes, core API version, package load metadata, localization references and branch context. Reuse `lua_literals.py` only for literal parsing; add a bounded tokenizer/parser for explicitly supported declaration/handler patterns. Do not market it as a universal Lua interpreter.

Outputs: module coverage matrix, a small versioned normalized snapshot contract, supported/unsupported grammar diagnostics and source-line references. Inspect the actual selected Forever package and relevant branches before claiming per-boss coverage. Treat the historical Onyxia module as an edition-rejection fixture. If no applicable full module exists, proceed with identity/class preparation and record the gap.

Acceptance: comments produce no claims; SoD/different-client branches cannot satisfy Forever dependencies; unknown guards remain unresolved; variable timers retain ranges; delegated values remain unavailable; a parser failure preserves the previous good revision. This spike determines the useful DBM scope before generic architecture expands.

### 1. Repair current ingestion and expose health at the point of use

Existing touchpoints: `ingestion/item_export_setup.py`, `foreverguide_items.py`, `foreverguide_dungeons.py`, `static_watcher.py`, `foreverguide.py`, `services.py`, `research_queries.py`, and compact output in `agent_responses.py`.

- Review Alts 0.12.0's full extension contract and add explicit tested compatibility. All four existing scanner markers are still present, but marker presence alone does not certify behavior. Preserve backup/idempotency and unknown-version rejection.
- Support the inspected literal item-name assignments safely, with duplicate/override handling and provenance. Review the changed dungeon attribution and distinguish Classic rates from newer community associations. Do not merely remove the header checks.
- Standardize fingerprints across content hashes, parser/schema revision and applicable metadata. Keep last checked, successful parse and actual observation dates distinct.
- Include latest update error, last-good revision and applicability limitations in dependent query results. A stale source can support a labeled limited section without looking current.

Acceptance: fixtures for reviewed new formats pass; malformed/unreviewed formats fail without replacing data; retry works; components fail independently; failed update status survives compact MCP output. Alts repair is valuable existing-product maintenance and is not a prerequisite for anonymous class packs.

### 2. Add resource discovery and a minimal evidence layer

Reuse `sources`, `source_documents`, `research_datasets`, domain fact tables and SQLite migrations. Existing `evidence_assertions`/`assertion_conflicts` are useful precedents. Their current trust-rank/newest-retrieval selection policy must not automatically decide encounter truth. No separate graph database or duplicate universal item catalog is needed.

Add only the necessary structures:

- Resource registry: provider, domain, permitted retrieval mode, edition, source policy, approved discovery roots and parser contract. Existing six URLs become initial registry data.
- Resource checks: per-resource status, checked time, HTTP validator where supported, content hash and last-good revision. One failed URL must not discard successful updates from other resources.
- Typed claims/evidence links: stable subject or unresolved local identity, predicate, typed value/unit, edition/client branch/build applicability, evidence kind, source/raw pointer, parser revision, lineage, limitations and supersession/retraction.
- Dependency edges connecting claims to reviewed recommendations and report sections. Existing item/recipe/acquisition facts are referenced with dataset identity instead of copied.

Use a full client identity rather than comparing arbitrary build integers across products. Keep provider commit IDs separate from client builds. A missing fact remains unknown. Source confidence values are not calibrated probabilities.

Discovery can find new publications and module files within configured providers. Normal retrieval/parse jobs run under existing worker patterns. No recurring Codex automation or new addon installation is implied. Replace the zone dictionary with sourced area/map labels and aliases as a separate compatibility change; retain namespace and coordinate distinctions.

Acceptance: one shared upstream record is one lineage; an unchanged body advances check time without fabricating a new observation; a parser change reparses identical bytes; source outages do not erase history; historical data remains excluded from current tactics by default; all chosen query scopes page completely.

### 3. Join encounter evidence to a class handbook and compile report data

Start with Warlock as a development slice. Import/capture official class statements as versioned evidence; review changed sections rather than treating article retrieval as automatic factual validation. Model talent-tree orientation, concrete configurations and role separately so hybrid builds remain expressible.

Add proposed `encounters.py`/`raid_reports.py` services with a pure report-data compiler. Inputs: raid/boss, class, optional specs, intent, target evidence set and cutoff. Resolve aliases to sourced identities; do not use per-boss branches in runtime code.

Every recommendation records cue, response, prerequisites, condition, failure consequence, recovery, supporting claims and declared assumptions. Class-native utility requires evidence of the actual ability/talent/pet requirements. External utilities are dependencies and fallback patterns, without named players or a roster manager.

Keep three independent axes: extraction coverage, applicability and section publishability. A class handbook can be ready while boss tactics remain blocked. Roster completeness is distinct from tactical completeness. A conditional planning assumption such as hypothetical adds cannot become an encounter fact.

Acceptance: the same generic compiler handles two unrelated encounters; a changed class utility invalidates all dependent sections but leaves unrelated loot research intact; newer evidence imported after a selected cutoff cannot leak into a historical report. Select one atomic evidence snapshot before compiling.

### 4. Ship the first portable class pack

Deliver a Warlock/Hyjal preparation edition when its class and roster inputs meet their individual gates. Use the sourced roster; compare it with the official expected count. Missing names remain explicitly missing rather than invented encounters. Do not require unsupported tactical content to make the page count look complete.

Structure: `index.html`, shared class/spec handbook, boss pages, prep/loot views, local CSS/SVG/minimal JS, source index, changelog and `evidence/manifest.json`. Essential display data is rendered into HTML; there is no runtime fetch of local JSON. The single-boss HTML embeds every essential asset.

Use Python standard-library HTML escaping and ZIP support initially. Figures are source-grounded SVGs with legends and text alternatives. Show actionable content first and deeper evidence in accessible expandable sections. Unknown geometry gets no invented map.

Expose proposed read-only MCP tools for encounter coverage and compiled report data. Artifact creation is a distinct, explicitly requested export operation, annotated as a file-writing action rather than mislabeled read-only. Restrict output to an application-controlled export directory and return artifact paths/download information; do not embed an entire raid bundle in a bounded MCP text reply. Register CLI/API/agent surfaces together when implementing.

The manifest pins normalized report data, raw/dataset hashes, claim IDs, request, compatibility decisions, cutoff, renderer/schema/asset versions and export timestamp. Live active flags must not be needed to reproduce an old pack. Deterministic ordering and ZIP metadata permit identical output for a frozen manifest; a new generation timestamp is a new edition.

Acceptance: pack opens locally with networking disabled; no CDN, fonts or required fetches; no private character data; malicious source text cannot become executable HTML/SVG; unsupported tactics visibly remain blocked; single-file export has no siblings; links and archive paths are valid; phone, keyboard and print views are inspected.

### 5. Add conditional loot, then supported saved-run review

Join existing item/acquisition/recipe evidence into spec scenarios before adding a ranking model. Each ranking needs availability, build, loadout, talents, buffs, encounter assumptions, proc/set model and objective. Label candidates separately from validated upgrades. Preserve full variants and uncertainty; no global stat-weight table.

Only add acquisition probability forecasts when eligibility, sample/published basis and distribution assumptions support them. Optional preparation costing uses explicit market/source/capture identity and does not establish sales.

Saved-run analysis is a later independent adapter. Verify a permitted saved log/export's event coverage and attribution before designing metrics. DBM core compatibility or stored preferences are not proof of a complete replay. No live monitoring or protected-event workaround is part of this plan.

Acceptance: unavailable/client-only items cannot become confirmed boss drops; a ranking discloses all scenario/model inputs; incomplete logs cannot establish missed assignments or causal blame; original reports remain reproducible after new evidence arrives.

## First implementation batches

1. DBM source contract and coverage prototype, paired with visible source-error/freshness output. This resolves the largest uncertainty quickly.
2. Separately reviewed Alts extension and Forever Guide parser repairs, including current-format fixtures and parser identity updates.
3. Resource registry plus minimal encounter/class claims and dependencies; connect the DBM snapshot adapter and official class sources.
4. Pure report compiler and real offline export contract, then the Warlock/Hyjal preparation pilot.
5. Additional raids/classes through evidence adapters, conditional loot modeling, and finally any proven saved-run inputs.

Advance each boss section when evidence permits; the class-wide product does not have to wait for every raid to be tactically complete. Product scope remains raids and class/spec packs. Regular dungeon guides, roster management, a new live boss-mod engine and automatic guild distribution are outside this implementation plan.

## Validation boundary

This turn refreshed MCP evidence, read the relevant local source and installed static files, and checked the linked upstream materials. It did not rerun the 31 regression tests from the earlier audit because runtime code was unchanged. Future implementation must run the existing ingestion/provenance/game-boundary tests plus the focused acceptance checks above. Preserve the checkout's unrelated working changes and existing database history throughout.
