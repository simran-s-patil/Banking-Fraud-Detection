# Project Context

## Title
Banking Transaction and Fraud Detection System — DBMS (CD252IA), RV College of
Engineering, Bengaluru. Team: Sharvani Mysoremath (1RV24CI113), Janvi S Hegde
(1RV24CI145), Simran S Patil (1RV24CI146).

## Purpose
An academic prototype combining a normalized MySQL database with a Python/ML layer
to manage customers, bank accounts and transactions, score transactions for fraud
risk, generate fraud alerts, and support investigation and resolution. Covers two
transaction categories in one common table: Real-Time P2P/UPI transfers and
CNP/e-commerce purchases.

## Scope limitations (hard constraints for every phase)
- Synthetic data only — no real customer or banking data.
- No real banking API integration; no actual money movement.
- Never store full card numbers, CVV, or real banking credentials — CNP card
  references are tokenized.
- A fraud score/alert is a review signal, not proof of fraud (ethical limitation,
  NFR-12).

## Source documents (read in full during Phase 1)
- `docs/Banking_Synopsis.pdf.pdf` — project synopsis, submitted proposal.
- `docs/Banking_ER_Notes.docx.docx` — entities, relationships, recommended FK design.
- `docs/Banking_Requirements.docx.docx` — functional/non-functional requirements,
  acceptance criteria.
- `docs/Banking_Fraud_Detection_DFD.pdf` — Level-1 data flow diagram and field-level
  rules (nullable fields, no real card data).

These four documents are mutually consistent; no conflicts were found between them.

## Technology stack
- **Database:** MySQL 8.x, InnoDB, utf8mb4.
- **Database GUI:** MySQL Workbench.
- **Language:** Python 3.
- **Later phases:** pandas, NumPy, scikit-learn, SQLAlchemy or mysql-connector-python,
  Streamlit, Plotly, joblib.
- Explicitly excluded: MongoDB, PostgreSQL, Firebase, Redis, microservices, or other
  frameworks not listed above.

## Proposed development phases
Phase numbering below is a reasonable project roadmap derived from the tech stack and
the DFD's five processes; it is not dictated verbatim by the source documents, so the
team may adjust it. Current status lives in `docs/PHASE_TRACKER.md`.

1. **Database design & schema** — entities, keys, constraints, master data
   (this phase).
2. **Synthetic data generation** — realistic P2P/UPI and CNP/e-commerce transaction
   volumes, including labeled fraud/legitimate examples.
3. **Feature engineering & EDA** — features per transaction category (amount/time,
   frequency, sender/receiver patterns, merchant category, device/IP/location).
4. **ML model training & evaluation** — Logistic Regression and Random Forest,
   compared via precision, recall, F1-score, confusion matrix.
5. **Fraud-scoring pipeline integration** — write FraudScore/FraudPrediction/
   RiskStatus back to MySQL; define alert-creation logic (trigger or application
   layer) and threshold.
6. **Backend/application layer** — Python + SQLAlchemy or mysql-connector-python CRUD,
   validation (FR-17), transaction retrieval/search (FR-09).
7. **Interface (Streamlit + Plotly)** — monitoring, alert review, investigation
   workflow, basic reporting (FR-18).
8. **Testing, documentation & demo prep** — end-to-end validation against the
   acceptance criteria in `Banking_Requirements.docx`, final report/demo.

## Key functional requirements (see `Banking_Requirements.docx.docx` for full list)
Customer/account/account-type management, P2P and CNP transaction recording with
category-specific fields, transaction search/filtering, ML feature extraction and
fraud prediction storage, configurable-threshold alert generation, alert review, and
investigation tracking (investigator, dates, notes, outcome).

## Non-functional priorities
Data integrity (PK/FK/validation), restricted access to sensitive tables, synthetic
data only, acceptable interactive performance on an academic dataset, documented
reproducibility for the ML pipeline, and auditable timestamps/identifiers throughout.
