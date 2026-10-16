# Policy Loader ETL Validation POC — Kiro Team Guide

## What This Guide Covers

This document walks your team through using Kiro IDE to build the Policy Loader validation pipeline. It covers workspace setup, how to use Kiro's features effectively, and a recommended execution plan to get a working demo quickly.

---

## 1. Workspace Overview

The workspace is pre-configured with Kiro features that will guide code generation across all sessions:

```
.kiro/
├── steering/
│   ├── policy-loader-conventions.md   ← Project rules (always active)
│   └── validation-patterns.md         ← Code patterns & templates (always active)
├── hooks/
│   ├── run-tests-after-task.json      ← Auto-runs pytest after each spec task
│   └── lint-python-on-save.json       ← Auto-lints Python files on save
```

### What These Do

| Component | Purpose |
|-----------|---------|
| **Steering files** | Automatically included in every Kiro session. They tell Kiro your conventions (Pandas only, VAL_ prefix, severity messages, etc.) so you don't have to repeat them in every prompt. |
| **PostTaskExec hook** | After Kiro finishes a spec task, it automatically runs `pytest` to verify the code works before moving on. |
| **PostFileSave hook** | Every time a `.py` file is saved, `ruff` runs to fix lint issues automatically. |

---

## 2. Prerequisites

Before starting, make sure you have:

1. **Kiro IDE** installed (built on VS Code)
2. **Python 3.12** available on your PATH
3. **pip packages** installed:
   ```
   pip install pandas psycopg2-binary pytest ruff
   ```
4. The source spreadsheet `DB_Section_v2_New_-_5-4-26_from_NByers.xlsm` (or the CSV export) in the workspace folder

---

## 3. How to Use Kiro Spec Sessions

This project is best built using **Spec sessions** (not Vibe sessions). Spec sessions provide a structured workflow: Requirements → Design → Tasks, with review gates between each stage.

### Starting a Spec Session

1. Open Kiro IDE with this workspace
2. Press `Ctrl+Shift+P` → type **"New Spec"** → select it
3. Paste your requirements into the spec prompt (see Section 5 below for what to paste)
4. Attach the CSV/Excel file as additional context (drag it into the chat)
5. Kiro generates Requirements → Design → Tasks
6. **Review each section before approving** — this is your control point

### Key Concepts

- **Autopilot mode** (default): Kiro works through tasks end-to-end. You can interrupt, review, or revert at any time.
- **Supervised mode**: Kiro pauses after each file edit for your approval. Use this if you want tighter control.
- To switch modes: look for the mode toggle in the Kiro panel.

---

## 4. What Are Steering Files?

Steering files are markdown files in `.kiro/steering/` that Kiro reads at the start of every session. They act as persistent instructions — think of them as "team standards" that Kiro always follows.

### Your Steering Files

**`policy-loader-conventions.md`** — Defines:
- Tech stack (Python 3.12, Pandas, psycopg2, Lambda)
- Naming conventions (VAL_ prefix, SEVERE:/WARNING: message format)
- Primary keys for each table
- How spec language maps to severity levels

**`validation-patterns.md`** — Defines:
- Module structure (one function per field, orchestrator, classifier, splitter)
- Function signature patterns with examples
- Cross-table validation pattern using Pandas merge
- Lambda handler template
- Testing requirements

### Editing Steering Files

If you need to update conventions (e.g., add a new allowed value, change a pattern), edit the files directly in `.kiro/steering/`. Changes take effect on the next session.

---

## 5. Recommended Execution Plan

### Phase 1: Quick Demo (1-2 hours)

Goal: Get a working CNT validator you can demo to stakeholders.

**Spec prompt for Phase 1:**
```
Build the validation_utils.py shared module and validate_cnt.py for the Contract table (32 fields). Include unit tests. Use the attached spreadsheet as the source of truth for field rules.

Scaffold the project at: policy_loader_poc/

After implementation, create a run_local.py script that:
1. Reads sample data from a CSV file
2. Runs the CNT validation
3. Prints a summary report (total rows, clean/warning/severe counts, top failure reasons)
4. Writes the three output DataFrames to separate CSV files
```

Attach the CSV file when submitting.

**What you get:**
- `policy_loader_poc/validation_utils.py` — shared helpers
- `policy_loader_poc/validate_cnt.py` — all 32 field validators + Lambda handler
- `policy_loader_poc/test_validate_cnt.py` — unit tests
- `policy_loader_poc/run_local.py` — local demo script

**Demo it:** Create a small sample CSV with 5-10 rows (some valid, some invalid) and run:
```bash
cd policy_loader_poc
python run_local.py --input sample_cnt.csv
```

### Phase 2: Cross-Table Validation (1-2 hours)

Goal: Demonstrate inter-table validation with PRM.

**Spec prompt for Phase 2:**
```
Build validate_prm.py for the Premium Billing table (30 fields). Include cross-table validations against CNT using Pandas merge. Include unit tests. Update run_local.py to support PRM validation with a --table flag.
```

### Phase 3: Complete Coverage (3-4 hours)

Goal: Build FIN and NFN validators.

**Spec prompt for Phase 3:**
```
Build validate_fin.py for the Financial History table (56 fields) and validate_nfn.py for the Non-Financial History table (64 fields). Include cross-table validations and unit tests for both.
```

### Phase 4: Lambda Packaging (optional, after demo approval)

Goal: Package for AWS deployment.

```
Package each validation module as a Lambda-ready ZIP. Create a deployment script that uses AWS CLI to create/update the Lambda functions.
```

---

## 6. How Hooks Work

### PostTaskExec Hook (Auto-Testing)

After Kiro completes each task in a spec, it automatically runs:
```
python -m pytest policy_loader_poc/ -v --tb=short
```

If tests fail, you'll see the output in the Kiro session. Kiro will attempt to fix failures before moving to the next task.

### PostFileSave Hook (Auto-Linting)

Every time you (or Kiro) save a `.py` file, ruff runs automatically:
```
python -m ruff check --fix .
```

This keeps code style consistent without manual intervention.

### Viewing/Managing Hooks

- Open the Explorer panel → look for **"Agent Hooks"** section
- Or press `Ctrl+Shift+P` → **"Open Kiro Hook UI"**

---

## 7. Tips for Working with Kiro on This Project

### Do

- **Attach the spreadsheet** every time you start a new spec session — Kiro uses it as source of truth
- **Review the Requirements stage** before approving — this is where you catch misunderstandings
- **Run one table at a time** — smaller specs produce better results than one massive prompt
- **Use `#File` references** in chat to point Kiro at specific files (e.g., "update #validate_cnt.py to fix the date check")
- **Check the test output** after each task — the hook runs tests automatically but review the results

### Don't

- Don't skip the review step between Requirements → Design → Tasks
- Don't try to generate all 4 tables in a single spec session — split them up
- Don't modify steering files mid-session (changes apply on next session)
- Don't worry about Lambda deployment until the validation logic is proven locally

### If Something Goes Wrong

- **Kiro generates incorrect logic:** Edit the steering file to add a more specific rule, then start a new session
- **Tests keep failing:** Switch to Supervised mode and review each change
- **Hook not running:** Hooks activate on session start — close and reopen the session
- **Need to undo:** Kiro tracks all changes — use the revert option in the Kiro panel

---

## 8. Project Structure (Target State)

After all phases are complete:

```
policy_loader_poc/
├── validation_utils.py          ← Shared helpers (date, numeric, length, classify, split)
├── validate_cnt.py              ← Contract validation (32 fields) + Lambda handler
├── validate_prm.py              ← Premium Billing validation (30 fields) + Lambda handler
├── validate_fin.py              ← Financial History validation (56 fields) + Lambda handler
├── validate_nfn.py              ← Non-Financial History validation (64 fields) + Lambda handler
├── test_validate_cnt.py         ← CNT unit tests
├── test_validate_prm.py         ← PRM unit tests
├── test_validate_fin.py         ← FIN unit tests
├── test_validate_nfn.py         ← NFN unit tests
├── run_local.py                 ← Local demo script (reads CSV, prints report)
├── requirements.txt             ← pandas, psycopg2-binary, pytest, ruff
└── sample_data/
    ├── sample_cnt.csv           ← Test data for CNT
    ├── sample_prm.csv           ← Test data for PRM
    ├── sample_fin.csv           ← Test data for FIN
    └── sample_nfn.csv           ← Test data for NFN
```

---

## 9. Kiro Features Summary

| Feature | What It Does | Where It Lives |
|---------|--------------|----------------|
| **Spec sessions** | Structured requirements → design → tasks workflow with review gates | Start via Ctrl+Shift+P → New Spec |
| **Steering files** | Persistent rules/conventions included in every session automatically | `.kiro/steering/*.md` |
| **Hooks** | Automated actions triggered by events (file save, task complete, etc.) | `.kiro/hooks/*.json` |
| **Autopilot mode** | Kiro works end-to-end, you review after | Toggle in Kiro panel |
| **Supervised mode** | Kiro pauses after each edit for approval | Toggle in Kiro panel |
| **Context references** | Use `#File` or `#Folder` in chat to reference specific files | Type `#` in chat input |
| **File attachments** | Drag CSV/Excel/images into chat for Kiro to analyze | Drag or click attachment icon |

---

## 10. Quick Reference: Spec Prompts

Copy-paste these when creating new spec sessions.

### Utilities + CNT (Start Here)
```
Build the shared validation_utils.py module and validate_cnt.py for the Contract table.
Include all 32 field validators based on the attached spreadsheet rules.
Include cross-field validations (SEX_CODE vs JOINT_LIFE_INDICATOR, dates, etc.).
Generate unit tests covering CLEAN, WARNING, and SEVERE scenarios.
Create a run_local.py demo script that processes a CSV and outputs a validation report.
```

### PRM
```
Build validate_prm.py for the Premium Billing table (30 fields).
Include cross-table validations against CNT using Pandas merge.
Include conditional rules driven by BILLING_FORM and PRODUCT_TYPE.
Generate unit tests with cross-table scenarios.
```

### FIN
```
Build validate_fin.py for the Financial History table (56 fields).
Include loan-related conditional rules, tax override rules, and trans-code-driven rules.
Include cross-table validations against CNT.
Generate unit tests.
```

### NFN
```
Build validate_nfn.py for the Non-Financial History table (64 fields).
Include PRODUCT_TYPE-driven blank rules for fields that must be blank when type is A/W/B/H.
Include old/new pair consistency checks.
Include cross-table validations against CNT.
Generate unit tests.
```

---

## 11. Contacts & Resources

- **Source spec:** `policy_loader_kiro_spec.md` (in this repo)
- **Field definitions:** `DB_Section_v2 New - 5-4-26 from NByers.csv` (in this repo)
- **Full spreadsheet:** `DB_Section_v2_New_-_5-4-26_from_NByers.xlsm` (if available, has all tabs)

---

*Guide created: July 2026*
*For questions about Kiro features, use the Kiro chat and ask directly — it can explain its own capabilities.*
