# Standards and accreditation mapping

How the platform's indicators and controls line up with CBAHI, JCI,
Magnet and the Saudi Health Sector Transformation Programme.

> **Scope of this claim.** The platform *measures and evidences* these
> requirements. It does not make a hospital compliant, and no software
> can. Accreditation depends on the underlying clinical practice; what
> this platform removes is the manual data assembly that usually consumes
> the months before a survey.

## CBAHI — Saudi Central Board for Accreditation of Healthcare Institutions

CBAHI's national hospital standards require measurement of specified
indicators with defined numerators and denominators. Definitions matter
as much as values: a surveyor asks how a rate was calculated.

| CBAHI area | Platform indicator | Where |
|---|---|---|
| Emergency triage timeliness | `door_to_triage_min` (median) | Emergency command centre |
| Emergency physician assessment | `door_to_physician_min`, plus per-CTAS breakdown | Emergency |
| ED length of stay | `ed_los_min`, split admitted vs discharged | Emergency |
| Left without being seen | `lwbs_rate` with numerator and denominator | Emergency |
| Left against medical advice | `lama_rate` | Emergency |
| Unplanned ED return within 72 h | `ed_revisit_72h_rate` | Emergency |
| Bed occupancy | `occupancy_rate` against staffed beds | Executive, Bed management |
| Average length of stay | `alos_days` | Executive, Operations |
| Hospital mortality | `mortality_rate` | Executive, Quality |
| Unplanned readmission within 30 days | `readmission_30d_rate` | Quality |
| Laboratory turnaround | `lab_tat_min`, `lab_stat_tat_min` (collection → verified result) | Operations |
| Radiology turnaround | `radiology_tat_min`, by modality | Operations |
| Hospital-acquired infection rates | `hai_rate` per 1,000 patient days, CLABSI / CAUTI / VAP / SSI | Quality |
| Patient falls | `fall_rate`, `fall_with_injury_rate` | Quality, Nursing |
| Medication errors | `medication_error_rate`, by process stage | Quality |
| Pressure injuries | `pressure_injury_rate`, stage II+ | Quality, Nursing |

**Definitional points a surveyor will probe, and how the platform answers:**

* *Lab turnaround measured from when?* From specimen collection, not from
  order. The pre-analytic wait belongs to nursing, and CBAHI audits the
  laboratory's segment.
* *Are infections hospital-acquired?* Only events with
  `present_on_admission = false` enter the numerator. The flag is part of
  the dataset contract.
* *What is the occupancy denominator?* Staffed beds, recorded per unit in
  `ref_unit.staffed_beds`, distinct from `physical_beds`.

## JCI — Joint Commission International

| JCI chapter | Requirement | Platform support |
|---|---|---|
| **ACC** Access to Care and Continuity | Manage patient flow through the facility; monitor ED boarding | `ed_boarding_min`, hourly boarder counts, NEDOCS, bed allocation and placement intervals |
| **ACC.2.2** | Monitor and reduce delays for admitted patients held in the ED | Boarding median and p90, count boarded over 4 hours, hourly reconstruction |
| **QPS** Quality Improvement and Patient Safety | Select, collect and analyse indicator data; validate it | Metric catalogue with explicit numerators and denominators; per-batch data quality scoring across five DAMA dimensions |
| **QPS.7 / QPS.8** | Sentinel events and near-miss analysis | `qly_safety_event.is_sentinel`, harm grading, event drill-down by unit |
| **IPSG.1** Patient identification | — | Not applicable: the platform holds no direct identifiers |
| **IPSG.6** Reduce harm from falls | Fall rate monitoring | `fall_rate`, `fall_with_injury_rate` per 1,000 patient days, per unit |
| **PCI** Prevention and Control of Infections | Surveillance with rate-based reporting | HAI rates per 1,000 patient days, hospital-acquired only, by type and unit |
| **COP.3.1** Deteriorating patient recognition | Early warning system | NEWS2 computed on ingest, `news2_high_rate`, RRT-to-code-blue ratio |
| **COP.3.2** Resuscitation services | Code blue monitoring | `code_blue_rate` per 1,000 discharges |
| **MMU.7.1** Medication error reporting | — | `medication_error_rate` by prescribing / transcribing / dispensing / administration |
| **IMS** Management of Information | Data accuracy, security, retention, audit | Staging layer retains source files and checksums; `audit_log`; reversible loads; hashed identifiers |

**On the RRT-to-code-blue ratio.** A high ratio is a *good* sign —
deterioration is being caught before arrest. Reported as context on the
`rrt_activation_rate` tile, because a rising RRT count read in isolation
looks like a worsening safety picture when it is usually the opposite.

## Magnet / NDNQI — nursing excellence

Magnet requires nurse-sensitive indicators reported at unit level and
benchmarked, with nursing hours expressed per patient day.

| Magnet requirement | Platform indicator |
|---|---|
| Nursing care hours per patient day | `nchpd` (RN + LPN + NA productive hours ÷ patient days), per unit |
| RN hours per patient day | `rn_hppd` |
| RN skill mix | `rn_skill_mix` |
| Nurse-to-patient ratio | `nurse_to_patient_ratio` |
| Falls and falls with injury | `fall_rate`, `fall_with_injury_rate` per 1,000 patient days |
| Hospital-acquired pressure injuries | `pressure_injury_rate`, stage II+ |
| RN turnover | `turnover_rate`, annualised |
| Vacancy rate | `vacancy_rate` |
| Agency and overtime reliance | `agency_rate`, `overtime_rate` |

**The denominator decision that matters.** Patient days come from the
bed-movement trail, not from the roster's own census column. Rosters are
typically built on midnight census, which understates a busy short-stay
unit's workload and makes its nursing hours per patient day look generous.
Where the two sources disagree by more than 10%, the platform surfaces it
in a census reconciliation panel rather than silently preferring one.

## Saudi Health Sector Transformation Programme

Vision 2030's HSTP targets model-of-care change, measured through access,
efficiency and experience.

| HSTP theme | Platform contribution |
|---|---|
| Improve access to services | ED waiting times, LWBS, 72-hour revisits, bed availability forecasting |
| Improve quality and efficiency | ALOS, occupancy, bed turnover interval, avoidable-discharge-delay ranking, theatre utilisation |
| Patient experience | `patient_satisfaction`, `net_promoter_score` |
| Workforce sustainability | Vacancy, turnover, overtime, agency reliance, sick leave |
| Value-based care measurement | Consistent numerator/denominator definitions with facility-level benchmark overrides |
| Digital health and data | Structured warehouse, documented API, Power BI compatibility through SQL views |

Cluster-level operation is supported: `ref_facility.cluster_name` and
facility-scoped queries allow several hospitals in one health cluster to
run on a single deployment with comparable definitions.

## PDPL — Saudi Personal Data Protection Law

| Principle | Implementation |
|---|---|
| Data minimisation | The dataset contracts contain no name, national ID, address or phone field — there is nowhere to put them |
| Pseudonymisation | MRNs are SHA-256 hashed with a per-deployment salt at ingest; the raw value never reaches the warehouse |
| Purpose limitation | Every field exists to serve a documented indicator; the data dictionary states the purpose of each |
| Storage limitation | Loads are reversible by batch; retention is configurable per deployment |
| Integrity and confidentiality | TLS in transit, non-root read-only containers, NetworkPolicy restricting API ingress, secrets outside the image |
| Accountability | `audit_log` records access and administrative change; import batches retain source checksum and mapping |

**The salt is effectively permanent.** Rotating it re-pseudonymises every
patient and destroys longitudinal linkage — readmission rates would reset
to zero. It belongs in the secret manager with a documented no-rotation
policy, and this is stated in the deployment plan and in the manifests.

## Evidence a surveyor can be shown

| Question | Where the answer lives |
|---|---|
| How is this indicator defined? | `docs/data-dictionary.md`, Part 2 — numerator, denominator, direction, source |
| Where did this number come from? | `GET /api/v1/import/batches/{id}` — source file, checksum, column mapping, every finding |
| How do you know the data is accurate? | Per-batch quality score across completeness, validity, uniqueness, consistency and timeliness, with each rule's findings retained |
| What happens to bad data? | Quarantined at row level with the reason recorded; the batch report states how many and why |
| Can you reproduce last quarter's figure? | Yes — loads are reversible by batch and metric definitions are versioned in code |
| Who looked at this? | `audit_log` |

## Honest limitations

* **Indicator coverage depends on the extract.** A hospital that cannot
  supply `present_on_admission` cannot report a defensible HAI rate, and
  the platform says so rather than computing one anyway.
* **No automatic case-mix adjustment.** Mortality and readmission are
  crude rates. Comparing units or hospitals on them without adjustment is
  a misuse, and the documentation says so rather than implying otherwise.
* **Sepsis bundle compliance requires a dedicated extract** most hospitals
  do not yet produce; the schema supports it, the dashboard shows it as
  unavailable until it arrives.
* **The platform evidences compliance; it does not confer it.**
