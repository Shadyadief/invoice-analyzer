# AI Invoice Analyzer -- MVP

Streamlit app to upload invoices (PDF/image), extract structured data via
OCR, store it in a database, view spend analytics on a dashboard, and ask
a simple chatbot questions about the data.

## Features

- **Upload** invoices as PDF, JPG, or PNG.
- **OCR extraction** (Tesseract) of: Invoice Number, Date, Vendor, Line
  Items (Product / Quantity / Unit Price / Line Total), Total Amount.
  Extracted fields are shown in an **editable form** before saving, since
  OCR on varied layouts is never 100% reliable -- you can correct any
  field before it's stored.
- **SQLite database** (`invoices.db`, auto-created) with `invoices` and
  `line_items` tables.
- **Dashboard**: total expenses, monthly expenses chart, top suppliers,
  top-cost products, invoice count, average invoice value.
- **Invoices browser**: search/filter, view raw OCR text, delete records.
- **AI Chatbot**: answers questions like
  - "How much did we spend with Supplier X?"
  - "Which month had the highest expenses?"
  - "What are the most expensive products?"
  - "How many invoices do we have?"

  This runs **rule-based over the stored data by default** (no API key
  needed, works fully offline). If you set an `ANTHROPIC_API_KEY`
  environment variable, free-form questions that don't match a known
  pattern are additionally forwarded to Claude for a more flexible answer
  -- this is an optional upgrade path, not a requirement to run the MVP.

## Project structure

```
invoice_analyzer/
├── app.py                    # Streamlit app (4 pages: Upload, Dashboard, Invoices, Chatbot)
├── ocr_extractor.py          # OCR (Tesseract) + regex/heuristic field extraction
├── database.py               # SQLite schema + read/write helpers
├── chatbot.py                # Rule-based Q&A over the data (+ optional LLM fallback)
├── sample_data_generator.py  # Generates synthetic test invoices (see note below)
├── sample_invoices/          # 6 ready-made synthetic invoice images for testing
├── requirements.txt
└── README.md
```

## Setup

1. Install system dependency (OCR engine) -- Ubuntu/Debian:
   ```bash
   sudo apt-get update && sudo apt-get install -y tesseract-ocr poppler-utils
   ```
   (`poppler-utils` is needed for PDF -> image conversion.)

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the app:
   ```bash
   streamlit run app.py
   ```
   Open the URL Streamlit prints (usually http://localhost:8501).

4. (Optional) Enable the LLM chatbot fallback:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

## Test data / dataset note

The brief asked for a public OCR dataset (e.g. **ICDAR-SROIE**) for
testing. This build environment's network access is restricted to a
fixed allow-list of package registries (PyPI, npm, GitHub, etc.) and does
**not** reach Kaggle or general dataset hosts, so a live SROIE download
wasn't possible here.

To keep the MVP fully testable today, `sample_data_generator.py` produces
6 synthetic invoice images (`sample_invoices/`) with varied vendors, line
items, and totals -- close in structure to a SROIE-style receipt. The OCR
pipeline has been run end-to-end against all 6 and correctly extracts
vendor, date, invoice number, totals, and line items.

**To switch to a real public dataset (recommended next step):** download
SROIE (or any invoice/receipt dataset) locally, e.g. via Kaggle, then
either:
- drop the images into `sample_invoices/` and upload them through the
  app's Upload page, or
- point a small script at the folder and call
  `ocr_extractor.extract_invoice_data()` in a loop to batch-test.

No code changes are needed to use real data -- the pipeline only expects
a PDF/JPG/PNG file's bytes and a filename.

## Known limitations (by design, MVP scope)

- Field extraction uses regex/heuristics, not a trained ML model --
  works well on clean, single-column invoices; may need per-layout tuning
  for heavily irregular formats. This is intentionally an easy piece to
  upgrade later (e.g. swap in an LLM-based extractor without touching
  storage/dashboard/chatbot code).
- Chatbot covers the question types in the brief plus an optional LLM
  fallback; it is not a general-purpose open-domain assistant.
- Single-user local SQLite DB -- fine for an MVP demo, would move to
  Postgres + auth for multi-user/production use.

## Next steps for scaling beyond MVP

- Swap the regex extractor for an LLM-based structured extractor
  (e.g. Claude with a JSON schema) for better accuracy across layouts.
- Move from SQLite to PostgreSQL; add user accounts.
- Add confidence scores and a review queue for low-confidence OCR fields.
- Batch upload + background processing for large volumes.
- Deploy behind proper auth (currently out of scope, as agreed).
