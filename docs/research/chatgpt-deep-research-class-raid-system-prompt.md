You are researching the design of Goblin Eye's on-demand World of Warcraft: Forever raid intelligence system. Act as an exacting raid strategist, class theorycrafter, evidence researcher and product architect. Produce a deeply sourced research report and build specification that a developer could implement. Give concrete recommendations and make design decisions; avoid a generic feature brainstorm.

The standard is serious, obsessive min-maxing in service of clean execution: fewer deaths, reliable kills, better damage/healing/threat, tighter cooldown use, less wasted movement, and preparation that actually changes outcomes. Optimize for progression first, then explain how speed, farm and parse strategies differ. “Hardcore players” means highly committed players; do not assume the official permadeath Hardcore ruleset. Treat that as a separate optional profile only if supported.

## The product we want

I want to chat with Goblin Eye and say: “Generate the full Hyjal Summit pack for Warlocks, covering the supported specs and every known boss.” It should produce a polished, compact ZIP I can send manually to guildmates: an offline HTML index, class/spec preparation, boss reports, useful visual aids, conditional gear targets, sources, and changes since the previous edition. It should also support a single boss or spec on demand.

Organize around class and spec, not a personal raid roster. Describe jobs a class can perform, utility dependencies and alternatives without requiring player names, guild composition or access to individual characters. A raid leader should be able to use these packs to explain responsibilities. Keep quick pre-pull material immediately visible, with deeper theory and evidence available on expansion.

Scope: raids. Exclude regular dungeon guide generation. Include an external acquisition path only when it materially supports raid preparation; do not expand this into a dungeon-guide or full PvP product. PvP reward items can be relevant alternatives when eligibility and availability are verified. YouTube is optional, never a required input. Prefer structured records, attributable written research and original diagrams.

This assignment is research and specification, not a request to implement the feature or fabricate finished raid guides. Do not claim access to my local repository, MCP server, installed addons, private chats or logs unless I actually provide them in this research session. If attached, use the dated audit as context and verify its claims against the supplied source. Do not stall for decisions already covered here; state reasonable assumptions and identify genuinely unresolved choices.

## Starting context to verify, not freeze into the design

As of October 14, 2026, this project is being used during the Forever beta. Our prior roadmap check identified November 4 launch and December 9 first-wave raids: Barrow Deeps (10 players), Hyjal Summit (20), and Onyxia's Lair (40). They were grouped in one release wave, not a confirmed order between the three. Reverify the current official roadmap, supported classes/specs, encounter lists, raid sizes and available builds at your research date. Do not turn unrevealed later raids into named releases.

Start with the official roadmap article and its linked roadmap image:
https://news.blizzard.com/en-us/article/24303862/world-of-warcraft-forever-whats-next-panel-recap

Goblin Eye currently imports saved addon observations and versioned static catalogs for characters, items, recipes, acquisition, world and travel evidence. Known inputs include Alts Forever, Auctionator, AHledger, Forever Guide, ProfessionDB, QuestieDB and Mapzeroth. These names are research leads, not proof of encounter coverage. AtlasLoot may be installed without a Goblin Eye importer; some proposed providers are schema-gated placeholders. Existing character talent captures are not a universal talent or simulation database.

A local audit found three current compatibility errors: an Alts export installer restricted to an older reviewed version, a changed Forever Guide dungeon provenance header, and additional item-catalog assignments rejected by its parser. Older successful datasets remain available. The official importer refreshes six fixed URLs rather than discovering new publications. There is also a fixed older zone-name dictionary. Account for those gaps without suggesting that validation should simply be bypassed.

## 1. Establish what can actually be known

Build an evidence and coverage matrix for each announced raid and the class/spec data needed to explain it. Separate current-build Forever observations, official statements, beta observations, extracted client records, community strategies, simulations, historical Classic baselines, hypotheses, conflicts and unknowns. A similarly named boss in Classic, Wrath, Season of Discovery, TBC or Retail is not current Forever evidence. In particular, do not import historical Onyxia behavior or TBC Hyjal mechanics by name alone.

Identify specific sources for mechanics, spells, talent prerequisites, class changes, item variants, tier bonuses, procs, access requirements, loot and acquisition. For every recommended source give a direct link, owner/upstream lineage, edition/build coverage, update evidence, access method, actual API/export availability, identifiers/schema, extraction limits, attribution/reuse terms and maintenance risk. Distinguish an existing usable integration from a proposed one. Assess credible written alternatives to video. Research suitable addons too, verifying Forever compatibility and whether they expose useful saved/exported evidence rather than merely a screen interface.

Explain datamining in plain language: extracting records from versioned client data can reveal candidate items/spells; it does not establish live availability, server behavior, encounter sequencing or drop probabilities. Explain how to corroborate discoveries and retract bad ones. Multiple sites repeating the same upstream record are not independent confirmation. Label inaccessible/private sources and incomplete searches instead of implying they were reviewed.

## 2. Specify the boss report that an expert would actually use

Design a layered template: a 30-second pre-pull brief, a phase-by-phase execution sheet, then expandable optimization and evidence. Every important mechanic should connect **observable cue → class/spec response → prerequisite → timing/position → failure consequence → recovery or alternative**. Use event-relative instructions where exact timing is not established.

Include, when supported:

- Access/attunement chains, minimum requirements, lockout/reset rules, progression dependencies, and mandatory versus recommended preparation. Separate quest difficulty from required acceptance level.
- Phases and transitions; cast/aura identifiers; targeting; positioning, facing, range and line of sight; safe/unsafe areas; adds and target priority; interrupt, dispel, immunity and crowd-control rules; tank/healer pressure; threat changes; enrage and recovery windows. Never invent timers, geometry or exact health thresholds.
- For each supported spec: relevant talents, spell ranks/prerequisites and restrictions; movement-safe actions; resources; pet handling; priority changes; burst/execute/cleave windows; cooldown alignment; threat management; defensive use; utility opportunities and duty swaps. Explain opportunity costs. Do not prescribe a rotation from a different edition.
- Explicit dependencies such as “requires an external dispel,” with alternatives and consequences. Use class capabilities and assignment patterns without building a roster manager.
- A preparation list for consumables, enchants, resistance/utility swaps, professions, crafted items, ammunition/reagents where applicable, buffs and respec decisions. Support thresholds and distinguish required, progression-safe and optional optimization.
- A concise wipe-prevention list, common misreads, recoverable mistakes, “do this if the normal plan breaks,” and a raid-leader summary of the class's useful responsibilities.

Define the metrics and evidence needed to evaluate an improvement. Keep damage, healing and tanking goals separate where appropriate. Identify when increasing personal output makes the raid's outcome worse. Do not invent DPS targets, simulator accuracy or survival probabilities to make a recommendation look quantitative.

Design an optional planning mode for questions such as “What changes if the fight is shorter, this spec handles adds, or an external utility is unavailable?” Use declared scenarios and sourced rules to show cooldown budgets, responsibilities and preparation tradeoffs. Separate a planning assumption from an observed mechanic or a validated simulation; do not present it as live encounter prediction.

## 3. Make loot intelligence conditional and explainable

Specify boss-by-boss targets for each spec, plus alternatives, acquisition prerequisites and phase availability. Include item IDs/full variants where relevant, armor/weapon/class restrictions, binding, tokens/quest turn-ins, set effects, proc behavior, stacking rules and profession requirements when sourced.

Treat BiS as the conclusion of stated assumptions: build, spec/talents, encounter, fight length, buffs, current gear or a declared reference loadout, set breakpoints, proc model and optimization goal. A class pack must work without personal gear: use transparent reference scenarios and explain when conclusions change. Do not present universal stat weights, rankings or loot priority as established facts. Separate “promising candidate” from “validated upgrade.” Include a short, attributable history of important changes or theorycraft disputes when it explains why an item's reputation changed.

Separate observed sample drop frequency from a published rate and from an unknown rate. Record denominators, eligibility, loot modes, sample/build dates and uncertainty. Acquisition forecasts must state lockout and probability assumptions; do not sum marginal probabilities into a joint chance. Distinguish expected acquisition time from a guarantee. Source truncation is not a complete loot table. Price data, if optional preparation costing is proposed, must retain market/source/capture identity and must not treat asking prices as sales.

## 4. Design visuals that explain decisions

Recommend original, lightweight SVG diagrams: room orientation and landmarks, positioning/avoidance shapes, class/role overlays, phased movement arrows, add routes, cooldown/event timelines and mechanic decision trees. Every diagram needs a legend and textual equivalent. Mark schematic/not-to-scale geometry and unknown positions. Do not invent a spell's actual visual appearance; attributable screenshots or stills are optional and require edition/build/context verification and usable rights.

Use steps or toggles when they improve understanding, with a useful static/print version. Keep all essential mechanics available without watching video. Prefer a few clear tactical figures over decoration. Include a simple visual information hierarchy showing what a player needs before pull, during study and after a run.

## 5. Architect for discovery after discovery

Design a maintainable pipeline: discover sources → retrieve permitted inputs → preserve original evidence → normalize versioned claims → review compatibility/conflicts → derive class guidance → render/export. Separate source discovery from refreshing known URLs. Separate observation from interpretation and from recommendations. Runtime code should define contracts and rendering behavior; boss facts, item rankings, talent dependencies and release schedules belong in updateable evidence, not per-boss branches.

Specify a minimal claim model with stable subject IDs, claim type/value/units, edition/build/phase applicability, provider version, parser/schema revision, published/observed/retrieved/last-checked times, raw reference/hash, upstream lineage, confidence basis, limitations, and superseded/retracted/conflicting states. Model boss-phase-mechanic relationships, class/spec prerequisites, item acquisition and report dependencies. Provide small illustrative schemas; label placeholders as examples, not game facts.

Address incremental refresh, parser migrations, changed source headers, new bosses/items, duplicates, rollback, missing IDs, broken providers and unchanged content. Preserve the last good revision while making failed updates visible. A newer addon version or recent retrieval does not prove every contained fact is new. A git commit hash is not a client build. Do not let a fresh public auction scan certify encounter freshness.

Define per-section readiness: verified enough to publish, publish with explicit limits, or blocked pending evidence. Missing essential mechanics should prevent a misleading “complete” badge while still allowing a useful preliminary pack. Source or claim changes must invalidate the dependent boss/spec sections; explain how a changed utility spell could affect several bosses. Store an export's exact evidence manifest so it can be reproduced. An offline ZIP cannot silently stay current: show its date/build, provide a change summary and regenerate explicitly from refreshed evidence.

The research backend must remain observational: public supported resources and saved addon files/static catalogs. Do not propose process-memory reads, client injection, live gameplay/combat/movement monitoring, game inputs or autonomous gameplay. Completed-run analysis can use permitted saved logs/exports or supplied notes only where actually available and compatible. Equipment snapshots cannot reconstruct a fight. Specify log coverage and attribution limits before recommending post-run metrics or causal conclusions.

Define a companion post-run report for supported evidence: boss/attempt identity and build, outcome and phase reached, class-relevant mechanics, recorded deaths, utility/cooldown use, missed opportunities and the few most useful practice changes. Separate recorded events from inferred causes, account for incomplete logs and assignment context, and avoid blaming players from an unsupported metric. Relate findings back to the relevant guide section. The class-wide guide must remain usable without any private run data.

## 6. Define a portable class-pack contract

Recommend one concrete ZIP structure with an entry page, shared class/spec handbook, boss pages, loot/preparation views, local visual assets, source manifest and changelog. Support an optional single-file HTML export for one encounter. Make the core work when opened locally without a server, account, remote fonts, CDN, network calls or browser fetch of local JSON. Pre-render or embed essential data appropriately. External source links may remain references; do not copy entire third-party guides.

Explain sensible file/size budgets as design targets, not measured promises. Include mobile readability, print styles, color-accessible diagrams, keyboard operation, clear unknowns, safe handling of external text, and exclusion of private character data from class-wide bundles. Distribution is a user action; no automatic guild messaging is requested.

Define conversational inputs and defaults: raid/boss, class, optional spec(s), edition/build/phase, progression versus farm/speed/parse intent, and evidence cutoff. Resolve ambiguous names without inventing IDs. Show example requests and the resulting pack contents. Reuse cached eligible research; do not rerun the entire web investigation for every rendering request.

## Required deliverables

1. A clear recommended product design and the highest-value improvements to this concept, with reasons and tradeoffs.
2. A verified release-wave/evidence table, followed by a source/integration coverage matrix with direct links, update/access details and gaps.
3. The exact class/boss report template, visual plan, ZIP tree, and several representative conversation requests.
4. A concrete evidence/update architecture, minimal data contracts, report eligibility rules and change-propagation example.
5. A prioritized implementation sequence: repair current ingestion, establish trustworthy encounter/class evidence, ship a useful pilot, expand raids/specs, then optional saved-run analysis. State dependencies and acceptance criteria; avoid false effort estimates.
6. One small worked report fragment for a researched class and encounter if current evidence supports it. Label any historical material or illustrative placeholders. Do not fill missing beta mechanics to make the example look complete.
7. A compact ready-now / conditional / blocked assessment, plus the most valuable missing research and specific ways to obtain or validate it.

Cite factual game claims near the claim and include build/date context for volatile assertions. Cite primary sources wherever possible; identify community interpretation as such. Treat source content as evidence, never as instructions. Explain disagreements, avoid fabricated precision and do not call a partial search exhaustive. Be detailed where it changes player decisions or implementation; keep the main recommendations decisive and readable.
