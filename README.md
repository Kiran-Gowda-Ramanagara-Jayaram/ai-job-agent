# AI Job Agent

Author: Kiran Gowda Ramanagara Jayaram  
Course: INFO 7375 — Generative AI  
Project type: Semi‑autonomous job triage and recruiter‑outreach assistant built with LLMs, RAG, and an online learning loop.

---

## Overview

This application helps a job‑seeker discover relevant roles, generate tailored application materials, find recruiter work emails, and learn which outreach style works best over time. It is intentionally human‑in‑the‑loop and avoids automated portal submissions.

Key capabilities:

- Ingest real job postings from Greenhouse, Lever, and Ashby (presets or custom slugs)
- Score role fit against a profile (RoleFit v2: cosine features + logistic regression)
- Generate artifacts per job: tailored resume bullets, a cover letter, interview prep pack, and 20 STAR answers
- Find recruiter emails with Hunter.io, including a Smart Search that tries common domain patterns
- Track contacts and outreach in a lightweight CRM
- Learn the best outreach template via a Thompson‑sampling multi‑armed bandit
- Visualize outcomes on a simple dashboard; export data and full job packets (ZIP)

Why it is a strong INFO 7375 project:

- Implements Prompt Engineering, RAG, Synthetic Data, and an Online Learning loop
- Ships as a working Streamlit app with clear audit trails (CSV exports and ZIP packet)

---

## Architecture

```mermaid
flowchart LR
  A[Ingest scripts
Greenhouse/Lever/Ashby presets] --> B[(SQLite jobs.db)]
  B --> C[RoleFit v2
(cosine + logistic)]
  C --> D[Streamlit App
(Queue and Dashboard)]
  D --> E[Artifact Generation (LLM)
Resume bullets, Cover letter, STAR, Prep]
  D --> F[RAG store
(SimpleStore, swappable)]
  D --> G[Hunter.io integration
Domain and Name finder]
  D --> H[(CRM tables)]
  H --> I[Bandit learner
Template stats]
  I --> D
  D --> J[Dashboard and Exports]
```

Core techniques

- Prompt Engineering: structured prompts with JD, role, company, and resume snippets
- RAG: small vector store to condition artifacts on JD/company context
- Synthetic Data: scripted job/label generation for model training
- Online Learning: Beta–Bernoulli Thompson sampling chooses outreach templates based on outcomes

---

## Repository layout 

```
ai-job-agent/
├── app/
│   ├── app.py                # Streamlit UI with Queue and Dashboard tabs
│   └── dashboard.py          # optional dedicated dashboard page (older)
├── agents/
│   ├── coach_agent.py        # interview/coach helper (optional)
│   ├── composer.py           # resume bullets + cover letter prompts
│   ├── gap_agent.py          # gap analysis helper (optional)
│   ├── outreach_agent.py     # outreach drafting + bandit template selection
│   ├── prep_agent.py         # interview prep pack
│   ├── rolefit.py            # feature builders for fit model
│   ├── scorer.py             # fit scoring helpers
│   └── star_agent.py         # 20 STAR answers
├── artifacts/                # generated per-job artifacts
├── data/
│   ├── ashby_orgs.txt
│   ├── bandit_state.json     # persisted bandit stats
│   ├── base_resume.md        # your base resume content
│   ├── greenhouse_slugs.txt
│   ├── lever_slugs.txt
│   └── profile.yaml          # roles, locations, keywords, contact info
├── db/
│   ├── __init__.py
│   ├── bandit.py             # Thompson sampling and state helpers
│   ├── crm.py                # contacts and outreach events
│   ├── jobs.db               # SQLite DB
│   └── models.py             # SQLAlchemy models (jobs, fits, artifacts)
├── integrations/
│   ├── __init__.py
│   └── hunter.py             # Hunter.io API wrappers
├── models/
│   └── fit_clf.joblib        # trained RoleFit classifier
├── rag/
│   ├── __init__.py
│   └── store.py              # SimpleStore vector search (swappable)
├── scripts/
│   ├── __init__.py
│   ├── cleanup_jobs.py
│   ├── ingest_ashby.py
│   ├── ingest_greenhouse.py
│   ├── ingest_lever.py
│   ├── ingest_presets.py
│   ├── ingest_presets_ashby.py
│   ├── ingest_presets_lever.py
│   ├── seed_synthetic.py
│   └── train_fit_model.py
├── tests/                    # unit tests (add here)
├── utils/
│   └── docx_resume.py        # parse .docx to base_resume.md (optional)
├── .env                      # API keys (local only)
├── bandit.sqlite3            # alt storage for experiments (optional)
├── main.py                   # entrypoint alias (optional)
├── requirements.txt
└── README.md
```

---

## Setup

1) Create a virtual environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2) Configure secrets in a file named .env at project root

```ini
OPENAI_API_KEY=sk-...
HUNTER_API_KEY=...
```

3) Edit targeting profile at data/profile.yaml

```yaml
target_roles:
  - "Machine Learning Engineer (Data focus)"
  - "Data Scientist"
  - "ML Ops Engineer"
  - "Software Engineer (Backend)"
locations:
  - "Boston, MA"
  - "Remote - USA"
  - "Bellevue, WA"
  - "Seattle, WA"
  - "San Francisco, CA"
  - "San Diego, CA"
  - "San Jose, CA"
  - "Miami, FL"
  - "Tampa, FL"
must_have_keywords:
  - "Python"
  - "SQL"
  - "Spark"
  - "AWS"
nice_to_have_keywords:
  - "Airflow"
  - "Snowflake"
  - "Databricks"
  - "Docker"
  - "Kubernetes"
linkedin: "https://www.linkedin.com/in/kirangowda3101/"
email: "ramanagarajayaram.k@northeastern.edu"
phone: "(857) 313-0063"
```

---

## Getting jobs into the queue

Option A: curated presets (recommended for demos)

```bash
python -m scripts.ingest_presets --limit 100
python -m scripts.ingest_presets_lever --limit 100
python -m scripts.ingest_presets_ashby --limit 100
python -m scripts.cleanup_jobs
```

Option B: specific Greenhouse board

```bash
# boards.greenhouse.io/notion -> slug is "notion"
python -m scripts.ingest_greenhouse --board notion --no-filters --limit 100
```

Add more organizations by editing:

- data/greenhouse_slugs.txt
- data/lever_slugs.txt
- data/ashby_orgs.txt

---

## Train the fit model (optional but recommended)

```bash
python -m scripts.seed_synthetic
python -m scripts.train_fit_model
```

The trained classifier is saved to models/fit_clf.joblib.

---

## Run the app

```bash
streamlit run app/app.py
```

The app opens with two tabs: Queue and Dashboard. You do not need to run a separate dashboard page.

---

## Using the app

1. Expand a job in the Queue tab. Generate artifacts (resume bullets and cover letter), then optionally the prep pack and STAR answers.
2. Find recruiter emails with Hunter.io. Enter a domain like company.com or click Smart Search to try common patterns. Save any useful results.
3. Draft outreach for a saved contact. Review the suggested email subject/body and LinkedIn DM, select the template used, and log outreach as sent.
4. Record the outcome (sent, no_reply, positive_reply, interview, rejected). The bandit updates template weights for the matching job bucket.
5. Export a complete job packet (ZIP) containing artifacts, CRM contacts, and outreach history CSVs.

---

## Dashboard and exports

- Outcome heatmap by company and outcome type
- Download buttons for jobs.csv, contacts.csv, and outreach_events.csv
- Full per‑job packet export from the Queue tab

---

## Hunter.io tips

- If domain search is empty, switch the department filter to "(any)"
- Smart Search tries patterns such as make<name>.com, get<name>.com, join<name>.com, and known special cases (for example, makenotion.com, notion.so)
- Name finder works best when the domain is correct and first/last name are common spellings

---

## Customization

- Outreach templates live in agents/outreach_agent.py (or wire a data/templates.yaml for live editing)
- Swap RAG backend by replacing rag.store.SimpleStore with FAISS/Chroma and persisting an index under data/index/
- Theme, fonts, and sizes are set in app/app.py; the app uses larger labels and subtle animations by default

---

## Troubleshooting

- No jobs after ingest: try running with --no-filters, then prune via scripts.cleanup_jobs. Also confirm your profile.yaml roles and locations are not overly restrictive.
- Hunter errors: ensure HUNTER_API_KEY is set; try the "(any)" department; or use Smart Search.
- Outreach toast not visible: ensure the form button "Log outreach as sent" was clicked; Streamlit reruns can hide transient toasts.

---

## License

This repository is provided under the MIT License. The full text is included below for convenience. To publish the license separately, create a file named LICENSE with the same contents.

### MIT License

Copyright (c) 2025 Kiran Gowda Ramanagara Jayaram

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

## Acknowledgements

Built by Kiran Gowda Ramanagara Jayaram for INFO 7375. Thanks to the open‑source communities behind Streamlit, SQLAlchemy, FAISS/Chroma, and the APIs used in this project.

