type Observation = {
  observation_type: "listing" | "aggregated_price";
  source_key: string; market_key: string; item_id: number | null; item_key?: string; item_name?: string;
  observed_date?: string; captured_at?: string; source_modified_at?: string;
  current_min_unit_copper?: number | null; daily_min_unit_copper?: number | null;
  daily_max_low_unit_copper?: number | null; available_quantity?: number | null;
  quantity?: number; stack_size?: number; buyout_copper?: number; unit_buyout_copper?: number;
  confidence: number; evidence_kind: string;
};
type SourceHealth = { newest_snapshot: string | null; snapshot_count: number; age_hours: number | null; is_stale: boolean; markets: Record<string, unknown>[]; sources: Record<string, unknown>[]; adapters: Record<string, unknown>[]; unconnected_installed_data_addons?: Record<string, unknown>[] };
type NextData = { headline: string; auctionator_price_history_connected: boolean; items: { priority: number; title: string; needed: string; unlocks: string[] }[] };
type Summary = { product: string; market_key: string; source_count: number; observed_markets: Record<string, unknown>[]; record_counts: Record<string, number>; freshness: { newest_snapshot: string | null; is_stale: boolean }; safety: string };
type Catalog = { items: { item_id: number; name: string | null }[]; total: number; limit: number; offset: number };
type RecipeFact = { id: number; spell_id: number; name: string | null; profession: string; output_item_id: number | null; output_quantity: number | null; skill_required: number | null; source_key: string; source_version: string | null; game_build: string | null; retrieved_at: string; raw_reference: string; confidence: number; limitations: string[]; reagents: { item_id: number; quantity: number; name: string | null }[]; teaching_items: { item_id: number }[] };
type AcquisitionRecord = { entity_id: number; entity_type: string; entity_name: string | null; method: string; probability: number | null; quest_condition: number; choice_reward: number; evidence_basis: string; source_key: string; source_version: string; retrieved_at: string; raw_reference: string; entity_attributes: Record<string, unknown> };
type AcquisitionPage = { item_id: number; records: AcquisitionRecord[]; total: number; limit: number; offset: number; coverage: { method: string; omitted_count: number }[] };
type WorldDetail = { entity_type: string; entity_id: number; assertions: { name: string | null; attributes: Record<string, unknown>; source_key: string; source_version: string; retrieved_at: string; raw_reference: string }[]; items: { item_id: number; item_name: string | null; method: string; probability: number | null; evidence_basis: string; quest_condition: number; choice_reward: number; raw_reference: string }[]; total: number; limit: number; offset: number };
type DepthPage = { snapshot: { captured_at: string; region: string; source_complete_claim: number; game_build: string } | null; totals?: { listing_count: number; listed_units: number; buyout_units: number; bid_only_listings: number }; total: number; limit: number; offset: number; listings: { ordinal: number; quantity: number; buyout_copper: number; bid_copper: number; unit_buyout_copper: number | null }[]; stack_distribution?: { stack_size: number; listing_count: number; min_stack_buyout_copper: number | null }[] };
type ItemDetail = { item_id: number; name: string | null; source_key?: string; retrieved_at?: string; game_build?: string; listing_markets: { market_key: string; name: string }[]; acquisition: AcquisitionPage; recipe_relationships: Record<string, RecipeFact[]>; price_observations: Record<string, unknown>[]; identity_observations: Record<string, unknown>[]; loot_sources: Record<string, unknown>[]; recipes_using: Record<string, unknown>[]; recipes_making: Record<string, unknown>[] };
type CompanionEntry = { id:number;kind:string;title:string;body:string;status:string;basis:string;author:string;character_snapshot_id:number|null;evidence_refs:string[];occurred_at:string|null;created_at:string;updated_at:string };
type CompanionPage = {records:CompanionEntry[];total:number;limit:number;offset:number;next_offset:number|null};

const state: { observations: Observation[]; sources?: SourceHealth; nextData?: NextData; summary?: Summary; catalog?: Catalog; query: string; view: string } = { observations: [], query: "", view: "companion" };
const $ = <T extends Element>(selector: string): T => document.querySelector(selector) as T;
const esc = (value: unknown): string => String(value ?? "—").replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char] ?? char));

function copper(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const total = Math.abs(Math.round(value));
  const gold = Math.floor(total / 10000); const silver = Math.floor((total % 10000) / 100); const copperValue = total % 100;
  return `${value < 0 ? "−" : ""}${gold ? `${gold}g ` : ""}${silver ? `${silver}s ` : ""}${copperValue}c`;
}

function observationCard(value: Observation, index: number): string {
  const title = value.item_name || (value.item_id ? `Item ${value.item_id}` : value.item_key || "Unresolved item");
  const unit = value.current_min_unit_copper ?? value.unit_buyout_copper;
  const quantity = value.available_quantity ?? value.quantity;
  return `<article class="evidence-card" data-index="${index}" tabindex="0">
    <div class="card-top"><span class="strategy-tag">${esc(value.source_key)} · ${value.observation_type === "aggregated_price" ? "Aggregate" : "Listing"}</span><span class="confidence">${Math.round(value.confidence * 100)}% policy confidence (uncalibrated)</span></div>
    <h4>${esc(title)}</h4><p class="rationale">Observed key ${esc(value.item_key ?? value.item_id)} in ${esc(state.summary?.observed_markets.find(m => m.market_key === value.market_key)?.name ?? "WoW Forever")}. This is source evidence and carries no buy or sell recommendation.</p>
    <div class="money-row"><div><span class="money">${copper(unit)}</span><span class="label">Observed unit minimum</span></div><div><span class="money">${esc(quantity)}</span><span class="label">Available quantity</span></div><div><span class="money">${esc(value.observed_date ?? value.captured_at ?? "—")}</span><span class="label">Observed date</span></div></div>
    <div class="card-action"><span>Inspect source record</span><b>↗</b></div>
  </article>`;
}

function showObservation(index: number): void {
  const value = state.observations[index]; if (!value) return;
  const rows = Object.entries(value).map(([key, field]) => `<div class="calc-row"><span>${esc(key.replaceAll("_", " "))}</span><span>${key.includes("copper") ? copper(field as number) : esc(field)}</span></div>`).join("");
  $("#detail-content").innerHTML = `<p class="eyebrow">Observed evidence · ${esc(value.evidence_kind)}</p><h3>${esc(value.item_name || `Item ${value.item_id ?? value.item_key}`)}</h3><p class="muted">Preserved from ${esc(value.source_key)} · ${esc(state.summary?.observed_markets.find(m => m.market_key === value.market_key)?.name ?? "WoW Forever")}. ${value.source_key === "ahledger" ? "WoW Forever community reference; not your personal scan." : "Your saved local WoW Forever auction scans."}</p><h4>Stored record</h4><div class="calc-table">${rows}</div><div class="warning-box">${value.observation_type === "aggregated_price" ? "This source supplies aggregate price evidence, not individual auction stacks." : "This record describes an observed listing."} Neither establishes a completed sale.</div>`;
  $(".app-shell").classList.add("detail-open");
}

function renderMarket(): void {
  const grid = $("#evidence-grid");
  grid.innerHTML = state.observations.length ? state.observations.map(observationCard).join("") : `<div class="empty"><strong>No sourced market records are indexed.</strong><br><br>Do a new auction scan and let WoW save it. Your local scans import automatically.</div>`;
  grid.querySelectorAll<HTMLElement>(".evidence-card").forEach(element => {
    const open = () => showObservation(Number(element.dataset.index)); element.addEventListener("click", open);
    element.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") open(); });
  });
}

function renderWorld(): void {
  const counts = state.summary?.record_counts ?? {};
  const keys = ["item_observations", "recipe_facts", "reagent_facts", "research_datasets", "world_entity_facts", "acquisition_facts", "camps", "auction_rows", "price_observations"];
  $("#evidence-grid").innerHTML = keys.map(key => `<article class="source-card"><p class="eyebrow">Indexed records</p><h4>${esc(key.replaceAll("_", " "))}</h4><div class="money">${esc(counts[key] ?? 0)}</div></article>`).join("");
  $("#evidence-grid").insertAdjacentHTML("afterbegin", `<section class="history-panel"><form id="world-search-form" class="history-controls">
    <label>NPC or zone<input name="query" placeholder="Arugal, Grimtotem, Silverpine…"></label>
    <label>Zone filter<input name="zone" placeholder="Any zone"></label>
    <label>Minimum level<input name="min_level" type="number" min="1"></label>
    <label>Maximum level<input name="max_level" type="number" min="1"></label>
    <label>Rank<select name="rank"><option value="">All ranks</option><option value="0">Normal / unmarked</option><option value="1">Elite</option><option value="2">Rare elite</option><option value="3">Boss</option><option value="4">Rare</option></select></label>
    <button>Search world records</button></form><div id="world-search-output">Search stored NPC evidence; source locations and levels may be historical.</div></section>`);
  $("#world-search-form").addEventListener("submit", event => { event.preventDefault(); void loadWorldSearch(); });
}

let catalogRequest = 0;
let detailRequest = 0;
async function renderItems(offset = 0): Promise<void> {
  const request = ++catalogRequest;
  $("#evidence-grid").innerHTML = `<div class="empty">Searching local items…</div>`;
  try {
    const result = await fetchJson<Catalog>(`/api/items?q=${encodeURIComponent(state.query)}&limit=40&offset=${offset}`);
    if (request !== catalogRequest || state.view !== "items") return;
    state.catalog = result;
    $("#feed-heading").textContent = `${result.total.toLocaleString()} indexed items`;
    $("#evidence-grid").innerHTML = result.items.map(item => `<button class="evidence-card item-card" data-item="${item.item_id}"><p class="eyebrow">Item ${item.item_id}</p><h4>${esc(item.name ?? `Unresolved item ${item.item_id}`)}</h4><p class="muted">Market evidence · sources · recipe relationships</p><div class="card-action"><span>Explore item</span><b>↗</b></div></button>`).join("") || `<div class="empty">No sourced items match this search.</div>`;
    if (result.total > result.limit) $("#evidence-grid").insertAdjacentHTML("beforeend", `<div class="pagination"><button id="previous-items" ${offset === 0 ? "disabled" : ""}>Previous</button><span>${offset + 1}–${offset + result.items.length} of ${result.total}</span><button id="next-items" ${offset + result.items.length >= result.total ? "disabled" : ""}>Next</button></div>`);
    $("#evidence-grid").querySelectorAll<HTMLElement>("[data-item]").forEach(button => button.addEventListener("click", () => void showItem(Number(button.dataset.item))));
    document.querySelector("#previous-items")?.addEventListener("click", () => void renderItems(Math.max(0, offset - result.limit)));
    document.querySelector("#next-items")?.addEventListener("click", () => void renderItems(offset + result.limit));
  } catch (error) { if (request === catalogRequest && state.view === "items") $("#evidence-grid").innerHTML = `<div class="empty">Could not search items: ${esc(error)}</div>`; }
}

function itemLink(itemId: number, label?: string | null): string {
  return `<button class="text-link" data-item="${itemId}">${esc(label ?? `Item ${itemId}`)}</button>`;
}

function recipeCard(recipe: RecipeFact): string {
  return `<details class="recipe-card"><summary>${esc(recipe.name ?? `Spell ${recipe.spell_id}`)} <span>${esc(recipe.profession)}</span></summary><p class="muted">Spell ${recipe.spell_id} · Required skill: ${esc(recipe.skill_required ?? "unknown")}</p><p>Output: ${recipe.output_item_id ? itemLink(recipe.output_item_id) : "No item output recorded"} · Quantity: ${esc(recipe.output_quantity ?? "unknown")}</p><h5>Reagents</h5>${recipe.reagents.map(reagent => `<div class="calc-row">${itemLink(reagent.item_id, reagent.name)}<span>× ${reagent.quantity}</span></div>`).join("") || `<p class="muted">No reagents recorded.</p>`}${recipe.teaching_items.length ? `<h5>Teaching items</h5>${recipe.teaching_items.map(item => itemLink(item.item_id)).join(" · ")}` : ""}<p class="source-meta">${esc(recipe.source_key)} · ${esc(recipe.source_version)}<br>Build ${esc(recipe.game_build)} · Retrieved ${esc(recipe.retrieved_at)}<br>${esc(recipe.raw_reference)}</p>${recipe.limitations.map(value => `<p class="muted">${esc(value)}</p>`).join("")}</details>`;
}

function renderAcquisition(page: AcquisitionPage, request: number): void {
  if (request !== detailRequest) return;
  const omitted = page.coverage.filter(row => row.omitted_count > 0).map(row => `${row.method}: ${row.omitted_count} omitted`).join(" · ");
  $("#item-acquisition").innerHTML = `<h4>Where it comes from</h4><p class="muted">${page.total.toLocaleString()} indexed associations. Historical drop rates require Forever verification; these lists are incomplete.${omitted ? `<br>Source truncation: ${esc(omitted)}` : ""}</p>${page.records.map(row => `<details class="recipe-card"><summary>${esc(row.entity_name ?? `${row.entity_type} ${row.entity_id}`)}<span>${esc(row.method.replaceAll("_", " "))} · ${row.evidence_basis === "classic_baseline" ? "CLASSIC BASELINE" : row.evidence_basis === "bundled_reference" ? "Bundled reference · applicability unknown" : "Forever community association"}</span></summary>${row.probability !== null ? `<p>Source probability: ${(row.probability * 100).toFixed(2)}%${row.quest_condition ? " · quest conditional" : ""}</p>` : `<p class="muted">Probability unknown / not supplied.</p>`}${row.choice_reward ? `<p>Optional quest reward; requires choosing this item.</p>` : ""}${row.entity_attributes.ui_map_id ? `<p>Map ${esc(row.entity_attributes.ui_map_id)} · Reference coordinates ${esc(row.entity_attributes.x)}, ${esc(row.entity_attributes.y)}</p>` : ""}${row.entity_attributes.min_level !== undefined ? `<p>Source level: ${esc(row.entity_attributes.min_level)}–${esc(row.entity_attributes.max_level)}</p>` : ""}<p class="source-meta">${esc(row.source_key)} · v${esc(row.source_version)}<br>Retrieved ${esc(row.retrieved_at)}<br>${esc(row.raw_reference)}</p></details>`).join("") || `<p class="muted">No acquisition associations indexed yet.</p>`}${page.total > page.limit ? `<div class="pagination"><button id="acq-prev" ${page.offset === 0 ? "disabled" : ""}>Previous</button><span>${page.offset + 1}–${page.offset + page.records.length} / ${page.total}</span><button id="acq-next" ${page.offset + page.records.length >= page.total ? "disabled" : ""}>Next</button></div>` : ""}`;
  const load = async (offset: number) => {
    try { renderAcquisition(await fetchJson<AcquisitionPage>(`/api/acquisition?item_id=${page.item_id}&limit=10&offset=${offset}`), request); }
    catch (error) { if (request === detailRequest) $("#item-acquisition").innerHTML = `<p class="muted">Could not load acquisition evidence: ${esc(error)}</p>`; }
  };
  document.querySelector("#acq-prev")?.addEventListener("click", () => void load(Math.max(0, page.offset - 10)));
  document.querySelector("#acq-next")?.addEventListener("click", () => void load(page.offset + page.records.length));
  $("#item-acquisition").querySelectorAll<HTMLDetailsElement>(".recipe-card").forEach((card, index) => {
    const row = page.records[index];
    const button = document.createElement("button");
    button.className = "text-link";
    button.textContent = "Inspect source and its linked items →";
    button.addEventListener("click", () => void showWorld(row.entity_type, row.entity_id, page.item_id));
    card.append(button);
  });
}

async function showWorld(entityType: string, entityId: number, originItemId: number, offset = 0): Promise<void> {
  const request = ++detailRequest;
  $("#detail-content").innerHTML = `<p class="muted">Loading source evidence…</p>`;
  try {
    const value = await fetchJson<WorldDetail>(`/api/world/${encodeURIComponent(entityType)}/${entityId}?limit=20&offset=${offset}`);
    if (request !== detailRequest) return;
    const primary = value.assertions[0];
    $("#detail-content").innerHTML = `<button class="text-link" id="back-to-item">← Back to item ${originItemId}</button><p class="eyebrow">${esc(entityType)} ${entityId}</p><h3>${esc(primary?.name ?? `${entityType} ${entityId}`)}</h3><p class="warning-box">This is a reverse item-source index, not a complete loot table. Drop quantities and current Forever availability remain unverified.</p>${value.assertions.map(fact => `<details class="recipe-card"><summary>Source metadata · ${esc(fact.source_key)}</summary>${Object.entries(fact.attributes).filter(([key]) => key !== "packed_fields").map(([key, field]) => `<div class="calc-row"><span>${esc(key.replaceAll("_", " "))}</span><span>${esc(Array.isArray(field) ? field.join(", ") : field)}</span></div>`).join("")}<p class="source-meta">v${esc(fact.source_version)} · ${esc(fact.retrieved_at)}<br>${esc(fact.raw_reference)}</p></details>`).join("")}<h4>${value.total.toLocaleString()} item associations</h4>${value.items.map(row => `<article class="recipe-card">${itemLink(row.item_id,row.item_name)}<p class="muted">${esc(row.method.replaceAll("_", " "))} · ${esc(row.evidence_basis.replaceAll("_", " "))}${row.probability !== null ? `<br>Source probability ${(row.probability * 100).toFixed(2)}%` : ""}${row.quest_condition ? " · quest conditional" : ""}${row.choice_reward ? " · optional reward choice" : ""}</p><p class="source-meta">${esc(row.raw_reference)}</p></article>`).join("") || `<p class="muted">No item associations indexed.</p>`}${value.total > value.limit ? `<div class="pagination"><button id="world-prev" ${offset === 0 ? "disabled" : ""}>Previous</button><span>${offset + 1}–${offset + value.items.length} / ${value.total}</span><button id="world-next" ${offset + value.items.length >= value.total ? "disabled" : ""}>Next</button></div>` : ""}`;
    $(".app-shell").classList.add("detail-open");
    if (originItemId) $("#back-to-item").addEventListener("click", () => void showItem(originItemId));
    else $("#back-to-item").remove();
    $("#detail-content").querySelectorAll<HTMLElement>("[data-item]").forEach(button => button.addEventListener("click", () => void showItem(Number(button.dataset.item))));
    document.querySelector("#world-prev")?.addEventListener("click", () => void showWorld(entityType,entityId,originItemId,Math.max(0,offset - value.limit)));
    document.querySelector("#world-next")?.addEventListener("click", () => void showWorld(entityType,entityId,originItemId,offset + value.items.length));
  } catch (error) { if (request === detailRequest) $("#detail-content").innerHTML = `<p class="muted">Could not load source: ${esc(error)}</p>`; }
}

async function showItem(itemId: number, desiredSnapshotId?: number, desiredMarket?: string): Promise<void> {
  const request = ++detailRequest;
  $(".app-shell").classList.add("detail-open");
  $("#detail-content").innerHTML = `<p class="muted">Loading item ${itemId}…</p>`;
  try {
    const item = await fetchJson<ItemDetail & {generic_assertions?:unknown; identity_history?:unknown; identity_selection_policy?:string}>(`/api/items/${itemId}`);
    if (request !== detailRequest) return;
    const markets = [...new Set(item.price_observations.map(row => String(row.market_key)))];
    const relations = [["produces", "Created by"], ["consumes", "Used in"], ["teaches", "Teaches"]];
    $("#detail-content").innerHTML = `<p class="eyebrow">Item ${itemId} · Local evidence</p><h3>${esc(item.name ?? `Unresolved item ${itemId}`)}</h3><h4>Market observations</h4>${markets.length ? `<label for="item-market">Price evidence</label><select id="item-market">${markets.map(market => `<option value="${esc(market)}">${esc(market === "wow-forever" ? "Your scans" : state.summary?.observed_markets.find(m => m.market_key === market)?.name ?? market)}</option>`).join("")}</select><div id="item-prices"></div><p class="muted">Listed prices do not establish a sale or expected liquidation value.</p>` : `<p class="muted">No market observations indexed for this item.</p>`}${relations.map(([key, label]) => `<h4>${label}</h4>${(item.recipe_relationships[key] ?? []).map(recipeCard).join("") || `<p class="muted">No sourced relationships indexed yet.</p>`}`).join("")}<h4>Identity evidence</h4>${item.identity_observations.map(record => `<details class="recipe-card"><summary>${esc(record.name)} · ${esc(record.source_key)}</summary><p class="source-meta">Retrieved ${esc(record.retrieved_at)}<br>Build ${esc(record.game_build ?? "unknown")}<br>${esc(record.raw_reference)}</p></details>`).join("") || `<p class="muted">${item.source_key ? `Source: ${esc(item.source_key)} · Retrieved ${esc(item.retrieved_at)}` : "The source supplied an item ID; its name and properties remain unresolved."}</p>`}`;
    $("#detail-content").insertAdjacentHTML("afterbegin", `<button id="open-item-history" class="text-link">Explore price and scan history</button>`);
    $("#open-item-history").addEventListener("click", () => { historyItem = itemId; $(".app-shell").classList.remove("detail-open"); setView("history"); });
    $("#detail-content").insertAdjacentHTML("beforeend", `<details class="recipe-card"><summary>Retained assertions and selection policy</summary><p class="muted">${esc(item.identity_selection_policy)}</p><pre class="history-result">${esc(JSON.stringify({generic:item.generic_assertions,identity:item.identity_history},null,2))}</pre></details>`);
    const renderPrices = () => {
      const market = $<HTMLSelectElement>("#item-market").value;
      const rows = item.price_observations.filter(row => row.market_key === market).slice(0, 30);
      $("#item-prices").innerHTML = rows.map(row => `<div class="evidence-item"><strong>${copper(row.current_min_unit_copper as number | null)} observed minimum</strong><span>${esc(row.source_key)} · ${esc(row.observed_date)}<br>Item key ${esc(row.item_key)} · Quantity ${esc(row.available_quantity)}<br>${row.source_key === "local-auctionator" ? "File modified (not per-item quote time)" : "Source timestamp"} ${esc(row.source_modified_at)}</span></div>`).join("");
    };
    if (markets.length) { $<HTMLSelectElement>("#item-market").value = markets.includes("wow-forever") ? "wow-forever" : markets[0]; renderPrices(); $("#item-market").addEventListener("change", renderPrices); }
    $("#detail-content").insertAdjacentHTML("beforeend", `<section><h4>Actual auction listings</h4>${item.listing_markets.length ? `<select id="depth-market" hidden>${item.listing_markets.map(market => `<option value="${esc(market.market_key)}">${esc(market.name)}</option>`).join("")}</select><label class="muted" for="depth-snapshot">Retained snapshot</label><select id="depth-snapshot"><option value="">Latest scan</option></select><div id="item-depth"></div>` : `<p class="muted">No individual auction rows indexed for this item.</p>`}</section>`);
    if (item.listing_markets.length) {
      if (desiredMarket && item.listing_markets.some(m => m.market_key === desiredMarket)) $<HTMLSelectElement>("#depth-market").value = desiredMarket;
      let scansMarket = "";
      const loadDepth = async (offset = 0) => {
        const marketKey = $<HTMLSelectElement>("#depth-market").value;
        try {
          if (scansMarket !== marketKey) {
            const scans = await fetchJson<{records: {id:number;captured_at:string}[]}>(`/api/scans?market_key=${encodeURIComponent(marketKey)}&limit=500`);
            if (request !== detailRequest || $<HTMLSelectElement>("#depth-market").value !== marketKey) return;
            $<HTMLSelectElement>("#depth-snapshot").innerHTML = `<option value="">Latest scan</option>` + scans.records.map(scan => `<option value="${scan.id}">${esc(scan.captured_at)} / #${scan.id}</option>`).join("");
            if (desiredSnapshotId && scans.records.some(scan => scan.id === desiredSnapshotId)) $<HTMLSelectElement>("#depth-snapshot").value = String(desiredSnapshotId);
            desiredSnapshotId = undefined; scansMarket = marketKey;
          }
          const selected = $<HTMLSelectElement>("#depth-snapshot").value;
          const depth = await fetchJson<DepthPage>(`/api/market-depth?item_id=${itemId}&market_key=${encodeURIComponent(marketKey)}&limit=10&offset=${offset}${selected ? `&snapshot_id=${selected}` : ""}`);
          if (request !== detailRequest || $<HTMLSelectElement>("#depth-snapshot").value !== selected) return;
          if (request !== detailRequest || $<HTMLSelectElement>("#depth-market").value !== marketKey) return;
          $("#item-depth").innerHTML = depth.snapshot ? `<p class="source-meta">Captured ${esc(depth.snapshot.captured_at)}<br>Region ${esc(depth.snapshot.region)} · Build ${esc(depth.snapshot.game_build)}<br>Completeness unverified · gear variants unavailable</p><p>${depth.totals?.listing_count} listings · ${depth.totals?.listed_units} units · ${depth.totals?.bid_only_listings} bid-only</p><p class="muted">Listed supply is not sales or liquidity. Each amount below is the total for that stack.</p>${depth.listings.map(row => `<div class="evidence-item"><strong>Stack of ${row.quantity} · ${row.buyout_copper > 0 ? copper(row.buyout_copper) : "Bid-only; no buyout"}</strong><span>${row.unit_buyout_copper !== null ? `${copper(row.unit_buyout_copper)} per unit · ` : ""}Source bid field ${copper(row.bid_copper)} · Row ${row.ordinal}</span></div>`).join("") || `<p class="muted">No rows for this item in the selected scan; completeness is unverified.</p>`}<details class="recipe-card"><summary>Stack-size distribution</summary>${(depth.stack_distribution ?? []).map(row => `<div class="calc-row"><span>× ${row.stack_size} · ${row.listing_count} listings</span><span>${copper(row.min_stack_buyout_copper)} lowest stack buyout</span></div>`).join("")}</details>${depth.total > depth.limit ? `<div class="pagination"><button id="depth-prev" ${offset === 0 ? "disabled" : ""}>Previous</button><span>${offset + 1}–${offset + depth.listings.length} / ${depth.total}</span><button id="depth-next" ${offset + depth.listings.length >= depth.total ? "disabled" : ""}>Next</button></div>` : ""}` : `<p class="muted">No saved scan for this market.</p>`;
          document.querySelector("#depth-prev")?.addEventListener("click", () => void loadDepth(Math.max(0,offset - 10)));
          document.querySelector("#depth-next")?.addEventListener("click", () => void loadDepth(offset + depth.listings.length));
        } catch (error) { if (request === detailRequest) $("#item-depth").innerHTML = `<p class="muted">Could not load listings: ${esc(error)}</p>`; }
      };
      $("#depth-market").addEventListener("change", () => void loadDepth());
      $("#depth-snapshot").addEventListener("change", () => void loadDepth());
      void loadDepth();
    }
    $("#detail-content").insertAdjacentHTML("beforeend", `<section id="item-acquisition"></section>`);
    renderAcquisition({...item.acquisition, records: item.acquisition.records.slice(0, 10), limit: 10}, request);
    $("#detail-content").querySelectorAll<HTMLElement>("[data-item]").forEach(button => button.addEventListener("click", () => void showItem(Number(button.dataset.item))));
  } catch (error) { if (request === detailRequest) $("#detail-content").innerHTML = `<p class="muted">Could not load this item: ${esc(error)}</p>`; }
}

function renderSources(): void {
  if (!state.sources) return;
  const sourceCards = state.sources.sources.map(source => `<article class="source-card"><p class="eyebrow">Rank ${esc(source.trust_rank)} · ${esc(source.source_type)}</p><h4>${esc(source.name)}</h4><div class="source-meta">Key: ${esc(source.source_key)}<br>Price records: ${esc(source.price_record_count ?? 0)}<br>Auction rows: ${esc(source.auction_row_count ?? 0)}<br>Recipe records: ${esc(source.recipe_record_count ?? 0)}<br>Acquisition links: ${esc(source.acquisition_record_count ?? 0)}<br>World entities: ${esc(source.world_entity_record_count ?? 0)}<br>Travel nodes: ${esc(source.travel_node_count ?? 0)}<br>Travel connections: ${esc(source.travel_edge_count ?? 0)}<br>Cached documents: ${esc(source.cached_document_count ?? 0)}<br>Last import: ${esc(source.last_success_at ?? "none")}<br>Latest error: ${esc(source.last_error ?? "none")}</div><span class="source-state ${source.last_error ? "blocked" : ""}">${source.last_error ? "Import error" : !source.enabled ? "Disabled" : source.last_success_at ? "Imported" : "Waiting for import"}</span></article>`).join("");
  const adapters = state.sources.adapters.map(adapter => `<article class="source-card"><p class="eyebrow">Ingestion adapter</p><h4>${esc(adapter.display_name)}</h4><div class="source-meta">Inputs: ${esc((adapter.input_types as unknown[]).join(", "))}<br>Needs: ${esc((adapter.needs as unknown[]).join(" · ") || "Nothing")}</div><span class="source-state ${String(adapter.status).startsWith("ready") ? "" : "blocked"}">${esc(adapter.status)}</span></article>`).join("");
  const unconnected = (state.sources.unconnected_installed_data_addons ?? []).map(addon => `<article class="source-card"><p class="eyebrow">Installed data addon</p><h4>${esc(addon.addon)}</h4><div class="source-meta">${esc(addon.notes)}</div><span class="source-state blocked">Importer unavailable</span></article>`).join("");
  $("#sources-view").innerHTML = `<div class="section-heading"><div><p class="eyebrow">Data lineage</p><h3>Source health</h3></div></div><div class="source-grid">${sourceCards}${adapters}${unconnected}</div>`;
}

function renderNextData(): void {
  if (!state.nextData) return;
  $("#next-data-view").innerHTML = `<div class="section-heading"><div><p class="eyebrow">Research coverage</p><h3>${esc(state.nextData.headline)}</h3></div></div><div class="next-grid">${state.nextData.items.map(item => `<article class="next-card"><span class="priority">${item.priority}</span><p class="eyebrow">Missing evidence</p><h4>${esc(item.title)}</h4><p class="muted">${esc(item.needed)}</p><ul class="unlock-list">${item.unlocks.map(value => `<li>${esc(value)}</li>`).join("")}</ul></article>`).join("")}</div>`;
}

type CharacterSummary = { snapshot_id: number; name: string; realm: string | null; race: string | null; class_token: string; level: number; game_build: string | null; source_key: string; imported_at: string; captured_at: string | null };
type CharacterSnapshot = CharacterSummary & { limitations: string[]; confidence_basis: string; money_copper?: number; coverage?: Record<string,{status:string}>; character?: {faction?:string;zone?:string;hearth?:string;xp?:number;xpMax?:number;profs?:Record<string,number>;profMax?:Record<string,number>;recipes?:Record<string,Record<string,boolean>>;reps?:Record<string,number>;dura?:number}; source_payload?: {factions?:Record<string,string>}; items: { location: string; item_id: number; quantity?: number; item_link?:string; enchant_id: number | null; random_suffix: number | null; slot_id: number | null }[] };

async function showCharacter(snapshotId: number): Promise<void> {
  const request = ++detailRequest;
  try {
    const character = await fetchJson<CharacterSnapshot>(`/api/characters/${snapshotId}`);
    if (request !== detailRequest) return;
    const locations = [...new Set(character.items.map(item => item.location))];
    const c = character.character;
    const context = c ? `<h4>Progress and professions</h4><p>${esc(c.faction)} · ${esc(c.zone)} · Hearth: ${esc(c.hearth)}<br>Money: ${copper(character.money_copper)} · XP: ${esc(c.xp)} / ${esc(c.xpMax)} · Lowest durability: ${esc(c.dura)}%</p>${Object.entries(c.profs ?? {}).map(([name,skill]) => `<div class="calc-row"><span>${esc(name)}</span><span>${skill} / ${esc(c.profMax?.[name])}</span></div>`).join("")}<h4>Recorded coverage</h4>${Object.entries(character.coverage ?? {}).map(([name,value])=>`<div class="calc-row"><span>${esc(name)}</span><span>${esc(value.status.replaceAll("_"," "))}</span></div>`).join("")}${c.recipes ? `<h4>Known recipes</h4>${Object.entries(c.recipes).map(([name,recipes])=>`<p>${esc(name)}: ${Object.keys(recipes).map(esc).join(", ") || "Recorded empty"}</p>`).join("")}` : ""}${c.reps ? `<h4>Reputation (source values)</h4>${Object.entries(c.reps).map(([id,value])=>`<div class="calc-row"><span>${esc(character.source_payload?.factions?.[id] ?? `Faction ${id}`)}</span><span>${value}</span></div>`).join("")}` : ""}` : "";
    $("#detail-content").innerHTML = `<p class="eyebrow">Saved character observation</p><h3>${esc(character.name)}${character.realm ? ` · ${esc(character.realm)}` : ""}</h3><p class="muted">Level ${esc(character.level)} ${character.race ? esc(character.race) : ""} ${esc(character.class_token)} · Source ${esc(character.source_key)}<br>Build ${esc(character.game_build ?? "unknown")} · Saved ${esc(character.captured_at ?? "time unknown")} · Imported ${esc(character.imported_at)}</p>${context}${locations.map(location => `<h4>${esc(location)}</h4>${character.items.filter(item => item.location === location).map(item => `<div class="calc-row">${itemLink(item.item_id,item.item_link?.match(/\|h\[([^\]]+)\]/)?.[1])}<span>× ${esc(item.quantity ?? 1)}${item.slot_id === null ? "" : ` · Slot ${esc(item.slot_id)}`}${item.enchant_id === null ? "" : ` · Enchant ${esc(item.enchant_id)}`}${item.random_suffix === null ? "" : ` · Suffix ${esc(item.random_suffix)}`}</span></div>`).join("")}`).join("")}<h4>Evidence limits</h4><ul>${character.limitations.map(value => `<li>${esc(value)}</li>`).join("")}</ul><p class="muted">${esc(character.confidence_basis)}</p>`;
    $("#detail-content").querySelectorAll<HTMLElement>("[data-item]").forEach(button => button.addEventListener("click", () => void showItem(Number(button.dataset.item))));
    $(".app-shell").classList.add("detail-open");
  } catch (error) { if (request === detailRequest) { $("#detail-content").textContent = `Could not load character: ${error}`; $(".app-shell").classList.add("detail-open"); } }
}

async function renderCharacters(): Promise<void> {
  const request = ++catalogRequest;
  $("#feed-heading").textContent = "Your character snapshots";
  $("#evidence-grid").innerHTML = `<div class="empty">Loading characters…</div>`;
  try {
    const result = await fetchJson<{ characters: CharacterSummary[]; refresh_instructions: string }>("/api/characters");
    if (request !== catalogRequest || state.view !== "characters") return;
    $("#evidence-grid").innerHTML = result.characters.map(character => `<button class="evidence-card item-card" data-character="${character.snapshot_id}"><p class="eyebrow">Level ${esc(character.level)} · ${esc(character.race)} ${esc(character.class_token)}</p><h4>${esc(character.name)}</h4><p>${esc(character.realm)} · Build ${esc(character.game_build)}</p><p class="muted">Source ${esc(character.source_key)}<br>Saved ${esc(character.captured_at ?? "time unknown")} · Imported ${esc(character.imported_at)}</p><div class="card-action"><span>Inspect character evidence</span><b>↗</b></div></button>`).join("") || `<div class="empty">No character observations saved yet.</div>`;
    $("#evidence-grid").insertAdjacentHTML("beforeend", `<article class="source-card"><h4>Refresh character data</h4><p>${esc(result.refresh_instructions)}</p></article>`);
    $("#evidence-grid").querySelectorAll<HTMLElement>("[data-character]").forEach(button => button.addEventListener("click", () => void showCharacter(Number(button.dataset.character))));
  } catch (error) { if (request === catalogRequest && state.view === "characters") $("#evidence-grid").innerHTML = `<div class="empty">Could not load characters: ${esc(error)}</div>`; }
}

function setView(view: string): void {
  state.view = view; document.querySelectorAll(".nav-item").forEach(element => element.classList.toggle("active", (element as HTMLElement).dataset.view === view));
  const normal = view === "items" || view === "market" || view === "world" || view === "characters" || view === "history" || view === "scans"; $("#hero").classList.toggle("hidden", !normal || view === "characters"); $("#evidence-view").classList.toggle("hidden", !normal);
  $("#item-search").classList.toggle("hidden", view !== "items");
  $("#sources-view").classList.toggle("hidden", view !== "sources"); $("#next-data-view").classList.toggle("hidden", view !== "next-data");
  $("#companion-view").classList.toggle("hidden", view !== "companion");
  const titles: Record<string, string> = { companion: "Gaming companion", scans: "Saved scan overview", history: "Market history", characters: "Characters", items: "Item explorer", market: "Market observations", world: "World data index", sources: "Source health", "next-data": "Missing evidence" }; $("#page-title").textContent = titles[view] ?? "Evidence";
  if (view === "companion") void renderCompanion();
  if (view === "scans") void renderScanSummary();
  if (view === "history") renderHistory();
  if (view === "characters") void renderCharacters();
  if (view === "items") void renderItems();
  if (view === "market") { $("#feed-heading").textContent = "Sourced market records"; renderMarket(); }
  if (view === "world") { $("#feed-heading").textContent = "Indexed evidence by type"; renderWorld(); }
}

async function fetchJson<T>(path: string): Promise<T> { const response = await fetch(path); if (!response.ok) { const problem = await response.json().catch(() => ({})); throw new Error(problem.error ?? `${response.status} ${response.statusText}`); } return response.json() as Promise<T>; }

async function postJson<T>(path: string, value: object): Promise<T> {
  const response = await fetch(path, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(value)});
  if (!response.ok) { const problem = await response.json().catch(() => ({})); throw new Error(problem.error ?? `${response.status} ${response.statusText}`); }
  return response.json() as Promise<T>;
}

let companionRequest = 0;
let companionOffset = 0;
let companionNextOffset: number | null = null;
async function renderCompanion(): Promise<void> {
  const request = ++companionRequest;
  const kind = $<HTMLSelectElement>("#companion-kind-filter").value;
  const status = $<HTMLSelectElement>("#companion-status-filter").value;
  const params = new URLSearchParams({limit:"20",offset:String(companionOffset)});
  if (kind) params.set("kind",kind);
  if (status) params.set("status",status);
  $("#companion-entries").innerHTML = `<p class="muted">Loading saved context…</p>`;
  try {
    const page = await fetchJson<CompanionPage>(`/api/companion/entries?${params}`);
    if (request !== companionRequest || state.view !== "companion") return;
    companionNextOffset = page.next_offset;
    $("#companion-entries").innerHTML = page.records.map(entry => `<article class="companion-entry">
      <p class="eyebrow">${esc(entry.kind)} · ${esc(entry.status)} · ${esc(entry.basis.replaceAll("_"," "))}</p>
      <h4>${esc(entry.title)}</h4><p class="companion-body">${esc(entry.body)}</p>
      <p class="source-meta">Recorded ${esc(entry.created_at)} by ${esc(entry.author)}${entry.occurred_at ? ` · Reported time ${esc(entry.occurred_at)}` : ""}${entry.character_snapshot_id ? ` · Character snapshot #${entry.character_snapshot_id}` : ""}</p>
      ${entry.evidence_refs.length ? `<details><summary>Stated references</summary><ul>${entry.evidence_refs.map(ref=>`<li>${esc(ref)}</li>`).join("")}</ul></details>` : ""}
      <div class="companion-actions">${entry.status !== "active" ? `<button data-entry="${entry.id}" data-status="active">Restore</button>` : ""}${entry.status !== "completed" ? `<button data-entry="${entry.id}" data-status="completed">Complete</button>` : ""}${entry.status !== "archived" ? `<button data-entry="${entry.id}" data-status="archived">Archive</button>` : ""}</div>
    </article>`).join("") || `<div class="empty">No ${esc(status || "saved")} entries here. Add a goal or note above.</div>`;
    $("#companion-page").textContent = `${page.total ? page.offset+1 : 0}–${page.offset+page.records.length} of ${page.total}`;
    $<HTMLButtonElement>("#companion-prev").disabled = companionOffset === 0;
    $<HTMLButtonElement>("#companion-next").disabled = companionNextOffset === null;
    $("#companion-entries").querySelectorAll<HTMLButtonElement>("[data-entry][data-status]").forEach(button => button.addEventListener("click", async () => {
      button.disabled = true;
      try { await postJson(`/api/companion/entries/${button.dataset.entry}/status`, {status:button.dataset.status}); void renderCompanion(); }
      catch (error) { $("#companion-message").textContent = `Could not update entry: ${String(error)}`; button.disabled = false; }
    }));
  } catch (error) { if (request === companionRequest) $("#companion-entries").textContent = `Could not load companion entries: ${String(error)}`; }
}

$("#companion-add-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget as HTMLFormElement;
  const data = new FormData(form);
  const evidence_refs = String(data.get("evidence_refs") ?? "").split(/\r?\n/).map(value=>value.trim()).filter(Boolean);
  const button = form.querySelector<HTMLButtonElement>("button[type=submit]")!;
  button.disabled = true;
  $("#companion-message").textContent = "Saving…";
  try {
    await postJson<CompanionEntry>("/api/companion/entries", {kind:data.get("kind"),title:data.get("title"),body:data.get("body"),basis:data.get("basis"),evidence_refs});
    form.reset(); companionOffset = 0; $("#companion-message").textContent = "Saved locally."; void renderCompanion();
  } catch (error) { $("#companion-message").textContent = `Could not save: ${String(error)}`; }
  finally { button.disabled = false; }
});
$("#companion-kind-filter").addEventListener("change", () => {companionOffset=0;void renderCompanion();});
$("#companion-status-filter").addEventListener("change", () => {companionOffset=0;void renderCompanion();});
$("#companion-prev").addEventListener("click", () => {companionOffset=Math.max(0,companionOffset-20);void renderCompanion();});
$("#companion-next").addEventListener("click", () => {if(companionNextOffset!==null){companionOffset=companionNextOffset;void renderCompanion();}});

async function start(): Promise<void> {
  $("#evidence-grid").innerHTML = `<div class="loading-card"></div><div class="loading-card"></div>`;
  try {
    const [summary, observations, sources, nextData] = await Promise.all([fetchJson<Summary>("/api/health"), fetchJson<Observation[]>("/api/market-observations?limit=250"), fetchJson<SourceHealth>("/api/sources"), fetchJson<NextData>("/api/next-data")]);
    state.summary = summary; state.observations = observations; state.sources = sources; state.nextData = nextData;
    const observedMarket = "WoW Forever"; $("#market-name").textContent = String(observedMarket);
    const freshness = $<HTMLElement>("#freshness-pill"); freshness.innerHTML = `<i></i>${summary.freshness.newest_snapshot ? (summary.freshness.is_stale ? "Stale source data" : "Recent auction evidence") : "Waiting for real data"}`; freshness.classList.toggle("warning", summary.freshness.is_stale);
    const metrics = $("#hero-metrics").querySelectorAll(".metric-value"); metrics[0].textContent = String(Object.values(summary.record_counts).reduce((total, value) => total + value, 0)); metrics[1].textContent = String(summary.source_count);
    setView(state.view); renderSources(); renderNextData();
    freshness.title = "Newest auction evidence across local scans and public references; inspect individual source times.";
  } catch (error) { $("#evidence-grid").innerHTML = `<div class="empty">Could not load local evidence: ${esc(error)}</div>`; }
}

document.querySelectorAll<HTMLElement>(".nav-item").forEach(element => element.addEventListener("click", () => setView(element.dataset.view ?? "market")));
$("#close-detail").addEventListener("click", () => { detailRequest++; $(".app-shell").classList.remove("detail-open"); });
$("#item-search").addEventListener("submit", event => { event.preventDefault(); state.query = $<HTMLInputElement>("#item-query").value; void renderItems(); });
let historyItem: number | undefined;
let historyRequest = 0;
type HistoryRow = {snapshot_id?: number; capture_id?: number; observed_at: string | null; observed_date?: string; minimum_copper: number | null; median_copper?: number | null; quantity_weighted_median_copper?: number | null; listed_units?: number; available_quantity?: number | null; granularity?: string; source_key?: string; economic_period?: string; [key: string]: unknown};

function renderHistory(): void {
  ++historyRequest;
  $("#feed-heading").textContent = "Retained observations over time";
  $("#evidence-grid").innerHTML = `<section class="history-panel"><form id="history-form" class="history-controls">
    <label>Item ID<input id="history-item" type="number" min="1" required value="${historyItem ?? ""}"></label>
    <input id="history-market" type="hidden" value="wow-forever">
    <label>Evidence<select id="history-kind"><option value="scans">Auction listings across scans</option><option value="prices">Auctionator price observations</option><option value="public">AHledger community prices</option></select></label>
    <label id="history-public-label" hidden>Comparison market<select id="history-public-market">${(state.summary?.observed_markets ?? []).filter(m => String(m.market_key).startsWith("forever.")).map(m => `<option value="${esc(m.market_key)}" >${esc(m.name)}</option>`).join("")}</select></label>
    <label>From (local time)<input id="history-from" type="datetime-local" required></label>
    <label>Through (local time)<input id="history-to" type="datetime-local" required></label>
    <label>Economic phase (optional)<input id="history-period" placeholder="Exact phase label, e.g. unknown"></label>
    <button type="submit">Load history</button></form>
    <p class="muted">WoW Forever · Your scans and AHledger community prices, separated by source. Listing scans retain timestamps and supply. Auctionator observations have day-level precision. Missing listings do not prove a sale. Economic phase filters content progression, not daily/hourly chart resolution.</p>
    <div id="history-output" aria-live="polite">Select an item and time window.</div></section>`;
  const local = (date: Date) => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0,16);
  $<HTMLInputElement>("#history-from").value = local(new Date(Date.now() - 7 * 86400000));
  $<HTMLInputElement>("#history-to").value = local(new Date(Date.now() + 60000));
  $("#history-kind").addEventListener("change", () => { $<HTMLElement>("#history-public-label").hidden = $<HTMLSelectElement>("#history-kind").value !== "public"; });
  $("#history-form").addEventListener("submit", event => { event.preventDefault(); void loadHistory(); });
}

async function loadHistory(offset = 0): Promise<void> {
  const request = ++historyRequest;
  const item = Number($<HTMLInputElement>("#history-item").value);
  const market = $<HTMLSelectElement>("#history-kind").value === "public" ? $<HTMLSelectElement>("#history-public-market").value : "wow-forever";
  const startTime = new Date($<HTMLInputElement>("#history-from").value).toISOString();
  const endTime = new Date($<HTMLInputElement>("#history-to").value).toISOString();
  const local = $<HTMLSelectElement>("#history-kind").value === "scans";
  const params = new URLSearchParams({item_id:String(item),market_key:market,start:startTime,end:endTime,limit:local ? "500" : "100",offset:String(offset)});
  if (!local) params.set("source_key", $<HTMLSelectElement>("#history-kind").value === "public" ? "ahledger" : "local-auctionator");
  const selectedPeriod = $<HTMLInputElement>("#history-period").value.trim();
  if(selectedPeriod) params.set("period",selectedPeriod);
  $("#history-output").textContent = "Loading retained evidence…";
  try {
    const page = await fetchJson<{records:HistoryRow[];total?:number;truncated?:boolean;limitations:string[]}>(`/api/${local ? "scan-history" : "price-history"}?${params}`);
    if (request !== historyRequest || state.view !== "history") return;
    const rows = page.records;
    const dots = rows.filter(r => r.minimum_copper !== null && r.minimum_copper > 0 && (r.observed_at || r.observed_date));
    const prices = dots.map(r => r.minimum_copper as number);
    const low = Math.min(...prices), high = Math.max(...prices);
    const a = new Date(startTime).getTime(), b = new Date(endTime).getTime();
    const chart = dots.map(row => {
      const x = 45 + (new Date(row.observed_at ?? `${row.observed_date}T00:00:00Z`).getTime() - a) / Math.max(1,b-a) * 800;
      const y = 170 - ((row.minimum_copper as number) - low) / Math.max(1,high-low) * 130;
      return `<circle cx="${x}" cy="${y}" r="4" fill="${row.granularity?.includes("daily") ? "#dfb863" : "#9bcf74"}"><title>${esc(row.observed_at ?? row.observed_date)} / ${copper(row.minimum_copper)}</title></circle>`;
    }).join("");
    $("#history-output").innerHTML = `<p>${rows.length} records shown${page.total !== undefined ? ` / ${page.total} matching` : ""}${page.truncated ? " · Window truncated; narrow dates" : ""}. Loaded ${esc(new Date().toLocaleTimeString())}.</p>
      ${dots.length ? `<svg class="history-chart" viewBox="0 0 900 210" role="img" aria-label="Observed unit minima; dots are observations, not continuous prices"><text x="10" y="20" fill="#89968c">${esc(copper(high))} max · ${esc(copper(low))} min · amber = day-level evidence</text><path d="M40 35V180H860" stroke="#566159" fill="none"/>${chart}</svg>` : `<p>No positive buyout minima in this selection.</p>`}
      <button id="history-reference">Calculate explicit price reference</button><button id="history-refresh">Refresh this window</button><div id="history-calculation"></div>
      <div class="history-scroll"><table class="history-table"><thead><tr><th>Source time / date</th><th>Unit minimum</th><th>Units / source quantity</th><th>Precision</th><th>Evidence</th></tr></thead><tbody>${rows.map((row,i) => `<tr><td>${esc(row.observed_at ?? row.observed_date)}</td><td>${copper(row.minimum_copper)}</td><td>${esc(row.listed_units ?? row.available_quantity)}</td><td>${esc(row.granularity ?? "saved scan")} / ${esc(row.economic_period)}</td><td><button data-history-evidence="${i}">Inspect ${esc(row.snapshot_id ?? row.capture_id)}</button>${row.snapshot_id ? `<button data-history-scan="${row.snapshot_id}">Open depth</button>` : ""}</td></tr>`).join("")}</tbody></table></div>
      ${!local && (page.total ?? 0) > 100 ? `<div class="pagination"><button id="history-prev" ${offset===0 ? "disabled" : ""}>Previous</button><button id="history-next" ${offset+rows.length >= (page.total ?? 0) ? "disabled" : ""}>Next</button></div>` : ""}
      <div id="history-evidence"></div>${page.limitations.map(s => `<p class="muted">${esc(s)}</p>`).join("")}`;
    $("#history-output").querySelectorAll<HTMLElement>("[data-history-evidence]").forEach(button => button.addEventListener("click",() => { $("#history-evidence").innerHTML = `<pre class="history-result">${esc(JSON.stringify(rows[Number(button.dataset.historyEvidence)],null,2))}</pre>`; }));
    $("#history-output").querySelectorAll<HTMLElement>("[data-history-scan]").forEach(button => button.addEventListener("click",() => void showItem(item,Number(button.dataset.historyScan),market)));
    $("#history-refresh").addEventListener("click",() => void loadHistory(offset));
    document.querySelector("#history-prev")?.addEventListener("click",() => void loadHistory(Math.max(0,offset-100)));
    document.querySelector("#history-next")?.addEventListener("click",() => void loadHistory(offset+100));
    $("#history-reference").addEventListener("click", async () => {
      const sources = [...new Set(rows.filter(r => r.granularity === "source_table").map(r => r.source_key))];
      const periods = [...new Set(rows.filter(r => local || r.granularity === "source_table").map(r => r.economic_period))];
      if (periods.length !== 1 || (!local && sources.length !== 1)) { $("#history-calculation").textContent = "A price reference needs multiple timestamped listing scans in one economic period. Auctionator day-level observations cannot supply that precision."; return; }
      const query = new URLSearchParams({item_id:String(item),market_key:market,start:startTime,end:endTime,source_key:local ? "local-ahledger" : String(sources[0]),period:String(periods[0])});
      try {
        const reference = await fetchJson<unknown>(`/api/price-reference?${query}`);
        if(request===historyRequest && state.view === "history") $("#history-calculation").innerHTML=`<pre class="history-result">${esc(JSON.stringify(reference,null,2))}</pre>`;
      } catch(error) { if(request===historyRequest && state.view === "history") $("#history-calculation").textContent=String(error); }
    });
  } catch(error) { if(request===historyRequest && state.view === "history") $("#history-output").textContent=`Could not load history: ${error}`; }
}

// Refresh the overview independently; don't reset an open item or research form.
setInterval(async () => {
  try {
    const [summary,sources,observations] = await Promise.all([fetchJson<Summary>("/api/health"),fetchJson<SourceHealth>("/api/sources"),fetchJson<Observation[]>("/api/market-observations?limit=250")]);
    state.summary=summary;state.sources=sources;state.observations=observations;
    $("#freshness-pill").textContent=summary.freshness.is_stale ? "Source data stale or unknown" : "Recent auction evidence";
    $<HTMLElement>("#freshness-pill").title=`Overview refreshed ${new Date().toLocaleTimeString()}; inspect selected source times.`;
    if(state.view==='market') renderMarket();
    if(state.view==='sources') renderSources();
  } catch { $("#freshness-pill").textContent="Refresh failed; displayed records may be old"; }
},60000);
void start();

let worldSearchRequest = 0;
async function loadWorldSearch(offset = 0): Promise<void> {
  const request = ++worldSearchRequest;
  const params = new URLSearchParams({limit:"20", offset:String(offset)});
  new FormData($<HTMLFormElement>("#world-search-form")).forEach((value,key) => { if (String(value).trim()) params.set(key,String(value).trim()); });
  $("#world-search-output").textContent = "Searching sourced world records…";
  try {
    type WorldHit = { entity_type:string; entity_id:number; name:string; zone_name:string|null; rank_name:string|null; attributes:Record<string,unknown>; evidence_kind:string; source_key:string; retrieved_at:string };
    const page = await fetchJson<{records:WorldHit[];total:number;truncated:boolean}>(`/api/world-search?${params}`);
    if (request !== worldSearchRequest || state.view !== "world") return;
    $("#world-search-output").innerHTML = `<p>${page.total} matching source assertions · ${page.records.length} shown. Filters apply before pagination.</p>` + page.records.map(r => `<button class="evidence-card" data-world-id="${r.entity_id}" data-world-kind="${esc(r.entity_type)}"><h4>${esc(r.name)}</h4><p>${esc(r.zone_name ?? r.attributes.ui_map_id)} · Level ${esc(r.attributes.min_level)}–${esc(r.attributes.max_level)} · ${esc(r.rank_name ?? "Rank unknown")}</p><p class="muted">${esc(r.evidence_kind)} · ${esc(r.source_key)} · ${esc(r.retrieved_at)}</p></button>`).join("") + `${!page.total ? '<p>No matching records. This does not establish absence from the game.</p>' : ''}<div class="pagination"><button id="world-search-prev" ${offset===0 ? 'disabled' : ''}>Previous</button><button id="world-search-next" ${!page.truncated ? 'disabled' : ''}>Next</button></div>`;
    $("#world-search-output").querySelectorAll<HTMLElement>("[data-world-id]").forEach(button => button.addEventListener("click", () => void showWorld(button.dataset.worldKind!,Number(button.dataset.worldId),0)));
    $("#world-search-prev").addEventListener("click", () => void loadWorldSearch(Math.max(0,offset-20)));
    $("#world-search-next").addEventListener("click", () => void loadWorldSearch(offset+20));
  } catch (error) { if (request===worldSearchRequest && state.view==='world') $("#world-search-output").textContent=String(error); }
}

let scanSummaryRequest = 0;
async function renderScanSummary(offset=0, sortBy='listed_units'): Promise<void> {
  const request = ++scanSummaryRequest;
  $("#feed-heading").textContent = "Latest personal listing scan";
  $("#evidence-grid").innerHTML = '<p>Reading saved listings…</p>';
  try {
    type ScanItem = {item_id:number;item_name:string|null;listing_count:number;listed_units:number;bid_only_listings:number;min_unit_buyout_copper:number|null;quality_evidence:{quality:string}|null};
    const page = await fetchJson<{snapshot:{id:number;captured_at:string}|null;totals?:{listing_count:number;item_count:number};records:ScanItem[];total:number;limitations?:string[]}>(`/api/scan-summary?limit=30&offset=${offset}&sort_by=${sortBy}`);
    if(request!==scanSummaryRequest || state.view!=='scans') return;
    $("#evidence-grid").innerHTML = `<section class="history-panel"><p>${page.snapshot ? `Saved ${esc(page.snapshot.captured_at)} · ${esc(page.totals?.listing_count)} listings · ${esc(page.total)} items` : 'No saved local listing scans.'}</p><label>Sort descending <select id="scan-sort">${['listed_units','listing_count','listed_buyout_copper','min_unit_buyout_copper'].map(k=>`<option value="${k}" ${k===sortBy?'selected':''}>${esc(k.replaceAll('_',' '))}</option>`).join('')}</select></label><p class="muted">Asking supply, not demand, profit or completed sales. Select an item for depth and history.</p><table class="history-table"><thead><tr><th>Item</th><th>Quality</th><th>Listings</th><th>Units</th><th>Unit minimum</th></tr></thead><tbody>${page.records.map(r=>`<tr><td>${itemLink(r.item_id,r.item_name)}</td><td>${esc(r.quality_evidence?.quality)}</td><td>${r.listing_count}</td><td>${r.listed_units}</td><td>${copper(r.min_unit_buyout_copper)}</td></tr>`).join('')}</tbody></table><div class="pagination"><button id="scan-prev" ${offset===0?'disabled':''}>Previous</button><button id="scan-next" ${offset+page.records.length>=page.total?'disabled':''}>Next</button></div></section>`;
    $("#scan-sort").addEventListener("change",()=>void renderScanSummary(0,$<HTMLSelectElement>('#scan-sort').value));
    $("#scan-prev").addEventListener("click",()=>void renderScanSummary(Math.max(0,offset-30),sortBy));
    $("#scan-next").addEventListener("click",()=>void renderScanSummary(offset+30,sortBy));
    $("#evidence-grid").querySelectorAll<HTMLElement>("[data-item]").forEach(button=>button.addEventListener("click",()=>void showItem(Number(button.dataset.item),page.snapshot?.id)));
  } catch(error) { if(request===scanSummaryRequest && state.view==='scans') $("#evidence-grid").textContent=String(error); }
}
