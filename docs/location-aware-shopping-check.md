# Location-aware Shopping Check

Shopping Check tells a user, on arrival, what they can safely spend at *this* store right
now. This document covers the location side: what is monitored, how new places are
discovered, what leaves the phone, and what Android can and cannot guarantee.

The feature is an extension of the existing Shopping Check page, not a second location
system: tracked places, visit history and the guidance text all live in the same tables and
screens that the manual Shopping Check already used.

- Backend: `app/services/visits.py`, `app/services/places.py`, `app/api/shopping.py`
- Android: `com.pfc.companion.location` and `ui/screens/ShoppingIntelligenceScreen.kt`

## Consent and controls

`NotificationPreference` holds the consent, and every entry point checks it before doing any
work (`record_arrival()` and `detect_visit()` both return
`"Location features have not been enabled on this account."` when it is off).

| Control | Field |
| --- | --- |
| Master consent | `location_features_opted_in` |
| Shopping Intelligence on/off | `shopping_intelligence_enabled` |
| New-place discovery on/off | `discovery_enabled` |
| Temporary pause | `location_paused_until` (+ `pause_minutes` in the patch) |
| Quiet hours | `quiet_hours_start`, `quiet_hours_end`, `quiet_hours_timezone` |
| Notification cooldown | `notification_cooldown_minutes` (15–1440) |
| History retention | `visit_history_retention_days` (1–365) |

Read them with `GET /api/v1/shopping/location-settings`, change them with
`PATCH`. The response also reports `tracked_location_count` and a `supported` map so the UI
can explain what is available rather than failing silently.

Denying location permission never blocks the rest of the app: the financial screens work
without it, and the Shopping Intelligence screen shows which capabilities are unavailable
and why.

## Two complementary systems

### A. Known place monitoring (geofences)

Saved places live in `tracked_locations`: name, merchant, address, optional coordinates
(normalised as decimal degrees), `radius_m` (50–2000, clamped on device too), optional
`category_id`, optional `monthly_budget`, `notify_enabled`, `is_active`, `source`.

`ShoppingMonitoring.registerGeofences()` registers each active place that has coordinates:

- `Geofence.GEOFENCE_TRANSITION_ENTER | DWELL`
- `setLoiteringDelay(5 * 60 * 1000)` — dwell is what separates a visit from driving past
- `NEVER_EXPIRE`, with `INITIAL_TRIGGER_ENTER`

Nothing is registered without foreground **and** background location permission. Removing a
place, disabling the feature or revoking consent calls `stop()`, which removes geofences and
activity transitions.

`GeofenceReceiver` sends **only the tracked location's id** to the server
(`POST /api/v1/shopping/locations/{id}/arrive`). The coordinate never leaves the phone on an
arrival, because the server already knows where the place is.

### B. New-place discovery (low power)

There is no continuous GPS polling. Discovery is triggered by **Activity Recognition**
transitions — `STILL` and `WALKING` enter — registered through
`ActivityRecognition.requestActivityTransitionUpdates()`. When the phone reports a stop,
`ActivityTransitionReceiver` takes **one** fix with
`PRIORITY_BALANCED_POWER_ACCURACY` (`getCurrentLocation`, not a request stream) and posts it
once to `POST /api/v1/shopping/visits/detect`.

The server then names the place:

- a saved place nearby wins outright (`source: geofence`, confidence ≥ 0.9);
- otherwise the configured `PlacesProvider` is asked for nearby businesses;
- an unrecognised or too-vague fix is stored as `Unrecognised location` with confidence 0.2
  and produces no notification.

Address-only lookups (Android's `Geocoder`) are deliberately not used to identify a business:
it returns street addresses, not shops. `OsmPlacesProvider` queries Overpass for
`shop=*` and a small set of retail-relevant `amenity` values (`restaurant`, `cafe`,
`fast_food`, `bar`, `pub`, `fuel`, `pharmacy`, `bank`), returning up to six candidates with a
distance-derived confidence capped at 0.95. The provider is swappable via
`places_provider` (`osm`/`none`), `places_endpoint`, `places_timeout_seconds`.

## Confidence, ambiguity and false positives

On the device, `ShoppingRules.confidenceFor(accuracyM, dwellMinutes)` combines accuracy
(60%) and dwell (40%) and returns 0 for any fix worse than 250 m:

| Accuracy | Score | Dwell | Score |
| --- | --- | --- | --- |
| ≤ 35 m | 1.0 | ≥ 10 min | 1.0 |
| ≤ 75 m | 0.85 | ≥ 5 min | 0.8 |
| ≤ 150 m | 0.6 | ≥ 3 min | 0.55 |
| > 150 m | 0.35 | < 3 min | 0.25 |

A driving pass fails on both inputs, so it does not become a visit. On the server a place is
only **suggested** when all of these hold:

1. discovery is enabled for the account;
2. confidence ≥ `visit_notification_min_confidence` (default 0.55);
3. `resolve_place()` did not flag the fix as ambiguous;
4. the place actually has a name.

**Ambiguity** is the shopping-centre case: two different businesses within 15 m of each
other on distance. The visit is still recorded (as `detected`, with the note "Several
businesses are within a few metres of this point") but nothing is announced and no place is
created.

## Notification rules

`ShoppingRules.shouldNotify()` is the single gate: feature on, not paused, not in quiet
hours, cooldown elapsed, a prompt exists, and the server did not suppress it.

The server suppresses and says why in `prompt.suppress_reason`:

- "Shopping Intelligence is paused."
- "Shopping Intelligence is turned off."
- "Quiet hours are active."
- "You were notified about another place recently." (another visit inside the cooldown)
- "Notifications are off for this location." (per-place `notify_enabled`)

Spam prevention is structural, not just timed:

- a **unique (user, merchant_key, visit_day)** row means one visit per place per day, even
  after a reboot or a second device (the race is caught by the unique index);
- ignored places are never suggested again;
- a plate the user dismissed ("Don't suggest") keeps that state permanently;
- quiet hours can wrap midnight, and a zero-length window means "off", not "always quiet".

## Notifications

One channel (`shopping_intelligence`), at most two actions, cancelled as soon as the visit is
handled (`ShoppingNotifications`):

- **Arrival** at a tracked place: "You're at {store}" plus the server's guidance message and,
  when present, a suggested spend limit. Action: *Not now*.
- **New place**: "New place: {business}" with *Not now* and *Don't suggest*. A place is never
  added silently — adding requires an explicit tap that calls
  `POST /api/v1/shopping/locations/from-visit/{visit_id}`.

`BootReceiver` re-registers geofences and transitions after `BOOT_COMPLETED` and
`MY_PACKAGE_REPLACED`, so monitoring survives a reboot without the app being opened.

## Visit history and spending

`GET /api/v1/shopping/visits` returns the history with `status`
(`detected` / `suggested` / `confirmed` / `ignored`), visit time, visit count per place, and
any reliably matched merchant transactions. `PATCH /visits/{id}` corrects a business name or
merges it into a tracked place, `POST /visits/{id}/ignore` dismisses it permanently,
`DELETE /visits/{id}` deletes one record and `DELETE /visits` clears the whole history
(server-side included, not just a local cache).

Retention is enforced on every visit write: rows older than
`visit_history_retention_days` are deleted.

**A visit is not a purchase.** No location detection creates, edits or categorises a
transaction. The only financial link is a read-only lookup of purchases the user already has
at that merchant, and the API says so in its `note`.

## Guidance shown on arrival

`store_guidance()` (deterministic, from `app/services/recommendations.py`) returns
Safe-to-Spend, the category remainder, the store's own remaining monthly budget (matched on
the normalised merchant key, so another shop in the same category cannot consume it), the
typical visit size, what is due within seven days, and
`suggested_limit` = the smallest of those figures. `facts` reports `"unknown"` and
`"not enough history"` rather than filling gaps, and `data_is_stale` is passed through from
Safe-to-Spend. The AI may explain these numbers; it never computes or replaces them.

## Privacy

- Opt-in, with an immediate pause and a one-tap disable.
- Only saved places hold coordinates, because the phone needs them for geofences.
- A discovery coordinate is used once to name a place and is not stored; only the derived
  merchant key, distance and confidence are kept.
- The arrival path sends an identifier, not a position.
- Visit records are private to the account: every query is scoped by `user_id`, and there is
  no household or sharing path to them.
- No location history is sent to any AI model.
- Third-party lookup is limited to a coordinate → nearby business names call to Overpass
  (`places_provider`), which can be switched off entirely with `places_provider=none`.

## What Android cannot promise

- Doze, manufacturer battery managers and revoked permissions can delay or drop geofence and
  activity events. Monitoring is best-effort, never guaranteed.
- Background location on Android 11+ needs a separate grant; without it only foreground
  arrivals are detected.
- Geofence radius is a hint. GPS error in dense areas is larger than the radius, which is why
  dwell time and the ambiguity check exist.

## Testing and device status

- `backend/tests/test_shopping_intelligence.py` covers detection, duplicate suppression,
  quiet hours, cooldown, ambiguity, ignored places, retention, user isolation and the
  double-deduction rules for guidance.
- `android/app/src/test/java/com/pfc/companion/location/ShoppingRulesTest.kt` covers radius
  clamping, quiet-hours wrapping, cooldown, the notification gate and confidence scoring on
  the JVM.
- **Not verified on a physical device.** No Android device or emulator session was available
  in this environment, so battery use and real-world detection reliability are **unmeasured**.
  The acceptance report records this as a limitation; do not read the unit tests as a battery
  measurement.

## Related

- [Merchant spending intelligence](merchant-spending-intelligence.md)
- [Safe-to-Spend calculation](safe-to-spend-calculation.md)
- [Android client](android.md)
