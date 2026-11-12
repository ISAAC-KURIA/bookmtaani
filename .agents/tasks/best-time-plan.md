# Implementation Plan — "Best time to book" busy-level suggestion

Feature: on the slot-selection step of the booking flow, label each available
time slot Quiet / Normal / Busy (or "Not enough data"), computed from the
business's past bookings in the database, plus a short verdict message for the
selected slot and quieter nearby-slot suggestions when a slot is Busy.

Scope is strictly the busy-level suggestion. Loyalty discount and helper chat
are NOT built. Payment and double-booking logic are NOT touched.

All commands run from `c:\Users\user\Downloads\bookmtaani\bookmtaani` using the
venv python. Test command: `.venv\Scripts\python.exe manage.py test`.

---

## Key findings from the codebase (grounding for the plan)

- **Booking model** (`core/models.py`): fields `customer` (FK User),
  `service` (FK Service), `date` (DateField), `start_time` (TimeField),
  `end_time` (TimeField), `status` (CharField). Status choices:
  `STATUS_PENDING='pending'`, `STATUS_CONFIRMED='confirmed'`,
  `STATUS_COMPLETED='completed'`, `STATUS_CANCELLED='cancelled'`,
  `STATUS_NO_SHOW='no_show'`. Weekday comes from `booking.date.weekday()`
  (0=Mon…6=Sun); hour from `booking.start_time.hour`.
- **`get_available_slots(service, booking_date)`** (`core/services.py`) returns a
  list of `HH:MM` strings, ordered by time, already excluding booked/blocked/past
  slots. The booking-form view passes this list to the template as `slots`.
- **`booking_form` view** (`core/views.py`): renders `templates/core/booking_form.html`
  with context `service`, `business`, `form`, `selected_date`, `slots` (list of
  strings). `booking_confirm` independently re-checks `get_available_slots` — it is
  unaffected by this change.
- **`booking_form.html`**: renders a `.slot-btn` button per slot; inline
  `selectSlot(btn, time)` JS marks selection and builds the confirm link
  `/book/<id>/confirm/<date>/<time>/`. The confirm URL needs the plain `HH:MM`
  string, which must be preserved.
- **Font Awesome is served locally** (`templates/base.html`):
  `{% static 'fontawesome/css/all.min.css' %}`; webfonts live in
  `static/fontawesome/webfonts/`. No CDN. Use `fas`/`fa-solid` classes.
- **Design tokens** (`static/css/main.css`): `--color-brand:#1D4ED8`,
  `--color-green:#15803D`, plus existing amber (`#FEF3C7`/`#B45309`) and error
  (`#FEE2E2`/`#B91C1C`) tints. No gradients anywhere in the file. Status badge
  classes already exist; reuse this flat-color style.
- **Test style** (`core/tests/test_booking.py`): module-level helpers
  `_make_user`, `_make_business`, `_make_hours`, `_make_service`, `_next_weekday`;
  one `TestCase` class per concern; deterministic future dates via `_next_weekday`.
  It also monkey-patches `RequestContext.__copy__`/`Context.__copy__` for
  Python 3.14 + Django 5.1 — the new test file must include the same patch
  (copy it verbatim) because rendered templates trigger it.
- **Seed data** (`core/management/commands/seed_demo.py`): creates 8–12 past
  bookings per business, weighted ~60% completed / ~15% confirmed / ~10% no_show
  / ~15% cancelled, skewed to evenings and weekends. With
  CONFIRMED+COMPLETED counted, most businesses land above the not-enough-data
  threshold, so the demo shows real levels (a few quiet, a couple busy) — no
  seed change needed.

## Design decisions (recorded)

1. **Which statuses count as historical "real" bookings**: count bookings with
   `status in (STATUS_CONFIRMED, STATUS_COMPLETED)`. Rationale: these are bookings
   that actually occupied the slot (honored demand). PENDING may be cancelled,
   CANCELLED freed the slot, and NO_SHOW means the customer never arrived so the
   business experienced that slot as quiet — counting it as "busy" would mislead.
   Documented in a code comment.
2. **Not-enough-data threshold**: if the business has fewer than
   `BUSY_MIN_HISTORY = 5` total real historical bookings, return level
   `"no_data"` ("Not enough data") for every slot rather than guessing.
   Single documented threshold. (The task also allows "too few for that weekday";
   the global threshold is chosen for simplicity and clear testability.)
3. **Level thresholds**: group real historical bookings by `(weekday, hour)`.
   `mean = total_real_bookings / number_of_distinct_occupied_buckets`
   (buckets with ≥1 booking; guard divide-by-zero). For a slot,
   `count = bookings.get((slot_weekday, slot_hour), 0)`,
   `ratio = count / mean`. `ratio >= 1.3 → Busy`, `ratio <= 0.7 → Quiet`,
   else `Normal`. (A never-booked slot → count 0 → ratio 0 → Quiet, which is
   reasonable once enough history exists.) Documented in comments.
4. **One service function**: `get_slot_busy_levels(business, selected_date, slots)`
   in `core/services.py` holds all busy-level logic and returns a dict
   `{'slots': [info, ...], 'has_data': bool, 'basis': str}`. Small private helpers
   (`_booking_counts`, `_classify_ratio`) live in the same module. The view calls
   it; the template/JS never compute levels.
5. **Selected-slot verdict that updates on click**: all per-slot data (level,
   message, suggestions) is precomputed server-side and emitted as HTML
   `data-*` attributes on each slot button. The existing `selectSlot` JS is
   extended only to read those attributes and show the verdict panel — it does
   no busy-level math. This satisfies "the template must NOT compute busy levels."
6. **Icons + text (accessibility)**: Quiet = `fa-circle-check` + "Quiet",
   Normal = `fa-clock` + "Normal", Busy = `fa-triangle-exclamation` + "Busy",
   Not enough data = `fa-circle-question` + "Not enough data". Color is never the
   only signal.

---

## Implementation steps

- [ ] 1. Add the busy-level service function and helpers to `core/services.py`.
      Add `get_slot_busy_levels(business, selected_date, slots)` plus private
      helpers `_booking_counts(business)` (returns
      `{(weekday,hour): count}` and `total_real`/`num_buckets`) and
      `_classify_ratio(ratio) -> level`. Constants: `BUSY_MIN_HISTORY = 5`,
      `BUSY_BUSY_RATIO = 1.3`, `BUSY_QUIET_RATIO = 0.7`, level constants
      `LEVEL_QUIET='quiet'`, `LEVEL_NORMAL='normal'`, `LEVEL_BUSY='busy'`,
      `LEVEL_NO_DATA='no_data'`. Logic: query
      `Booking.objects.filter(service__business=business, status__in=(CONFIRMED, COMPLETED))`;
      group by `(date__week_day`-independent — use Python `b.date.weekday()` and
      `b.start_time.hour`); compute `mean`; if `total_real < BUSY_MIN_HISTORY`,
      mark all slots `no_data`; else per slot parse `hour = int(slot.split(':')[0])`,
      `count = counts.get((selected_date.weekday(), hour), 0)`, classify by ratio.
      Build per-slot info dicts in the SAME order as the input `slots` list:
      `{'time': 'HH:MM', 'level': ..., 'level_label': 'Quiet'/'Normal'/'Busy'/'Not enough data',
      'icon': 'fa-circle-check'|'fa-clock'|'fa-triangle-exclamation'|'fa-circle-question',
      'message': str, 'suggestions': [str, ...]}`. Messages: quiet →
      "Usually quiet at this time, good choice"; normal →
      "A usual number of bookings at this time"; busy →
      "Usually busy at this time, you may wait"; no_data →
      "Not enough booking history to estimate this slot yet". For Busy slots,
      `suggestions` = up to 2 nearest (by list index) available slots whose level
      is Quiet or Normal; empty list otherwise. Return
      `{'slots': infos, 'has_data': total_real >= BUSY_MIN_HISTORY,
      'basis': 'Simulated insight (rule-based, from booking history)'}`. Add a
      module docstring comment documenting the 5-booking threshold and the
      CONFIRMED+COMPLETED status choice. Do NOT touch `get_available_slots`,
      `create_booking`, or any payment code.
      Files: `core/services.py`
      Verify: `cd c:\Users\user\Downloads\bookmtaani\bookmtaani ; .venv\Scripts\python.exe -c "import django,os;os.environ.setdefault('DJANGO_SETTINGS_MODULE','bookmtaani.settings');django.setup();from core.services import get_slot_busy_levels;print(get_slot_busy_levels.__name__)"` — imports cleanly with no error.

- [ ] 2. Wire the service into `booking_form` view and pass data to the template.
      In `core/views.py` `booking_form`: after `slots = get_available_slots(service, selected_date)`,
      call `busy = get_slot_busy_levels(service.business, selected_date, slots)`
      and add `'slot_infos': busy['slots']`, `'busy_basis': busy['basis']`,
      `'busy_has_data': busy['has_data']` to the context (keep the existing
      `'slots'` list so nothing else breaks). Import `get_slot_busy_levels` from
      `.services` alongside the existing imports. No change to `booking_confirm`,
      `available_slots_json`, payment, or double-booking views.
      Files: `core/views.py`
      Verify: `cd c:\Users\user\Downloads\bookmtaani\bookmtaani ; .venv\Scripts\python.exe manage.py test core.tests.test_booking` — existing booking tests still pass (view change is additive).

- [ ] 3. Add flat-color CSS for slot levels, legend, and the verdict panel.
      Append a "Best time to book" section to `static/css/main.css` using only
      flat solid colors and existing tokens — no gradients. Rules: slot button
      level tints (`.slot-btn.level-quiet` green tint `#DCFCE7`/border `#86EFAC`
      /text `var(--color-green)`; `.slot-btn.level-normal` amber tint
      `#FEF3C7`/border `#FCD34D`/text `#B45309`; `.slot-btn.level-busy` red tint
      `#FEE2E2`/border `#FCA5A5`/text `var(--color-error)`; `.slot-btn.level-no_data`
      neutral `#F3F4F6`/border `var(--color-border)`/text `var(--color-secondary)`).
      Keep the existing green `.slot-btn.selected` outline working on top of the
      level tint (selected wins for text/border but level color stays as a left
      accent or keep both). A `.slot-level-label` style for the small icon+text
      line under the time. A `.busy-legend` flex row and a `.busy-verdict` panel
      styled per level (`v-quiet` green / `v-normal` amber / `v-busy` red /
      `v-no_data` neutral), plus a `.busy-suggestion` chip style (green-tinted).
      Reuse the existing `.insight-box`/`.insight-label` look for the
      "Simulated insight…" label so it matches the analytics page.
      Files: `static/css/main.css`
      Verify: load `http://localhost:8000/book/<service_id>/?date=<future-date>` after step 5 and confirm labels are flat (no gradient) and colors match `#1D4ED8` / `#15803D` / amber / red.

- [ ] 4. Update `templates/core/booking_form.html` to render levels, legend, verdict, suggestions, and the heuristic label.
      Replace the bare slot-button loop with one over `slot_infos` (each item has
      `time`, `level`, `level_label`, `icon`, `message`, `suggestions`). Each
      `.slot-btn` keeps `data-time="{{ info.time }}"`, the existing `onclick`, and
      gains class `level-{{ info.level }}` plus `data-level`, `data-message`,
      and `data-suggestions` (join suggestions with `, `; HTML-escape via Django
      auto-escaping). The button shows the time on the first line and a small
      `<span class="slot-level-label"><i class="fas {{ info.icon }}"></i>
      {{ info.level_label }}</span>` below it (icon + text, not color alone).
      Above the grid add a `.busy-legend` with three entries (Quiet/Normal/Busy,
      each icon + text) and the `.insight-label` text
      "Simulated insight (rule-based, from booking history)" near the slots card
      title. Add a `.busy-verdict` panel (initially hidden, `aria-live="polite"`)
      that `selectSlot` populates from the clicked button's `data-*` attributes:
      the level icon + message, and — when `data-level === 'busy'` and
      `data-suggestions` is non-empty — a "Quieter nearby slots: …" line listing
      them as clickable chips that call `selectSlot` for that time. Keep the
      existing confirm-link logic intact (it still uses `time`). Extend
      `selectSlot` to: (a) do the existing selection/confirm-link work, (b) read
      the clicked button's `data-level`/`data-message`/`data-suggestions`, (c)
      show the verdict panel with the matching `v-<level>` class and content, and
      (d) hide it when no slot selected. No busy-level computation in JS — only
      display of precomputed strings. No emojis. Use `fas` Font Awesome classes.
      Files: `templates/core/booking_form.html`
      Verify: run the server, open the booking form for a future date, click slots, and confirm the verdict panel updates with icon + message and (for a Busy slot) quieter nearby suggestions; confirm the "Simulated insight (rule-based, from booking history)" label is visible.

- [ ] 5. Write Django tests for the service function covering all four cases.
      Create `core/tests/test_busy_level.py` matching the style of
      `core/tests/test_booking.py`: copy the `RequestContext.__copy__`/`Context.__copy__`
      patch block verbatim, reuse the same helper pattern (`_make_user`,
      `_make_business`, `_make_hours`, `_make_service`, and a local
      `_past_date_for_weekday(weekday)` returning a past date on that weekday).
      Build realistic booking fixtures (real past dates, correct weekday +
      `start_time` hour) with status CONFIRMED/COMPLETED so the service counts
      them. One `TestCase` class `BusyLevelTest` with cases:
      (a) `test_quiet_slot` — a slot whose (weekday,hour) count is well below the
      mean asserts `level == 'quiet'` and message contains "quiet";
      (b) `test_normal_slot` — count near the mean asserts `level == 'normal'`;
      (c) `test_busy_slot` — count well above the mean asserts `level == 'busy'`,
      message contains "busy", and `suggestions` lists 1–2 nearby Quiet/Normal
      slot times;
      (d) `test_not_enough_data` — fewer than 5 total real bookings asserts every
      slot's `level == 'no_data'` and message mentions not enough history.
      Design a deterministic fixture (e.g., Monday 09:00 = 6 bookings,
      Monday 10:00 = 3, Monday 11:00 = 1, plus Tuesday 09:00 = 3 and 10:00 = 3,
      so mean ≈ 3.2; Monday 09:00 → busy, 10:00 → normal, 11:00 → quiet) and verify
      the ratio math by hand in a comment. Call
      `get_slot_busy_levels(business, monday, ['09:00','10:00','11:00'])` and
      assert per-slot levels. Keep total ≥ 5 for the three level cases and < 5
      for the no-data case. Do not use the seed command.
      Files: `core/tests/test_busy_level.py`
      Verify: `cd c:\Users\user\Downloads\bookmtaani\bookmtaani ; .venv\Scripts\python.exe manage.py test core.tests.test_busy_level` — all four cases pass.

- [ ] 6. Append one short demo step to `DEMO_SCRIPT.md`.
      Append a concise step (a few lines) at the end of the file describing how to
      demo the feature: on the slot-selection page, point out each slot is labeled
      Quiet/Normal/Busy with an icon (or "Not enough data" when history is thin),
      the "Simulated insight (rule-based, from booking history)" label, clicking a
      Busy slot shows a "you may wait" message plus quieter nearby slots, and
      clicking a Quiet slot shows a "good choice" message. No emojis.
      Files: `DEMO_SCRIPT.md`
      Verify: read back `DEMO_SCRIPT.md` and confirm one new short step is present at the end.

- [ ] 7. Full verification pass.
      Run the entire suite and confirm both new and existing tests pass, then
      inspect the rendered template for the design rules.
      Files: (none — verification only)
      Verify: `cd c:\Users\user\Downloads\bookmtaani\bookmtaani ; .venv\Scripts\python.exe manage.py test` — record the summary (e.g., "Ran N tests… OK"). Then open the booking form for a future date and confirm: slots show icon + text labels for Quiet/Normal/Busy/"Not enough data"; the "Simulated insight (rule-based, from booking history)" label is present; no emojis and no gradients anywhere in the slot/verdict area; brand blue `#1D4ED8` and green `#15803D` are the only primary colors; Font Awesome loads locally (no CDN `<link>`); selecting a Busy slot shows the "you may wait" verdict plus quieter nearby suggestions; selecting a Quiet slot shows "good choice". Confirm payment and double-booking flows are untouched (existing `test_booking` and `test_paystack` pass).

---

## Deliverables checklist (for the implementer to produce at the end)

List every file changed with a one-line summary:
- `core/services.py` — added `get_slot_busy_levels` + helpers (busy-level logic, 5-booking threshold, Quiet/Normal/Busy ratios).
- `core/views.py` — `booking_form` calls the service and passes `slot_infos`/`busy_basis`/`busy_has_data` to the template.
- `static/css/main.css` — flat-color rules for slot levels, legend, verdict panel, suggestions (no gradients).
- `templates/core/booking_form.html` — slot labels (icon + text), legend, verdict panel that updates on selection, quieter nearby suggestions, "Simulated insight…" label.
- `core/tests/test_busy_level.py` — service tests for quiet/normal/busy/not-enough-data.
- `DEMO_SCRIPT.md` — one appended short step.

## Notes / assumptions (gaps filled)

- The task left the not-enough-data threshold open ("fewer than N total" OR "too
  few for that weekday"). Chosen: a single global threshold of 5 total real
  historical bookings (CONFIRMED+COMPLETED) for the business, documented in code.
- The task left "which statuses count" open. Chosen: CONFIRMED + COMPLETED
  (honored demand), excluding PENDING/CANCELLED/NO_SHOW, with rationale in a
  comment.
- The task left thresholds open. Chosen: ratio ≥ 1.3 Busy, ≤ 0.7 Quiet, else
  Normal, where ratio = count(weekday,hour) / mean per occupied bucket.
- No worktree/branch changes are required by this plan; the implementer commits
  locally per the workflow's standard loop.
