# Grade-Aware Evaluation — Calibration & Tuning Guide

This guide explains **how to validate that the AI grader scores fairly across all class levels** and **how to tune the grading rules** when scores diverge from a human teacher's judgment.

It covers Phase 5 of the grade-aware evaluation rollout.

---

## Why Calibrate?

Without ground truth, you have no way to know if your grading rubric is actually fairer to a Class 2 student than the previous one-size-fits-all approach. The AI may *feel* right but still be 2-3 marks off systematically.

Calibration solves this by:

1. Building a small **set of hand-graded sample answers** spanning every class band.
2. Running the AI grader against that set.
3. Comparing AI scores to the human scores.
4. Tuning the rubric in `grading_standards.json` until they match within ±1 mark.

You repeat this loop whenever you change:
- The grading bands (e.g. shifting Primary from 1–3 to 1–2)
- The rubric instructions inside a band
- The subject-specific overlays
- The LLM provider (Ollama → Claude)

---

## Files Involved

| File | Purpose |
|---|---|
| `backend/calibration_data/calibration_set.json` | The hand-graded samples |
| `backend/services/grading_standards.json` | The rubric configuration you tune |
| `backend/scripts/run_calibration.py` | The runner that compares AI vs human |

---

## The Calibration Set

`calibration_set.json` already ships with 10 example samples spanning all 4 bands and 5 subjects. Each entry looks like this:

```json
{
  "id": "middle_001",
  "class_level": 7,
  "subject": "Science",
  "question": "Explain how photosynthesis works.",
  "expected_answer": "Photosynthesis is the process by which green plants use sunlight, water, and carbon dioxide to make glucose and release oxygen. It takes place in the chloroplasts.",
  "keywords": ["sunlight", "water", "carbon dioxide", "glucose", "oxygen", "chloroplasts"],
  "student_answer": "Plants take sunlight and water and carbon dioxide and make their food which is glucose and they give out oxygen.",
  "human_score": 7,
  "rationale": "5 of 6 keywords present; missing 'chloroplasts' (location)."
}
```

### Building Your Own (Recommended)

Replace or extend the shipped set with **5–10 samples per class band drawn from real student work**. The more representative the set, the more meaningful the tuning.

**Coverage checklist** — your calibration set should include:

| Band | Suggested coverage |
|---|---|
| Primary (1–3) | One excellent answer, one partial, one minimum-effort, plus one with childlike spelling |
| Upper Primary (4–5) | Same mix, with one math word problem and one science description |
| Middle (6–8) | Excellent, partial, weak; one explain-style, one compare-style, one numeric/math |
| Secondary (9–10) | Full-marks, partial, weak, and one that's *almost* correct but missing precise terminology |

Hand-grade each one as a teacher would. **The human score is the source of truth** — every tuning decision below comes back to it.

---

## Running the Calibration

From the project root:

```powershell
# Default: Ollama, ±1 mark tolerance
python -m backend.scripts.run_calibration

# Tighter tolerance
python -m backend.scripts.run_calibration --tolerance 0.5

# Run only Primary band samples
python -m backend.scripts.run_calibration --filter primary

# Test the production provider
python -m backend.scripts.run_calibration --provider anthropic

# Save a JSON report for tracking over time
python -m backend.scripts.run_calibration --report runtime_data/calibration_2026-05-04.json
```

### What You'll See

```
Running 10 sample(s) with provider=ollama tolerance=±1.0

  [1/10] primary_001: AI=8.5  H=9.0  d=-0.50  ✓
  [2/10] primary_002: AI=5.0  H=4.0  d=+1.00  ✓
  [3/10] middle_001: AI=5.5  H=7.0  d=-1.50  ✗
  …

ID                     Class Subject    Human    AI    Diff Method     Band             OK
--------------------------------------------------------------------------------------------
primary_001                2 Science      9.0   8.5   -0.50 keyword    primary           ✓
primary_002                2 Science      4.0   5.0   +1.00 keyword    primary           ✓
middle_001                 7 Science      7.0   5.5   -1.50 semantic   middle            ✗
…

============================================================
Samples evaluated      : 10
Pass (|diff| <= 1.0) : 8 / 10  (80%)
Mean abs diff          : 0.74
Stdev abs diff         : 0.62
Max overshoot (AI>H)   : +1.30
Max undershoot (AI<H)  : -1.50

Per-band breakdown:
  primary        n= 3   pass=3/3  mean|d|=0.40  bias=+0.10
  upper_primary  n= 2   pass=2/2  mean|d|=0.50  bias=-0.25
  middle         n= 2   pass=1/2  mean|d|=1.10  bias=-1.10
  secondary      n= 3   pass=2/3  mean|d|=0.95  bias=-0.30
============================================================
```

The **bias** column is the most useful number. Negative bias = AI is harsher than the human; positive = AI is more lenient.

---

## Diagnosing the Result

Look at the **per-band breakdown** first. Treat each band independently because they use different rubrics.

### Pattern 1: All bands pass (`bias` between –0.5 and +0.5)
You're done. The system is well-calibrated.

### Pattern 2: One band consistently scores too low (e.g. middle bias = −1.1)
The middle-school rubric is **too strict**. Open `grading_standards.json` → middle band → `rubric_instructions`:

- Soften specific lines (e.g. "Penalize spelling/grammar moderately" → "Penalize only when meaning is unclear").
- Lower `keyword_pass_ratio` from 0.7 to 0.65.
- Change `partial_credit_generosity` from `medium` to `medium-high`.

Save, then run:

```powershell
# Reload without restarting the backend
curl -X POST http://localhost:8000/api/admin/grading-standards/reload \
     -H "Authorization: Bearer <admin-token>"

# Re-run calibration
python -m backend.scripts.run_calibration --filter middle
```

Repeat until the band's bias is within ±0.5.

### Pattern 3: One band consistently scores too high (e.g. primary bias = +1.5)
The primary rubric is **too lenient**. Tighten:

- Raise `keyword_pass_ratio` from 0.5 to 0.6.
- Add a line like: "If 2 or more required keywords are missing, score should not exceed 6."
- Lower `partial_credit_generosity` to `medium-high`.

### Pattern 4: Wide stdev within a band (some samples +2, others –2)
The rubric is *inconsistent*, not biased. The fix is usually:

- **Make instructions more specific.** "Be encouraging" is vague. "Score 7-10 for any answer that contains all required keywords, even if phrased simply" is actionable.
- **Add tie-breaker rules.** "If correct in idea but wrong in numerical answer: cap at 6."
- **Switch from Ollama to Claude** for that band. Tiny local models often have higher variance.

### Pattern 5: One subject fails across all bands
The subject overlay is wrong. Open `grading_standards.json` → `subjects.{Math|Science|...}` and revise `extra_instructions`.

---

## Tuning Workflow (Step-by-Step)

```
┌──────────────────────────────┐
│  1. Run calibration          │
│     python -m backend...     │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  2. Read per-band bias       │
│     and pass rate            │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  3. Identify worst band      │
│     or worst subject         │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  4. Edit grading_standards   │
│     .json (one band at a     │
│     time)                    │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  5. Hot-reload via            │
│     POST /api/admin/grading-  │
│     standards/reload          │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  6. Re-run calibration with  │
│     --filter <band>          │
└──────────┬───────────────────┘
           │
           ▼
   bias within ±0.5? ─── No ──▶ back to step 4
           │
           Yes
           ▼
┌──────────────────────────────┐
│  7. Re-run full calibration  │
│     to confirm no regression │
│     in other bands           │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  8. Commit grading_standards │
│     .json + calibration JSON │
│     report to git            │
└──────────────────────────────┘
```

---

## When to Re-Calibrate

Run the calibration **before** you:
- Ship to production
- Switch providers (Ollama ↔ Claude)
- Upgrade the LLM model (e.g. Sonnet → Opus, qwen 0.5b → 3b → 8b)
- Change a band's `class_min` / `class_max`
- Add a new subject overlay

Run it **periodically** (e.g. monthly) to catch drift after model updates from Anthropic or Ollama.

---

## CI Integration

`run_calibration.py` exits with code 0 when every sample passes the tolerance, and code 2 otherwise. Wire it into your CI:

```yaml
# Example GitHub Actions step
- name: Grading calibration regression test
  run: |
    python -m backend.scripts.run_calibration --tolerance 1.0
```

---

## How the AI Score Is Computed (Reminder)

For each sample, the runner calls `hybrid_evaluate(class_level, subject, ...)` which:

1. Loads the **band rubric** for the class level.
2. Layers on the **subject overlay** if a subject is given.
3. Computes a **keyword score** (rule-based, fast).
4. Computes a **semantic score** via the LLM using the rubric-augmented prompt.
5. Decides:
   - If `keyword_ratio >= band.keyword_pass_ratio` → use keyword score.
   - Else → use semantic score.
6. Returns `score_out_of_10`, `method`, `grading_band`, plus feedback.

So tuning has **two knobs per band**:
- `keyword_pass_ratio` — how generous the rule-based path is.
- `rubric_instructions` — what the LLM is told to look for in the semantic path.

Adjust the right knob for the failure pattern: keyword bias → adjust ratio; semantic bias → adjust instructions.

---

## Sample Sizes — How Many Is Enough?

| Stage | Samples per band | What it gives you |
|---|---|---|
| Quick smoke test | 3 | Catches blatant regressions |
| Routine tuning | 5–10 | Detects bias direction reliably |
| Pre-production sign-off | 15–20 | Detects subtle subject/topic biases |
| Research-grade evaluation | 50+ | Statistical confidence intervals |

Start with the shipped 10. Grow the set every week or two as real student answers come in.

---

## Trust, but Verify

A passing calibration run does **not** guarantee fairness on the next student answer — it guarantees fairness on the *distribution* you sampled. Always:

- Spot-check 2–3 real student answers per week against the AI score.
- Add any answer where the AI was more than 1 mark off back into the calibration set as a new sample.
- Treat calibration as continuous, not one-and-done.

---

That's it. Run, measure, tune, repeat — and your grading will stay aligned with what an experienced teacher would give.
