# User interface — wireframes and dashboard specifications

Six command centres, one import console and one forecast view. Each
command centre is a projection over a single computation, so no two roles
can ever see different values for the same indicator.

## Layout grammar

Every command centre uses the same vertical rhythm. A director who learns
one learns all six.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Role title                      [7d][30d][90d][MTD][QTD][YTD] [CSV] [ع] │
│ Period: 08 Jul 2026 – 06 Aug 2026 · Generated 14:22                      │
├──────────────────────────────────────────────────────────────────────────┤
│ [Executive][Operations][Emergency][Beds][Nursing][Quality] │ Forecast Import│
├──────────────────────────────────────────────────────────────────────────┤
│ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐              │
│ │ Occupancy ●│ │ ALOS      ●│ │ Mortality ●│ │ Readmit   ●│  ← 8 KPI     │
│ │  84.9 %    │ │  5.43 days │ │  2.7 %     │ │  1.6 %     │    tiles     │
│ │ Target 85  │ │ Target 4.0 │ │ Target 2.0 │ │ Target 8.0 │              │
│ │ ▼ 1.2% prev│ │ ▲ 3.1% prev│ │ ▲ 0.4% prev│ │ ▼ 0.2% prev│              │
│ └────────────┘ └────────────┘ └────────────┘ └────────────┘              │
│ (four more)                                                              │
├──────────────────────────────────────────────────────────────────────────┤
│ Records in period: encounters 1,836 · ed visits 6,834 · movements 2,084   │
├──────────────────────────────────────────────────────────────────────────┤
│ ▍Indicators outside target                                               │
│ ▍ NEDOCS crowding score is 157.5, above the target of 60.0.       157.5  │
│ ▍ Theatre turnover is 75.1 min, above the target of 30 min.        75.1  │
├──────────────────────────────────────────────────────────────────────────┤
│ Occupancy by unit and day  (heat map, unit × day, 40–105 % scale)        │
├──────────────────────────────────────────────────────────────────────────┤
│ Role-specific panels (see below)                                         │
└──────────────────────────────────────────────────────────────────────────┘
```

**Every tile carries four things**: the value, its target, its RAG status
and its movement against the previous period. A number without its
benchmark invites the reader to invent one, and the invented benchmark is
usually wrong.

**Status is never colour alone.** The dot is reinforced by the printed
target and the signed delta, so the dashboard survives a colour-blind
reader and a monochrome printout.

## Per-role composition

| Command centre | Leading tiles | Panels below |
|---|---|---|
| **Executive (CEO)** | Occupancy · ALOS · Mortality · 30-day readmission · Satisfaction · ED boarding · ADC · NPS | Occupancy heat map, unit table, quality summary |
| **Operations (COO)** | Occupancy · ED boarding · Discharge delay · Turnover interval · ALOS · Bed allocation · First-case delay · Discharges/day | Bottleneck ranking, journey segments, unit table |
| **Emergency (ED Director)** | NEDOCS · Door-to-physician · ED LOS · Boarding · LWBS · Visits · Admission rate · 72h revisits | Hourly census/boarders/NEDOCS chart, CTAS mix, arrival heat map by hour × weekday |
| **Bed Management** | Occupancy · ICU utilisation · Bed allocation · Assignment-to-arrival · Discharge delay · Turnover interval · ADC · Transfer rate | Unit table sorted by occupancy, heat map, journey placement segments |
| **Nursing (CNO)** | NCHPD · RN skill mix · Overtime · Vacancy · Falls · Pressure injuries · Turnover · Sick leave | Per-unit nursing table, census reconciliation warnings, safety-by-unit |
| **Quality** | Mortality · Readmission · HAI · Falls with injury · Medication errors · Pressure injuries · Code blue · NEWS2 high | Event breakdown by type and harm, unit safety table, sepsis bundle compliance |

## Emergency department command centre

The ED view is the one that differs structurally, because ED management
is an hourly job rather than a daily one.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Emergency department load                                                │
│ Hourly census, admitted patients still waiting for a bed, NEDOCS         │
│                                                                          │
│  60 ┤                          ╭─╮          Census ───                   │
│     │                     ╭────╯ ╰─╮        Boarders ───                 │
│  40 ┤          ╭──────────╯        ╰──╮     NEDOCS ⋯⋯                    │
│     │     ╭────╯                      ╰───╮                              │
│  20 ┤ ╭───╯  ⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯ Overcrowded (100)         │
│   0 ┴─┴────┴────┴────┴────┴────┴────┴────┴────┴────                      │
│      00   03   06   09   12   15   18   21   00                          │
└──────────────────────────────────────────────────────────────────────────┘
```

The NEDOCS series carries a dotted line at 100 — the published threshold
where a department stops being merely busy and becomes formally
overcrowded. Without the reference line the score is an uninterpretable
number.

**Arrival profile heat map** (hour of day × day of week, mean arrivals)
sits beside it. This is the panel that changes rosters: it shows that the
19:00 Sunday peak is 2.4× the 04:00 Friday trough, which is an argument
about staffing rather than about effort.

## Bottleneck panel

Ranked by *avoidable patient-hours*: median delay above target multiplied
by the number of patients who hit it.

```
Where patient time is lost
  Medically ready → departure    ████████████████████  549 h   (78 min median, target 60)
  Triage → physician             ████████████          318 h   (43 min median, target 30)
  Bed request → assignment       █████████             247 h   (68 min median, target 60)
  Assignment → ward arrival      ██                     44 h   (37 min median, target 45)
```

Ranking by median duration alone points leadership at rare, slow steps.
Weighting by volume points them at where the hospital as a whole loses the
most time — which is where an intervention actually pays back.

## Forecast view

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Forecast — Occupancy      Shaded band is the 95% interval                 │
│                                                                          │
│ 100 ┤                              ░░░░░░░░░░░░░░                        │
│     │                        ░░░░░░░░░░░░░░░░░░░░░░                      │
│  80 ┤━━━━━━━━━━━━━━━━━━━━━━━━╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌                      │
│     │                        ░░░░░░░░░░░░░░░░░░░░░░                      │
│  60 ┤          actual  │  forecast    ░░░░░░░░░░░░                       │
│     └──────────────────┴──────────────────────────                       │
│ Model: GradientBoostingRegressor · Trained on 120 days ·                  │
│ Backtest accuracy: ±6.1 MAE · Improvement over carry-forward: −4.8%       │
└──────────────────────────────────────────────────────────────────────────┘
```

The model badge is not decoration. **Improvement over carry-forward** is
shown even when negative, because a bed plan should not rest on a model
that has not beaten "assume tomorrow looks like today". A platform that
hides that number is asking to be trusted rather than earning it.

## Import console

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Data import                                                              │
│ [encounters ▾]  [Choose file]  ☑ Validate only (do not load)  [Validate] │
├──────────────────────────────────────────────────────────────────────────┤
│ Batch 47 · State VALIDATED · 28,138 rows · 0 loaded · 370 quarantined     │
│ Quality 69.5   completeness 61.2 · validity 88.0 · uniqueness 98.7 ·      │
│                consistency 92.1 · timeliness 100.0                       │
│ ▸ Column mapping (18 matched, 2 unmapped)                                │
│                                                                          │
│ Data quality findings                                                    │
│ ERROR    370 row(s) have 'discharge_at' before 'admission_at'. Rows were  │
│          quarantined. Check the source system's date format.             │
│ WARNING  'discharge_ready_at' is 62% empty. Metrics that depend on it     │
│          will be computed on a reduced denominator.                      │
└──────────────────────────────────────────────────────────────────────────┘
```

**Validate-only is the default.** A hospital's first upload is a probe —
"will this file even work?" — and letting them see the mapping and the
quality report before anything is written removes the fear of corrupting
the warehouse on the first attempt.

## Bilingual and responsive behaviour

* `lang` and `dir` are set on `<html>` from the locale segment, so
  Tailwind's logical properties (`ms-`, `ps-`, `text-start`) mirror the
  entire interface for Arabic with no second stylesheet.
* Charts read `document.documentElement.dir` and invert their category
  axes, so an Arabic time series runs right to left.
* Indicator names come from the API in both languages. Translating the
  chrome while leaving metric names in English is the standard failure of
  "bilingual" hospital dashboards and makes them unusable for the
  Arabic-first half of the audience.
* Numerals are forced to Western digits in both locales — Gulf hospital
  reporting uses them almost universally, and mixed numeral systems across
  one screen are genuinely hard to scan.
* Tiles reflow 4 → 2 → 1 across `lg` / `sm` / mobile. Wide tables and
  charts scroll inside their own container; the page body never scrolls
  horizontally.

## Accessibility

* Every tile is an `<article>` with an `aria-label` carrying the localised
  indicator name.
* Navigation marks the current view with `aria-current="page"`.
* Status colours meet WCAG AA against the dark canvas, and are always
  paired with text.
* Tables use real `<th>` scope headers so a screen reader announces the
  unit name with each cell.
