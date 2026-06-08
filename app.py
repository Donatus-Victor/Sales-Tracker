"""
SalesTrack Pro — Multi-Tenant SaaS v3
=======================================
Fixes & features in this version:
  ✅ New users must set their own password on first login
  ✅ CDC log error fixed (orders by changed_at, not created_at)
  ✅ Products are editable (name + category)
  ✅ Company admin can disable/enable users
  ✅ Superadmin can disable companies
  ✅ Each company sees only their own data
  ✅ Closing stock auto-calculated from opening - units sold
  ✅ Revenue preview shown before submit
  ✅ Opening stock always visible/editable
  ✅ Sales rep can correct their own entries (with reason required)
  ✅ Corrections: product_name, customer_phone, opening_stock,
                  units_sold, closing_stock, unit_price, payment_method
  ✅ Reason required before any correction submits
Roles: superadmin | admin | manager | sales
"""

import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, date, timedelta
import uuid, hashlib, time
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
#  PWA
# ─────────────────────────────────────────────
st.markdown("""
<link rel="manifest" href="data:application/json;charset=utf-8,\
%7B%22name%22%3A%22SalesTrack%20Pro%22%2C%22short_name%22%3A%22SalesTrack%22%2C\
%22start_url%22%3A%22%2F%22%2C%22display%22%3A%22standalone%22%2C\
%22background_color%22%3A%22%230b0d14%22%2C%22theme_color%22%3A%22%235b5ef4%22%2C\
%22icons%22%3A%5B%7B%22src%22%3A%22https%3A%2F%2Fcdn-icons-png.flaticon.com%2F512%2F1170%2F1170678.png%22%2C\
%22sizes%22%3A%22512x512%22%2C%22type%22%3A%22image%2Fpng%22%7D%5D%7D">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="SalesTrack Pro">
<meta name="theme-color" content="#5b5ef4">
<script>
let deferredPrompt;
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault(); deferredPrompt = e;
});
function installPWA() {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(() => { deferredPrompt = null; });
  }
}
</script>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"]{ font-family:'Inter',sans-serif !important; }
.stApp { background:#0b0d14; color:#e2e4ed; }
section[data-testid="stSidebar"]{background:#111320 !important;border-right:1px solid #1e2132 !important;}
section[data-testid="stSidebar"] *{color:#c5c9e0 !important;}
[data-testid="metric-container"]{background:#161924;border:1px solid #1e2235;border-radius:14px;padding:18px 20px !important;}
.stButton>button{background:linear-gradient(135deg,#5b5ef4,#7c3aed) !important;color:white !important;
  border:none !important;border-radius:10px !important;font-weight:600 !important;padding:10px 24px !important;}
.stButton>button:hover{opacity:.85 !important;}
.stTabs [data-baseweb="tab-list"]{background:#111320;border-radius:12px;padding:4px;gap:4px;}
.stTabs [data-baseweb="tab"]{border-radius:8px;color:#7a7f9a !important;font-weight:600;}
.stTabs [aria-selected="true"]{background:#5b5ef4 !important;color:white !important;}
.section-header{font-size:24px;font-weight:800;color:#e2e4ed;margin-bottom:4px;letter-spacing:-0.4px;}
.section-sub{font-size:13px;color:#6b7280;margin-bottom:24px;}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;
  letter-spacing:.5px;text-transform:uppercase;}
.badge-superadmin{background:#ec489920;color:#ec4899;border:1px solid #ec489940;}
.badge-admin{background:#5b5ef420;color:#818cf8;border:1px solid #5b5ef440;}
.badge-manager{background:#059c6920;color:#10b981;border:1px solid #059c6940;}
.badge-sales{background:#d9770620;color:#f59e0b;border:1px solid #d9770640;}
.company-card{background:#161924;border:1px solid #1e2235;border-radius:14px;padding:18px 22px;margin-bottom:12px;}
.company-active{border-left:4px solid #10b981 !important;}
.company-inactive{border-left:4px solid #ef4444 !important;}
.company-expired{border-left:4px solid #f59e0b !important;}
.risk-low{color:#10b981;font-weight:700;}
.risk-medium{color:#f59e0b;font-weight:700;}
.risk-high{color:#ef4444;font-weight:700;}
.rev-box{background:#161924;border:1px solid #1e2235;border-radius:12px;padding:16px 20px;margin:12px 0;}
hr{border-color:#1e2235 !important;}
footer{visibility:hidden;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  SUPABASE
# ─────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_sb() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def db_fetch(table: str, filters: dict = None) -> pd.DataFrame:
    try:
        q = get_sb().table(table).select("*")
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        r = q.execute()
        return pd.DataFrame(r.data) if r.data else pd.DataFrame()
    except Exception as e:
        st.error(f"Read error ({table}): {e}")
        return pd.DataFrame()

def db_insert(table: str, row: dict) -> bool:
    try:
        get_sb().table(table).insert(row).execute()
        return True
    except Exception as e:
        st.error(f"Insert error ({table}): {e}")
        return False

def db_update(table: str, record_id: str, data: dict) -> bool:
    try:
        get_sb().table(table).update(data).eq("id", record_id).execute()
        return True
    except Exception as e:
        st.error(f"Update error ({table}): {e}")
        return False

# ─────────────────────────────────────────────
#  UTILS
# ─────────────────────────────────────────────
def new_uid() -> str:
    return str(uuid.uuid4())[:8].upper()

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def fmt(val) -> str:
    try:    return f"₦{float(val):,.2f}"
    except: return "₦0.00"

def role_badge(role: str) -> str:
    icons = {"superadmin":"⭐","admin":"🔐","manager":"👔","sales":"💼"}
    cls   = {"superadmin":"badge-superadmin","admin":"badge-admin",
             "manager":"badge-manager","sales":"badge-sales"}
    return (f'<span class="badge {cls.get(role,"badge-admin")}">'
            f'{icons.get(role,"👤")} {role.upper()}</span>')

# ─────────────────────────────────────────────
#  CDC
# ─────────────────────────────────────────────
def cdc_log(table_name, record_id, field, old_val, new_val,
            changed_by, reason, company_id=""):
    db_insert("cdc_log", {
        "id":            new_uid(),
        "table_name":    table_name,
        "record_id":     record_id,
        "field_changed": field,
        "old_value":     str(old_val),
        "new_value":     str(new_val),
        "changed_by":    changed_by,
        "reason":        reason,
        "company_id":    company_id,
        "changed_at":    datetime.now().isoformat(),
    })

def correct_sale(record_id, field, new_val, changed_by, reason, company_id):
    df = db_fetch("sales", {"id": record_id})
    if df.empty: return False
    old_val = df.iloc[0].get(field, "")
    ok = db_update("sales", record_id, {field: new_val})
    if ok:
        cdc_log("sales", record_id, field, old_val, new_val,
                changed_by, reason, company_id)
        # Auto-recalculate revenue if units or price changed
        if field in ("units_sold", "unit_price"):
            row   = df.iloc[0]
            units = float(new_val) if field == "units_sold" else float(row.get("units_sold", 0))
            price = float(new_val) if field == "unit_price" else float(row.get("unit_price", 0))
            new_rev = round(units * price, 2)
            # Also fix closing stock if units_sold changed
            if field == "units_sold":
                opening = float(row.get("opening_stock", 0))
                new_closing = int(opening - units)
                db_update("sales", record_id, {
                    "total_revenue": new_rev,
                    "closing_stock": new_closing
                })
                cdc_log("sales", record_id, "closing_stock",
                        row.get("closing_stock", 0), new_closing,
                        changed_by, "Auto-recalculated after units_sold correction", company_id)
            else:
                db_update("sales", record_id, {"total_revenue": new_rev})
            cdc_log("sales", record_id, "total_revenue",
                    row.get("total_revenue", 0), new_rev,
                    changed_by, "Auto-recalculated after correction", company_id)
    return ok

# ─────────────────────────────────────────────
#  FRAUD SCORE
# ─────────────────────────────────────────────
def fraud_score(units_sold, opening, closing, unit_price, revenue, history_df) -> float:
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
        except: pass
    return min(round(score, 1), 100.0)

# ─────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────
def authenticate(username: str, password: str):
    df = db_fetch("users")
    if df.empty: return None, None
    row = df[(df["username"] == username) &
             (df["password_hash"] == hash_pw(password))]
    if row.empty: return None, None
    user = row.iloc[0].to_dict()

    # Superadmin bypasses company checks
    if user["role"] == "superadmin":
        return user, None

    # Check if user is active
    if not user.get("is_active", True):
        return None, "⛔ Your account has been disabled. Contact your administrator."

    # Check company
    company_id = user.get("company_id", "")
    if not company_id:
        return None, "No company assigned to your account."
    df_c = db_fetch("companies", {"id": company_id})
    if df_c.empty:
        return None, "Company not found."
    company = df_c.iloc[0].to_dict()
    if not company.get("is_active", False):
        return None, "⛔ Your company account is disabled. Please contact support."
    exp = company.get("subscription_expires")
    if exp:
        try:
            if date.today() > datetime.fromisoformat(str(exp)).date():
                return None, f"⏰ Subscription expired on {exp}. Please renew."
        except: pass
    return user, None

def ensure_superadmin():
    df = db_fetch("users", {"role": "superadmin"})
    if df.empty:
        db_insert("users", {
            "id":            new_uid(),
            "username":      "superadmin",
            "password_hash": hash_pw("Super@2025"),
            "role":          "superadmin",
            "company_id":    "",
            "branch":        "HQ",
            "is_active":     True,
            "must_set_password": False,
            "created_at":    datetime.now().isoformat(),
        })

# ─────────────────────────────────────────────
#  FIRST-LOGIN: SET OWN PASSWORD
# ─────────────────────────────────────────────
def page_set_password():
    u = st.session_state["user"]
    st.markdown('<div class="section-header">🔑 Set Your Password</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Your admin has created your account. Please set a personal password to continue.</div>',
                unsafe_allow_html=True)

    col, _ = st.columns([1.3, 1])
    with col:
        with st.form("set_pw_form"):
            new_pw  = st.text_input("New Password",     type="password")
            conf_pw = st.text_input("Confirm Password", type="password")
            submit  = st.form_submit_button("Set Password & Continue →", use_container_width=True)

        if submit:
            if len(new_pw) < 6:
                st.error("Password must be at least 6 characters.")
            elif new_pw != conf_pw:
                st.error("Passwords do not match.")
            else:
                db_update("users", u["id"], {
                    "password_hash":     hash_pw(new_pw),
                    "must_set_password": False,
                })
                cdc_log("users", u["id"], "password_hash",
                        "***", "***", u["username"],
                        "User set their own password on first login",
                        u.get("company_id",""))
                st.session_state["user"]["must_set_password"] = False
                st.success("✅ Password set! Welcome to SalesTrack Pro.")
                time.sleep(0.8)
                st.rerun()

# ─────────────────────────────────────────────
#  LOGIN PAGE
# ─────────────────────────────────────────────
def page_login():
    col, _ = st.columns([1.3, 1])
    with col:
        st.markdown("""
        <div style='text-align:center;margin-bottom:28px;'>
            <div style='width:60px;height:60px;background:linear-gradient(135deg,#5b5ef4,#7c3aed);
                        border-radius:16px;display:inline-flex;align-items:center;
                        justify-content:center;font-size:28px;margin-bottom:16px;'>📦</div>
            <h2 style='font-weight:800;margin-bottom:4px;'>SalesTrack Pro</h2>
            <p style='color:#6b7280;font-size:13px;'>Sign in to access your dashboard</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            ok       = st.form_submit_button("Sign In →", use_container_width=True)

        if ok:
            with st.spinner("Authenticating…"):
                user, error = authenticate(username, password)
            if error:
                st.error(error)
            elif user:
                company = {}
                if user["role"] != "superadmin" and user.get("company_id"):
                    df_c = db_fetch("companies", {"id": user["company_id"]})
                    if not df_c.empty:
                        company = df_c.iloc[0].to_dict()
                st.session_state.update(
                    logged_in=True, user=user,
                    role=user["role"], company=company)
                st.success(f"Welcome, **{username}**!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Invalid username or password.")

        st.caption("Contact your administrator if you need access.")

# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────
def sidebar() -> str:
    with st.sidebar:
        st.markdown("## 📦 SalesTrack Pro")
        st.markdown("---")

        if not st.session_state.get("logged_in"):
            st.markdown("Please sign in to continue.")
            st.markdown("---")
            st.caption("© 2025 SalesTrack Pro")
            return "🔑 Login"

        u    = st.session_state["user"]
        role = u["role"]
        st.markdown(f"**{u['username']}**")
        st.markdown(role_badge(role), unsafe_allow_html=True)
        company = st.session_state.get("company", {})
        if role != "superadmin" and company:
            st.caption(f"🏢 {company.get('name','—')}")
            st.caption(f"🌿 {u.get('branch','—')}")
        st.markdown("---")

        if role == "superadmin":
            pages = ["🏢 Companies","👤 All Users","📊 Platform Stats","⚙️ Super Settings"]
        elif role == "admin":
            pages = ["📊 Dashboard","📝 Sales Entry","✏️ Corrections",
                     "👥 Sellers","📦 Products","🔐 Users","⚙️ Settings"]
        elif role == "manager":
            pages = ["📊 Dashboard","📝 Sales Entry","✏️ Corrections",
                     "👥 Sellers","📦 Products"]
        else:  # sales
            pages = ["📊 Dashboard","📝 Sales Entry","✏️ My Corrections"]

        page = st.radio("", pages, label_visibility="collapsed")
        st.markdown("---")

        st.markdown("""
        <button onclick='installPWA()'
            style='background:linear-gradient(135deg,#5b5ef4,#7c3aed);color:white;
                   border:none;border-radius:10px;padding:8px 16px;font-size:13px;
                   font-weight:600;cursor:pointer;width:100%;margin-bottom:10px;'>
            📱 Install as App
        </button>""", unsafe_allow_html=True)

        if st.button("🚪 Sign Out"):
            for k in ["logged_in","user","role","company"]:
                st.session_state.pop(k, None)
            st.rerun()

        st.markdown("---")
        st.caption("© 2025 SalesTrack Pro")
    return page

# ─────────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────────
def page_dashboard():
    u          = st.session_state["user"]
    company    = st.session_state.get("company", {})
    company_id = u.get("company_id","")

    st.markdown('<div class="section-header">📊 Sales Dashboard</div>', unsafe_allow_html=True)
    if company:
        exp = company.get("subscription_expires","")
        if exp:
            try:
                days = (datetime.fromisoformat(str(exp)).date() - date.today()).days
                if 0 < days <= 7:
                    st.warning(f"⚠️ Subscription expires in **{days} days** ({exp}). Please renew.")
            except: pass
        st.markdown(f'<div class="section-sub">{company.get("name","")} · Plan: {company.get("plan","")}</div>',
                    unsafe_allow_html=True)

    df = db_fetch("sales", {"company_id": company_id}) if company_id else db_fetch("sales")
    if df.empty:
        st.info("No sales data yet. Add products & sellers, then submit entries.")
        return

    for c in ["units_sold","unit_price","total_revenue","fraud_score"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    k1,k2,k3,k4 = st.columns(4)
    k1.metric("💰 Total Revenue",   fmt(df["total_revenue"].sum()))
    k2.metric("📦 Units Sold",      f"{int(df['units_sold'].sum()):,}")
    k3.metric("🧾 Entries",         f"{len(df):,}")
    k4.metric("📈 Avg Order Value", fmt(df["total_revenue"].mean()))
    st.markdown("---")

    c1,c2 = st.columns(2)
    start = c1.date_input("From", value=date.today().replace(day=1))
    end   = c2.date_input("To",   value=date.today())
    if "date" in df.columns:
        df = df[(df["date"].dt.date >= start) & (df["date"].dt.date <= end)]
    if df.empty:
        st.warning("No data for selected range.")
        return

    role = u["role"]
    if role in ("admin","manager") and "fraud_score" in df.columns:
        high = df[df["fraud_score"] >= 60]
        if not high.empty:
            st.error(f"🚨 **{len(high)} high-risk entries** flagged — review in Corrections.")

    PLOT = dict(plot_bgcolor="#0b0d14",paper_bgcolor="#0b0d14",
                font_color="#c5c9e0",margin=dict(t=20,b=20))

    tab1,tab2,tab3,tab4 = st.tabs(["📈 Revenue","🏆 Leaderboard","📦 Products","🗃️ Data"])

    with tab1:
        if "date" in df.columns:
            trend = df.groupby(df["date"].dt.date)["total_revenue"].sum().reset_index()
            trend.columns = ["date","revenue"]
            fig = px.area(trend, x="date", y="revenue",
                          color_discrete_sequence=["#5b5ef4"],
                          labels={"revenue":"Revenue (₦)","date":"Date"})
            fig.update_layout(**PLOT,
                              yaxis=dict(gridcolor="#1e2235",tickprefix="₦"),
                              xaxis=dict(showgrid=False))
            st.plotly_chart(fig, use_container_width=True)
            df["month"] = df["date"].dt.to_period("M").astype(str)
            monthly = df.groupby("month")["total_revenue"].sum().reset_index()
            if len(monthly) > 1:
                st.markdown("#### Monthly Revenue")
                fig2 = px.bar(monthly, x="month", y="total_revenue",
                              color_discrete_sequence=["#7c3aed"],
                              labels={"total_revenue":"Revenue (₦)","month":"Month"})
                fig2.update_layout(**PLOT,yaxis=dict(gridcolor="#1e2235",tickprefix="₦"))
                st.plotly_chart(fig2, use_container_width=True)

    with tab2:
        if "seller_name" in df.columns:
            lb = (df.groupby("seller_name")
                  .agg(Revenue=("total_revenue","sum"),
                       Units=("units_sold","sum"),
                       Entries=("id","count"))
                  .sort_values("Revenue",ascending=False).reset_index())
            lb["Rev_fmt"] = lb["Revenue"].apply(fmt)
            fig = px.bar(lb, x="seller_name", y="Revenue", text="Rev_fmt",
                         color="Revenue",
                         color_continuous_scale=["#1e2235","#5b5ef4","#7c3aed"])
            fig.update_layout(**PLOT,showlegend=False,coloraxis_showscale=False)
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(lb[["seller_name","Rev_fmt","Units","Entries"]]
                         .rename(columns={"seller_name":"Seller","Rev_fmt":"Revenue"}),
                         use_container_width=True, hide_index=True)

    with tab3:
        if "product_name" in df.columns:
            prod = (df.groupby("product_name")
                    .agg(Revenue=("total_revenue","sum"),Units=("units_sold","sum"))
                    .sort_values("Revenue",ascending=False).reset_index())
            ca,cb = st.columns(2)
            with ca:
                fig = px.pie(prod,names="product_name",values="Revenue",
                             color_discrete_sequence=px.colors.sequential.Purples_r)
                fig.update_layout(**PLOT)
                st.plotly_chart(fig,use_container_width=True)
            with cb:
                fig2 = px.bar(prod,x="product_name",y="Units",
                              color_discrete_sequence=["#10b981"])
                fig2.update_layout(**PLOT,yaxis=dict(gridcolor="#1e2235"))
                st.plotly_chart(fig2,use_container_width=True)

    with tab4:
        show = [c for c in ["date","seller_name","product_name","branch",
                            "customer_name","invoice_no","units_sold",
                            "unit_price","total_revenue","payment_method","fraud_score"]
                if c in df.columns]
        st.dataframe(df[show],use_container_width=True,hide_index=True)
        st.download_button("⬇️ Export CSV",
                           df.to_csv(index=False).encode(),
                           file_name=f"sales_{date.today()}.csv",mime="text/csv")

# ─────────────────────────────────────────────
#  SALES ENTRY
# ─────────────────────────────────────────────
def page_sales_entry():
    u          = st.session_state["user"]
    company_id = u.get("company_id","")
    company    = st.session_state.get("company",{})

    st.markdown('<div class="section-header">📝 Daily Sales Entry</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="section-sub">{u["username"]} · {u.get("branch","")} · {company.get("name","")}</div>',
                unsafe_allow_html=True)

    df_p = db_fetch("products", {"company_id": company_id})
    df_s = db_fetch("sellers",  {"company_id": company_id})
    df_h = db_fetch("sales",    {"company_id": company_id})

    products = df_p["name"].tolist() if not df_p.empty and "name" in df_p.columns else ["No products — ask admin"]
    sellers  = df_s["name"].tolist() if not df_s.empty and "name" in df_s.columns else [u["username"]]

    # ── Live calculation outside form using session state ──
    st.markdown(f"**📅 {date.today().strftime('%A, %d %B %Y')}**")
    st.markdown("---")

    with st.form("entry_form", clear_on_submit=True):
        c1,c2 = st.columns(2)
        seller_name    = c1.selectbox("👤 Salesperson", sellers)
        branch         = c1.text_input("🏢 Branch", value=u.get("branch",""))
        product_name   = c2.selectbox("📦 Product", products)
        payment_method = c2.selectbox("💳 Payment Method",
                                      ["Cash","Bank Transfer","POS","Cheque","Mixed"])

        c3,c4 = st.columns(2)
        customer_name  = c3.text_input("🧑 Customer Name")
        customer_phone = c3.text_input("📞 Customer Phone")
        invoice_no     = c4.text_input("🧾 Invoice No.", value=f"INV-{new_uid()}")
        unit_price     = c4.number_input("💰 Unit Price (₦)", min_value=0.0, step=50.0,
                                          help="Price per unit sold")

        st.markdown("---")
        st.markdown("**📦 Stock Details**")
        c5,c6,c7 = st.columns(3)

        opening_stock = c5.number_input("📥 Opening Stock",
                                         min_value=0, step=1,
                                         help="Total stock at start of day")
        units_sold    = c6.number_input("📤 Units Sold",
                                         min_value=0, step=1,
                                         help="How many units sold today")

        # Auto-calculate closing stock
        auto_closing  = max(0, opening_stock - units_sold)
        closing_stock = c7.number_input("📦 Closing Stock",
                                         min_value=0, step=1,
                                         value=auto_closing,
                                         help="Auto-calculated: Opening − Sold")

        notes = st.text_area("📋 Notes (optional)", height=60)

        # ── Revenue & stock preview inside form ──
        revenue  = units_sold * unit_price
        expected = opening_stock - units_sold
        stock_ok = closing_stock == expected

        st.markdown(f"""
        <div class='rev-box'>
            <div style='font-size:11px;color:#6b7280;font-weight:600;
                        text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;'>
                ✅ Confirm Before Submitting</div>
            <div style='display:flex;justify-content:space-between;align-items:center;'>
                <div>
                    <div style='font-size:12px;color:#6b7280;'>Revenue</div>
                    <div style='font-size:32px;font-weight:800;
                                background:linear-gradient(135deg,#5b5ef4,#7c3aed);
                                -webkit-background-clip:text;-webkit-text-fill-color:transparent;'>
                        {fmt(revenue)}</div>
                </div>
                <div style='text-align:right;font-size:13px;'>
                    <div>Units: <b>{units_sold}</b> × <b>{fmt(unit_price)}</b></div>
                    <div style='margin-top:4px;color:{"#10b981" if stock_ok else "#f59e0b"}'>
                        {"✅ Stock OK" if stock_ok
                          else f"⚠️ Expected closing: {expected} (got {closing_stock})"}
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        submitted = st.form_submit_button("✅ Submit Entry", use_container_width=True)

    if submitted:
        if units_sold == 0:
            st.warning("Units sold cannot be zero.")
            return
        if unit_price == 0:
            st.warning("Unit price cannot be zero.")
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
            "company_id":     company_id,
            "created_at":     datetime.now().isoformat(),
        })

        if ok:
            st.success(f"✅ Entry saved! Invoice **{invoice_no}** · Revenue **{fmt(revenue)}**")
            if fs >= 60:
                st.error(f"🚨 High risk score ({fs}/100) — a manager will review this entry.")
            elif fs >= 25:
                st.warning(f"⚠️ Anomaly detected ({fs}/100) — please verify your stock figures.")
            time.sleep(0.5)
            st.rerun()

# ─────────────────────────────────────────────
#  CORRECTIONS  — Manager/Admin view
# ─────────────────────────────────────────────
def page_corrections():
    u          = st.session_state["user"]
    company_id = u.get("company_id","")
    role       = u["role"]

    st.markdown('<div class="section-header">✏️ Data Corrections</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Every change is permanently logged in the audit trail</div>',
                unsafe_allow_html=True)

    df = db_fetch("sales", {"company_id": company_id})
    if df.empty:
        st.info("No records yet.")
        return

    for c in ["units_sold","unit_price","total_revenue","fraud_score"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # Manager/Admin can search all; sales role searches only their own
    st.markdown("#### 🔍 Find Record to Correct")
    sc1,sc2 = st.columns(2)
    by   = sc1.selectbox("Search by", ["invoice_no","seller_name","id"])
    term = sc2.text_input("Search value")

    if not term:
        st.info("Enter a search value above to find a record.")
        _show_cdc_log(company_id)
        return

    found = df[df[by].astype(str).str.contains(term, case=False, na=False)]

    # Sales role can only correct their own records
    if role == "sales":
        found = found[found["seller_name"] == u["username"]] if "seller_name" in found.columns else found

    if found.empty:
        st.warning("No matching records found.")
        _show_cdc_log(company_id)
        return

    st.dataframe(found, use_container_width=True, hide_index=True)
    record_id = st.selectbox("Select Record ID to correct",
                             found["id"].tolist() if "id" in found.columns else [])

    if record_id:
        rec = df[df["id"]==record_id].iloc[0]

        # Fields a sales rep can correct on their own entries
        if role == "sales":
            editable = ["product_name","customer_phone","opening_stock",
                        "units_sold","closing_stock","unit_price","payment_method"]
        else:
            editable = ["product_name","customer_name","customer_phone",
                        "opening_stock","units_sold","closing_stock",
                        "unit_price","payment_method","notes","invoice_no"]

        with st.form("corr_form"):
            st.markdown(f"**✏️ Editing Record `{record_id}`**")
            field = st.selectbox("Field to correct", editable)
            cur   = str(rec.get(field,""))
            st.markdown(f"""
            <div style='background:#0b0d14;border:1px solid #1e2235;border-radius:8px;
                        padding:10px 14px;margin-bottom:12px;font-size:13px;color:#6b7280;'>
                Current value: <span style='color:#e2e4ed;font-weight:600;'>{cur}</span>
            </div>""", unsafe_allow_html=True)
            new_val = st.text_input("New value", placeholder="Enter the corrected value")

            st.markdown("---")
            reason = st.text_area(
                "📋 Reason for correction *(required — this is saved permanently)*",
                height=90,
                placeholder="e.g. Wrong units entered — actual sale was 5 units not 10"
            )

            save = st.form_submit_button("💾 Save Correction", use_container_width=True)

        if save:
            if not new_val.strip():
                st.error("Please enter a new value.")
                return
            if not reason.strip():
                st.error("⚠️ Reason is required. Please explain why this correction is being made.")
                return
            if new_val.strip() == cur.strip():
                st.warning("New value is the same as the current value — no change made.")
                return
            if correct_sale(record_id, field, new_val.strip(), u["username"],
                            reason.strip(), company_id):
                st.success(f"✅ **{field}** corrected from `{cur}` → `{new_val.strip()}`. CDC logged.")
                st.rerun()

    _show_cdc_log(company_id)


def _show_cdc_log(company_id: str):
    st.markdown("---")
    st.markdown("#### 📜 Full Audit Log (CDC)")
    try:
        r = get_sb().table("cdc_log").select("*").eq("company_id", company_id)\
                    .order("changed_at", desc=True).execute()
        df_cdc = pd.DataFrame(r.data) if r.data else pd.DataFrame()
    except Exception as e:
        st.error(f"Could not load CDC log: {e}")
        return

    if df_cdc.empty:
        st.info("No corrections have been made yet.")
    else:
        st.dataframe(df_cdc, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Export CDC Log",
                           df_cdc.to_csv(index=False).encode(),
                           file_name=f"cdc_log_{date.today()}.csv", mime="text/csv")


# ─────────────────────────────────────────────
#  SALES — MY CORRECTIONS  (sales role only)
# ─────────────────────────────────────────────
def page_my_corrections():
    st.markdown('<div class="section-header">✏️ My Corrections</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">You can only correct your own entries. All changes are logged.</div>',
                unsafe_allow_html=True)
    page_corrections()  # reuses same function — role check inside handles restriction

# ─────────────────────────────────────────────
#  SELLERS
# ─────────────────────────────────────────────
def page_sellers():
    u   = st.session_state["user"]
    cid = u.get("company_id","")
    st.markdown('<div class="section-header">👥 Manage Sellers</div>', unsafe_allow_html=True)

    with st.form("add_seller", clear_on_submit=True):
        st.markdown("#### ➕ Add Seller")
        c1,c2 = st.columns(2)
        name   = c1.text_input("Seller Name")
        branch = c2.text_input("Branch")
        if st.form_submit_button("Add Seller") and name.strip():
            db_insert("sellers", {
                "id": new_uid(), "name": name.strip(),
                "branch": branch.strip(), "company_id": cid,
                "created_at": datetime.now().isoformat()
            })
            st.success(f"✅ {name} added.")
            st.rerun()

    st.markdown("---")
    df = db_fetch("sellers", {"company_id": cid})
    if df.empty:
        st.info("No sellers yet.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────
#  PRODUCTS  — with edit
# ─────────────────────────────────────────────
def page_products():
    u   = st.session_state["user"]
    cid = u.get("company_id","")
    st.markdown('<div class="section-header">📦 Manage Products</div>', unsafe_allow_html=True)

    tab_add, tab_edit = st.tabs(["➕ Add Product", "✏️ Edit Product"])

    with tab_add:
        with st.form("add_product", clear_on_submit=True):
            c1,c2 = st.columns(2)
            name = c1.text_input("Product Name")
            cat  = c2.text_input("Category (optional)")
            if st.form_submit_button("Add Product") and name.strip():
                db_insert("products", {
                    "id": new_uid(), "name": name.strip(),
                    "category": cat.strip(), "company_id": cid,
                    "created_at": datetime.now().isoformat()
                })
                st.success(f"✅ {name} added.")
                st.rerun()

    with tab_edit:
        df = db_fetch("products", {"company_id": cid})
        if df.empty:
            st.info("No products to edit yet.")
        else:
            product_options = dict(zip(df["name"].tolist(), df["id"].tolist()))
            selected_name   = st.selectbox("Select product to edit",
                                           list(product_options.keys()))
            selected_id     = product_options[selected_name]
            selected_row    = df[df["id"]==selected_id].iloc[0]

            with st.form("edit_product"):
                new_name = st.text_input("Product Name", value=selected_row.get("name",""))
                new_cat  = st.text_input("Category",     value=selected_row.get("category",""))
                reason   = st.text_area("Reason for change *(required)*", height=70)
                save_edit = st.form_submit_button("💾 Save Changes")

            if save_edit:
                if not reason.strip():
                    st.error("⚠️ Please provide a reason for the change.")
                else:
                    changed = False
                    if new_name.strip() != selected_row.get("name",""):
                        db_update("products", selected_id, {"name": new_name.strip()})
                        cdc_log("products", selected_id, "name",
                                selected_row.get("name",""), new_name.strip(),
                                u["username"], reason.strip(), cid)
                        changed = True
                    if new_cat.strip() != selected_row.get("category",""):
                        db_update("products", selected_id, {"category": new_cat.strip()})
                        cdc_log("products", selected_id, "category",
                                selected_row.get("category",""), new_cat.strip(),
                                u["username"], reason.strip(), cid)
                        changed = True
                    if changed:
                        st.success("✅ Product updated. Change logged.")
                        st.rerun()
                    else:
                        st.info("No changes detected.")

    st.markdown("---")
    st.markdown("#### 📋 All Products")
    df = db_fetch("products", {"company_id": cid})
    if df.empty:
        st.info("No products yet.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────
#  USERS  — company admin
# ─────────────────────────────────────────────
def page_users():
    u   = st.session_state["user"]
    cid = u.get("company_id","")
    st.markdown('<div class="section-header">🔐 User Management</div>', unsafe_allow_html=True)

    with st.form("add_user", clear_on_submit=True):
        st.markdown("#### ➕ Create User")
        st.info("💡 The new user will be prompted to set their own password on first login.")
        c1,c2 = st.columns(2)
        uname   = c1.text_input("Username")
        urole   = c1.selectbox("Role", ["sales","manager","admin"])
        ubranch = c2.text_input("Branch")
        # Temporary password — user must change on first login
        temp_pw = c2.text_input("Temporary Password", type="password",
                                 help="User will be forced to set their own password on first login")

        if st.form_submit_button("Create User"):
            if not uname.strip() or not temp_pw.strip():
                st.error("Username and temporary password required.")
            else:
                df_u = db_fetch("users")
                if not df_u.empty and uname in df_u.get("username", pd.Series()).values:
                    st.error("Username already exists.")
                else:
                    db_insert("users", {
                        "id":                new_uid(),
                        "username":          uname.strip(),
                        "password_hash":     hash_pw(temp_pw),
                        "role":              urole,
                        "branch":            ubranch.strip(),
                        "company_id":        cid,
                        "is_active":         True,
                        "must_set_password": True,
                        "created_at":        datetime.now().isoformat(),
                    })
                    st.success(f"✅ User **{uname}** ({urole}) created. They will set their password on first login.")
                    st.rerun()

    # ── User list with enable/disable ──
    st.markdown("---")
    st.markdown("#### 👥 All Users")
    df = db_fetch("users", {"company_id": cid})
    if df.empty:
        st.info("No users yet.")
        return

    for _, row in df.iterrows():
        if row.get("role") == "superadmin":
            continue
        is_active = row.get("is_active", True)
        status_color = "#10b981" if is_active else "#ef4444"
        status_text  = "Active" if is_active else "Disabled"

        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        col1.markdown(f"""
        <div style='padding:8px 0;'>
            <span style='font-weight:600;'>{row.get('username','—')}</span>
            <span style='margin-left:10px;font-size:11px;color:{status_color};
                         font-weight:700;'>{status_text}</span><br>
            <span style='font-size:12px;color:#6b7280;'>
                {row.get('role','').upper()} · {row.get('branch','—')}
            </span>
        </div>""", unsafe_allow_html=True)

        col2.markdown(" ")
        with col3:
            if is_active:
                if st.button("🔴 Disable", key=f"dis_u_{row['id']}"):
                    db_update("users", row["id"], {"is_active": False})
                    cdc_log("users", row["id"], "is_active", True, False,
                            u["username"], "Admin disabled user account", cid)
                    st.success(f"User **{row['username']}** disabled.")
                    st.rerun()
            else:
                if st.button("🟢 Enable", key=f"en_u_{row['id']}"):
                    db_update("users", row["id"], {"is_active": True})
                    cdc_log("users", row["id"], "is_active", False, True,
                            u["username"], "Admin re-enabled user account", cid)
                    st.success(f"User **{row['username']}** enabled.")
                    st.rerun()

        st.markdown("---")

# ─────────────────────────────────────────────
#  SETTINGS — company admin
# ─────────────────────────────────────────────
def page_settings():
    u = st.session_state["user"]
    st.markdown('<div class="section-header">⚙️ Settings</div>', unsafe_allow_html=True)
    st.markdown("#### 🔑 Change My Password")
    with st.form("pw_form"):
        old = st.text_input("Current Password", type="password")
        new = st.text_input("New Password",      type="password")
        cf  = st.text_input("Confirm Password",  type="password")
        if st.form_submit_button("Update Password"):
            if hash_pw(old) != u.get("password_hash",""):
                st.error("Current password is incorrect.")
            elif new != cf:
                st.error("Passwords do not match.")
            elif len(new) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                db_update("users", u["id"], {"password_hash": hash_pw(new)})
                st.session_state["user"]["password_hash"] = hash_pw(new)
                cdc_log("users", u["id"], "password_hash", "***", "***",
                        u["username"], "Password changed by user",
                        u.get("company_id",""))
                st.success("✅ Password updated successfully.")

# ─────────────────────────────────────────────
#  SUPERADMIN — COMPANIES
# ─────────────────────────────────────────────
def page_companies():
    st.markdown('<div class="section-header">🏢 Company Management</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Add companies, manage subscriptions, enable or disable access</div>',
                unsafe_allow_html=True)

    with st.expander("➕ Add New Company"):
        with st.form("add_company"):
            c1,c2 = st.columns(2)
            cname   = c1.text_input("Company Name")
            cemail  = c1.text_input("Contact Email")
            cphone  = c2.text_input("Contact Phone")
            cplan   = c2.selectbox("Plan", ["Basic","Standard","Premium"])
            exp_date= st.date_input("Subscription Expires",
                                    value=date.today()+timedelta(days=30))
            if st.form_submit_button("Create Company"):
                if cname.strip():
                    cid = new_uid()
                    db_insert("companies", {
                        "id": cid, "name": cname.strip(),
                        "email": cemail.strip(), "phone": cphone.strip(),
                        "plan": cplan, "is_active": True,
                        "subscription_expires": str(exp_date),
                        "created_at": datetime.now().isoformat(),
                    })
                    st.success(f"✅ **{cname}** created! Company ID: `{cid}`")
                    st.info(f"Go to 👤 All Users → create an admin user with this company.")
                    st.rerun()

    st.markdown("---")
    df = db_fetch("companies")
    if df.empty:
        st.info("No companies yet.")
        return

    for _, row in df.iterrows():
        is_active = row.get("is_active", True)
        exp       = row.get("subscription_expires","")
        expired   = False
        if exp:
            try:
                expired = date.today() > datetime.fromisoformat(str(exp)).date()
            except: pass

        if not is_active:    status, cls, icon = "DISABLED", "company-inactive", "🔴"
        elif expired:         status, cls, icon = "EXPIRED",  "company-expired",  "🟡"
        else:                 status, cls, icon = "ACTIVE",   "company-active",   "🟢"

        st.markdown(f"""
        <div class='company-card {cls}'>
            <div style='display:flex;justify-content:space-between;'>
                <div>
                    <span style='font-size:16px;font-weight:700;'>{row.get('name','—')}</span>
                    &nbsp;<span style='font-size:11px;color:#6b7280;'>{icon} {status}</span>
                </div>
                <div style='font-size:12px;color:#6b7280;'>
                    Plan: <b>{row.get('plan','—')}</b> · Expires: <b>{exp}</b>
                    · ID: <code>{row.get('id','—')}</code>
                </div>
            </div>
            <div style='font-size:12px;color:#6b7280;margin-top:6px;'>
                📧 {row.get('email','—')} · 📞 {row.get('phone','—')}
            </div>
        </div>""", unsafe_allow_html=True)

        bt1,bt2,bt3,bt4 = st.columns([1,1,1,2])
        with bt1:
            if is_active:
                if st.button("🔴 Disable", key=f"dis_c_{row['id']}"):
                    db_update("companies", row["id"], {"is_active": False})
                    st.success("Company disabled."); st.rerun()
            else:
                if st.button("🟢 Enable", key=f"en_c_{row['id']}"):
                    db_update("companies", row["id"], {"is_active": True})
                    st.success("Company enabled."); st.rerun()
        with bt2:
            new_exp = st.date_input("Renew until",
                                    value=date.today()+timedelta(days=30),
                                    key=f"exp_{row['id']}",
                                    label_visibility="collapsed")
        with bt3:
            if st.button("🔄 Renew", key=f"ren_{row['id']}"):
                db_update("companies", row["id"],
                          {"subscription_expires": str(new_exp), "is_active": True})
                st.success(f"✅ Renewed until {new_exp}"); st.rerun()
        st.markdown("---")

# ─────────────────────────────────────────────
#  SUPERADMIN — ALL USERS
# ─────────────────────────────────────────────
def page_all_users():
    st.markdown('<div class="section-header">👤 All Users</div>', unsafe_allow_html=True)
    df_c = db_fetch("companies")
    company_map = {}
    if not df_c.empty and "id" in df_c.columns:
        company_map = dict(zip(df_c["id"], df_c["name"]))

    company_options = {v: k for k, v in company_map.items()}

    with st.form("add_user_super", clear_on_submit=True):
        st.markdown("#### ➕ Create User for Company")
        st.info("💡 User will be forced to set their own password on first login.")
        c1,c2,c3 = st.columns(3)
        uname     = c1.text_input("Username")
        temp_pw   = c1.text_input("Temporary Password", type="password")
        urole     = c2.selectbox("Role", ["admin","manager","sales"])
        ubranch   = c2.text_input("Branch")
        comp_name = c3.selectbox("Company",
                                  list(company_options.keys()) or ["— No companies yet —"])
        if st.form_submit_button("Create User"):
            if uname.strip() and temp_pw.strip() and comp_name in company_options:
                df_u = db_fetch("users")
                if not df_u.empty and uname in df_u.get("username", pd.Series()).values:
                    st.error("Username already exists.")
                else:
                    db_insert("users", {
                        "id":                new_uid(),
                        "username":          uname.strip(),
                        "password_hash":     hash_pw(temp_pw),
                        "role":              urole,
                        "branch":            ubranch.strip(),
                        "company_id":        company_options[comp_name],
                        "is_active":         True,
                        "must_set_password": True,
                        "created_at":        datetime.now().isoformat(),
                    })
                    st.success(f"✅ **{uname}** ({urole}) created for **{comp_name}**.")
                    st.rerun()

    st.markdown("---")
    df = db_fetch("users")
    if not df.empty:
        if "company_id" in df.columns:
            df["company_name"] = df["company_id"].map(company_map).fillna("superadmin")
        cols = [c for c in ["username","role","company_name","branch",
                             "is_active","must_set_password","created_at"]
                if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────
#  SUPERADMIN — PLATFORM STATS
# ─────────────────────────────────────────────
def page_platform_stats():
    st.markdown('<div class="section-header">📊 Platform Overview</div>', unsafe_allow_html=True)
    df_c = db_fetch("companies")
    df_s = db_fetch("sales")
    df_u = db_fetch("users")

    active  = len(df_c[df_c["is_active"]==True]) if not df_c.empty and "is_active" in df_c.columns else 0
    total_c = len(df_c) if not df_c.empty else 0
    total_u = len(df_u[df_u["role"]!="superadmin"]) if not df_u.empty and "role" in df_u.columns else 0
    total_r = 0
    if not df_s.empty and "total_revenue" in df_s.columns:
        total_r = pd.to_numeric(df_s["total_revenue"], errors="coerce").sum()

    k1,k2,k3,k4 = st.columns(4)
    k1.metric("🏢 Companies",        total_c)
    k2.metric("🟢 Active",           active)
    k3.metric("👤 Users",            total_u)
    k4.metric("💰 Platform Revenue", fmt(total_r))

    if not df_s.empty and "total_revenue" in df_s.columns and "company_id" in df_s.columns:
        st.markdown("---")
        df_s["total_revenue"] = pd.to_numeric(df_s["total_revenue"], errors="coerce").fillna(0)
        by_co = (df_s.groupby("company_id")["total_revenue"]
                 .sum().reset_index().sort_values("total_revenue",ascending=False))
        if not df_c.empty:
            cm = dict(zip(df_c["id"], df_c["name"]))
            by_co["company_name"] = by_co["company_id"].map(cm)
        PLOT = dict(plot_bgcolor="#0b0d14",paper_bgcolor="#0b0d14",
                    font_color="#c5c9e0",margin=dict(t=20,b=20))
        fig = px.bar(by_co, x="company_name", y="total_revenue",
                     color_discrete_sequence=["#5b5ef4"],
                     labels={"company_name":"Company","total_revenue":"Revenue (₦)"})
        fig.update_layout(**PLOT, yaxis=dict(gridcolor="#1e2235",tickprefix="₦"))
        st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────────
#  SUPERADMIN — SETTINGS
# ─────────────────────────────────────────────
def page_super_settings():
    u = st.session_state["user"]
    st.markdown('<div class="section-header">⚙️ Super Settings</div>', unsafe_allow_html=True)
    st.markdown("#### 🔑 Change Superadmin Password")
    with st.form("super_pw"):
        old = st.text_input("Current Password", type="password")
        new = st.text_input("New Password",      type="password")
        cf  = st.text_input("Confirm",           type="password")
        if st.form_submit_button("Update Password"):
            if hash_pw(old) != u.get("password_hash",""):
                st.error("Current password incorrect.")
            elif new != cf:
                st.error("Passwords do not match.")
            elif len(new) < 8:
                st.error("Minimum 8 characters.")
            else:
                db_update("users", u["id"], {"password_hash": hash_pw(new)})
                st.session_state["user"]["password_hash"] = hash_pw(new)
                st.success("✅ Password updated.")

# ─────────────────────────────────────────────
#  MAIN ROUTER
# ─────────────────────────────────────────────
def main():
    try: ensure_superadmin()
    except: pass

    page = sidebar()
    role = st.session_state.get("role","")

    # ── Not logged in ──
    if not st.session_state.get("logged_in"):
        page_login()
        return

    u = st.session_state["user"]

    # ── Force password set on first login ──
    if u.get("must_set_password") and u["role"] != "superadmin":
        page_set_password()
        return

    # ── Superadmin routes ──
    if role == "superadmin":
        {
            "🏢 Companies":      page_companies,
            "👤 All Users":      page_all_users,
            "📊 Platform Stats": page_platform_stats,
            "⚙️ Super Settings": page_super_settings,
        }.get(page, page_companies)()
        return

    # ── Company user routes ──
    {
        "📊 Dashboard":      page_dashboard,
        "📝 Sales Entry":    page_sales_entry,
        "✏️ Corrections":    page_corrections    if role in ("admin","manager") else lambda: st.error("Access denied."),
        "✏️ My Corrections": page_my_corrections if role == "sales"            else lambda: st.error("Access denied."),
        "👥 Sellers":        page_sellers        if role in ("admin","manager") else lambda: st.error("Access denied."),
        "📦 Products":       page_products       if role in ("admin","manager") else lambda: st.error("Access denied."),
        "🔐 Users":          page_users          if role == "admin"            else lambda: st.error("Access denied."),
        "⚙️ Settings":       page_settings       if role == "admin"            else lambda: st.error("Access denied."),
    }.get(page, page_dashboard)()


if __name__ == "__main__":
    main()
