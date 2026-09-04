"""
chatbot.py
-----------
A lightweight Q&A layer over the invoices/line_items data.

Two modes:
  1. Rule-based (default, no API key needed) -- covers the exact question
     types requested in the brief (spend by supplier, highest-expense month,
     most expensive products, invoice counts, etc.) using pandas.
  2. Optional LLM mode -- if an Anthropic API key is available in the
     environment (ANTHROPIC_API_KEY), free-form questions that don't match
     a known pattern are forwarded to Claude along with a compact summary
     of the data as context. This keeps the MVP fully functional offline
     while leaving a clean upgrade path to a "real" AI chatbot.
"""

import os
import re

import pandas as pd


def _month_name(period):
    return period.strftime("%B %Y")


def answer_question(question: str, invoices_df: pd.DataFrame, items_df: pd.DataFrame) -> str:
    """
    Route a natural-language question to the right handler.
    invoices_df columns: id, invoice_number, invoice_date, vendor,
                          total_amount, source_file, raw_text, created_at
    items_df columns:    id, invoice_id, product, quantity, unit_price, line_total
    """
    q = question.strip().lower()

    if invoices_df.empty:
        return "لا يوجد فواتير مخزّنة بعد. من فضلك ارفع فاتورة أولاً."

    # --- spend with a specific supplier -----------------------------------
    m = re.search(r"(?:spend|spent|total).{0,15}(?:with|on|from)\s+([a-zA-Z0-9 &\-']{2,40})", q)
    if m or "supplier" in q or "vendor" in q or "مورد" in question:
        vendor_guess = m.group(1).strip() if m else None
        if vendor_guess:
            mask = invoices_df["vendor"].fillna("").str.lower().str.contains(re.escape(vendor_guess))
            subset = invoices_df[mask]
            if not subset.empty:
                total = subset["total_amount"].fillna(0).sum()
                return f"إجمالي المصروفات مع '{vendor_guess}': {total:,.2f}"
        # fallback: show top suppliers
        top = (invoices_df.groupby("vendor")["total_amount"]
               .sum().sort_values(ascending=False).head(5))
        lines = "\n".join(f"- {v}: {t:,.2f}" for v, t in top.items())
        return f"أكثر الموردين تعاملاً حسب إجمالي المبالغ:\n{lines}"

    # --- highest expense month ---------------------------------------------
    if ("highest" in q and "month" in q) or "أعلى شهر" in question or "أكثر شهر" in question:
        df = invoices_df.dropna(subset=["invoice_date"]).copy()
        if df.empty:
            return "لا توجد تواريخ كافية لتحديد الشهر الأعلى في المصروفات."
        df["period"] = pd.to_datetime(df["invoice_date"], errors="coerce").dt.to_period("M")
        monthly = df.dropna(subset=["period"]).groupby("period")["total_amount"].sum()
        if monthly.empty:
            return "لا توجد تواريخ صالحة لتحليل المصروفات الشهرية."
        best = monthly.idxmax()
        return f"أعلى شهر في المصروفات هو {_month_name(best)} بإجمالي {monthly[best]:,.2f}"

    # --- most expensive products --------------------------------------------
    if ("expensive" in q and "product" in q) or "أغلى" in question or "أعلى منتج" in question:
        if items_df.empty:
            return "لا توجد بنود/منتجات مسجلة بعد."
        top = (items_df.groupby("product")["line_total"]
               .sum().sort_values(ascending=False).head(5))
        lines = "\n".join(f"- {p}: {t:,.2f}" for p, t in top.items())
        return f"أعلى المنتجات تكلفة:\n{lines}"

    # --- how many invoices ---------------------------------------------------
    if ("how many" in q and "invoice" in q) or "عدد الفواتير" in question or "كام فاتورة" in question:
        return f"عدد الفواتير المسجلة: {len(invoices_df)}"

    # --- total expenses overall ----------------------------------------------
    if "total" in q and ("expense" in q or "spend" in q) or "إجمالي المصروفات" in question:
        return f"إجمالي المصروفات الكلي: {invoices_df['total_amount'].fillna(0).sum():,.2f}"

    # --- fallback: try LLM if a key is configured, else a helpful default ----
    llm_answer = _try_llm_fallback(question, invoices_df, items_df)
    if llm_answer:
        return llm_answer

    return (
        "معنديش إجابة جاهزة لهذا السؤال بالضبط. جرّب تسأل بصيغة زي:\n"
        "- How much did we spend with <Supplier>?\n"
        "- Which month had the highest expenses?\n"
        "- What are the most expensive products?\n"
        "- How many invoices do we have?"
    )


def _try_llm_fallback(question, invoices_df, items_df):
    """
    Optional: if ANTHROPIC_API_KEY is set in the environment, ask Claude to
    answer the free-form question using a small textual summary of the data
    as context. Returns None (silently) if no key is configured or the call
    fails, so the app keeps working without any external dependency.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        summary_df = invoices_df[["vendor", "invoice_date", "total_amount"]].copy()
        summary = summary_df.to_csv(index=False)

        prompt = (
            "You are an assistant answering questions about a company's invoices. "
            "Here is a CSV summary of invoices (vendor, date, total_amount):\n\n"
            f"{summary}\n\n"
            f"Question: {question}\n"
            "Answer concisely in the same language as the question."
        )
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if hasattr(b, "text"))
    except Exception:
        return None
