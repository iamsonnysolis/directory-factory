# Phase 2.3 — Per-Niche Feature Taxonomy Draft (Mobile Dog Groomers)

> **OPEN DESIGN TASK — review with Shanon before building extraction logic.**

## Background

The original `enrich.js` used a **fixed 21-key toilet taxonomy** (`CSV_TO_FEATURE`):
`male`, `female`, `unisex`, `all_gender`, `accessible`, `ambulant`, `lh_transfer`,
`rh_transfer`, `baby_change`, `baby_care_room`, `adult_change`, `changing_places`,
`key_required`, `mlak`, `payment_required`, `parking`, `parking_accessible`,
`shower`, `drinking_water`, `dump_point`, `sharps_disposal`, `sanitary_disposal`,
`mens_pad_disposal`.

These came from **boolean CSV columns** in the ABS dataset. In the directory
factory, Google Places API responses don't have these columns — features are
derived from `types`, `accessibilityOptions`, `priceLevel`, and
`regularOpeningHours`.

The per-niche taxonomy replaces this fixed set with **niche-specific feature
keys** that make sense for each business type.

## Sample dataset: Mobile Dog Groomers (project_id=42)

Search term: `"mobile dog groomer"`. Sample places from `dataset-collector`:

| Place | Types | primaryType | Rating | Accessibility | Has Hours |
|---|---|---|---|---|---|
| LUSCIOUS PAWS Dog Grooming | pet_care, point_of_interest, service, establishment | pet_care | 4.9 (44) | none | yes |
| Nose 2 Tail | pet_care, point_of_interest, service, establishment | pet_care | 5.0 (10) | wheelchairAccessibleParking | yes |
| Groomed by Karyn | pet_care, point_of_interest, service, establishment | pet_care | 5.0 (17) | N/A | yes |
| Wagglebumz Pet Grooming | pet_care, service, point_of_interest, establishment | pet_care | 5.0 (15) | wheelchairAccessibleParking | yes |
| Jim's dog wash and grooming | pet_care, service, point_of_interest, establishment | pet_care | 4.9 (111) | wheelchairAccessibleParking | no |

Common features observed:
- All are `pet_care` → grooming
- Some describe themselves as "mobile" in the name, but Google doesn't expose a `mobile` type
- Some have wheelchair-accessible parking
- Some have opening hours, some don't
- All accept dogs (implied by search term)

## Draft taxonomy: Mobile Dog Groomers

```yaml
taxonomy:
  name: "Mobile Dog Groomers"
  primary_type: "pet_care"
  feature_keys:
    # Service delivery model
    - mobile_service          # explicitly mobile (from name/description or search term context)
    - walk_in_accepted        # accepts walk-in customers without appointment
    - appointment_only        # appointment-only (from Google's appointmentRequired if available)

    # Grooming services
    - full_groom              # full grooming package
    - bath_only               # bath/wash-only service
    - nail_trimming           # nail clipping/trimming
    - hair_coloring           # dye/colouring services
    - deshedding              # deshedding/de-shedding service
    - breed_specific_cut      # breed-specific styling

    # Amenities
    - pet_wash                # self-service or supervised pet washing
    - flea_treatment          # flea/tic treatment offered
    - nail_grinding            # alternative to nail clipping

    # Accessibility (from accessibilityOptions)
    - accessible              # wheelchairAccessibleEntrance
    - accessible_parking      # wheelchairAccessibleParking

    # Operational flags
    - open_24_hours          # 24/7 operation (rare for groomers)
    - weekend_available      # open weekends
    - emergency_service      # emergency grooming availability

    # Quality signals (not features per se, but inform quality score)
    - high_rating             # rating >= 4.5
    - many_reviews            # userRatingCount >= 50
    - google_verified         # business_status === OPERATIONAL (always true for results)
```

## Extraction logic (draft — to be implemented in `derive_features`)

| Feature key | Source in Google Places response |
|---|---|
| `mobile_service` | Search term contains "mobile" → set for all places in a mobile project; OR check if `name`/`description` contains "mobile" |
| `walk_in_accepted` | Absence of appointment-only indicator (Google may expose `appointmentRequired` in some fields) |
| `full_groom` | `primaryType === "pet_care"` (inferred — pet grooming is the main service) |
| `accessible` | `accessibilityOptions.wheelchairAccessibleEntrance === true` |
| `accessible_parking` | `accessibilityOptions.wheelchairAccessibleParking === true` |
| `open_24_hours` | `regularOpeningHours` contains 24h periods or `is_24_hours` flag |
| `high_rating` | `rating >= 4.5` |
| `many_reviews` | `userRatingCount >= 50` |

## Notes for Shanon

1. **Mobile vs. fixed**: Google Places `types` for mobile dog groomers are
   identical to fixed-location pet care (`pet_care`). The "mobile" aspect
   comes from the **search term context** (`"mobile dog groomer"`), not from
   the place data itself. The taxonomy system needs to support
   **project-level default features** (e.g., all places in a "Mobile Dog
   Groomers" project get `mobile_service` by default).

2. **Missing signals**: Google Places (New) limited field tier may not return
   `appointmentRequired`, `opening_hours` in all cases (e.g., Jim's dog wash
   had `has regularOpeningHours: no`). Features that can't be derived from
   available data should be omitted, not set to `false`.

3. **Generic features**: The `GOOGLE_TYPE_MAP` in `cleaning.py` already maps
   some types generically (`pet_care` → no direct mapping, `credit_card_accepted`
   → `credit_card`). The per-niche taxonomy should **override/refine** this
   with niche-specific keys.

4. **Feature storage**: The original stored features as `(facility_id, feature_key)`
   rows. In the directory factory, features are stored as a JSON list in the
   `cleaned_json` column of `places`, with `feature_key` strings.
