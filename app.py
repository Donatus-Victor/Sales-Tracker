"""
SalesTrack Pro — Streamlit SaaS
================================
Storage  : Supabase (PostgreSQL)
Auth     : Built-in role system (viewer / sales / manager / admin)
CDC      : Full change data capture on every correction
Currency : Nigerian Naira ₦
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date
import uuid
import hashlib
import time
import plotly.express as px

# ─────────────────────────────────────────────
#  PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="SalesTrack Pro",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
#  CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }

.stApp { background: #0b0d14; color: #e2e4ed; }

section[data-testid="stSidebar"] {
    background: #111320 !important;
    border-right: 1px solid #1e2132 !important;
}
section[data-testid="stSidebar"] * { color: #c5c9e0 !important; }

[data-testid="metric-container"] {
    background: #161924;
    border: 1px solid #1e2235;
    border-radius: 14px;
    padding: 18px 20px !important;
}

.stButton > button {
    background: linear-gradient(135deg,#5b5ef4,#7c3aed) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 10px 24px !important;
}
.stButton > button:hover { opacity: .85 !important; }

.stTabs [data-baseweb="tab-list"] {
    background: #111320; border-radius: 12px; padding: 4px; gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px; color: #7a7f9a !important; font-weight: 600;
}
.stTabs [aria-selected="true"] {
    background: #5b5ef4 !important; color: white !important;
}

.section-header {
    font-size: 24px; font-weight: 800; color: #e2e4ed;
    margin-bottom: 4px; letter-spacing: -0.4px;
}
.section-sub { font-size: 13px; color: #6b7280; margin-bottom: 24px; }

.badge { display:inline-block; padding:3px 10px; border-radius:20px;
         font-size:11px; font-weight:700; letter-spacing:.5px; text-transform:uppercase; }
.badge-admin   { background:#5b5ef420; color:#818cf8; border:1px solid #5b5ef440; }
.badge-manager { background:#059c6920; color:#10b981; border:1px solid #059c6940; }
.badge-sales   { background:#d9770620; color:#f59e0b; border:1px solid #d9770640; }
.badge-viewer  { background:#37415120; color:#9ca3af; border:1px solid #37415140; }

.risk-low    { color:#10b981; font-weight:700; }
.risk-medium { color:#f59e0b; font-weight:700; }
.risk-high   { color:#ef4444; font-weight:700; }

hr { border-color: #1e2235 !important; }
footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  SUPABASE CLIENT
# ─────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


# ─────────────────────────────────────────────
#  DATABASE HELPERS
# ─────────────────────────────────────────────
def db_fetch(table: str, filters: dict = None) -> pd.DataFrame:
    """Fetch all rows from a table, optional eq filters."""
    try:
        sb = get_supabase()
        q  = sb.table(table).select("*")
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        resp = q.order("created_at", desc=True).execute()
        return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()
    except Exception as e:
        st.error(f"DB read error ({table}): {e}")
        return pd.DataFrame()


def db_insert(table: str, row: dict) -> bool:
    try:
        get_supabase().table(table).insert(row).execute()
        return True
    except Exception as e:
        st.error(f"DB insert error ({table}): {e}")
        return False


def db_update(table: str, record_id: str, data: dict) -> bool:
    try:
        get_supabase().table(table).update(data).eq("id", record_id).execute()
        return True
    except Exception as e:
        st.error(f"DB update error ({table}): {e}")
        return False


def db_delete(table: str, record_id: str) -> bool:
    try:
        get_supabase().table(table).delete().eq("id", record_id).execute()
        return True
    except Exception as e:
        st.error(f"DB delete error: {e}")
        return False


# ─────────────────────────────────────────────
#  CHANGE DATA CAPTURE
# ─────────────────────────────────────────────
def cdc_log(table_name: str, record_id: str, field: str,
            old_val, new_val, changed_by: str, reason: str):
    db_insert("cdc_log", {
        "id":           new_uid(),
        "table_name":   table_name,
        "record_id":    record_id,
        "field_changed": field,
        "old_value":    str(old_val),
        "new_value":    str(new_val),
        "changed_by":   changed_by,
        "reason":       reason,
        "changed_at":   datetime.now().isoformat(),
    })


def correct_sale(record_id: str, field: str, new_val,
                 changed_by: str, reason: str) -> bool:
    """Update a sales field and write CDC entry."""
    df = db_fetch("sales", {"id": record_id})
    if df.empty:
        return False
    old_val = df.iloc[0].get(field, "")
    ok = db_update("sales", record_id, {field: new_val})
    if ok:
        cdc_log("sales", record_id, field, old_val, new_val, changed_by, reason)
        # Auto-recalculate revenue if price/units changed
        if field in ("units_sold", "unit_price"):
            row = df.iloc[0]
            units = float(new_val)    if field == "units_sold"  else float(row.get("units_sold", 0))
            price = float(new_val)    if field == "unit_price"  else float(row.get("unit_price", 0))
            new_rev = round(units * price, 2)
            db_update("sales", record_id, {"total_revenue": new_rev})
            cdc_log("sales", record_id, "total_revenue",
                    row.get("total_revenue", 0), new_rev,
                    changed_by, "Auto-recalculated after correction")
    return ok


# ─────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def authenticate(username: str, password: str):
    df = db_fetch("users")
    if df.empty:
        return None
    row = df[(df["username"] == username) &
             (df["password_hash"] == hash_pw(password))]
    return row.iloc[0].to_dict() if not row.empty else None


def ensure_default_admin():
    df = db_fetch("users")
    if df.empty or "username" not in df.columns:
        db_insert("users", {
            "id":            new_uid(),
            "username":      "admin",
            "password_hash": hash_pw("admin123"),
            "role":          "admin",
            "branch":        "HQ",
            "created_at":    datetime.now().isoformat(),
        })


# ─────────────────────────────────────────────
#  FRAUD SCORE  (rule-based — Phase 1)
# ─────────────────────────────────────────────
def fraud_score(units_sold: int, opening: int, closing: int,
                unit_price: float, revenue: float,
                history_df: pd.DataFrame) -> float:
    score = 0.0
    if closing != (opening - units_sold):           score += 30
    if units_sold > 0 and revenue == 0:             score += 40
    if units_sold > opening:                        score += 25
    if unit_price > 0 and unit_price % 1000 == 0 and units_sold > 50:
                                                    score += 10
    if not history_df.empty and "units_sold" in history_df.columns:
        try:
            s = pd.to_numeric(history_df["units_sold"], errors="coerce")
            avg, std = s.mean(), s.std()
            if std and units_sold > avg + 3 * std:  score += 20
        except Exception:
            pass
    return min(round(score, 1), 100.0)


def risk_badge(score: float) -> str:
    if score < 25:   return f'<span class="risk-low">🟢 Low ({score:.0f})</span>'
    if score < 60:   return f'<span class="risk-medium">🟡 Medium ({score:.0f})</span>'
    return               f'<span class="risk-high">🔴 High ({score:.0f})</span>'


# ─────────────────────────────────────────────
#  UTILS
# ─────────────────────────────────────────────
def new_uid() -> str:
    return str(uuid.uuid4())[:8].upper()


def fmt(val) -> str:
    try:    return f"₦{float(val):,.2f}"
    except: return "₦0.00"


def role_badge(role: str) -> str:
    icons = {"admin":"🔐","manager":"👔","sales":"💼","viewer":"👁️"}
    cls   = {"admin":"badge-admin","manager":"badge-manager",
             "sales":"badge-sales","viewer":"badge-viewer"}
    return (f'<span class="badge {cls.get(role,"badge-viewer")}">'
            f'{icons.get(role,"👁️")} {role.upper()}</span>')


# ─────────────────────────────────────────────
#  SIDEBAR  (navigation + login state)
# ─────────────────────────────────────────────
def sidebar() -> str:
    with st.sidebar:
        st.markdown("## 📦 SalesTrack Pro")
        st.markdown("---")

        if st.session_state.get("logged_in"):
            u = st.session_state["user"]
            st.markdown(f"**{u['username']}**")
            st.markdown(role_badge(u["role"]), unsafe_allow_html=True)
            st.caption(f"Branch: {u.get('branch','—')}")
            st.markdown("---")

            pages = ["📊 Dashboard"]
            if u["role"] in ("admin","manager","sales"):
                pages += ["📝 Sales Entry"]
            if u["role"] in ("admin","manager"):
                pages += ["✏️ Corrections", "👥 Sellers", "📦 Products"]
            if u["role"] == "admin":
                pages += ["🔐 Users", "⚙️ Settings"]

            page = st.radio("", pages, label_visibility="collapsed")
            st.markdown("---")
            if st.button("🚪 Sign Out"):
                for k in ["logged_in","user","role"]:
                    st.session_state.pop(k, None)
                st.rerun()
        else:
            page = st.radio("", ["📊 Dashboard","🔑 Login"],
                            label_visibility="collapsed")

        st.markdown("---")
        st.caption("© 2025 SalesTrack Pro")
    return page


# ─────────────────────────────────────────────
#  PAGE — DASHBOARD
# ─────────────────────────────────────────────
def page_dashboard():
    st.markdown('<div class="section-header">📊 Sales Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Live revenue & performance — visible to everyone</div>',
                unsafe_allow_html=True)

    df = db_fetch("sales")
    if df.empty:
        st.info("No sales data yet. Sales reps can start logging entries.")
        return

    for c in ["units_sold","unit_price","total_revenue","opening_stock",
              "closing_stock","fraud_score"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # ── KPIs ──
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("💰 Total Revenue",  fmt(df["total_revenue"].sum()))
    k2.metric("📦 Units Sold",     f"{int(df['units_sold'].sum()):,}")
    k3.metric("🧾 Sales Entries",  f"{len(df):,}")
    k4.metric("📈 Avg Order Value",fmt(df["total_revenue"].mean()))

    st.markdown("---")

    # ── Date filter ──
    c1, c2 = st.columns(2)
    start = c1.date_input("From", value=date.today().replace(day=1))
    end   = c2.date_input("To",   value=date.today())

    if "date" in df.columns:
        df = df[(df["date"].dt.date >= start) & (df["date"].dt.date <= end)]

    if df.empty:
        st.warning("No data for selected date range.")
        return

    # ── Show fraud alerts to logged-in managers ──
    role = st.session_state.get("role","viewer")
    if role in ("admin","manager") and "fraud_score" in df.columns:
        high_risk = df[df["fraud_score"] >= 60]
        if not high_risk.empty:
            st.error(f"🚨 **{len(high_risk)} high-risk entries** flagged for review — check Corrections tab.")

    tab1, tab2, tab3, tab4 = st.tabs(["📈 Revenue","🏆 Leaderboard","📦 Products","🗃️ Raw Data"])

    PLOT = dict(plot_bgcolor="#0b0d14", paper_bgcolor="#0b0d14",
                font_color="#c5c9e0", margin=dict(t=20,b=20))

    with tab1:
        if "date" in df.columns:
            trend = (df.groupby(df["date"].dt.date)["total_revenue"]
                     .sum().reset_index())
            trend.columns = ["date","revenue"]
            fig = px.area(trend, x="date", y="revenue",
                          color_discrete_sequence=["#5b5ef4"],
                          labels={"revenue":"Revenue (₦)","date":"Date"})
            fig.update_layout(**PLOT, yaxis=dict(gridcolor="#1e2235",tickprefix="₦"),
                              xaxis=dict(showgrid=False))
            st.plotly_chart(fig, use_container_width=True)

            df["month"] = df["date"].dt.to_period("M").astype(str)
            monthly = df.groupby("month")["total_revenue"].sum().reset_index()
            if len(monthly) > 1:
                st.markdown("#### Monthly Revenue")
                fig2 = px.bar(monthly, x="month", y="total_revenue",
                              color_discrete_sequence=["#7c3aed"],
                              labels={"total_revenue":"Revenue (₦)","month":"Month"})
                fig2.update_layout(**PLOT, yaxis=dict(gridcolor="#1e2235",tickprefix="₦"))
                st.plotly_chart(fig2, use_container_width=True)

    with tab2:
        if "seller_name" in df.columns:
            lb = (df.groupby("seller_name")
                  .agg(Revenue=("total_revenue","sum"),
                       Units=("units_sold","sum"),
                       Entries=("id","count"))
                  .sort_values("Revenue", ascending=False)
                  .reset_index())
            lb["Rev_fmt"] = lb["Revenue"].apply(fmt)
            fig = px.bar(lb, x="seller_name", y="Revenue", text="Rev_fmt",
                         color="Revenue",
                         color_continuous_scale=["#1e2235","#5b5ef4","#7c3aed"],
                         labels={"seller_name":"Seller","Revenue":"Revenue (₦)"})
            fig.update_layout(**PLOT, showlegend=False, coloraxis_showscale=False)
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(lb[["seller_name","Rev_fmt","Units","Entries"]]
                         .rename(columns={"seller_name":"Seller","Rev_fmt":"Revenue"}),
                         use_container_width=True, hide_index=True)

    with tab3:
        if "product_name" in df.columns:
            prod = (df.groupby("product_name")
                    .agg(Revenue=("total_revenue","sum"),
                         Units=("units_sold","sum"))
                    .sort_values("Revenue",ascending=False).reset_index())
            ca, cb = st.columns(2)
            with ca:
                fig = px.pie(prod, names="product_name", values="Revenue",
                             color_discrete_sequence=px.colors.sequential.Purples_r)
                fig.update_layout(**PLOT)
                st.plotly_chart(fig, use_container_width=True)
            with cb:
                fig2 = px.bar(prod, x="product_name", y="Units",
                              color_discrete_sequence=["#10b981"])
                fig2.update_layout(**PLOT, yaxis=dict(gridcolor="#1e2235"))
                st.plotly_chart(fig2, use_container_width=True)

    with tab4:
        show = [c for c in ["date","seller_name","product_name","branch",
                            "customer_name","invoice_no","units_sold",
                            "unit_price","total_revenue","payment_method",
                            "fraud_score"] if c in df.columns]
        st.dataframe(df[show], use_container_width=True, hide_index=True)
        st.download_button("⬇️ Export CSV",
                           df.to_csv(index=False).encode(),
                           file_name=f"salestrack_{date.today()}.csv",
                           mime="text/csv")


# ─────────────────────────────────────────────
#  PAGE — SALES ENTRY
# ─────────────────────────────────────────────
def page_sales_entry():
    u = st.session_state["user"]
    st.markdown('<div class="section-header">📝 Daily Sales Entry</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="section-sub">Logged in as <b>{u["username"]}</b> · {u.get("branch","")}</div>',
                unsafe_allow_html=True)

    df_p = db_fetch("products")
    df_s = db_fetch("sellers")
    df_h = db_fetch("sales")

    products = df_p["name"].tolist() if not df_p.empty and "name" in df_p.columns else ["No products — ask admin"]
    sellers  = df_s["name"].tolist() if not df_s.empty and "name" in df_s.columns else [u["username"]]

    with st.form("entry_form", clear_on_submit=True):
        st.markdown(f"**📅 {date.today().strftime('%A, %d %B %Y')}**")
        st.markdown("---")

        c1, c2 = st.columns(2)
        seller_name    = c1.selectbox("👤 Salesperson",     sellers)
        branch         = c1.text_input("🏢 Branch",         value=u.get("branch",""))
        product_name   = c2.selectbox("📦 Product",         products)
        payment_method = c2.selectbox("💳 Payment Method",
                                      ["Cash","Bank Transfer","POS","Cheque","Mixed"])

        c3, c4 = st.columns(2)
        customer_name  = c3.text_input("🧑 Customer Name")
        customer_phone = c3.text_input("📞 Customer Phone")
        invoice_no     = c4.text_input("🧾 Invoice No.", value=f"INV-{new_uid()}")
        unit_price     = c4.number_input("💰 Unit Price (₦)", min_value=0.0, step=50.0)

        c5, c6, c7 = st.columns(3)
        opening_stock  = c5.number_input("📥 Opening Stock", min_value=0, step=1)
        units_sold     = c6.number_input("📤 Units Sold",    min_value=0, step=1)
        closing_stock  = c7.number_input("📦 Closing Stock", min_value=0, step=1)

        notes = st.text_area("📋 Notes", height=70)

        # Revenue preview
        revenue  = units_sold * unit_price
        expected = opening_stock - units_sold
        stock_ok = closing_stock == expected
        st.markdown(f"""
        <div style='background:#161924;border:1px solid #1e2235;border-radius:12px;
                    padding:16px 20px;margin:12px 0;'>
            <div style='font-size:12px;color:#6b7280;font-weight:600;
                        text-transform:uppercase;letter-spacing:.5px;'>Revenue Preview</div>
            <div style='font-size:30px;font-weight:800;
                        background:linear-gradient(135deg,#5b5ef4,#7c3aed);
                        -webkit-background-clip:text;-webkit-text-fill-color:transparent;'>
                {fmt(revenue)}</div>
            <div style='font-size:13px;margin-top:6px;
                        color:{"#10b981" if stock_ok else "#f59e0b"}'>
                {"✅ Stock balances correctly" if stock_ok
                 else f"⚠️ Expected closing stock: {expected} units — please verify"}
            </div>
        </div>""", unsafe_allow_html=True)

        submitted = st.form_submit_button("✅ Submit Entry", use_container_width=True)

    if submitted:
        if units_sold == 0:
            st.warning("Units sold cannot be zero.")
            return

        fs = fraud_score(units_sold, opening_stock, closing_stock,
                         unit_price, revenue, df_h)
        pid = (df_p[df_p["name"]==product_name].iloc[0]["id"]
               if not df_p.empty and "name" in df_p.columns else "")
        sid = (df_s[df_s["name"]==seller_name].iloc[0]["id"]
               if not df_s.empty and "name" in df_s.columns else "")

        ok = db_insert("sales", {
            "id":             new_uid(),
            "date":           str(date.today()),
            "seller_id":      sid,
            "seller_name":    seller_name,
            "product_id":     pid,
            "product_name":   product_name,
            "branch":         branch,
            "customer_name":  customer_name,
            "customer_phone": customer_phone,
            "invoice_no":     invoice_no,
            "opening_stock":  opening_stock,
            "units_sold":     units_sold,
            "closing_stock":  closing_stock,
            "unit_price":     unit_price,
            "total_revenue":  round(revenue, 2),
            "payment_method": payment_method,
            "notes":          notes,
            "submitted_at":   datetime.now().isoformat(),
            "fraud_score":    fs,
            "created_at":     datetime.now().isoformat(),
        })

        if ok:
            st.success(f"✅ Saved! Invoice **{invoice_no}** · Revenue **{fmt(revenue)}**")
            if fs >= 60:
                st.error(f"🚨 High risk score ({fs}/100) — a manager will review this entry.")
            elif fs >= 25:
                st.warning(f"⚠️ Anomaly score {fs}/100 — please verify your stock figures.")
            time.sleep(0.5)
            st.rerun()


# ─────────────────────────────────────────────
#  PAGE — CORRECTIONS  (CDC)
# ─────────────────────────────────────────────
def page_corrections():
    u = st.session_state["user"]
    st.markdown('<div class="section-header">✏️ Data Corrections</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Every change is permanently logged in the audit trail</div>',
                unsafe_allow_html=True)

    df = db_fetch("sales")
    if df.empty:
        st.info("No sales records yet.")
        return

    for c in ["units_sold","unit_price","total_revenue","fraud_score"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    st.markdown("#### 🔍 Find Record")
    sc1, sc2 = st.columns(2)
    search_by   = sc1.selectbox("Search by", ["invoice_no","seller_name","id"])
    search_term = sc2.text_input("Search value")

    if search_term:
        found = df[df[search_by].astype(str).str.contains(search_term, case=False, na=False)]
        if found.empty:
            st.warning("No matching records.")
            return

        st.dataframe(found, use_container_width=True, hide_index=True)
        record_id = st.selectbox("Select Record ID",
                                 found["id"].tolist() if "id" in found.columns else [])

        if record_id:
            rec = df[df["id"]==record_id].iloc[0]
            editable = ["units_sold","unit_price","opening_stock","closing_stock",
                        "payment_method","notes","customer_name","invoice_no"]

            with st.form("correction_form"):
                st.markdown(f"**Editing `{record_id}`**")
                field   = st.selectbox("Field to correct", editable)
                cur_val = str(rec.get(field,""))
                st.caption(f"Current value: **{cur_val}**")
                new_val = st.text_input("New value")
                reason  = st.text_area("Reason for correction *(required)*", height=80)
                save    = st.form_submit_button("💾 Save Correction")

            if save:
                if not reason.strip():
                    st.error("Please provide a reason.")
                    return
                if correct_sale(record_id, field, new_val, u["username"], reason):
                    st.success(f"✅ **{field}** corrected. CDC entry logged.")
                    st.rerun()

    st.markdown("---")
    st.markdown("#### 📜 Full Audit Log (CDC)")
    df_cdc = db_fetch("cdc_log")
    if df_cdc.empty:
        st.info("No corrections made yet.")
    else:
        st.dataframe(df_cdc, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Export CDC Log",
                           df_cdc.to_csv(index=False).encode(),
                           file_name=f"cdc_log_{date.today()}.csv",
                           mime="text/csv")


# ─────────────────────────────────────────────
#  PAGE — SELLERS
# ─────────────────────────────────────────────
def page_sellers():
    st.markdown('<div class="section-header">👥 Manage Sellers</div>', unsafe_allow_html=True)

    with st.form("add_seller", clear_on_submit=True):
        st.markdown("#### ➕ Add Seller")
        c1, c2 = st.columns(2)
        name   = c1.text_input("Name")
        branch = c2.text_input("Branch")
        if st.form_submit_button("Add Seller") and name.strip():
            db_insert("sellers", {"id": new_uid(), "name": name.strip(),
                                  "branch": branch.strip(),
                                  "created_at": datetime.now().isoformat()})
            st.success(f"✅ {name} added.")
            st.rerun()

    df = db_fetch("sellers")
    st.markdown("---")
    st.markdown("#### 📋 Sellers")
    if df.empty:
        st.info("No sellers yet.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
#  PAGE — PRODUCTS
# ─────────────────────────────────────────────
def page_products():
    st.markdown('<div class="section-header">📦 Manage Products</div>', unsafe_allow_html=True)

    with st.form("add_product", clear_on_submit=True):
        st.markdown("#### ➕ Add Product")
        c1, c2 = st.columns(2)
        name = c1.text_input("Product Name")
        cat  = c2.text_input("Category")
        if st.form_submit_button("Add Product") and name.strip():
            db_insert("products", {"id": new_uid(), "name": name.strip(),
                                   "category": cat.strip(),
                                   "created_at": datetime.now().isoformat()})
            st.success(f"✅ {name} added.")
            st.rerun()

    df = db_fetch("products")
    st.markdown("---")
    st.markdown("#### 📋 Products")
    if df.empty:
        st.info("No products yet.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
#  PAGE — USERS  (admin only)
# ─────────────────────────────────────────────
def page_users():
    st.markdown('<div class="section-header">🔐 User Management</div>', unsafe_allow_html=True)

    with st.form("add_user", clear_on_submit=True):
        st.markdown("#### ➕ Create User")
        c1, c2, c3 = st.columns(3)
        uname  = c1.text_input("Username")
        upw    = c1.text_input("Password", type="password")
        urole  = c2.selectbox("Role", ["sales","manager","admin","viewer"])
        ubranch= c2.text_input("Branch")

        if st.form_submit_button("Create User"):
            if not uname.strip() or not upw.strip():
                st.error("Username and password required.")
            else:
                df = db_fetch("users")
                if not df.empty and uname in df["username"].values:
                    st.error("Username already exists.")
                else:
                    db_insert("users", {
                        "id":            new_uid(),
                        "username":      uname.strip(),
                        "password_hash": hash_pw(upw),
                        "role":          urole,
                        "branch":        ubranch.strip(),
                        "created_at":    datetime.now().isoformat(),
                    })
                    st.success(f"✅ User **{uname}** ({urole}) created.")
                    st.rerun()

    df = db_fetch("users")
    st.markdown("---")
    st.markdown("#### 👥 All Users")
    if not df.empty:
        cols = [c for c in ["id","username","role","branch","created_at"]
                if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
#  PAGE — SETTINGS
# ─────────────────────────────────────────────
def page_settings():
    u = st.session_state["user"]
    st.markdown('<div class="section-header">⚙️ Settings</div>', unsafe_allow_html=True)

    st.markdown("#### 🔑 Change Password")
    with st.form("change_pw"):
        old = st.text_input("Current Password", type="password")
        new = st.text_input("New Password",      type="password")
        cf  = st.text_input("Confirm Password",  type="password")
        if st.form_submit_button("Update Password"):
            if hash_pw(old) != u["password_hash"]:
                st.error("Current password incorrect.")
            elif new != cf:
                st.error("Passwords don't match.")
            elif len(new) < 6:
                st.error("Minimum 6 characters.")
            else:
                db_update("users", u["id"], {"password_hash": hash_pw(new)})
                cdc_log("users", u["id"], "password_hash",
                        "***", "***", u["username"], "Password changed by user")
                st.success("✅ Password updated.")


# ─────────────────────────────────────────────
#  PAGE — LOGIN
# ─────────────────────────────────────────────
def page_login():
    st.markdown('<div class="section-header">🔑 Sign In</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Managers and sales staff log in here · Dashboard is public</div>',
                unsafe_allow_html=True)

    col, _ = st.columns([1.3, 1])
    with col:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            ok       = st.form_submit_button("Sign In →", use_container_width=True)

        if ok:
            with st.spinner("Authenticating…"):
                user = authenticate(username, password)
            if user:
                st.session_state.update(
                    logged_in=True, user=user, role=user["role"])
                st.success(f"Welcome, **{username}**!")
                time.sleep(0.6)
                st.rerun()
            else:
                st.error("Invalid username or password.")

        st.caption("Default admin → username: **admin** · password: **admin123**")
        st.caption("⚠️ Change the default password immediately after first login.")


# ─────────────────────────────────────────────
#  MAIN ROUTER
# ─────────────────────────────────────────────
def main():
    try:
        ensure_default_admin()
    except Exception:
        pass

    page = sidebar()
    role = st.session_state.get("role","viewer")

    routes = {
        "📊 Dashboard":    page_dashboard,
        "🔑 Login":        page_login,
        "📝 Sales Entry":  page_sales_entry  if st.session_state.get("logged_in") else page_login,
        "✏️ Corrections":  page_corrections  if role in ("admin","manager") else lambda: st.error("Access denied."),
        "👥 Sellers":      page_sellers      if role in ("admin","manager") else lambda: st.error("Access denied."),
        "📦 Products":     page_products     if role in ("admin","manager") else lambda: st.error("Access denied."),
        "🔐 Users":        page_users        if role == "admin"            else lambda: st.error("Access denied."),
        "⚙️ Settings":     page_settings     if role == "admin"            else lambda: st.error("Access denied."),
    }
    routes.get(page, page_dashboard)()


if __name__ == "__main__":
    main()
