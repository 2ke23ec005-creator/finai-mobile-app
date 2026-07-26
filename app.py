import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import json
import re
import pandas as pd
from PIL import Image
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from groq import Groq

# ReportLab PDF Imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# -----------------------------------------------------------------------------
# 1. Page Configuration & Mobile UI Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="FinAI Mobile App",
    page_icon="📱",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}

    .block-container {
        max-width: 580px !important;
        padding-top: 1rem !important;
        padding-bottom: 4rem !important;
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
        margin: 0 auto;
    }

    .app-header {
        background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
        color: white;
        padding: 16px;
        border-radius: 16px;
        text-align: center;
        margin-bottom: 16px;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
    }
    .app-header h2 {
        color: white !important;
        margin: 0;
        font-size: 1.4rem;
        font-weight: 700;
    }
    .app-header p {
        margin: 4px 0 0 0;
        font-size: 0.8rem;
        opacity: 0.9;
    }

    div.stButton > button {
        width: 100% !important;
        border-radius: 12px !important;
        height: 2.8rem !important;
        font-weight: 600 !important;
        border: none !important;
    }

    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
        color: white !important;
    }

    [data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        padding: 12px;
        border-radius: 14px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.02);
    }

    .score-card {
        background: #ffffff;
        border-radius: 16px;
        padding: 20px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
        text-align: center;
        margin-bottom: 16px;
    }
    
    .score-number {
        font-size: 2.8rem;
        font-weight: 800;
        line-height: 1;
        margin: 6px 0;
    }

    .feature-card {
        background-color: #f8fafc;
        border-left: 4px solid #2563eb;
        padding: 12px;
        border-radius: 8px;
        margin-bottom: 8px;
        font-size: 0.85rem;
    }

    .action-card {
        background-color: #f0fdf4;
        border-left: 4px solid #16a34a;
        padding: 12px;
        border-radius: 8px;
        margin-bottom: 8px;
        font-size: 0.85rem;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 12px;
        font-size: 0.85rem;
        border-radius: 8px;
    }
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# 2. Numbered Canvas for PDF Generation
# -----------------------------------------------------------------------------
class NumberedCanvas(canvas.Canvas):

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._saved_page_states = []

  def showPage(self):
    self._saved_page_states.append(dict(self.__dict__))
    self._startPage()

  def save(self):
    num_pages = len(self._saved_page_states)
    for state in self._saved_page_states:
      self.__dict__.update(state)
      self.draw_header_footer(num_pages)
      super().showPage()
    super().save()

  def draw_header_footer(self, page_count):
    self.saveState()
    self.setFont("Helvetica-Bold", 8)
    self.setFillColor(colors.HexColor("#64748b"))
    self.drawString(
        36, 762, "CONFIDENTIAL | PERSONAL FINANCIAL HEALTH & AUDIT REPORT"
    )
    self.setStrokeColor(colors.HexColor("#cbd5e1"))
    self.setLineWidth(0.5)
    self.line(36, 754, 576, 754)

    self.setFont("Helvetica", 8)
    self.drawString(36, 25, "Generated via AI Financial Mobile App")
    page_str = f"Page {self._pageNumber} of {page_count}"
    self.drawRightString(576, 25, page_str)
    self.line(36, 35, 576, 35)
    self.restoreState()


# -----------------------------------------------------------------------------
# 3. PDF Generator Function
# -----------------------------------------------------------------------------
def generate_detailed_pdf_report(
    income,
    expenses,
    savings_goal,
    remaining_balance,
    cat_totals,
    sip_inputs,
    sip_schedule_df,
    transactions_df=None,
    ai_json=None,
):
  buffer = io.BytesIO()
  doc = SimpleDocTemplate(
      buffer,
      pagesize=letter,
      rightMargin=36,
      leftMargin=36,
      topMargin=54,
      bottomMargin=54,
  )

  story = []
  styles = getSampleStyleSheet()

  NAVY = colors.HexColor("#0f172a")
  BLUE_HEADER = colors.HexColor("#1e3a8a")
  SLATE = colors.HexColor("#475569")
  EMERALD = colors.HexColor("#059669")
  BG_LIGHT = colors.HexColor("#f8fafc")
  BORDER_COLOR = colors.HexColor("#cbd5e1")

  title_style = ParagraphStyle(
      "DocTitle",
      parent=styles["Heading1"],
      fontSize=15,
      leading=18,
      textColor=NAVY,
  )
  subtitle_style = ParagraphStyle(
      "DocSubtitle",
      parent=styles["Normal"],
      fontSize=8,
      leading=10,
      textColor=SLATE,
      spaceAfter=8,
  )
  section_heading = ParagraphStyle(
      "SectionHeading",
      parent=styles["Heading2"],
      fontSize=10,
      leading=13,
      textColor=BLUE_HEADER,
      spaceBefore=8,
      spaceAfter=4,
  )
  body_style = ParagraphStyle(
      "BodyCustom",
      parent=styles["Normal"],
      fontSize=8,
      leading=10,
      textColor=NAVY,
  )
  body_bold = ParagraphStyle(
      "BodyCustomBold",
      parent=styles["Normal"],
      fontSize=8,
      leading=10,
      textColor=NAVY,
      fontName="Helvetica-Bold",
  )

  story.append(Paragraph("AI PERSONAL FINANCIAL AUDIT REPORT", title_style))
  story.append(
      Paragraph(
          "Automated Expense Classification & Financial Growth Statement",
          subtitle_style,
      )
  )
  story.append(
      HRFlowable(
          width="100%", thickness=1.5, color=NAVY, spaceAfter=8, spaceBefore=0
      )
  )

  story.append(Paragraph("1. Executive Summary & Core Metrics", section_heading))
  savings_ratio = (
      max(0.0, remaining_balance) / income * 100 if income > 0 else 0
  )
  expense_ratio = (expenses / income * 100) if income > 0 else 0

  exec_data = [
      [
          Paragraph("Monthly Net Income:", body_bold),
          Paragraph(f"₹{income:,.2f}", body_style),
          Paragraph("Savings Ratio:", body_bold),
          Paragraph(f"{savings_ratio:.1f}%", body_style),
      ],
      [
          Paragraph("Total Monthly Spending:", body_bold),
          Paragraph(f"₹{expenses:,.2f}", body_style),
          Paragraph("Expense-to-Income Ratio:", body_bold),
          Paragraph(f"{expense_ratio:.1f}%", body_style),
      ],
      [
          Paragraph("Target Savings Goal:", body_bold),
          Paragraph(f"₹{savings_goal:,.2f}", body_style),
          Paragraph("Net Balance / Surplus:", body_bold),
          Paragraph(f"₹{remaining_balance:,.2f}", body_style),
      ],
  ]

  t_exec = Table(exec_data, colWidths=[130, 120, 140, 110])
  t_exec.setStyle(
      TableStyle([
          ("BACKGROUND", (0, 0), (-1, -1), BG_LIGHT),
          ("BOX", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
          ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
          ("PADDING", (0, 0), (-1, -1), 4),
      ])
  )
  story.append(t_exec)
  story.append(Spacer(1, 8))

  if ai_json:
    score = ai_json.get("health_score", "N/A")
    status = ai_json.get("score_status", "Evaluated")
    summary_text = ai_json.get("executive_summary", "")

    score_data = [[
        Paragraph(
            f"<b>Financial Health Score:</b> <font color='{EMERALD.hexval()}'>"
            f"<b>{score}/100</b></font><br/>Status: <b>{status}</b>",
            body_style,
        ),
        Paragraph(f"<b>AI Diagnostic Summary:</b><br/>{summary_text}", body_style),
    ]]
    t_score = Table(score_data, colWidths=[150, 350])
    t_score.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdf4")),
            ("BOX", (0, 0), (-1, -1), 0.5, EMERALD),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    story.append(t_score)
    story.append(Spacer(1, 8))

  story.append(Paragraph("2. Expense Category Breakdown", section_heading))
  exp_rows = [[
      Paragraph("<b>Category</b>", body_style),
      Paragraph("<b>Monthly (₹)</b>", body_style),
      Paragraph("<b>Annualized (₹)</b>", body_style),
      Paragraph("<b>% Share</b>", body_style),
  ]]

  for cat, amt in cat_totals.items():
    if amt > 0:
      pct = (amt / income * 100) if income > 0 else 0
      exp_rows.append([
          Paragraph(cat, body_style),
          Paragraph(f"₹{amt:,.2f}", body_style),
          Paragraph(f"₹{(amt * 12):,.2f}", body_style),
          Paragraph(f"{pct:.1f}%", body_style),
      ])

  t_exp = Table(exp_rows, colWidths=[180, 110, 110, 100])
  t_exp.setStyle(
      TableStyle([
          ("BACKGROUND", (0, 0), (-1, 0), BG_LIGHT),
          ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
          ("PADDING", (0, 0), (-1, -1), 4),
      ])
  )
  story.append(t_exp)
  story.append(Spacer(1, 8))

  if transactions_df is not None and not transactions_df.empty:
    story.append(
        Paragraph("3. Transaction Audit Ledger (Automated Inputs)", section_heading)
    )
    tx_rows = [[
        Paragraph("<b>Date</b>", body_style),
        Paragraph("<b>Description / Merchant</b>", body_style),
        Paragraph("<b>Category</b>", body_style),
        Paragraph("<b>Amount (₹)</b>", body_style),
    ]]
    for _, tx in transactions_df.head(15).iterrows():
      tx_rows.append([
          Paragraph(str(tx.get("Date", "N/A")), body_style),
          Paragraph(str(tx.get("Description", "N/A"))[:28], body_style),
          Paragraph(str(tx.get("Category", "Other")), body_style),
          Paragraph(f"₹{float(tx.get('Amount', 0.0)):,.2f}", body_style),
      ])
    t_tx = Table(tx_rows, colWidths=[80, 180, 130, 110])
    t_tx.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BG_LIGHT),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ("PADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(t_tx)

  doc.build(story, canvasmaker=NumberedCanvas)
  buffer.seek(0)
  return buffer.getvalue()


# -----------------------------------------------------------------------------
# 4. Ultra-Fast Image Compressor & Vision AI Functions
# -----------------------------------------------------------------------------
def compress_image_for_ocr(image_bytes, max_dim=1024, quality=80):
  """Resizes camera photos to ~150KB for fast 1-second Vision AI calls."""
  try:
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode in ("RGBA", "P"):
      img = img.convert("RGB")

    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    out_buf = io.BytesIO()
    img.save(out_buf, format="JPEG", quality=quality)
    return out_buf.getvalue()
  except Exception:
    return image_bytes


def scan_receipt_with_vision(
    image_bytes,
    image_type,
    api_key,
    model_name="llama-3.2-11b-vision-preview",
):
  client = Groq(api_key=api_key)
  compressed_bytes = compress_image_for_ocr(image_bytes)
  base64_image = base64.b64encode(compressed_bytes).decode("utf-8")

  prompt = """
    Extract details from this receipt/bill image into a JSON object:
    {
      "Date": "YYYY-MM-DD",
      "Description": "Merchant or Store Name",
      "Category": "One of: Housing / Rent, Groceries & Food, Transportation, Utilities & Bills, Shopping, Entertainment, Miscellaneous / Other",
      "Amount": 0.0,
      "Tax_Amount": 0.0,
      "Payment_Method": "Card / UPI / Cash / NetBanking / Unknown",
      "Confidence": "High / Medium / Low",
      "Summary_Items": "Brief item list summary"
    }
    Return ONLY raw JSON.
    """

  response = client.chat.completions.create(
      model=model_name,
      messages=[{
          "role": "user",
          "content": [
              {"type": "text", "text": prompt},
              {
                  "type": "image_url",
                  "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
              },
          ],
      }],
      temperature=0.1,
      response_format={"type": "json_object"},
  )

  raw = response.choices[0].message.content
  cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
  match = re.search(r"\{.*\}", cleaned, re.DOTALL)

  if match:
    return json.loads(match.group(0))
  return json.loads(cleaned)


def scan_single_file(file_obj, api_key):
  """Wrapper that processes both uploaded files and live camera photos."""
  try:
    img_bytes = file_obj.getvalue()
    img_ext = getattr(file_obj, "type", "image/jpeg")
    img_ext = "png" if "png" in str(img_ext).lower() else "jpeg"
    file_name = getattr(file_obj, "name", "live_camera_capture.jpg")

    try:
      parsed = scan_receipt_with_vision(
          img_bytes, img_ext, api_key, "llama-3.2-11b-vision-preview"
      )
    except Exception:
      parsed = scan_receipt_with_vision(
          img_bytes, img_ext, api_key, "llama-3.2-90b-vision-preview"
      )

    return {"success": True, "file_name": file_name, "data": parsed}
  except Exception as e:
    return {
        "success": False,
        "file_name": getattr(file_obj, "name", "photo"),
        "error": str(e),
    }


# -----------------------------------------------------------------------------
# 5. Session State Initialization
# -----------------------------------------------------------------------------
if "df_raw" not in st.session_state:
  st.session_state.df_raw = None
if "categorized_df" not in st.session_state:
  st.session_state.categorized_df = None
if "active_demo_label" not in st.session_state:
  st.session_state.active_demo_label = ""
if "ai_json" not in st.session_state:
  st.session_state.ai_json = None
if "scanned_receipts" not in st.session_state:
  st.session_state.scanned_receipts = []

CATEGORIES = [
    "Housing / Rent",
    "Groceries & Food",
    "Transportation",
    "Utilities & Bills",
    "Shopping",
    "Entertainment",
    "Miscellaneous / Other",
]

# -----------------------------------------------------------------------------
# 6. Mobile App UI Header & Budget Inputs
# -----------------------------------------------------------------------------
st.markdown(
    """
<div class="app-header">
    <h2>📱 FinAI Mobile</h2>
    <p>Smart Expense Tracking & Wealth Intelligence</p>
</div>
""",
    unsafe_allow_html=True,
)

with st.expander("🔑 App Settings & Groq API Key"):
  groq_api_key = st.text_input(
      "Groq API Key:", type="password", key="app_groq_key"
  )
  st.caption("Auto-Compression Active | Live Mobile Camera Scanning Enabled ⚡")

col_inc, col_sav = st.columns(2)
with col_inc:
  income = st.number_input(
      "Income (₹):", min_value=0.0, value=65000.0, step=1000.0
  )
with col_sav:
  savings_goal = st.number_input(
      "Target (₹):", min_value=0.0, value=20000.0, step=500.0
  )

st.markdown("---")

tab_entry, tab_analytics, tab_sip, tab_ai = st.tabs([
    "📥 Entry & OCR",
    "📊 Analytics",
    "📈 Growth",
    "🤖 AI Audit",
])

# -----------------------------------------------------------------------------
# TAB 1: Live Camera + File Upload + Parallel OCR
# -----------------------------------------------------------------------------
DEMO_1_ACHIEVED = """Date,Description,Amount
2026-07-01,HOUSE RENT TRANSFER,15000
2026-07-03,BESCOM ELECTRICITY BILL,1800
2026-07-05,D MART SUPERMARKET,5500
2026-07-08,INDIAN OIL PETROL PUMP,2200
2026-07-10,ZEPTO QUICK GROCERIES,1200
"""

DEMO_2_SHORTFALL = """Date,Description,Amount
2026-07-01,HOUSE RENT TRANSFER,18000
2026-07-02,FLIPKART ELECTRONICS SALE,14500
2026-07-04,ZARA CLOTHING STORE,8200
"""

with tab_entry:
  st.subheader("📥 Add Expenses")

  entry_mode = st.radio(
      "Choose Input Method:",
      ["📷 Take Live Photo", "📸 Upload Images", "📄 Bank Statement CSV"],
      horizontal=True,
  )

  # OPTION A: Live Spot Camera Photo
  if entry_mode == "📷 Take Live Photo":
    st.info("Tap below to open camera & take a bill photo:")
    camera_photo = st.camera_input("Snap receipt on spot")

    if camera_photo is not None:
      if st.button("⚡ Scan Captured Photo", type="primary"):
        if not groq_api_key:
          st.error("Please enter your Groq API Key above!")
        else:
          with st.spinner("Compressing & Scanning with Vision AI..."):
            res = scan_single_file(camera_photo, groq_api_key)
            if res["success"]:
              parsed = res["data"]
              is_dup = any(
                  existing.get("Description") == parsed.get("Description")
                  and float(existing.get("Amount", 0))
                  == float(parsed.get("Amount", 0))
                  and existing.get("Date") == parsed.get("Date")
                  for existing in st.session_state.scanned_receipts
              )
              if not is_dup:
                st.session_state.scanned_receipts.append(parsed)
                st.success("Receipt added to ledger!")
                st.rerun()
              else:
                st.warning("This receipt was already scanned.")
            else:
              st.error(f"Scan failed: {res['error']}")

  # OPTION B: Upload Image Files (Parallel Batch Scan)
  elif entry_mode == "📸 Upload Images":
    img_files = st.file_uploader(
        "Upload photos/screenshots:",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
    )

    if img_files:
      if st.button("⚡ Fast AI Parallel Scan", type="primary"):
        if not groq_api_key:
          st.error("Please enter your Groq API Key above!")
        else:
          st.info(
              f"Compressing & scanning {len(img_files)} receipt(s) in"
              " parallel..."
          )
          progress_bar = st.progress(0)

          max_workers = min(len(img_files), 5)
          with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(
                    scan_single_file, f, groq_api_key
                ): f.name
                for f in img_files
            }

            completed_count = 0
            for future in as_completed(future_to_file):
              res = future.result()
              completed_count += 1
              progress_bar.progress(completed_count / len(img_files))

              if res["success"]:
                parsed = res["data"]
                is_dup = any(
                    existing.get("Description") == parsed.get("Description")
                    and float(existing.get("Amount", 0))
                    == float(parsed.get("Amount", 0))
                    and existing.get("Date") == parsed.get("Date")
                    for existing in st.session_state.scanned_receipts
                )
                if not is_dup:
                  st.session_state.scanned_receipts.append(parsed)
              else:
                st.error(f"Failed to scan {res['file_name']}: {res['error']}")

          progress_bar.empty()
          st.success("All receipts processed successfully!")
          st.rerun()

  # OPTION C: CSV Statement Import
  else:
    d_col1, d_col2 = st.columns(2)
    with d_col1:
      if st.button("🟢 Load Goal Demo"):
        st.session_state.df_raw = pd.read_csv(io.StringIO(DEMO_1_ACHIEVED))
        st.session_state.categorized_df = None
        st.session_state.active_demo_label = "Demo 1"

    with d_col2:
      if st.button("🔴 Load Overbudget Demo"):
        st.session_state.df_raw = pd.read_csv(io.StringIO(DEMO_2_SHORTFALL))
        st.session_state.categorized_df = None
        st.session_state.active_demo_label = "Demo 2"

    uploaded_csv = st.file_uploader("Upload Statement CSV:", type=["csv"])
    if uploaded_csv is not None:
      st.session_state.df_raw = pd.read_csv(uploaded_csv)
      st.session_state.categorized_df = None
      st.session_state.active_demo_label = "Uploaded CSV"

    if st.session_state.df_raw is not None:
      st.info(f"Loaded: **{st.session_state.active_demo_label}**")
      st.dataframe(st.session_state.df_raw, use_container_width=True)

      if st.button("🤖 Auto-Categorize CSV", type="primary"):
        if not groq_api_key:
          st.error("Please enter your Groq API Key above!")
        else:
          with st.spinner("Categorizing..."):
            try:
              client = Groq(api_key=groq_api_key)
              unique_desc = (
                  st.session_state.df_raw["Description"].unique().tolist()
              )

              prompt = f"""
                            Classify each transaction description into EXACTLY one category:
                            {json.dumps(CATEGORIES)}

                            Descriptions:
                            {json.dumps(unique_desc)}

                            Return ONLY a JSON mapping description -> category.
                            """

              completion = client.chat.completions.create(
                  model="llama-3.3-70b-versatile",
                  messages=[{"role": "user", "content": prompt}],
                  temperature=0.1,
                  response_format={"type": "json_object"},
              )

              cat_map = json.loads(completion.choices[0].message.content)
              df_cat = st.session_state.df_raw.copy()
              df_cat["Category"] = df_cat["Description"].map(
                  lambda d: cat_map.get(d, "Miscellaneous / Other")
              )
              st.session_state.categorized_df = df_cat
              st.success("CSV Categorized!")

            except Exception as e:
              st.error(f"Categorization failed: {e}")

  # Display Current Ledger / Scanned Items
  if st.session_state.scanned_receipts:
    st.markdown("---")
    st.caption("✏️ **Scanned Receipts Ledger** (Tap cell to edit)")
    scanned_df = pd.DataFrame(st.session_state.scanned_receipts)
    edited_df = st.data_editor(
        scanned_df,
        column_config={
            "Category": st.column_config.SelectboxColumn(
                "Category", options=CATEGORIES, required=True
            ),
            "Amount": st.column_config.NumberColumn(
                "Amount (₹)", format="₹%.2f"
            ),
        },
        num_rows="dynamic",
        use_container_width=True,
    )
    st.session_state.scanned_receipts = edited_df.to_dict("records")

    if st.button("🗑️ Clear Scanned Receipts"):
      st.session_state.scanned_receipts = []
      st.rerun()

# Calculate totals
cat_totals = {cat: 0.0 for cat in CATEGORIES}

if st.session_state.categorized_df is not None:
  grouped = (
      st.session_state.categorized_df.groupby("Category")["Amount"]
      .sum()
      .to_dict()
  )
  for c, a in grouped.items():
    if c in cat_totals:
      cat_totals[c] += float(a)

for rec in st.session_state.scanned_receipts:
  c = rec.get("Category", "Miscellaneous / Other")
  a = float(rec.get("Amount", 0.0))
  if c in cat_totals:
    cat_totals[c] += a
  else:
    cat_totals["Miscellaneous / Other"] += a

total_expenses = sum(cat_totals.values())
remaining_balance = income - total_expenses
actual_savings = max(0.0, remaining_balance)

# -----------------------------------------------------------------------------
# TAB 2: Financial Analytics
# -----------------------------------------------------------------------------
with tab_analytics:
  st.subheader("📊 Financial Overview")

  m1, m2 = st.columns(2)
  m1.metric("Expenses", f"₹{total_expenses:,.0f}")
  m2.metric("Net Balance", f"₹{remaining_balance:,.0f}")

  if remaining_balance < 0:
    st.error(f"⚠️ Overbudget by ₹{abs(remaining_balance):,.0f}")
  elif remaining_balance >= savings_goal:
    st.success(f"🎉 Target Met! Surplus: ₹{(remaining_balance - savings_goal):,.0f}")
  else:
    st.warning(f"💡 Shortfall: ₹{(savings_goal - remaining_balance):,.0f}")

  st.markdown("### Expense Breakdown")
  df_expenses = pd.DataFrame(
      list(cat_totals.items()), columns=["Category", "Amount"]
  )
  df_expenses = df_expenses[df_expenses["Amount"] > 0]

  if not df_expenses.empty:
    fig_pie = px.pie(
        df_expenses,
        values="Amount",
        names="Category",
        hole=0.45,
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig_pie.update_layout(
        margin=dict(t=10, b=10, l=10, r=10), showlegend=True, height=280
    )
    st.plotly_chart(fig_pie, use_container_width=True)
  else:
    st.info("No expense data loaded yet.")

  st.markdown("### Cash Flow")
  df_compare = pd.DataFrame({
      "Type": ["Income", "Expenses", "Target"],
      "Amount": [income, total_expenses, savings_goal],
  })
  fig_bar = px.bar(
      df_compare,
      x="Type",
      y="Amount",
      color="Type",
      color_discrete_sequence=["#10b981", "#ef4444", "#3b82f6"],
      text_auto="₹,.0f",
  )
  fig_bar.update_layout(
      showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=260
  )
  st.plotly_chart(fig_bar, use_container_width=True)

# -----------------------------------------------------------------------------
# TAB 3: SIP & Wealth Simulator
# -----------------------------------------------------------------------------
with tab_sip:
  st.subheader("📈 SIP Wealth Simulator")

  default_sip = max(
      1000.0, remaining_balance if remaining_balance > 0 else 5000.0
  )

  monthly_sip = st.number_input(
      "Monthly SIP (₹):",
      min_value=500.0,
      value=float(default_sip),
      step=500.0,
  )
  s_col1, s_col2 = st.columns(2)
  with s_col1:
    expected_return = st.slider("Return (%):", 4.0, 20.0, 12.0, 0.5)
  with s_col2:
    investment_years = st.slider("Years:", 1, 30, 15, 1)

  annual_stepup = st.slider("Annual Step-Up (%):", 0, 25, 5, 1)

  yearly_data = []
  monthly_rate = (expected_return / 100) / 12
  current_sip = monthly_sip
  total_invested = 0.0
  current_wealth = 0.0

  for year in range(1, investment_years + 1):
    for month in range(1, 13):
      total_invested += current_sip
      current_wealth = (current_wealth + current_sip) * (1 + monthly_rate)

    yearly_data.append({
        "Year_Num": year,
        "Total Invested": round(total_invested, 2),
        "Est. Wealth": round(current_wealth, 2),
    })
    current_sip = current_sip * (1 + (annual_stepup / 100))

  df_sip = pd.DataFrame(yearly_data)

  fig_sip = go.Figure()
  fig_sip.add_trace(
      go.Scatter(
          x=df_sip["Year_Num"],
          y=df_sip["Total Invested"],
          mode="lines",
          name="Invested",
          fill="tozeroy",
          line=dict(color="#3b82f6"),
      )
  )
  fig_sip.add_trace(
      go.Scatter(
          x=df_sip["Year_Num"],
          y=df_sip["Est. Wealth"],
          mode="lines",
          name="Corpus",
          fill="tonexty",
          line=dict(color="#10b981"),
      )
  )

  fig_sip.update_layout(
      xaxis_title="Years",
      yaxis_title="Corpus (₹)",
      margin=dict(t=10, b=10, l=10, r=10),
      height=280,
  )
  st.plotly_chart(fig_sip, use_container_width=True)

  if not df_sip.empty:
    st.metric(
        "Projected Corpus", f"₹{df_sip.iloc[-1]['Est. Wealth']:,.0f}"
    )

# -----------------------------------------------------------------------------
# TAB 4: AI Financial Health Audit & PDF Export
# -----------------------------------------------------------------------------
with tab_ai:
  st.subheader("🤖 AI Health Score & Export")

  if st.button("Evaluate Financial Health ✨", type="primary"):
    if not groq_api_key:
      st.error("Please enter your Groq API Key above!")
    else:
      with st.spinner("Analyzing financial health..."):
        try:
          client = Groq(api_key=groq_api_key)

          prompt = f"""
                    Act as a personal financial auditor. Analyze this data:
                    - Income: ₹{income:,.2f} | Savings Target: ₹{savings_goal:,.2f}
                    - Total Expenses: ₹{total_expenses:,.2f} | Remaining Balance: ₹{remaining_balance:,.2f}
                    - Category Spending: {json.dumps(cat_totals)}
                    - SIP: ₹{monthly_sip:,.2f} for {investment_years} Years @ {expected_return}% returns.

                    Return ONLY a JSON object:
                    {{
                        "health_score": <Integer 0-100>,
                        "score_status": "<'Excellent' | 'Good' | 'Needs Improvement' | 'Critical'>",
                        "executive_summary": "<2 sentence overview>",
                        "spending_observations": ["<Obs 1>", "<Obs 2>"],
                        "action_plan": ["<Step 1>", "<Step 2>", "<Step 3>"]
                    }}
                    """

          completion = client.chat.completions.create(
              model="llama-3.3-70b-versatile",
              messages=[{"role": "user", "content": prompt}],
              temperature=0.3,
              response_format={"type": "json_object"},
          )
          st.session_state.ai_json = json.loads(
              completion.choices[0].message.content
          )

        except Exception as e:
          st.error(f"Error generating score: {e}")

  if st.session_state.ai_json:
    data = st.session_state.ai_json
    score = data.get("health_score", 50)
    status = data.get("score_status", "Needs Improvement")

    st.markdown(f"""
        <div class="score-card">
            <div style="font-size:0.8rem; font-weight:bold; color:#64748b;">HEALTH SCORE</div>
            <div class="score-number" style="color: #2563eb;">{score}<span style="font-size:1.2rem; color:#94a3b8;">/100</span></div>
            <div style="font-weight:bold; font-size:0.9rem;">{status}</div>
        </div>
        """, unsafe_allow_html=True)

    st.progress(score / 100)
    st.info(data.get("executive_summary", ""))

    for obs in data.get("spending_observations", []):
      st.markdown(
          f'<div class="feature-card">💡 {obs}</div>', unsafe_allow_html=True
      )

    for idx, act in enumerate(data.get("action_plan", []), 1):
      st.markdown(
          f'<div class="action-card"><strong>Step {idx}:</strong> {act}</div>',
          unsafe_allow_html=True,
      )

  st.markdown("---")
  st.subheader("📄 Export Audit Report")

  sip_inputs = {
      "sip_amount": monthly_sip,
      "rate": expected_return,
      "years": investment_years,
      "stepup": annual_stepup,
  }

  combined_txs = []
  if st.session_state.categorized_df is not None:
    combined_txs.extend(st.session_state.categorized_df.to_dict("records"))
  if st.session_state.scanned_receipts:
    combined_txs.extend(st.session_state.scanned_receipts)

  merged_df = pd.DataFrame(combined_txs) if combined_txs else None

  pdf_bytes = generate_detailed_pdf_report(
      income=income,
      expenses=total_expenses,
      savings_goal=savings_goal,
      remaining_balance=remaining_balance,
      cat_totals=cat_totals,
      sip_inputs=sip_inputs,
      sip_schedule_df=df_sip,
      transactions_df=merged_df,
      ai_json=st.session_state.ai_json,
  )

  st.download_button(
      label="📥 Download PDF Statement",
      data=pdf_bytes,
      file_name="Financial_Health_Statement.pdf",
      mime="application/pdf",
      type="primary",
  )