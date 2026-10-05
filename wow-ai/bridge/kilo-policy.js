'use strict';
// Companion policy is process-local; it never rewrites the user's Kilo config.
const TOOL_NAMES=[
  "calculate_price_reference",
  "calculate_trade_scenario",
  "compare_market_scans",
  "get_acquisition_evidence",
  "get_character_snapshot",
  "get_companion_context",
  "get_companion_entry",
  "get_economic_summary",
  "get_fact_assertions",
  "get_farming_research",
  "get_history_coverage",
  "get_item_acquisition",
  "get_item_research",
  "get_market_depth",
  "get_market_observations",
  "get_next_data_needed",
  "get_price_history",
  "get_recipe_evidence",
  "get_research_datasets",
  "get_scan_history",
  "get_scan_provenance",
  "get_scan_summary",
  "get_source_health",
  "get_world_entity",
  "list_cached_source_documents",
  "list_characters",
  "list_companion_entries",
  "list_market_scans",
  "read_cached_source_document",
  "search_acquisition_sources",
  "search_cached_source_documents",
  "search_evidence",
  "search_items",
  "search_travel_edges",
  "search_travel_nodes",
  "search_world_entities"
];
function restrictedEnv(env) {
 let content={};
 if(env.KILO_CONFIG_CONTENT){try{content=JSON.parse(env.KILO_CONFIG_CONTENT);}catch{throw Error('KILO_CONFIG_CONTENT must be valid JSON for companion restrictions.');}}
 const permission={'*':'deny',read:{'*':'allow','.env':'deny','*.env.*':'deny'},glob:'allow',grep:'allow',list:'allow',webfetch:'allow',websearch:'allow',todoread:'allow',todowrite:'allow'};
 for(const name of TOOL_NAMES)permission['goblin-eye_'+name]='allow';
 content.agent={...(content.agent||{}),'goblin-research':{description:'Read-only Goblin Eye companion',mode:'primary',permission}};
 return {...env,KILO_CONFIG_CONTENT:JSON.stringify(content)};
}
module.exports={restrictedEnv,TOOL_NAMES};
