import streamlit as st
import sqlite3
import pandas as pd
from datetime import date
import math
import plotly.graph_objects as go

# ─── Constants ────────────────────────────────────────────────────────────────
DB_PATH = "finanzas.db"

CATEGORIAS_INGRESO = ["Salario", "Préstamo", "Otro"]
CATEGORIAS_GASTO   = ["Alimentación", "Transporte", "Vivienda", "Salud", "Educación",
                      "Entretenimiento", "Ropa", "Servicios", "Deudas", "Otro gasto"]
TIPOS_ACTIVO       = ["Acciones", "Crypto", "Ahorro", "Inmuebles", "Bonos", "Otro"]
TIPOS_DEUDA        = ["Tarjeta de crédito", "Préstamo personal", "Hipoteca", "Auto", "Estudiantil", "Otro"]
CUENTAS            = ["Efectivo", "Cuenta bancaria", "Tarjeta de débito",
                      "Tarjeta de crédito", "Billetera digital", "Transferencia", "Otro"]
META_EMOJIS        = ["🎯", "✈️", "🏠", "🚗", "💍", "🎓", "🏖️", "💪", "🛍️", "🌟"]

CUENTA_ICONS = {
    "Efectivo":"💵","Cuenta bancaria":"🏦","Tarjeta de débito":"💳",
    "Tarjeta de crédito":"💳","Billetera digital":"📱","Transferencia":"🔄","Otro":"🏷️",
}
CAT_ICONS = {
    "Salario":"💼","Préstamo":"🏦","Otro":"💰",
    "Alimentación":"🛒","Transporte":"🚗","Vivienda":"🏠","Salud":"💊","Educación":"📚",
    "Entretenimiento":"🎬","Ropa":"👗","Servicios":"⚡","Deudas":"💳","Otro gasto":"📦",
    "Acciones":"📊","Crypto":"₿","Ahorro":"🏦","Inmuebles":"🏡","Bonos":"📜","Otro":"💎",
}
DEUDA_ICONS = {
    "Tarjeta de crédito":"💳","Préstamo personal":"🤝","Hipoteca":"🏠",
    "Auto":"🚗","Estudiantil":"🎓","Otro":"📋",
}
CHART_COLORS = ["#00C896","#00A878","#FFB547","#64A0FF","#A78BFA",
                "#F472B6","#FF4757","#FF6B7A","#008C64","#006E50"]

# ─── Database ─────────────────────────────────────────────────────────────────
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS transacciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL,
                tipo TEXT NOT NULL, categoria TEXT NOT NULL,
                descripcion TEXT, monto REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS portafolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL,
                tipo TEXT NOT NULL, cantidad REAL NOT NULL,
                valor_unitario REAL NOT NULL, fecha TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS deudas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL,
                tipo TEXT NOT NULL, deuda_inicial REAL NOT NULL,
                saldo REAL NOT NULL, tasa_interes REAL NOT NULL DEFAULT 0,
                pago_minimo REAL NOT NULL DEFAULT 0, fecha_inicio TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pagos_deuda (
                id INTEGER PRIMARY KEY AUTOINCREMENT, deuda_id INTEGER NOT NULL,
                fecha TEXT NOT NULL, monto REAL NOT NULL, nota TEXT
            );
            CREATE TABLE IF NOT EXISTS metas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL,
                objetivo REAL NOT NULL, actual REAL NOT NULL DEFAULT 0,
                fecha_limite TEXT, emoji TEXT NOT NULL DEFAULT '🎯'
            );
        """)
        conn.commit()
        try:
            conn.execute("ALTER TABLE transacciones ADD COLUMN cuenta TEXT DEFAULT 'Efectivo'")
            conn.commit()
        except Exception:
            pass

def run(sql, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(sql, params)
        conn.commit()

def query(sql, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(sql, conn, params=params)

# ─── Helpers ──────────────────────────────────────────────────────────────────
def cop(n):
    """Formatea como peso colombiano: $ 1.800.000"""
    n = int(round(float(n or 0)))
    return "$ " + f"{abs(n):,}".replace(",", ".")

def proyectar_deuda(saldo, tasa_anual, pago_minimo):
    """Retorna (fecha_fin: date, total_intereses: int) o (None, None)."""
    if pago_minimo <= 0 or saldo <= 0:
        return None, None
    tasa_m = tasa_anual / 12 / 100
    s, total_int, meses = float(saldo), 0.0, 0
    while s > 0.01 and meses < 600:
        interes = s * tasa_m
        if tasa_m > 0 and pago_minimo <= interes:
            return None, None
        total_int += interes
        s = s + interes - pago_minimo
        if s < 0:
            s = 0
        meses += 1
    if meses >= 600:
        return None, None
    today = date.today()
    m = today.month - 1 + meses
    yr, mo = today.year + m // 12, m % 12 + 1
    try:
        fecha_fin = today.replace(year=yr, month=mo)
    except ValueError:
        fecha_fin = today.replace(year=yr, month=mo, day=28)
    return fecha_fin, int(round(total_int))

# ─── CSS ──────────────────────────────────────────────────────────────────────
CSS = """
.stApp { background: #0D0D14 !important; }
#MainMenu, footer, header, .stDeployButton { visibility: hidden !important; }
.main > .block-container { max-width: 580px !important; padding: 1.2rem 1rem 5rem !important; margin: 0 auto !important; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { background:#1A1A2E !important; border-radius:16px !important; padding:5px !important; gap:3px !important; border:1px solid rgba(255,255,255,0.06) !important; box-shadow:0 2px 16px rgba(0,0,0,0.5) !important; }
.stTabs [data-baseweb="tab"] { background:transparent !important; border-radius:11px !important; color:#555570 !important; font-weight:500 !important; font-size:12px !important; padding:9px 4px !important; flex:1 !important; justify-content:center !important; border:none !important; white-space:nowrap !important; }
.stTabs [aria-selected="true"][data-baseweb="tab"] { background:#00C896 !important; color:#001810 !important; font-weight:700 !important; box-shadow:0 2px 10px rgba(0,200,150,0.35) !important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display:none !important; }
.stTabs [data-baseweb="tab-panel"] { padding-top:1.2rem !important; }

/* Inputs */
.stTextInput label,.stNumberInput label,.stSelectbox label,.stDateInput label,.stTextArea label { color:#6E6E82 !important; font-size:11px !important; font-weight:600 !important; text-transform:uppercase !important; letter-spacing:0.7px !important; }
.stTextInput input,.stNumberInput input,.stTextArea textarea { background:#12121C !important; border:1.5px solid #22223A !important; border-radius:12px !important; color:#FFFFFF !important; font-size:15px !important; padding:11px 14px !important; }
.stTextInput input:focus,.stNumberInput input:focus,.stTextArea textarea:focus { border-color:#00C896 !important; box-shadow:0 0 0 3px rgba(0,200,150,0.12) !important; }
.stDateInput input { background:#12121C !important; border:1.5px solid #22223A !important; border-radius:12px !important; color:#FFFFFF !important; }
.stSelectbox [data-baseweb="select"] > div:first-child { background:#12121C !important; border:1.5px solid #22223A !important; border-radius:12px !important; color:#FFFFFF !important; }
[data-baseweb="popover"] ul li { background:#1A1A2E !important; color:#FFFFFF !important; }

/* Buttons */
.stButton > button { background:linear-gradient(135deg,#00C896,#00A878) !important; color:#001810 !important; border:none !important; border-radius:14px !important; font-weight:700 !important; font-size:14px !important; padding:13px 20px !important; width:100% !important; box-shadow:0 4px 16px rgba(0,200,150,0.28) !important; transition:all 0.15s ease !important; }
.stButton > button:hover { background:linear-gradient(135deg,#00DBA8,#00C896) !important; box-shadow:0 6px 22px rgba(0,200,150,0.4) !important; transform:translateY(-1px) !important; }
[data-testid="stFormSubmitButton"] > button { background:linear-gradient(135deg,#00C896,#00A878) !important; color:#001810 !important; border:none !important; border-radius:14px !important; font-weight:700 !important; font-size:14px !important; padding:13px 20px !important; width:100% !important; box-shadow:0 4px 16px rgba(0,200,150,0.28) !important; margin-top:6px !important; }
[data-testid="baseButton-secondary"] { background:rgba(255,71,87,0.1) !important; color:#FF4757 !important; border:1px solid rgba(255,71,87,0.25) !important; border-radius:10px !important; padding:8px 6px !important; box-shadow:none !important; font-size:15px !important; font-weight:600 !important; line-height:1 !important; margin-top:4px !important; transform:none !important; }
[data-testid="baseButton-secondary"]:hover { background:rgba(255,71,87,0.22) !important; border-color:rgba(255,71,87,0.5) !important; box-shadow:none !important; transform:none !important; }

/* Form */
[data-testid="stForm"] { background:#1A1A2E !important; border-radius:20px !important; padding:1.4rem !important; border:1px solid rgba(255,255,255,0.06) !important; box-shadow:0 4px 28px rgba(0,0,0,0.4) !important; }

/* Number input step buttons */
[data-testid="stNumberInputStepUp"],[data-testid="stNumberInputStepDown"] { display:none !important; }
.stNumberInput > div > div { border-radius:12px !important; }

/* Alerts */
.stSuccess > div { background:rgba(0,200,150,0.12) !important; border-color:#00C896 !important; color:#00C896 !important; border-radius:12px !important; }
.stError > div { background:rgba(255,71,87,0.12) !important; border-color:#FF4757 !important; color:#FF4757 !important; border-radius:12px !important; }
.stInfo > div { background:rgba(100,160,255,0.1) !important; border-color:#64A0FF !important; color:#64A0FF !important; border-radius:12px !important; }

/* Scrollbar */
::-webkit-scrollbar { width:4px; }
::-webkit-scrollbar-track { background:#0D0D14; }
::-webkit-scrollbar-thumb { background:#22223A; border-radius:4px; }
hr { border-color:#1A1A2E !important; }
"""

PWA_TAGS = """
<link rel="manifest" href="/app/static/manifest.json">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Finanzas">
<meta name="theme-color" content="#0D0D14">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
"""

# ─── HTML Components ───────────────────────────────────────────────────────────
def section_title(text):
    return f'<p style="color:#6E6E82;font-size:11px;text-transform:uppercase;letter-spacing:0.9px;font-weight:700;margin:20px 0 10px;">{text}</p>'

def card_wrap(content, padding="1.4rem 1.5rem"):
    return f'<div style="background:#1A1A2E;border-radius:20px;padding:{padding};border:1px solid rgba(255,255,255,0.06);margin-bottom:12px;box-shadow:0 4px 24px rgba(0,0,0,0.3);">{content}</div>'

def balance_card_html(balance, ingresos, gastos):
    bal_color = "#00C896" if balance >= 0 else "#FF4757"
    sign_lbl  = "↑ Saldo positivo" if balance >= 0 else "↓ Saldo negativo"
    bal_str   = ("" if balance >= 0 else "- ") + cop(balance)
    return f"""
    <div style="background:linear-gradient(145deg,#1A1A2E 0%,#12122A 100%);border-radius:24px;
                padding:1.6rem 1.6rem 1.4rem;border:1px solid rgba(0,200,150,0.18);
                box-shadow:0 8px 40px rgba(0,0,0,0.45);margin-bottom:14px;">
      <p style="color:#6E6E82;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;font-weight:600;">Balance Total</p>
      <p style="color:{bal_color};font-size:2.4rem;font-weight:800;margin:0 0 4px;letter-spacing:-1px;line-height:1;font-family:-apple-system,sans-serif;">{bal_str}</p>
      <p style="color:#6E6E82;font-size:12px;margin:0 0 16px;">{sign_lbl}</p>
      <div style="display:flex;padding-top:14px;border-top:1px solid rgba(255,255,255,0.06);">
        <div style="flex:1;text-align:center;">
          <p style="color:#6E6E82;font-size:10px;text-transform:uppercase;letter-spacing:0.8px;margin:0 0 4px;font-weight:600;">Ingresos</p>
          <p style="color:#00C896;font-size:15px;font-weight:700;margin:0;">+{cop(ingresos)}</p>
        </div>
        <div style="width:1px;background:rgba(255,255,255,0.06);"></div>
        <div style="flex:1;text-align:center;">
          <p style="color:#6E6E82;font-size:10px;text-transform:uppercase;letter-spacing:0.8px;margin:0 0 4px;font-weight:600;">Gastos</p>
          <p style="color:#FF4757;font-size:15px;font-weight:700;margin:0;">-{cop(gastos)}</p>
        </div>
      </div>
    </div>"""

def tx_row(icon, categoria, desc, fecha, monto, is_income):
    color = "#00C896" if is_income else "#FF4757"
    sign  = "+" if is_income else "-"
    label = desc if desc else categoria
    return f"""
    <div style="display:flex;align-items:center;padding:11px 0;border-bottom:1px solid rgba(255,255,255,0.04);">
      <div style="width:42px;height:42px;border-radius:13px;background:#1E1E30;display:flex;align-items:center;justify-content:center;font-size:19px;margin-right:12px;flex-shrink:0;">{icon}</div>
      <div style="flex:1;min-width:0;">
        <p style="color:#EEEEF5;font-size:13px;font-weight:500;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{label}</p>
        <p style="color:#6E6E82;font-size:11px;margin:2px 0 0;">{categoria} · {fecha}</p>
      </div>
      <p style="color:{color};font-size:14px;font-weight:600;margin:0;flex-shrink:0;padding-left:8px;">{sign}{cop(monto)}</p>
    </div>"""

def asset_row(icon, nombre, tipo, valor):
    return f"""
    <div style="display:flex;align-items:center;padding:12px 0;border-bottom:1px solid rgba(255,255,255,0.04);">
      <div style="width:44px;height:44px;border-radius:14px;background:#1E1E30;display:flex;align-items:center;justify-content:center;font-size:20px;margin-right:13px;flex-shrink:0;">{icon}</div>
      <div style="flex:1;">
        <p style="color:#EEEEF5;font-size:14px;font-weight:500;margin:0;">{nombre}</p>
        <p style="color:#6E6E82;font-size:12px;margin:2px 0 0;">{tipo}</p>
      </div>
      <p style="color:#00C896;font-size:14px;font-weight:600;margin:0;">{cop(valor)}</p>
    </div>"""

def debt_card(nombre, tipo, deuda_inicial, saldo, tasa, pago_minimo, fecha_fin=None, total_int=None):
    pagado = max(deuda_inicial - saldo, 0)
    pct    = pagado / deuda_inicial if deuda_inicial > 0 else 0
    bar_w  = int(pct * 100)
    pct_r  = saldo / deuda_inicial if deuda_inicial > 0 else 0
    color  = "#00C896" if pct_r < 0.25 else "#FFB547" if pct_r < 0.6 else "#FF4757"
    icon   = DEUDA_ICONS.get(tipo, "📋")
    tasa_s = f"{tasa:.1f}% anual" if tasa > 0 else "Sin interés"

    if fecha_fin and total_int is not None:
        proj_html = (
            f'<div style="background:#12121C;border-radius:12px;padding:10px 12px;margin-top:12px;border:1px solid rgba(255,71,87,0.1);">'
            f'<p style="color:#6E6E82;font-size:10px;text-transform:uppercase;letter-spacing:0.7px;font-weight:600;margin:0 0 6px;">📅 Proyección de pago</p>'
            f'<div style="display:flex;justify-content:space-between;">'
            f'<div><p style="color:#6E6E82;font-size:11px;margin:0;">Fecha estimada de pago</p>'
            f'<p style="color:#EEEEF5;font-size:13px;font-weight:600;margin:2px 0 0;">{fecha_fin.strftime("%b %Y")}</p></div>'
            f'<div style="text-align:right;"><p style="color:#6E6E82;font-size:11px;margin:0;">Total en intereses</p>'
            f'<p style="color:#FF4757;font-size:13px;font-weight:600;margin:2px 0 0;">{cop(total_int)}</p></div>'
            f'</div></div>'
        )
    elif pago_minimo <= 0:
        proj_html = '<p style="color:#6E6E82;font-size:11px;margin:10px 0 0;">Sin pago mínimo registrado para proyectar.</p>'
    else:
        proj_html = '<p style="color:#FF4757;font-size:11px;margin:10px 0 0;">⚠️ El pago mínimo no alcanza a cubrir los intereses.</p>'

    return f"""
    <div style="background:#1A1A2E;border-radius:20px;padding:1.3rem 1.5rem;
                border:1px solid rgba(255,71,87,0.12);margin-bottom:10px;
                box-shadow:0 4px 24px rgba(0,0,0,0.3);">
      <div style="display:flex;align-items:center;margin-bottom:14px;">
        <span style="font-size:20px;background:#1E1E30;width:44px;height:44px;border-radius:14px;
                     display:inline-flex;align-items:center;justify-content:center;margin-right:12px;flex-shrink:0;">{icon}</span>
        <div style="flex:1;">
          <p style="color:#EEEEF5;font-size:15px;font-weight:600;margin:0;">{nombre}</p>
          <p style="color:#6E6E82;font-size:12px;margin:2px 0 0;">{tipo} · {tasa_s}</p>
        </div>
        <div style="text-align:right;">
          <p style="color:{color};font-size:18px;font-weight:700;margin:0;">{cop(saldo)}</p>
          <p style="color:#6E6E82;font-size:11px;margin:2px 0 0;">restante</p>
        </div>
      </div>
      <div style="background:#12121C;border-radius:8px;height:8px;overflow:hidden;margin-bottom:12px;">
        <div style="width:{bar_w}%;height:100%;border-radius:8px;background:linear-gradient(90deg,#00C896,#00A878);"></div>
      </div>
      <div style="display:flex;justify-content:space-between;">
        <div>
          <p style="color:#6E6E82;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;margin:0;">Pagado</p>
          <p style="color:#00C896;font-size:13px;font-weight:600;margin:3px 0 0;">{cop(pagado)} <span style="color:#6E6E82;font-weight:400;">({int(pct*100)}%)</span></p>
        </div>
        <div style="text-align:center;">
          <p style="color:#6E6E82;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;margin:0;">Pago mínimo</p>
          <p style="color:#EEEEF5;font-size:13px;font-weight:600;margin:3px 0 0;">{cop(pago_minimo)}/mes</p>
        </div>
        <div style="text-align:right;">
          <p style="color:#6E6E82;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;margin:0;">Deuda original</p>
          <p style="color:#EEEEF5;font-size:13px;font-weight:600;margin:3px 0 0;">{cop(deuda_inicial)}</p>
        </div>
      </div>
      {proj_html}
    </div>"""

def meta_card(emoji, nombre, actual, objetivo, fecha_limite):
    pct      = min(actual / objetivo, 1.0) if objetivo > 0 else 0
    falta    = max(objetivo - actual, 0)
    bar_w    = int(pct * 100)
    deadline = f"Límite: {fecha_limite}" if fecha_limite else "Sin fecha límite"
    color    = "#00C896" if pct >= 1 else "#FFB547" if pct >= 0.6 else "#64A0FF"
    status   = "¡Meta alcanzada! 🎉" if pct >= 1 else f"Falta {cop(falta)}"
    milestones = ""
    for pct_m in [25, 50, 75]:
        left = pct_m
        dot_color = "#00C896" if bar_w >= pct_m else "#2A2A3E"
        milestones += f'<div style="position:absolute;left:{left}%;top:-2px;width:2px;height:12px;background:{dot_color};border-radius:1px;"></div>'

    return f"""
    <div style="background:#1A1A2E;border-radius:20px;padding:1.3rem 1.5rem;
                border:1px solid rgba(255,255,255,0.06);margin-bottom:10px;
                box-shadow:0 4px 24px rgba(0,0,0,0.3);">
      <div style="display:flex;align-items:center;margin-bottom:14px;">
        <span style="font-size:26px;margin-right:12px;">{emoji}</span>
        <div style="flex:1;">
          <p style="color:#EEEEF5;font-size:15px;font-weight:600;margin:0;">{nombre}</p>
          <p style="color:#6E6E82;font-size:12px;margin:2px 0 0;">{deadline}</p>
        </div>
        <div style="text-align:right;">
          <p style="color:{color};font-size:18px;font-weight:800;margin:0;">{int(pct*100)}%</p>
        </div>
      </div>
      <div style="position:relative;margin-bottom:6px;">
        <div style="background:#12121C;border-radius:8px;height:12px;overflow:hidden;">
          <div style="width:{bar_w}%;height:100%;border-radius:8px;
                      background:linear-gradient(90deg,{color},{color}BB);
                      transition:width 0.6s ease;"></div>
        </div>
        {milestones}
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;">
        <div>
          <p style="color:#6E6E82;font-size:11px;margin:0;">Ahorrado</p>
          <p style="color:#EEEEF5;font-size:14px;font-weight:700;margin:2px 0 0;">{cop(actual)}</p>
        </div>
        <div style="text-align:center;">
          <p style="color:{color};font-size:12px;font-weight:600;margin:0;
                    background:{"rgba(0,200,150,0.1)" if pct>=1 else "rgba(100,160,255,0.1)"};
                    padding:4px 10px;border-radius:20px;">{status}</p>
        </div>
        <div style="text-align:right;">
          <p style="color:#6E6E82;font-size:11px;margin:0;">Objetivo</p>
          <p style="color:#EEEEF5;font-size:14px;font-weight:700;margin:2px 0 0;">{cop(objetivo)}</p>
        </div>
      </div>
    </div>"""

# ─── Pages ────────────────────────────────────────────────────────────────────
def page_dashboard():
    df = query("SELECT * FROM transacciones ORDER BY fecha DESC, id DESC")

    if df.empty:
        st.markdown(balance_card_html(0, 0, 0), unsafe_allow_html=True)
        st.markdown(card_wrap('<p style="color:#6E6E82;text-align:center;font-size:14px;padding:1rem 0;margin:0;">¡Agrega tu primera transacción en la pestaña Transacciones!</p>'), unsafe_allow_html=True)
        return

    ingresos = df[df["tipo"] == "Ingreso"]["monto"].sum()
    gastos   = df[df["tipo"] == "Gasto"]["monto"].sum()
    balance  = ingresos - gastos

    # ── Balance + dona side by side ──
    df_gas_all = df[df["tipo"] == "Gasto"].groupby("categoria")["monto"].sum().reset_index()

    col_bal, col_dona = st.columns([3, 2])
    with col_bal:
        st.markdown(balance_card_html(balance, ingresos, gastos), unsafe_allow_html=True)
    with col_dona:
        if not df_gas_all.empty:
            fig_dona = go.Figure(go.Pie(
                labels=df_gas_all["categoria"],
                values=df_gas_all["monto"],
                hole=0.60,
                marker=dict(colors=CHART_COLORS, line=dict(color="#0D0D14", width=2)),
                textinfo="none",
                hovertemplate="<b>%{label}</b><br>%{percent}<extra></extra>",
            ))
            top = df_gas_all.loc[df_gas_all["monto"].idxmax()]
            fig_dona.add_annotation(
                text=f"<b>{int(top['monto']/gastos*100)}%</b>",
                font=dict(size=14, color="#FFF"),
                showarrow=False, x=0.5, y=0.55, xref="paper", yref="paper",
            )
            fig_dona.add_annotation(
                text=top["categoria"],
                font=dict(size=9, color="#6E6E82"),
                showarrow=False, x=0.5, y=0.38, xref="paper", yref="paper",
            )
            fig_dona.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=30, b=0), height=200,
                showlegend=False,
            )
            st.plotly_chart(fig_dona, use_container_width=True, config={"displayModeBar": False})

    # ── Barras horizontales — gastos del mes actual ──
    mes_actual = date.today().strftime("%Y-%m")
    df_mes = df[(df["tipo"] == "Gasto") & (df["fecha"].str.startswith(mes_actual))]
    if not df_mes.empty:
        st.markdown(section_title(f"Gastos de {date.today().strftime('%B %Y')}"), unsafe_allow_html=True)
        df_cat_mes = df_mes.groupby("categoria")["monto"].sum().sort_values(ascending=True).reset_index()
        fig_bar = go.Figure(go.Bar(
            x=df_cat_mes["monto"],
            y=df_cat_mes["categoria"],
            orientation="h",
            marker=dict(
                color=CHART_COLORS[:len(df_cat_mes)],
                line=dict(width=0),
            ),
            text=[cop(v) for v in df_cat_mes["monto"]],
            textposition="outside",
            textfont=dict(color="#AAAABC", size=11),
            hovertemplate="<b>%{y}</b><br>%{text}<extra></extra>",
        ))
        fig_bar.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=70, t=10, b=0),
            height=max(160, len(df_cat_mes) * 36),
            xaxis=dict(visible=False),
            yaxis=dict(color="#AAAABC", tickfont=dict(size=12), gridcolor="rgba(0,0,0,0)"),
            showlegend=False,
        )
        st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

    # ── Actividad reciente ──
    st.markdown(section_title("Actividad reciente"), unsafe_allow_html=True)
    rows_html = ""
    for _, r in df.head(8).iterrows():
        icon = CAT_ICONS.get(r["categoria"], "💸")
        rows_html += tx_row(icon, r["categoria"], r["descripcion"], r["fecha"], r["monto"], r["tipo"] == "Ingreso")
    st.markdown(card_wrap(rows_html, "0.6rem 1.2rem"), unsafe_allow_html=True)


def page_transacciones():
    st.markdown(section_title("Nueva transacción"), unsafe_allow_html=True)
    tipo = st.selectbox("Tipo", ["Gasto", "Ingreso"], key="new_tipo")
    cats = CATEGORIAS_GASTO if tipo == "Gasto" else CATEGORIAS_INGRESO

    with st.form("form_tx", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            fecha = st.date_input("Fecha", value=date.today())
        with c2:
            categoria = st.selectbox("Categoría", cats)
        cat_custom = ""
        if categoria == "Otro":
            cat_custom = st.text_input("Especifica el tipo de ingreso", placeholder="Ej: Bono, Reembolso…")
        cuenta_label = "Cuenta de destino" if tipo == "Ingreso" else "Cuenta de origen"
        cuenta = st.selectbox(cuenta_label, CUENTAS)
        descripcion = st.text_input("Descripción", placeholder="Opcional…")
        monto = st.number_input("Monto ($)", min_value=0.0, value=None,
                                placeholder="0", step=1000.0, format="%.0f")
        ok = st.form_submit_button("Guardar transacción", use_container_width=True)
        if ok:
            cat_final = cat_custom.strip() if (categoria == "Otro" and cat_custom.strip()) else categoria
            if categoria == "Otro" and not cat_custom.strip():
                st.error("Especifica el tipo de ingreso.")
            elif not monto or monto <= 0:
                st.error("El monto debe ser mayor a 0.")
            else:
                run("INSERT INTO transacciones (fecha,tipo,categoria,descripcion,monto,cuenta) VALUES (?,?,?,?,?,?)",
                    (str(fecha), tipo, cat_final, descripcion, monto, cuenta))
                st.success(f"{'Ingreso' if tipo=='Ingreso' else 'Gasto'} de {cop(monto)} guardado.")

    df = query("SELECT * FROM transacciones ORDER BY fecha DESC, id DESC")
    if df.empty:
        st.info("Sin transacciones aún.")
        return

    st.markdown(section_title("Historial"), unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        ftipo = st.selectbox("Tipo", ["Todos", "Ingreso", "Gasto"], key="ftipo")
    with c2:
        cats_all = ["Todas"] + sorted(df["categoria"].unique().tolist())
        fcat = st.selectbox("Categoría", cats_all, key="fcat")
    with c3:
        cuentas_all = ["Todas"] + sorted(df["cuenta"].dropna().unique().tolist())
        fcuenta = st.selectbox("Cuenta", cuentas_all, key="fcuenta")

    dff = df.copy()
    if ftipo   != "Todos": dff = dff[dff["tipo"]      == ftipo]
    if fcat    != "Todas": dff = dff[dff["categoria"] == fcat]
    if fcuenta != "Todas": dff = dff[dff["cuenta"]    == fcuenta]

    if dff.empty:
        st.info("No hay resultados para estos filtros.")
        return

    for _, r in dff.iterrows():
        icon       = CAT_ICONS.get(r["categoria"], "💸")
        is_income  = r["tipo"] == "Ingreso"
        color      = "#00C896" if is_income else "#FF4757"
        sign       = "+" if is_income else "-"
        label      = r["descripcion"] if r["descripcion"] else r["categoria"]
        cuenta_val = r["cuenta"] if pd.notna(r.get("cuenta")) else "Efectivo"
        cuenta_ico = CUENTA_ICONS.get(cuenta_val, "🏷️")
        flecha     = "→" if is_income else "←"

        col_info, col_del = st.columns([11, 1])
        with col_info:
            st.markdown(f"""
            <div style="background:#1A1A2E;border-radius:16px;padding:10px 14px;
                        border:1px solid rgba(255,255,255,0.05);margin-bottom:6px;
                        display:flex;align-items:center;gap:12px;">
              <span style="font-size:20px;background:#1E1E30;width:42px;height:42px;border-radius:12px;
                           display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;">{icon}</span>
              <div style="flex:1;min-width:0;">
                <p style="color:#EEEEF5;font-size:14px;font-weight:500;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{label}</p>
                <p style="color:#6E6E82;font-size:12px;margin:2px 0 0;">{r["categoria"]} · {r["fecha"]}</p>
                <p style="color:#555570;font-size:11px;margin:3px 0 0;">{cuenta_ico} {flecha} {cuenta_val}</p>
              </div>
              <p style="color:{color};font-size:14px;font-weight:600;margin:0;flex-shrink:0;">{sign}{cop(r["monto"])}</p>
            </div>""", unsafe_allow_html=True)
        with col_del:
            if st.button("✕", key=f"del_{r['id']}", type="secondary", use_container_width=True, help="Eliminar"):
                run("DELETE FROM transacciones WHERE id=?", (int(r["id"]),))
                st.rerun()

    st.markdown(f'<p style="color:#6E6E82;font-size:12px;text-align:center;margin-top:4px;">{len(dff)} transacciones</p>', unsafe_allow_html=True)


def page_portafolio():
    df    = query("SELECT * FROM portafolio ORDER BY id DESC")
    total = df["cantidad"].sum() if not df.empty else 0

    st.markdown(card_wrap(f"""
      <p style="color:#6E6E82;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;font-weight:600;">Valor total del portafolio</p>
      <p style="color:#00C896;font-size:2.4rem;font-weight:800;margin:0;letter-spacing:-1px;">{cop(total)}</p>
    """), unsafe_allow_html=True)

    st.markdown(section_title("Agregar activo"), unsafe_allow_html=True)
    with st.form("form_activo", clear_on_submit=True):
        nombre = st.text_input("Nombre del activo", placeholder="Apple, Bitcoin, Fondo…")
        c1, c2 = st.columns(2)
        with c1:
            tipo  = st.selectbox("Tipo", TIPOS_ACTIVO)
        with c2:
            fecha = st.date_input("Fecha de compra", value=date.today())
        valor = st.number_input("Valor ($)", min_value=0.0, value=None,
                                placeholder="0", step=1000.0, format="%.0f")
        ok = st.form_submit_button("Agregar al portafolio", use_container_width=True)
        if ok:
            if not nombre:
                st.error("Ingresa un nombre.")
            elif not valor or valor <= 0:
                st.error("El valor debe ser mayor a 0.")
            else:
                run("INSERT INTO portafolio (nombre,tipo,cantidad,valor_unitario,fecha) VALUES (?,?,?,?,?)",
                    (nombre, tipo, valor, 1.0, str(fecha)))
                st.success(f"{nombre} agregado al portafolio.")
                st.rerun()

    if df.empty:
        return

    st.markdown(section_title("Mis activos"), unsafe_allow_html=True)

    if "editing_asset_id" not in st.session_state:
        st.session_state.editing_asset_id = None

    for _, r in df.iterrows():
        icon = CAT_ICONS.get(r["tipo"], "💎")
        col_info, col_btn = st.columns([9, 1])
        with col_info:
            st.markdown(card_wrap(asset_row(icon, r["nombre"], r["tipo"], r["cantidad"]), "0 1.2rem"), unsafe_allow_html=True)
        with col_btn:
            st.markdown("<div style='height:44px'></div>", unsafe_allow_html=True)
            if st.button("✏️", key=f"edit_{r['id']}", help="Editar valor"):
                st.session_state.editing_asset_id = r["id"]
                st.rerun()

        if st.session_state.editing_asset_id == r["id"]:
            with st.container():
                nuevo_valor = st.number_input(
                    f"Nuevo valor para {r['nombre']} ($)",
                    min_value=0.0,
                    value=float(r["cantidad"]),
                    step=1000.0,
                    format="%.0f",
                    key=f"val_{r['id']}"
                )
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("💾 Guardar", key=f"save_{r['id']}", use_container_width=True):
                        run("UPDATE portafolio SET cantidad=? WHERE id=?", (nuevo_valor, r["id"]))
                        st.session_state.editing_asset_id = None
                        st.rerun()
                with c2:
                    if st.button("Cancelar", key=f"cancel_{r['id']}", use_container_width=True):
                        st.session_state.editing_asset_id = None
                        st.rerun()

    df_tipo = df.groupby("tipo")["cantidad"].sum().reset_index()
    fig = go.Figure(go.Bar(
        x=df_tipo["tipo"], y=df_tipo["cantidad"],
        marker=dict(color=CHART_COLORS[:len(df_tipo)], line=dict(width=0)),
        hovertemplate="<b>%{x}</b><br>" + "<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=10, b=0), height=180,
        xaxis=dict(color="#6E6E82", gridcolor="rgba(255,255,255,0.04)"),
        yaxis=dict(color="#6E6E82", gridcolor="rgba(255,255,255,0.04)"),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with st.expander("Eliminar activo"):
        opciones = {f"{r['nombre']} · {r['tipo']} (#{r['id']})": r["id"] for _, r in df.iterrows()}
        sel = st.selectbox("Selecciona", list(opciones.keys()), key="del_activo")
        if st.button("Eliminar activo", key="btn_del_activo"):
            run("DELETE FROM portafolio WHERE id=?", (opciones[sel],))
            st.rerun()


def page_metas():
    df = query("SELECT * FROM metas ORDER BY id DESC")

    st.markdown(section_title("Nueva meta"), unsafe_allow_html=True)
    with st.form("form_meta", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            nombre = st.text_input("Nombre de la meta", placeholder="Viaje a Europa, Fondo…")
        with c2:
            emoji = st.selectbox("", META_EMOJIS)
        c3, c4 = st.columns(2)
        with c3:
            objetivo = st.number_input("Monto objetivo ($)", min_value=0.0, value=None,
                                       placeholder="0", step=100000.0, format="%.0f")
        with c4:
            deadline = st.date_input("Fecha límite (opcional)", value=None)
        ok = st.form_submit_button("Crear meta", use_container_width=True)
        if ok:
            if not nombre:
                st.error("Ponle un nombre a tu meta.")
            elif not objetivo or objetivo <= 0:
                st.error("El objetivo debe ser mayor a 0.")
            else:
                run("INSERT INTO metas (nombre,objetivo,actual,fecha_limite,emoji) VALUES (?,?,0,?,?)",
                    (nombre, objetivo, str(deadline) if deadline else None, emoji))
                st.success(f"Meta '{nombre}' creada.")
                st.rerun()

    if df.empty:
        st.info("Crea tu primera meta de ahorro.")
        return

    total_obj  = df["objetivo"].sum()
    total_act  = df["actual"].sum()
    pct_global = int(total_act / total_obj * 100) if total_obj > 0 else 0

    st.markdown(card_wrap(f"""
      <p style="color:#6E6E82;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;font-weight:600;">Progreso global</p>
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px;">
        <p style="color:#EEEEF5;font-size:20px;font-weight:700;margin:0;">{cop(total_act)}</p>
        <p style="color:#6E6E82;font-size:13px;margin:0;">de {cop(total_obj)}</p>
      </div>
      <div style="background:#12121C;border-radius:8px;height:10px;overflow:hidden;">
        <div style="width:{pct_global}%;height:100%;border-radius:8px;background:linear-gradient(90deg,#00C896,#00A878);"></div>
      </div>
      <p style="color:#00C896;font-size:12px;font-weight:600;margin:6px 0 0;text-align:right;">{pct_global}% completado</p>
    """), unsafe_allow_html=True)

    st.markdown(section_title("Mis metas"), unsafe_allow_html=True)
    for _, r in df.iterrows():
        st.markdown(meta_card(r["emoji"], r["nombre"], r["actual"], r["objetivo"], r["fecha_limite"]), unsafe_allow_html=True)

    with st.expander("Agregar fondos a una meta"):
        nombres = {r["nombre"]: r["id"] for _, r in df.iterrows()}
        sel_meta  = st.selectbox("Meta", list(nombres.keys()), key="sel_meta")
        add_monto = st.number_input("Monto a agregar ($)", min_value=0.0, value=None,
                                    placeholder="0", step=10000.0, format="%.0f", key="add_monto")
        if st.button("Agregar fondos", key="btn_add_funds"):
            if not add_monto or add_monto <= 0:
                st.error("Ingresa un monto válido.")
            else:
                run("UPDATE metas SET actual = MIN(actual + ?, objetivo) WHERE id = ?",
                    (add_monto, nombres[sel_meta]))
                st.success(f"+{cop(add_monto)} agregado a '{sel_meta}'.")
                st.rerun()

    with st.expander("Eliminar meta"):
        opciones = {f"{r['emoji']} {r['nombre']}": r["id"] for _, r in df.iterrows()}
        sel = st.selectbox("Selecciona", list(opciones.keys()), key="del_meta")
        if st.button("Eliminar meta", key="btn_del_meta"):
            run("DELETE FROM metas WHERE id=?", (opciones[sel],))
            st.rerun()


def page_deudas():
    df = query("SELECT * FROM deudas ORDER BY saldo DESC")

    total_saldo   = df["saldo"].sum() if not df.empty else 0
    total_inicial = df["deuda_inicial"].sum() if not df.empty else 0
    total_pagado  = max(total_inicial - total_saldo, 0)
    pct_g         = int(total_pagado / total_inicial * 100) if total_inicial > 0 else 0

    st.markdown(card_wrap(f"""
      <p style="color:#6E6E82;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;font-weight:600;">Deuda total restante</p>
      <p style="color:#FF4757;font-size:2.4rem;font-weight:800;margin:0 0 4px;letter-spacing:-1px;">{cop(total_saldo)}</p>
      <p style="color:#6E6E82;font-size:12px;margin:0 0 16px;">de {cop(total_inicial)} originales</p>
      <div style="background:#12121C;border-radius:8px;height:10px;overflow:hidden;margin-bottom:8px;">
        <div style="width:{pct_g}%;height:100%;border-radius:8px;background:linear-gradient(90deg,#00C896,#00A878);"></div>
      </div>
      <div style="display:flex;justify-content:space-between;">
        <p style="color:#00C896;font-size:12px;font-weight:600;margin:0;">✓ Pagado: {cop(total_pagado)} ({pct_g}%)</p>
        <p style="color:#6E6E82;font-size:12px;margin:0;">{len(df)} deuda(s)</p>
      </div>
    """), unsafe_allow_html=True)

    st.markdown(section_title("Registrar deuda"), unsafe_allow_html=True)
    with st.form("form_deuda", clear_on_submit=True):
        nombre = st.text_input("Nombre", placeholder="Tarjeta Visa, Préstamo banco…")
        c1, c2 = st.columns(2)
        with c1:
            tipo          = st.selectbox("Tipo", TIPOS_DEUDA)
            deuda_inicial = st.number_input("Deuda total ($)", min_value=0.0, value=None,
                                            placeholder="0", step=100000.0, format="%.0f")
        with c2:
            tasa        = st.number_input("Tasa de interés anual (%)", min_value=0.0,
                                          value=None, placeholder="18.5", step=0.1, format="%.2f")
            pago_minimo = st.number_input("Pago mínimo mensual ($)", min_value=0.0,
                                          value=None, placeholder="0", step=10000.0, format="%.0f")
        fecha_inicio = st.date_input("Fecha de inicio", value=date.today())
        ok = st.form_submit_button("Agregar deuda", use_container_width=True)
        if ok:
            if not nombre:
                st.error("Ingresa un nombre para la deuda.")
            elif not deuda_inicial or deuda_inicial <= 0:
                st.error("El monto de la deuda debe ser mayor a 0.")
            else:
                run("INSERT INTO deudas (nombre,tipo,deuda_inicial,saldo,tasa_interes,pago_minimo,fecha_inicio) VALUES (?,?,?,?,?,?,?)",
                    (nombre, tipo, deuda_inicial, deuda_inicial, tasa or 0.0, pago_minimo or 0.0, str(fecha_inicio)))
                st.success(f"Deuda '{nombre}' registrada.")
                st.rerun()

    if df.empty:
        st.info("Sin deudas registradas. ¡Eso es buena señal!")
        return

    st.markdown(section_title("Mis deudas"), unsafe_allow_html=True)
    for _, r in df.iterrows():
        fecha_fin, total_int = proyectar_deuda(r["saldo"], r["tasa_interes"], r["pago_minimo"])
        st.markdown(debt_card(r["nombre"], r["tipo"], r["deuda_inicial"], r["saldo"],
                              r["tasa_interes"], r["pago_minimo"], fecha_fin, total_int),
                    unsafe_allow_html=True)

        pagos = query("SELECT * FROM pagos_deuda WHERE deuda_id=? ORDER BY fecha DESC LIMIT 5",
                      params=(int(r["id"]),))
        if not pagos.empty:
            hist_html = ""
            for _, p in pagos.iterrows():
                nota = f" · {p['nota']}" if p["nota"] else ""
                hist_html += f"""
                <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04);">
                  <p style="color:#8E8E9A;font-size:12px;margin:0;">{p['fecha']}{nota}</p>
                  <p style="color:#00C896;font-size:12px;font-weight:600;margin:0;">-{cop(p['monto'])}</p>
                </div>"""
            st.markdown(card_wrap(
                '<p style="color:#6E6E82;font-size:11px;text-transform:uppercase;letter-spacing:0.7px;font-weight:600;margin:0 0 8px;">Últimos pagos</p>' + hist_html,
                "0.9rem 1.2rem"
            ), unsafe_allow_html=True)

    with st.expander("Registrar un pago"):
        deudas_map   = {r["nombre"]: (r["id"], r["saldo"]) for _, r in df.iterrows()}
        sel_deuda    = st.selectbox("Deuda", list(deudas_map.keys()), key="sel_deuda_pago")
        did, saldo_s = deudas_map[sel_deuda]
        st.markdown(f'<p style="color:#FF4757;font-size:13px;margin:4px 0 12px;">Saldo actual: <b>{cop(saldo_s)}</b></p>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            pago_fecha = st.date_input("Fecha del pago", value=date.today(), key="pago_fecha")
        with c2:
            pago_monto = st.number_input("Monto ($)", min_value=0.0, value=None,
                                         placeholder="0", step=10000.0, format="%.0f", key="pago_monto")
        pago_nota = st.text_input("Nota (opcional)", placeholder="Pago mensual, abono extra…", key="pago_nota")
        if st.button("Registrar pago", key="btn_pago"):
            if not pago_monto or pago_monto <= 0:
                st.error("Ingresa un monto válido.")
            elif pago_monto > saldo_s:
                st.error(f"El pago ({cop(pago_monto)}) supera el saldo ({cop(saldo_s)}).")
            else:
                nuevo_saldo = round(saldo_s - pago_monto, 2)
                run("INSERT INTO pagos_deuda (deuda_id,fecha,monto,nota) VALUES (?,?,?,?)",
                    (int(did), str(pago_fecha), pago_monto, pago_nota or None))
                run("UPDATE deudas SET saldo=? WHERE id=?", (nuevo_saldo, int(did)))
                st.success(f"Pago de {cop(pago_monto)} registrado. Saldo: {cop(nuevo_saldo)}")
                st.rerun()

    with st.expander("Eliminar deuda"):
        opciones = {r["nombre"]: r["id"] for _, r in df.iterrows()}
        sel = st.selectbox("Selecciona", list(opciones.keys()), key="del_deuda")
        if st.button("Eliminar deuda", key="btn_del_deuda"):
            run("DELETE FROM pagos_deuda WHERE deuda_id=?", (opciones[sel],))
            run("DELETE FROM deudas WHERE id=?", (opciones[sel],))
            st.rerun()


# ─── Main ─────────────────────────────────────────────────────────────────────
init_db()
st.set_page_config(page_title="Finanzas", page_icon="💳", layout="centered",
                   initial_sidebar_state="collapsed")
st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
st.markdown(PWA_TAGS, unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Dashboard", "Transacciones", "Portafolio", "Metas", "Deudas"]
)
with tab1: page_dashboard()
with tab2: page_transacciones()
with tab3: page_portafolio()
with tab4: page_metas()
with tab5: page_deudas()
