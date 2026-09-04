"""
app.py
-------
AI Invoice Analyzer -- Streamlit MVP.

Pages (sidebar tabs):
  1. Upload Invoice   -> OCR + review extracted data + save to DB
  2. Dashboard         -> spend analytics (total, monthly, top vendors, top products)
  3. Invoices          -> browse/search stored invoices, view raw OCR text
  4. AI Chatbot         -> ask natural-language questions about the data

Run with:
    streamlit run app.py
"""

import pandas as pd
import plotly.express as px
import streamlit as st

import database as db
import ocr_extractor as ocr
from chatbot import answer_question

st.set_page_config(page_title="AI Invoice Analyzer", page_icon="🧾", layout="wide")
db.init_db()


# --------------------------------------------------------------------------
# Data loading helpers
# --------------------------------------------------------------------------

def load_dataframes():
    invoices = db.get_all_invoices()
    items = db.get_all_line_items()
    inv_df = pd.DataFrame([dict(r) for r in invoices])
    item_df = pd.DataFrame([dict(r) for r in items])
    if not inv_df.empty:
        inv_df["total_amount"] = pd.to_numeric(inv_df["total_amount"], errors="coerce")
        inv_df["invoice_date_parsed"] = pd.to_datetime(inv_df["invoice_date"], errors="coerce")
    return inv_df, item_df


# --------------------------------------------------------------------------
# Sidebar navigation
# --------------------------------------------------------------------------

st.sidebar.title("🧾 AI Invoice Analyzer")
page = st.sidebar.radio(
    "التنقل",
    ["📤 رفع فاتورة", "📊 لوحة التحكم (Dashboard)", "📄 كل الفواتير", "💬 AI Chatbot"],
)

st.sidebar.markdown("---")
st.sidebar.caption(
    "MVP لتحليل الفواتير: OCR لاستخراج البيانات، تخزينها في قاعدة بيانات، "
    "وعرضها في Dashboard مع Chatbot للاستعلام."
)
if st.sidebar.button("🗑️ إعادة ضبط البيانات (Reset demo data)"):
    db.reset_db()
    st.sidebar.success("تم مسح كل البيانات.")
    st.rerun()


# --------------------------------------------------------------------------
# PAGE 1: Upload
# --------------------------------------------------------------------------

if page == "📤 رفع فاتورة":
    st.title("📤 رفع فاتورة جديدة")
    st.write("ارفع فاتورة بصيغة PDF أو صورة (JPG/PNG)، وهيتم استخراج البيانات تلقائيًا عن طريق OCR.")

    uploaded = st.file_uploader(
        "اختر ملف الفاتورة", type=["pdf", "png", "jpg", "jpeg"]
    )

    if uploaded is not None:
        file_bytes = uploaded.read()

        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("معاينة الملف")
            if uploaded.type == "application/pdf":
                st.info("ملف PDF -- ستتم معالجته صفحة بصفحة.")
            else:
                st.image(file_bytes, use_container_width=True)

        with st.spinner("جاري تشغيل OCR واستخراج البيانات..."):
            try:
                extracted = ocr.extract_invoice_data(file_bytes, uploaded.name)
                error = None
            except Exception as e:
                extracted = None
                error = str(e)

        with col2:
            st.subheader("البيانات المستخرجة (قابلة للتعديل)")
            if error:
                st.error(f"حصل خطأ أثناء المعالجة: {error}")
            else:
                inv_number = st.text_input("Invoice Number", value=extracted["invoice_number"] or "")
                inv_date = st.text_input("Date", value=extracted["invoice_date"] or "")
                vendor = st.text_input("Vendor / Supplier", value=extracted["vendor"] or "")
                total = st.number_input(
                    "Total Amount", value=float(extracted["total_amount"] or 0.0), step=0.01
                )

                st.markdown("**Line Items**")
                items_df = pd.DataFrame(extracted["line_items"]) if extracted["line_items"] else pd.DataFrame(
                    columns=["product", "quantity", "unit_price", "line_total"]
                )
                edited_items = st.data_editor(
                    items_df, num_rows="dynamic", use_container_width=True, key="items_editor"
                )

                with st.expander("عرض النص الخام الناتج من OCR"):
                    st.text(extracted["raw_text"] or "(لا يوجد نص مستخرج)")

                if st.button("💾 حفظ الفاتورة في قاعدة البيانات", type="primary"):
                    to_save = {
                        "invoice_number": inv_number,
                        "invoice_date": inv_date,
                        "vendor": vendor,
                        "total_amount": total,
                        "source_file": uploaded.name,
                        "raw_text": extracted["raw_text"],
                        "line_items": edited_items.to_dict(orient="records"),
                    }
                    new_id = db.save_invoice(to_save)
                    st.success(f"تم حفظ الفاتورة بنجاح! (Invoice ID: {new_id})")


# --------------------------------------------------------------------------
# PAGE 2: Dashboard
# --------------------------------------------------------------------------

elif page == "📊 لوحة التحكم (Dashboard)":
    st.title("📊 لوحة التحكم -- تحليل المصروفات")

    inv_df, item_df = load_dataframes()

    if inv_df.empty:
        st.info("لا توجد فواتير مخزّنة بعد. ابدأ برفع فاتورة من صفحة 'رفع فاتورة'.")
    else:
        total_expenses = inv_df["total_amount"].fillna(0).sum()
        n_invoices = len(inv_df)
        n_vendors = inv_df["vendor"].nunique()
        avg_invoice = inv_df["total_amount"].fillna(0).mean()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("إجمالي المصروفات", f"{total_expenses:,.2f}")
        c2.metric("عدد الفواتير", f"{n_invoices}")
        c3.metric("عدد الموردين", f"{n_vendors}")
        c4.metric("متوسط قيمة الفاتورة", f"{avg_invoice:,.2f}")

        st.markdown("---")

        colA, colB = st.columns(2)

        with colA:
            st.subheader("المصروفات حسب الشهر")
            monthly = (
                inv_df.dropna(subset=["invoice_date_parsed"])
                .assign(month=lambda d: d["invoice_date_parsed"].dt.to_period("M").astype(str))
                .groupby("month")["total_amount"].sum().sort_index()
            )
            if not monthly.empty:
                fig = px.bar(x=monthly.index, y=monthly.values,
                             labels={"x": "الشهر", "y": "المصروفات"})
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("لا توجد تواريخ صالحة كافية لعرض الرسم الشهري.")

        with colB:
            st.subheader("أكثر الموردين تعاملًا")
            top_vendors = (
                inv_df.groupby("vendor")["total_amount"].sum()
                .sort_values(ascending=False).head(8)
            )
            if not top_vendors.empty:
                fig = px.bar(x=top_vendors.values, y=top_vendors.index, orientation="h",
                             labels={"x": "إجمالي المصروفات", "y": "المورد"})
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.subheader("أعلى المنتجات/البنود تكلفة")
        if not item_df.empty:
            item_df["line_total"] = pd.to_numeric(item_df["line_total"], errors="coerce")
            top_products = (
                item_df.groupby("product")["line_total"].sum()
                .sort_values(ascending=False).head(10)
            )
            fig = px.bar(x=top_products.index, y=top_products.values,
                         labels={"x": "المنتج", "y": "إجمالي التكلفة"})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("لا توجد بنود/منتجات مسجلة بعد.")


# --------------------------------------------------------------------------
# PAGE 3: Browse invoices
# --------------------------------------------------------------------------

elif page == "📄 كل الفواتير":
    st.title("📄 كل الفواتير")
    inv_df, item_df = load_dataframes()

    if inv_df.empty:
        st.info("لا توجد فواتير مخزّنة بعد.")
    else:
        search = st.text_input("بحث حسب اسم المورد أو رقم الفاتورة")
        display_df = inv_df[["id", "invoice_number", "invoice_date", "vendor", "total_amount", "source_file"]]
        if search:
            mask = (
                display_df["vendor"].fillna("").str.contains(search, case=False)
                | display_df["invoice_number"].fillna("").str.contains(search, case=False)
            )
            display_df = display_df[mask]

        st.dataframe(display_df, use_container_width=True)

        st.markdown("---")
        selected_id = st.selectbox(
            "اختر فاتورة لعرض التفاصيل", options=display_df["id"].tolist() if not display_df.empty else []
        )
        if selected_id:
            invoice, items = db.get_invoice_with_items(int(selected_id))
            st.subheader(f"تفاصيل الفاتورة #{selected_id}")
            st.json({k: invoice[k] for k in invoice.keys() if k != "raw_text"})
            if items:
                st.markdown("**Line Items**")
                st.dataframe(pd.DataFrame([dict(i) for i in items]), use_container_width=True)
            with st.expander("النص الخام (OCR)"):
                st.text(invoice["raw_text"] or "")
            if st.button("🗑️ حذف هذه الفاتورة"):
                db.delete_invoice(int(selected_id))
                st.success("تم الحذف.")
                st.rerun()


# --------------------------------------------------------------------------
# PAGE 4: Chatbot
# --------------------------------------------------------------------------

elif page == "💬 AI Chatbot":
    st.title("💬 اسأل عن بيانات الفواتير")
    inv_df, item_df = load_dataframes()

    st.caption(
        "أمثلة: 'How much did we spend with Nile Office Supplies?' • "
        "'Which month had the highest expenses?' • 'What are the most expensive products?' • "
        "'How many invoices do we have?'"
    )

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for role, msg in st.session_state.chat_history:
        with st.chat_message(role):
            st.markdown(msg)

    question = st.chat_input("اكتب سؤالك هنا...")
    if question:
        st.session_state.chat_history.append(("user", question))
        with st.chat_message("user"):
            st.markdown(question)

        answer = answer_question(question, inv_df, item_df)
        st.session_state.chat_history.append(("assistant", answer))
        with st.chat_message("assistant"):
            st.markdown(answer)
