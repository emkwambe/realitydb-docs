> **NOTE: Pricing updated July 2026.**
> Current pricing: **Starter $299 / 50 cases**, **Professional $799 / 150 cases**.
> This supersedes earlier pricing in this document — including the pack table
> in section 2 (100 cases / 500 cases) and the pricing page in section 15
> ($1,250 Professional). The tier structure, case anatomy and taxonomy in this
> document are unchanged and remain current.

RealityDB Financial Case Intelligence

The product should not be positioned as “a tool that generates financial PDFs.”

That description makes it sound like a document-template utility.

The stronger product category is:

Production-realistic financial case generation and evaluation infrastructure for lending AI, document intelligence, fraud detection, and underwriting systems.

A case is the commercial unit—not a PDF, page, row, token, or generation prompt.

One case may contain:

loan application
bank statements
pay stubs
W-2
identity document
credit-report summary
vehicle purchase order
insurance evidence
employment verification
structured ground truth
expected underwriting result
deliberately inserted inconsistencies

This matters because financial institutions evaluate identity, employment, income, assets, liabilities, cash flow, and affordability across multiple sources. Current financial-data platforms similarly combine identity, income, assets, liabilities, transactions, statements, and underwriting signals rather than treating each artifact as an isolated file.

1. Recommended product family

I would organize this as a dedicated RealityDB product line:

RealityDB Financial Cases

├── Case Packs
├── Case Studio
├── Case Engine
├── Evaluation Bench
├── Scenario Foundry
└── Private Financial Lab

The products should serve progressively more sophisticated buyers without requiring separate disconnected systems.

2. Product One: Financial Case Packs
Purpose

Ready-made, downloadable collections of internally aligned synthetic lending cases.

These are for teams that need data immediately and do not yet need an API or custom generation.

Initial packs
Auto Loan Underwriting Pack

Each case contains:

auto-loan application
borrower identity profile
two or three bank statements
two pay stubs
W-2
vehicle buyer’s order
proof of insurance
existing liability records
structured truth file
expected underwriting outcome
Income Verification Pack

Designed for:

income extraction
employment matching
annualized-income calculations
gross versus net income comparison
variable-income detection
deposit reconciliation
Document Fraud Pack

Contains controlled anomalies such as:

name mismatch
altered income
duplicate bank statement
inconsistent employer
improbable balances
modified transaction history
altered PDF metadata
incorrect tax calculations
unexplained large deposits
Thin-File and Alternative-Income Pack

Includes:

gig workers
contractors
tipped employees
seasonal workers
self-employed applicants
multiple employers
irregular deposits
limited credit histories
Adverse-Action and Edge-Case Pack

Includes cases around:

high debt-to-income ratio
insufficient verified income
unstable employment
excessive payment-to-income ratio
unverifiable identity
inconsistent documentation
insufficient down payment
conditional approval
What every case must include

Each case should ship as:

case-000184/
├── documents/
│   ├── application.pdf
│   ├── bank_statement_oct.pdf
│   ├── bank_statement_nov.pdf
│   ├── paystub_01.pdf
│   ├── paystub_02.pdf
│   ├── w2.pdf
│   ├── buyers_order.pdf
│   └── insurance.pdf
│
├── truth/
│   ├── borrower.json
│   ├── employment.json
│   ├── income.json
│   ├── liabilities.json
│   ├── vehicle.json
│   └── case_manifest.json
│
├── evaluation/
│   ├── expected_extractions.json
│   ├── alignment_matrix.json
│   ├── anomaly_labels.json
│   └── expected_decision.json
│
└── README.md

The truth and evaluation layers are what make this more valuable than generic synthetic PDFs.

Proposed pack pricing
Pack    Cases    Documents    Price
Sample Pack    10    60–100    Free
Starter Pack    100    600–1,000    $299
Professional Pack    500    3,000–5,000    $1,250
Team Pack    2,500    15,000–25,000    $4,500
Enterprise Dataset    10,000+    Configurable    From $15,000

These should be perpetual-download licenses for internal development and testing.

Do not charge by PDF page. Page pricing makes buyers worry about output mechanics rather than business value.

3. Product Two: Case Studio
Purpose

A browser-based visual interface where analysts, QA engineers, product teams, and model evaluators can generate cases without writing code.

Core workflow
Choose lending scenario
        ↓
Configure borrower profile
        ↓
Configure financial behavior
        ↓
Choose document bundle
        ↓
Choose alignment level
        ↓
Generate case
        ↓
Inspect documents and truth
        ↓
Download or send to evaluation
Important controls
Borrower controls
age range
location
employment type
occupation
income range
credit tier
residence type
dependents
employment tenure
Loan controls
vehicle price
down payment
trade-in value
loan amount
term
interest rate
new versus used vehicle
dealer versus direct lending
Financial controls
monthly gross income
net payroll amount
recurring obligations
average account balance
cash-flow volatility
overdraft frequency
debt-to-income ratio
payment-to-income ratio
Alignment controls

This should be one of the distinguishing features.

Alignment mode

● Fully aligned
○ Naturally noisy
○ Manual-review case
○ Fraud-injected
○ Custom inconsistencies

The user should also be able to choose exact mismatch types.

☑ Employer-name variation
☑ Income overstatement
☐ Identity mismatch
☑ Undisclosed debt
☐ Altered account balance
☐ Duplicate document
Proposed Studio pricing
Plan    Monthly price    Included cases    Primary user
Explorer    Free    10/month    Evaluation and discovery
Builder    $79/month    250/month    Individual engineer
Team    $299/month    1,500/month    Small product or QA team
Business    $899/month    6,000/month    Fintech or document-AI team
Enterprise    Custom    Pooled/custom    Regulated institution

Additional case generation:

Builder: $0.40 per additional case
Team: $0.25 per additional case
Business: $0.15 per additional case

A case should have a reasonable included document limit, perhaps up to 12 documents. Very large bundles can consume more than one case credit.

A nearby market pattern is to offer a low-friction free tier, a modest paid self-service tier, and custom enterprise contracts. For example, Tonic’s current synthetic-generation product offers free access, a $29 individual plan, usage-based expansion, and custom enterprise deployment and governance.

RealityDB should be priced higher than a generic generation chat tool because it supplies domain logic, cross-document consistency, labels, expected outcomes, and financial-case validation.

4. Product Three: Case Engine
Purpose

Programmatic generation through CLI, SDK, and API.

This is the primary product for engineering teams.

Access methods
CLI
realitydb finance case generate \
  --product auto-loan \
  --scenario stable-prime \
  --cases 100 \
  --documents application,bank,w2,paystub,buyers-order \
  --alignment fully-aligned \
  --format bundle

Intentional mismatch:

realitydb finance case generate \
  --product auto-loan \
  --scenario income-inflation \
  --cases 250 \
  --inject employer-mismatch,income-overstatement \
  --severity medium

Evaluation dataset:

realitydb finance benchmark create \
  --task cross-document-validation \
  --cases 1000 \
  --difficulty mixed \
  --output s3://company-evaluation-bucket
REST API
POST /v1/financial-cases
{
  "product": "auto_loan",
  "count": 100,
  "scenario": "stable_prime",
  "documents": [
    "loan_application",
    "bank_statement",
    "paystub",
    "w2",
    "buyers_order"
  ],
  "alignment": {
    "mode": "controlled_noise",
    "severity": "low"
  },
  "seed": 48291
}
SDKs

Start with:

Python
TypeScript

Add Java later because many large financial institutions use JVM environments.

Engine pricing

I recommend case credits, not tokens.

Tokens are understandable to AI-platform builders but poorly aligned with how banks, QA teams, and underwriting vendors budget. Tonic currently meters some synthetic generation using underlying model tokens and credits, while Plaid uses product-dependent one-time, subscription, and per-request models.

RealityDB should simplify this into one customer-facing unit:

One case credit produces one complete borrower case with up to a defined number of documents and its ground truth.

API plans
Plan    Monthly price    Cases/month    Effective included price
Developer    $149    500    $0.30
Team API    $599    3,000    $0.20
Scale    $1,999    15,000    $0.13
Enterprise    Custom    50,000+    Negotiated

Overages should decline by volume.

Monthly volume    Suggested price per case
1–1,000    $0.35
1,001–10,000    $0.20
10,001–100,000    $0.10
100,001+    Custom

Do not make every document a separate API charge. It would discourage complete case generation and create unpredictable invoices.

5. Product Four: Evaluation Bench

This may become the most defensible product.

Purpose

Evaluate whether a document AI, OCR system, lending agent, or underwriting workflow correctly understands complete financial cases.

Generation alone creates test inputs.

Evaluation Bench creates measurable evidence.

Evaluation tasks
Document classification

Did the system correctly recognize:

W-2
pay stub
bank statement
application
identity document
buyer’s order
Field extraction

Did it extract:

borrower name
employer
wages
account balance
liabilities
payment amount
vehicle price
Entity resolution

Did it understand that:

Northwind Trading LLC
Northwind Traders
NORTHWIND TRADING PAYROLL

may refer to the same employer?

Cross-document consistency

Did it detect:

applicant-name conflict
employer mismatch
unsupported declared income
undeclared recurring liability
inconsistent address
bank balance discrepancy
Financial reasoning

Did it calculate:

monthly gross income
annualized income
debt-to-income ratio
payment-to-income ratio
verified cash reserves
recurring obligations
average monthly inflow
income stability
Decision evaluation

Did the system produce the expected:

approve
decline
conditional approval
manual review
request for documentation
Explanation evaluation

Did it cite the correct evidence and avoid unsupported conclusions?

Metrics

Evaluation Bench should report:

Document Classification Accuracy
Field-Level Precision / Recall / F1
Exact Match Rate
Normalized Match Rate
Entity Resolution Accuracy
Cross-Document Contradiction Recall
False-Flag Rate
Financial Calculation Accuracy
Decision Agreement
Evidence Citation Accuracy
Unsupported Claim Rate
Latency
Cost per Case
Proposed pricing
Plan    Price    Evaluations/month
Evaluator    $249/month    2,000
Team Bench    $999/month    15,000
Scale Bench    $3,500/month    75,000
Enterprise    Custom    Custom

An evaluation means submitting one model or workflow result against one case.

Charge separately for hosted model execution only when RealityDB itself calls an external model. Allow customers to bring their own API keys to avoid markup and security concerns.

6. Product Five: Scenario Foundry
Purpose

Custom financial scenario and document-pack development for institutions with proprietary workflows.

This is the service-led enterprise offering.

What the customer supplies

They may provide:

field schema
blank templates
underwriting rules
document taxonomy
desired borrower segments
fraud scenarios
model-input requirements
output format
evaluation rubric

They should not need to provide production customer data.

What RealityDB delivers
canonical case schema
document templates
financial-behavior model
alignment rules
anomaly taxonomy
initial sample cases
validation report
production dataset
CLI/API configuration
documentation
reproducibility manifest

A comparable enterprise delivery pattern is to begin with requirements, create a representative sample, obtain sign-off, run a pilot, and then complete full deployment. Tonic describes a similar staged process for custom synthetic datasets.

Proposed service pricing
Template adaptation

Existing RealityDB case model, customer-specific appearance or fields:

$5,000–$12,000
Custom scenario pack

New underwriting scenario with existing document types:

$12,000–$30,000
Custom document family

New document type, renderer, extraction schema, and validation rules:

$15,000–$40,000 per family
Full lending implementation

Custom case model, documents, scenarios, evaluation suite, and API delivery:

$50,000–$150,000
Strategic enterprise engagement

Multiple lending products, private deployment, governance, and integration:

$150,000–$500,000+

Do not price custom work only by number of generated cases. The difficult work is designing the domain model, alignment constraints, exception taxonomy, renderers, and evaluators.

7. Product Six: Private Financial Lab
Purpose

A private or self-hosted environment for banks, credit unions, regulated fintechs, and large lending vendors.

Deployment choices
RealityDB Cloud

Best for:

pilots
fintech startups
document-AI vendors
evaluation teams
Single-tenant managed cloud

Best for:

regulated organizations
stricter segregation requirements
custom retention policies
Customer VPC

RealityDB deploys into the customer’s cloud account.

Best for:

sensitive schemas
proprietary underwriting rules
internal-only evaluation
Fully self-hosted

Best for:

institutions that cannot allow prompts, templates, or outputs to leave their environment
offline or restricted networks
model evaluation involving confidential systems

Enterprise synthetic-data products commonly distinguish hosted from self-hosted deployment and add SSO, RBAC, dedicated support, and contractual controls at the enterprise tier.

Proposed annual pricing
Deployment    Annual platform price
Single-tenant cloud    From $30,000
Customer VPC    From $60,000
Self-hosted    From $90,000
Multi-business-unit enterprise    From $150,000

Implementation:

standard onboarding: $10,000–$25,000
custom integration: $25,000–$100,000
premium support: 15%–20% of annual contract
8. The case taxonomy

The product needs a disciplined scenario library.

Alignment classes
A0: Perfectly aligned

Every material value reconciles.

Used for:

OCR testing
extraction baselines
happy-path workflow testing
A1: Benign variation

Examples:

employer-name abbreviation
address formatting differences
rounding differences
payroll description variation
delayed deposit date

Used to test tolerance.

A2: Explainable discrepancy

Examples:

recent move
employer changed during the year
bonus included in W-2
joint bank account
inconsistent pay periods
legitimate transfer between accounts

Used to test contextual reasoning.

A3: Material inconsistency

Examples:

declared income unsupported
recurring debt omitted
employer conflict
down payment unavailable
unexplained large deposits

Used to test manual-review detection.

A4: Probable manipulation

Examples:

altered wage amount
modified balance
reused document
impossible tax relationship
transaction arithmetic failure
metadata inconsistency

Used for fraud detection.

A5: Coordinated synthetic fraud

Multiple documents support a false story but contain subtle shared defects.

Used for advanced fraud and agent evaluation.

This creates a clear progression from simple document extraction to complex adversarial reasoning.

9. Every case needs two truth layers
Layer One: World truth

What is actually true about the borrower?

{
  "borrower_id": "bor_48291",
  "name": "Susan Johnson",
  "employer": "Northwind Traders",
  "gross_monthly_income": 7203,
  "monthly_debt": 1120,
  "verified_assets": 29885.62
}
Layer Two: Document truth

What does each document claim?

{
  "loan_application": {
    "gross_monthly_income": 8500
  },
  "w2": {
    "annual_wages": 85668.34
  },
  "bank_statements": {
    "average_monthly_payroll": 7304.76
  }
}

The difference between world truth and document truth allows RealityDB to represent:

honest mistakes
outdated documents
omitted liabilities
manipulated documents
fraud
ambiguity

Without both layers, the system can only say whether fields match. It cannot say which source is correct.

10. Smooth access and delivery strategy

The user should be able to start at four levels.

Level 1: Preview without registration

On the website:

open one sample case
flip between documents
view the alignment graph
see detected inconsistencies
inspect the expected underwriting outcome

This communicates the product faster than a long landing page.

Level 2: Free account

The user receives:

10 complete cases monthly
one standard auto-loan pack
JSON ground truth
browser downloads
basic evaluation results
no credit card
Level 3: Self-service purchase

The user can:

buy a fixed pack
subscribe to Studio
generate cases immediately
download ZIP, JSONL, CSV, PDF, or Parquet
obtain API credentials
view usage
regenerate deterministically using a seed

Avoid requiring a sales call for anything below enterprise deployment.

Plaid, for example, provides sandbox and trial access before larger custom arrangements, while enterprise-scale products add volume pricing, support, and integration assistance.

Level 4: Enterprise workflow
Discovery
   ↓
Sample specification
   ↓
10-case proof
   ↓
100-case pilot
   ↓
Acceptance testing
   ↓
Production contract
   ↓
Ongoing generation/evaluation

The pilot should be paid but creditable toward the annual contract.

Suggested pilot:

500–2,000 cases
one lending product
three to six document types
two custom scenarios
evaluation report
30-day access

Price:

$7,500–$20,000

Credit 50%–100% against an annual enterprise agreement signed within 60 days.

11. Delivery formats

Support the workflow in which the customer already operates.

Human-friendly
ZIP
individual PDF
case viewer
downloadable report
Data-science friendly
JSONL
CSV
Parquet
Hugging Face-style dataset structure
Python dataset loader
Engineering friendly
REST API
Python SDK
TypeScript SDK
CLI
webhook when batch completes
Enterprise infrastructure
Amazon S3
Azure Blob Storage
Google Cloud Storage
Snowflake stage
PostgreSQL
secure file transfer
customer VPC bucket
Evaluation integrations

Later:

MLflow
LangSmith
Langfuse
OpenAI Evals-compatible exports
custom CI/CD test runner
GitHub Actions
12. Licensing

Keep the license easy to understand.

Standard internal-use license

Permits:

software development
QA
model training
internal evaluation
demonstrations
internal research

Prohibits:

representing documents as authentic
using synthetic identities to apply for real credit
resale of the raw dataset
removal of synthetic markings for deceptive purposes
Commercial model license

For customers embedding models trained using the data into a commercial product.

Suggested premium:

1.5× the pack price, or
included in Business and Enterprise subscriptions
Redistribution license

For vendors that need to include synthetic samples in their own test environment.

Custom pricing only.

13. Safety and anti-misuse design

Financial documents are inherently dual-use. RealityDB should make them useful for testing while difficult to misuse.

Every generated document should contain:

visible “SYNTHETIC — NOT VALID” marking
persistent footer
reserved synthetic SSNs and identifiers
invalid or controlled routing/account numbers
embedded cryptographic provenance
PDF metadata identifying RealityDB generation
case ID
generation timestamp
machine-readable watermark
optional QR verification endpoint

Enterprise customers may need visually clean documents for OCR testing. In that case, the visible watermark could be configurable, but invisible provenance and non-actionable identifiers should remain mandatory.

14. Recommended launch sequence

Do not launch all six products simultaneously.

Phase 1: Sellable foundation

Launch:

Auto Loan Case Pack
Case Studio
CLI generation
canonical case manifest
three alignment levels
downloadable ground truth

This creates immediate revenue.

Initial public offer
RealityDB Auto Loan Case Pack

100 complete synthetic borrower cases
700+ financial documents
Structured ground truth
Cross-document alignment labels
Expected underwriting decisions

$299
Phase 2: Engineering adoption

Add:

API
Python SDK
batch generation
custom seeds
object-storage delivery
subscription plans
Phase 3: Evaluation moat

Add:

Evaluation Bench
model comparison
contradiction detection metrics
financial-calculation scoring
CI integration
Phase 4: Enterprise expansion

Add:

customer VPC
self-hosted deployment
custom templates
Scenario Foundry
governance and approval workflows
15. The strongest initial pricing page

I would make the public pricing page extremely simple.

Datasets

Starter Case Pack — $299 one time

100 aligned and misaligned cases
600–1,000 PDFs
ground truth
anomaly labels
expected decisions

Professional Case Pack — $1,250 one time

500 cases
broader borrower segments
controlled fraud scenarios
commercial model-training rights
Platform

Builder — $79/month

250 generated cases
Case Studio
CLI
PDF and JSON exports

Team — $299/month

1,500 cases
API
five users
shared workspaces
evaluation reports

Business — $899/month

6,000 cases
20 users
advanced scenarios
S3 delivery
priority support

Enterprise — Custom

private deployment
custom document templates
SSO and RBAC
custom scenario engineering
volume generation
dedicated support

This gives the buyer three simple ways to engage:

Download a dataset
Generate cases continuously
Build a private institutional solution
16. The core positioning

Do not say:

Generate realistic bank statements, W-2s, and loan applications.

Say:

Generate complete, production-realistic lending cases in which identity, income, assets, liabilities, transactions, and documents align—or fail to align in controlled, measurable ways.

And the strongest concise message is:

Test whether your lending AI understands the borrower, not just the PDF.

That is the product boundary separating RealityDB from generic document generators.
