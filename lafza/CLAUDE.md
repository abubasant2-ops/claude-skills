# Lafza (لفظة) — Arabic AI Speech & Language Therapy Platform for Children

> This file is read automatically by Claude Code at the start of every session.
> It is the single source of truth for the project. Keep it updated as the build progresses.

---

## 1. What we are building

Lafza (لفظة) is an Arabic-first digital health platform that assesses and treats
speech and language disorders in children aged 18 months to 12 years.

It is NOT a pronunciation game. It is a clinical therapy assistant: the child speaks
into the microphone (and later camera), the system analyses the pronunciation of each
Arabic phoneme, detects error patterns, and auto-generates a personalised therapy plan
with a monitoring dashboard for the parent and the supervising speech-language
pathologist (SLP).

**Current scope: MVP ONLY.** Do not build features outside the MVP list below, even if
they appear in the wider vision. Ask before expanding scope.

### MVP scope (build only these)
- Arabic parent screening questionnaire (ages 1.5–12): red flags + vocabulary checklist.
- AI articulation assessment for **12 priority letters** (ر س ش ك ق ص ط ث ذ ج غ ل),
  each tested in 3 positions (initial / medial / final).
- Per-phoneme pronunciation score (0–100) + error-pattern profile per child.
- Auto-generated therapy plan (3 target phonemes), editable and approvable by an SLP.
- Articulation therapy library for the 12 letters (word → phrase → sentence → story).
- Gamification core: coins, badges, avatar, daily missions, mascot "لَفُّوظ".
- Parent app: dashboard, daily home program, reminders, weekly report.
- Therapist web dashboard: caseload, plan approval, notes, reports.

### Explicitly OUT of scope for MVP (do NOT build yet)
Visual/camera articulation analysis, teletherapy, dialect packs, AAC/autism module,
fluency module, insurance/EHR integration, school console. These come in later versions.

---

## 2. Tech stack (do not substitute without asking)

| Layer            | Technology                                  |
|------------------|---------------------------------------------|
| Child + Parent app | Flutter (Dart) — one codebase             |
| Backend / API    | FastAPI (Python 3.11+)                       |
| Database         | PostgreSQL 15+ (SQLAlchemy + Alembic)       |
| Therapist dashboard | Next.js + TypeScript + Tailwind          |
| Object storage   | S3-compatible (local MinIO in dev)          |
| Cache / queues   | Redis                                        |
| Auth             | OAuth2 / JWT (short-lived tokens, role-based)|

The heavy AI speech model is NOT built in the MVP. See §6.

---

## 3. Repository layout (create and maintain this structure)

```
lafza/
├── CLAUDE.md                 # this file
├── backend/                  # FastAPI service
│   ├── app/
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── api/              # routers
│   │   ├── services/         # business logic (scoring stub, plan generator)
│   │   └── core/             # config, db, security
│   ├── alembic/              # migrations
│   └── tests/
├── mobile/                   # Flutter app (child + parent)
│   └── lib/
│       ├── features/         # screens grouped by feature
│       ├── core/             # theme (RTL), routing, api client
│       └── data/             # models, repositories
├── dashboard/                # Next.js therapist dashboard
└── docs/                     # keep the blueprint + decisions here
```

---

## 4. Hard rules (never break these)

1. **RTL first.** Every UI in mobile and dashboard is right-to-left by default.
   Test layouts in Arabic, not English.
2. **Arabic UI text is fully vocalised (بالتشكيل).** All child-facing words carry
   diacritics. Store UI strings in Arabic; keep code identifiers in English.
3. **One feature at a time.** Do not start the next feature until the current one runs
   and is proven working. Run the code and show the result before moving on.
4. **Stub the AI.** Any function that needs speech recognition or phoneme scoring must
   return a realistic mock result behind a clean interface (see §6). The real model is
   wired in later without changing callers.
5. **Child safety & privacy.** Recordings of minors are sensitive. Encrypt at rest,
   keep a `retention_until` field, support hard-delete. Never log raw audio or personal
   identifiers. Guardian consent is required before any capture.
6. **Prove it works.** After each task, run migrations / start the server / run tests and
   paste the output. No "should work" — show it working.
7. **Commit after each working step** with a clear message.
8. **Ask before scope changes, new dependencies, or architectural shifts.**

---

## 5. Core data model (MVP)

Build these tables first. Fields are the minimum; add sensibly.

- **users** — id, role (parent | slp | admin), phone, email, locale, password_hash, created_at
- **children** — id, guardian_id (→users), dob, sex, dialect, consent_flags (json), created_at
- **assessments** — id, child_id, type (screening | articulation), raw_json, severity, red_flags (json), created_at
- **phoneme_profiles** — id, child_id, phoneme, position (initial | medial | final), gop_score (0–100), error_type, created_at
- **treatment_plans** — id, child_id, author (ai | slp), goals (json), target_phonemes (json), status (draft | approved | active), approved_by, created_at
- **activities** — id, letter, position, level (word | phrase | sentence | story), text_ar, image_ref, audio_ref
- **sessions** — id, child_id, plan_id, activity_ids (json), duration_sec, scores_json, adherence, created_at
- **recordings** — id, session_id, audio_uri, retention_until, created_at

---

## 6. The AI scoring interface (stub now, real later)

Create ONE service with a stable interface. The MVP uses the stub implementation.

```python
# backend/app/services/scoring.py
class ScoringService:
    def score_utterance(self, audio_path: str, target_phoneme: str,
                        position: str) -> dict:
        """
        Returns:
        {
          "phoneme": "ر",
          "position": "initial",
          "gop_score": 0-100,        # goodness of pronunciation
          "error_type": None | "lateralization" | "substitution" | "omission" | "distortion",
          "confidence": 0.0-1.0
        }
        """
        ...
```

MVP behaviour: return a plausible random-but-consistent score per phoneme, biased so that
"hard" letters (ر ص ض ط ق) score lower. This lets the whole product work end-to-end.
LATER: replace the body with a fine-tuned Whisper/wav2vec2 model + GOP scoring. Callers
must NOT change when this happens.

---

## 7. Arabic phoneme reference (for content + scoring)

- 12 MVP letters: ر س ش ك ق ص ط ث ذ ج غ ل
- Common error patterns to model: ر→ل (lateralization), س→ث (interdentalization),
  ك→ت (fronting), ق→ك (fronting), غ→خ, de-emphasis (ص→س، ط→ت), stopping,
  final-consonant deletion, cluster reduction.
- Developmental order (earlier = easier): ك ل ج before ش س ز before ر ص ض ط ظ ذ ث غ.
  The plan generator should prefer earlier-order, more stimulable phonemes first.

---

## 8. Build order (follow strictly — details in LAFZA_BUILD_PROMPTS.md)

- **Phase A** — Backend foundation: DB models, migrations, basic CRUD API. (done —
  8 tables + initial Alembic migration; CRUD for users/children/assessments/treatment-plans
  under /api/v1; 9 pytest tests passing)
- **Phase B** — Flutter shell: avatar home + audio-record screen with mock data. (done —
  RTL-first MaterialApp (ar locale) with bundled Arabic fonts; welcome → avatar home
  (mascot, coin counter, 3 mission cards) → mission player (stimulus card, guardian-consent
  gate, local mic recording via `record`, analyzing state, mock GOP ring via
  MockScoringService mirroring §6); 4 widget tests passing)
- **Phase C** — Assessment flow: capture → ScoringService (stub) → phoneme_profile → auto plan.
- **Phase D** — Gamification core + therapist dashboard.

Do not jump ahead. Finish, run, commit, then proceed.

---

## 9. Definition of done (every task)

- Code runs locally with no errors.
- New endpoints have at least one test; new screens render in RTL.
- Output/screenshot/log pasted as proof.
- Git commit made.
- CLAUDE.md updated if anything structural changed.
