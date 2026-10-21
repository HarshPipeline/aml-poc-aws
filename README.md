# Streaming AML Investigation POC

A runnable Python demo over the five-customer dataset in RDS. Replay the most recent synthetic transactions, inspect deterministic AML alerts, collect evidence with eight LangGraph capabilities, review a complete report, and record a human decision. No API key is required for demo mode.

Customers, accounts, counterparties, policy thresholds and transactions are read from Amazon RDS PostgreSQL. Alerts, cases, documents, the audit trail and LangGraph checkpoints are stored in a writable `aml_app` schema in the same database. The app does not read JSON or CSV files at runtime.

## Start

Copy `.env.example` to `.env` and set the `DB_*` values for the RDS instance. The database user must be able to create the `aml_app` schema.

```bash
cd aml-poc-aws
./run.sh
```

Open **http://127.0.0.1:8501**. Interactive API docs: **http://127.0.0.1:8001/docs**. The KYC dashboard is at **http://127.0.0.1:8001/kyc**.
The launcher creates a virtual environment on first use and installs the project. Both services bind only to localhost. Stop with Ctrl+C.

1. In **Live stream**, press **Start / resume**. The default rate is 50 events per second. Reports are built after replay finishes so investigators see the latest evidence.
2. In **Alert queue**, select **stream**, choose a signal and open its workbench.
3. Run the investigation. Original inputs have no invoices, explanations or depositor documents, so the first report correctly shows incomplete evidence and no recommendation.
4. Attach your structured supporting records in **Documents**, or use **Attach synthetic demo packet** to demonstrate the complete-report path. The packet is explicitly fictional and does not verify the transaction's legitimacy.
5. Run a fresh investigation. Review the findings, innocent explanation, evidence IDs, critic result and editable SAR draft.
6. Record **clear**, **request info** or **escalate** with your name and reason. This resumes the durable LangGraph interrupt. No automatic disposition or external SAR filing occurs.
7. Download the complete report and case JSON; inspect **Audit trail** and **Evaluation & policy**.

The workbench also demonstrates missing KYC, unavailable transactions, missing/unreadable documents and conflicting policy. These paths end in incomplete reports for a human.

For a container deployment, `docker compose up --build` starts the API and console. Both containers read RDS settings from `.env`. This optional path requires Docker; the local launcher is the verified development path.

## Python streaming

```bash
./run.sh replay --rate 100
```

On first start the API loads RDS transactions older than the stream cutoff as history, runs the detectors, and stores committed events in `aml_app.events`. The default cutoff is the most recent 1,000 RDS rows; override it with `AML_STREAM_START` or `AML_STREAM_EVENTS`. Start/resume skips already committed transaction IDs. Pause and API restarts preserve progress. A duplicate ID with different contents is rejected. Late events are explicitly rejected rather than silently changing the past. Each event timestamp is the simulation's UTC watermark; arrival rate controls wall-clock replay speed.

External events can be posted as one transaction JSON object to `POST /transactions`. `GET /events` streams server-sent status events. The console polls the API every two seconds. `POST /replay/clock` with `{"as_of":"2027-03-01T00:00:00"}` advances the demo clock without inserting fake payments, allowing the TM-08 quiet-period timer to fire. Advancing past unconsumed stream events will make them late; finish replay first.

## Rules and evidence

Enabled patterns: TM-01 structuring, TM-03 out-of-region funnel deposits, TM-04 rapid funnel outflows, TM-07 pass-through matching, TM-08 wire bursts, TM-09 international wires. Numeric thresholds come from the RDS `policy_patterns` table. Every alert retains the policy's SHA-256 and thresholds. A policy change requires a new `AML_APP_SCHEMA` to preserve the original run.

- TM-01 and TM-03 evaluate rolling windows before grouping overlapping activity into episodes.
- TM-04 uses FIFO monetary allocation within each deposit's 72-hour window. It never reuses an outgoing dollar or allocates more than a deposit's value. This is a tracing heuristic, not proof of money provenance; ordinary supplier payments can still be allocated.
- TM-07 matches incoming credits to outgoing wires, checks or ACH debits one-to-one by nearest amount within the policy's tolerance and time limit.
- TM-08 requires observed pre-burst quiet time, emits provisionally at the count/amount threshold, confirms after the post-burst quiet period, and withdraws an invalidated burst signal. A provisional alert does not assert future cessation.
- TM-09 applies the 90-day international-wire window to missing payment information, unknown counterparties, country-profile conflicts and round-amount frequency.
- Operational episode grouping uses 30 days of indicator inactivity for TM-07/TM-09, 7 days for TM-01 and 14 days for TM-03. Episode totals may span more than a qualifying rolling window. These are explicit demo deduplication choices, not regulatory thresholds.
- Runtime rules do not import a label reader. Synthesis hints such as `assigned_pattern_ids` are excluded from the evidence sent to agents.

The graph runs **Orchestrator → KYC → Transaction → Document → Policy → Investigation → Report → Critic → Human review**. The critic checks the full draft, including narrative sentences, retries once when appropriate, then sends defects to a person. Every fact/rule entry has a source; findings and narrative sentences cite evidence IDs. Code checks citation existence and numeric provenance. Demo mode does not measure semantic groundedness.

## OpenAI API

The current local configuration uses OpenAI. Add your key only to the ignored `.env` file:

```dotenv
AML_AGENT_MODE=openai
OPENAI_API_KEY=<your API key>
AML_OPENAI_MODEL=gpt-5-mini
```

The provider uses the Responses API with Pydantic structured outputs and `store=False`. GPT reasoning is set to low and output is bounded for shorter waits. Investigation and semantic critique use the live model; the report assembles their cited wording without an extra model round trip. Set AML_GENERATE_NARRATIVE=true for a separately generated SAR draft. Facts and detection stay deterministic. Model calls do not hold the monitoring database lock, so status and transaction views remain responsive. Restart `./run.sh` after changing provider settings. API keys are never sent to the browser or included in case reports.

## Claude and LangSmith

```bash
cp .env.example .env
# Edit .env:
# AML_AGENT_MODE=claude
# ANTHROPIC_API_KEY=...
# AML_CLAUDE_MODEL=<a model ID enabled for your Anthropic account>
# LANGSMITH_TRACING=true
# LANGSMITH_API_KEY=...
./run.sh
```

KYC, transaction, document-coverage and policy tools remain deterministic. Claude performs structured investigation, narrative drafting and semantic critique over their case file. It gets no arbitrary SQL, filesystem or network tool. Calls fail closed into an incomplete report. LangSmith uses the standard LangGraph tracing integration; enable it only for data you intend to send to that service. Live calls require your keys and are not part of the no-key test results.

## Data and persistence

All operational inputs are read from RDS: `customers`, `kyc_profiles`, `beneficial_owners`, `accounts`, `counterparties`, `customer_counterparties`, `transactions` and `policy_patterns`. Connections used for those reads are read-only, with a 15-second statement timeout.

Application state lives in the `aml_app` schema (override with `AML_APP_SCHEMA`): committed events, alerts, report versions, documents, hash-chained append-only audit records and LangGraph checkpoints. Each report snapshots an alert revision. New transaction evidence or a changed document collection requires a new report before a decision. Previous reports and human decisions remain accessible by case ID.

To create a separate run, set `AML_APP_SCHEMA=another_schema` before launching. One API process owns a run; multiple workers are unsupported. The audit hash chain detects modifications but is not tamper-proof against an administrator who rewrites the whole database.

The optional loader in `kyc-postgres/db/load_data.py` can fill the operational tables from `aml_demo_data_cleaned/`. **Do not run it against an existing database without a backup and explicit intent to replace its tables: it drops and recreates them.** The app never runs the loader.

## Validation

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check aml_poc tests
```

Tests talk to the same RDS instance and write only to temporary `aml_test_*` schemas, which they drop afterwards. They skip if `DB_HOST` is unset. Detector coverage scoring against held-out labels is not part of the runtime path; those labels are not stored in RDS.

## POC boundaries

This is a synthetic investigation demonstrator. Documents support structured intake, UTF-8 text, local PDF text extraction and optional Claude vision for PNG/JPEG/WebP. Model extraction is visibly classified as an observation; code compares extracted invoice IDs and amounts with transactions. Unreadable/low-confidence records stop the recommendation. Scanned-PDF OCR, authenticity checks and invoice-template forensics are not implemented. Policy retrieval uses exact triggered-pattern references from the RDS policy table, rather than a vector database or a refreshed regulatory corpus. The investigator name is an audit attribution field, not authenticated bank SSO or role enforcement. SAR narratives are drafts; nothing is filed. Do not expose the unauthenticated API publicly.

API implementation references: [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [Claude integration](https://docs.langchain.com/oss/python/integrations/chat/anthropic), [Streamlit fragments](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment).

## Interface design

The black-and-gold console uses prioritized queues, customer context, evidence registers and explicit disposition controls, informed by [NICE Actimize case management](https://www.niceactimize.com/enterprise-risk-case-management) and [Feedzai transaction monitoring](https://www.feedzai.com/solutions/aml-transaction-monitoring/). Colors communicate risk as well as priority; the gold accent is reserved for navigation, primary actions and review state.

## Embedded customer KYC dashboard

The supplied React dashboard is embedded in each investigation's **Customer KYC** tab and available through **Customer profiles**. All AML screens share its black/amber design system. FastAPI serves the dashboard at `http://127.0.0.1:8001/kyc`. Every `/api/customers` request queries RDS; the React app does not read JSON or CSV files.

Install Node.js 24 and npm alongside Python 3.12. On a fresh checkout, `./run.sh serve` installs and builds the KYC frontend automatically. To rebuild after frontend edits:

```bash
npm ci --prefix kyc-dashboard
NODE_DISABLE_COMPILE_CACHE=1 npm run build --prefix kyc-dashboard
```

Restart the Python services after the initial build. Unknown screening, review and balance fields remain unknown; no verification is inferred from missing data. Monthly comparisons exclude the first and last observed months conservatively. The reference dashboard's review-cycle values are demonstration settings, not a bank-approved policy.

Connection failures produce HTTP 503; the dashboard does not substitute local data. Review status (current, due soon, overdue) is calculated in the API by comparing `kyc_next_review_date` with today's date.

Two integration adjustments are retained: the `/kyc-assets/` build path and an explicit unknown PEP state when screening data is absent.
