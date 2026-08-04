# Phase 2.4 — `generate-eeat.js` and `generate-stats.js` Plain-English Summary

## `generate-eeat.js` (1151 lines) → `enrichment.py` (`enrich_place`)

### What it does

Generates AI content (EEAT = Experience, Expertise, Authoritativeness,
Trustworthiness) for all entity types (states, regions, suburbs) using Google
Gemini, and stores it in the Supabase `content` table.

### Constants & config

- **Rate limiting**: 4000 RPM Gemini paid tier, targets 500 RPM
  (120ms interval between requests). `DB_BATCH_SIZE = 50`,
  `RETRY_LIMIT = 3`, exponential backoff (2s, 4s, 8s).
- **All 21 feature keys** tracked (same set as `enrich.js`).
- **Feature labels** — human-readable names for the prompt.
- **Priority features per entity type**: `state`, `region`, `suburb` — which
  features get listed individually vs. collapsed into "also available".
- **Placeholder system**: `{{toilet_count}}`, `{{accessible_count}}`, etc.
  Content is stored with placeholders and resolved at page-render time in
  Next.js, so stats stay live without content regeneration.
  `sanitisePlaceholders()` validates all `{{x}}` patterns against an allowlist;
  unknown ones are replaced with their literal value + warning.

### Prompt structure (states/regions/suburbs)

Three prompt builders — `buildStatePrompt()`, `buildRegionPrompt()`,
`buildSuburbPrompt()`. Each is structurally distinct:

1. **Role**: "You are writing EEAT content for toiletsnearme.com.au about
   public toilets across [name]."
2. **Audience**: tailored per entity type (state = road-trippers/tourists;
   region = residents/visitors; suburb = local residents/dog walkers).
3. **Location data block**: state, toilet count, accessible, 24h, baby change,
   full feature breakdown — with `→ use {{placeholder}}` annotations.
4. **Placeholder rules**: exact token list, examples of correct vs. incorrect
   usage ("never hardcode numbers").
5. **Content spec** (6 sections):
   - **ABOUT** — geographic scale, travel patterns, why directory matters
   - **LOCAL CONTEXT** — how people move around the area
   - **WHERE TO FIND** — location types (parks, rest stops, shopping strips, etc.)
   - **ACCESSIBILITY AND FACILITIES** — honest assessment with stats
   - **TIPS FOR VISITORS** — practical local-knowledge tips
   - **FAQ** — 2–3 questions a real person would ask, returned as JSON array
6. **Rules**: Australian English, no hardcoded numbers, entity-specific tone,
   no invented addresses/business names.
7. **Output format**: return ONLY a JSON object with keys: `about`,
   `local_context`, `where_to_find`, `accessibility`, `tips`, `faq`.

### Gemini call flow

`callGemini(prompt, entityLabel, placeholderValues)`:
- Up to 3 attempts with exponential backoff.
- Strips markdown code-fence wrapper from response.
- `JSON.parse()` → validate required fields → sanitise placeholders → return.

### Content storage

`buildContentRows()` → 6 rows per entity (one per content_type: about,
local_context, where_to_find, accessibility, tips, faq).
`buildCountsRow()` → 1 row storing all placeholder values as JSON in
content_type='counts' (so Next.js fetches everything in one query).
Batched upsert to `content` table (onConflict: entity_type,entity_id,content_type).

### Entity processing flow

For each type (states/regions/suburbs):
1. Fetch entities from Supabase (with optional state filter, high-value filter).
2. Load "done" set (entity IDs already generated) — skip unless `--force`.
3. Load stats from Supabase `features` and `toilets` tables (2 queries).
4. For each entity:
   - Build placeholder values map (all 18+ stats from the stats lookup).
   - Always push a counts row.
   - If not `--counts-only`: build feature summary, build prompt, call Gemini,
     push 6 content rows.
   - Flush pending rows every N (50 for states, 100 for suburbs).
5. Concurrent execution via `RequestPool` (tracks rate limits).

### CLI flags
`--type`, `--state`, `--limit`, `--concurrency`, `--high-value`, `--counts-only`,
`--force`.

---

## `generate-stats.js` (755 lines) → `enrichment.py` (`compute_quality_score`)

### What it does

Computes composite quality scores for states, regions, and the nation, writes
them to the `stats` table in Supabase. Reads counts from `content` table
(content_type='counts') and hours from the `hours` table.

### Composite score functions (the key logic to port)

```
calcAccessibilityScore:
  = (accessible_pct * 0.50)
  + min(changing_places_count, 5) / 5 * 20
  + (mlak_count > 0 ? 15 : 0)
  + (ambulant_count > 0 ? 15 : 0)
  → capped at 100, rounded

calcFamilyScore:
  = (baby_change_pct * 0.50)
  + (baby_care_room_count > 0 ? 25 : 0)
  + (parking_accessible_count > 0 ? 25 : 0)
  → capped at 100, rounded

calcTravellerScore:
  = min(dump_point_count, 10) / 10 * 40
  + (open_24h_pct * 0.40)
  + (shower_count > 0 ? 20 : 0)
  → capped at 100, rounded

calcProvisionScore:
  = min(toilets_per_10k_equiv, 20) / 20 * 40
  + min(accessible_per_10k_equiv, 10) / 10 * 40
  + (open_24h_pct * 0.20)
  → capped at 100, rounded
```

### Quality score interpretation for directory factory

In the directory factory context, each place needs a single quality/composite
score for ranking and filtering. The four component scores above are computed
at state/region/nation level using aggregate stats. For a **per-place** quality
score, we adapt:

- **Accessibility component**: based on the place's `accessibilityOptions`
  and whether it has MLAK/key access, ambulant features.
- **Family component**: based on baby change facilities, accessible parking.
- **Traveller component**: based on 24-hour operation, dump points (not
  relevant for most business types — adapt to niche).
- **Provision component**: based on rating/userRatingCount, feature richness.

### Per-capita scaling (not needed for per-place)

The original uses `_per_10k` for states, `_per_1000` for regions, `_per_100k`
for changing_places/dump_point. For per-place scoring, these scale to:
**rating** as provision proxy, **feature count** as richness signal.

### Hours stats

`calculateHoursStats()` computes per-state/region: total open hours, weekday/
weekend counts, after-10pm counts, average closing time. This feeds
into the `open_24h_pct` and `avg_closing_time` metrics. For per-place scoring,
the 24h and opening hours flags come directly from the place record.
