import streamlit as st
import sqlite3
import pandas as pd
from datetime import date
import hashlib
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
CHART_COLORS = ["#b78a00","#4A7C59","#2D6A8F","#8B5E3C","#7B6EA0",
                "#C0392B","#D4956A","#5B8A6E","#A07040","#6B7DA8"]

# Colores fijos por categoría — garantiza consistencia entre gráficas
_CATS_ORDERED = [
    "Alimentación","Transporte","Vivienda","Salud","Educación",
    "Entretenimiento","Ropa","Servicios","Deudas","Otro gasto",
    "Salario","Préstamo","Otro",
]
CAT_COLOR_MAP = {cat: CHART_COLORS[i % len(CHART_COLORS)] for i, cat in enumerate(_CATS_ORDERED)}

def cat_colors(categories):
    """Devuelve una lista de colores estables para una lista de categorías."""
    return [CAT_COLOR_MAP.get(c, CHART_COLORS[hash(c) % len(CHART_COLORS)]) for c in categories]

# ─── Database ─────────────────────────────────────────────────────────────────
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transacciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL,
                tipo TEXT NOT NULL, categoria TEXT NOT NULL,
                descripcion TEXT, monto REAL NOT NULL,
                cuenta TEXT DEFAULT 'Efectivo',
                user_id INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS portafolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL,
                tipo TEXT NOT NULL, cantidad REAL NOT NULL,
                valor_unitario REAL NOT NULL, fecha TEXT NOT NULL,
                user_id INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS deudas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL,
                tipo TEXT NOT NULL, deuda_inicial REAL NOT NULL,
                saldo REAL NOT NULL, tasa_interes REAL NOT NULL DEFAULT 0,
                pago_minimo REAL NOT NULL DEFAULT 0, fecha_inicio TEXT NOT NULL,
                user_id INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS pagos_deuda (
                id INTEGER PRIMARY KEY AUTOINCREMENT, deuda_id INTEGER NOT NULL,
                fecha TEXT NOT NULL, monto REAL NOT NULL, nota TEXT
            );
            CREATE TABLE IF NOT EXISTS metas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL,
                objetivo REAL NOT NULL, actual REAL NOT NULL DEFAULT 0,
                fecha_limite TEXT, emoji TEXT NOT NULL DEFAULT '🎯',
                user_id INTEGER NOT NULL DEFAULT 1
            );
        """)
        conn.commit()
        for migration in [
            "ALTER TABLE transacciones ADD COLUMN cuenta TEXT DEFAULT 'Efectivo'",
            "ALTER TABLE transacciones ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE portafolio ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE deudas ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE metas ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1",
        ]:
            try:
                conn.execute(migration)
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

# ─── Auth ─────────────────────────────────────────────────────────────────────
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(nombre, email, password):
    try:
        run("INSERT INTO usuarios (nombre, email, password_hash) VALUES (?,?,?)",
            (nombre.strip(), email.strip().lower(), hash_password(password)))
        return True, None
    except sqlite3.IntegrityError:
        return False, "Este email ya está registrado."

def authenticate_user(email, password):
    df = query("SELECT id, nombre FROM usuarios WHERE email=? AND password_hash=?",
               (email.strip().lower(), hash_password(password)))
    if df.empty:
        return None, None
    return int(df.iloc[0]["id"]), df.iloc[0]["nombre"]

def uid():
    return st.session_state.get("user_id", 1)

# ─── Helpers ──────────────────────────────────────────────────────────────────
def cop(n):
    n = int(round(float(n or 0)))
    return "$ " + f"{abs(n):,}".replace(",", ".")

def proyectar_deuda(saldo, tasa_anual, pago_minimo):
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
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&display=swap');

.stApp { background: #F5F0E8 !important; }
#MainMenu, footer, header, .stDeployButton { visibility: hidden !important; }
.main > .block-container { max-width: 600px !important; padding: 1.2rem 1rem 5rem !important; margin: 0 auto !important; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { background:#322b49 !important; border-radius:16px !important; padding:5px !important; gap:3px !important; border:none !important; box-shadow:0 2px 12px rgba(50,43,73,0.18) !important; }
.stTabs [data-baseweb="tab"] { background:transparent !important; border-radius:11px !important; color:rgba(255,255,255,0.45) !important; font-weight:500 !important; font-size:12px !important; padding:9px 4px !important; flex:1 !important; justify-content:center !important; border:none !important; white-space:nowrap !important; }
.stTabs [aria-selected="true"][data-baseweb="tab"] { background:rgba(234,176,0,0.15) !important; color:#eab000 !important; font-weight:700 !important; box-shadow:none !important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display:none !important; }
.stTabs [data-baseweb="tab-panel"] { padding-top:1.2rem !important; }

/* Inputs */
.stTextInput label,.stNumberInput label,.stSelectbox label,.stDateInput label,.stTextArea label { color:#322b49 !important; font-size:11px !important; font-weight:600 !important; text-transform:uppercase !important; letter-spacing:0.7px !important; }
.stTextInput input,.stNumberInput input,.stTextArea textarea { background:#FFFFFF !important; border:1.5px solid #DDD8CC !important; border-radius:12px !important; color:#1c1829 !important; font-size:15px !important; padding:11px 14px !important; }
.stTextInput input:focus,.stNumberInput input:focus,.stTextArea textarea:focus { border-color:#b78a00 !important; box-shadow:0 0 0 3px rgba(183,138,0,0.12) !important; }
.stDateInput input { background:#FFFFFF !important; border:1.5px solid #DDD8CC !important; border-radius:12px !important; color:#1c1829 !important; }
.stSelectbox [data-baseweb="select"] > div:first-child { background:#FFFFFF !important; border:1.5px solid #DDD8CC !important; border-radius:12px !important; color:#1c1829 !important; }
[data-baseweb="popover"] ul li { background:#FFFFFF !important; color:#1c1829 !important; }
[data-baseweb="popover"] ul li:hover { background:#FDFAF5 !important; }

/* Buttons */
.stButton > button { background:#b78a00 !important; color:#FFFFFF !important; border:none !important; border-radius:14px !important; font-weight:700 !important; font-size:14px !important; padding:13px 20px !important; width:100% !important; box-shadow:0 4px 14px rgba(183,138,0,0.25) !important; transition:all 0.15s ease !important; }
.stButton > button:hover { background:#9a7400 !important; box-shadow:0 6px 20px rgba(183,138,0,0.35) !important; transform:translateY(-1px) !important; }
.stButton > button *, .stButton > button p, .stButton > button span, .stButton > button div { color:#FFFFFF !important; }
[data-testid="stFormSubmitButton"] > button { background:#b78a00 !important; color:#FFFFFF !important; border:none !important; border-radius:14px !important; font-weight:700 !important; font-size:14px !important; padding:13px 20px !important; width:100% !important; box-shadow:0 4px 14px rgba(183,138,0,0.25) !important; margin-top:6px !important; }
[data-testid="stFormSubmitButton"] > button *, [data-testid="stFormSubmitButton"] > button p, [data-testid="stFormSubmitButton"] > button span, [data-testid="stFormSubmitButton"] > button div { color:#FFFFFF !important; }
[data-testid="baseButton-secondary"] { background:rgba(192,57,43,0.08) !important; color:#C0392B !important; border:1px solid rgba(192,57,43,0.2) !important; border-radius:10px !important; padding:8px 6px !important; box-shadow:none !important; font-size:15px !important; font-weight:600 !important; line-height:1 !important; margin-top:4px !important; transform:none !important; }
[data-testid="baseButton-secondary"]:hover { background:rgba(192,57,43,0.15) !important; border-color:rgba(192,57,43,0.4) !important; box-shadow:none !important; transform:none !important; }

/* Form */
[data-testid="stForm"] { background:#FFFFFF !important; border-radius:20px !important; padding:1.4rem !important; border:1px solid rgba(0,0,0,0.06) !important; box-shadow:0 4px 20px rgba(0,0,0,0.05) !important; }

/* Radio — estilo normal (vertical) */
.stRadio [data-baseweb="radio"] label { color:#322b49 !important; font-size:14px !important; font-weight:500 !important; }
.stRadio [data-baseweb="radio"] label p,
.stRadio [data-baseweb="radio"] label span { color:#322b49 !important; }
.stRadio [data-baseweb="radio"][data-checked="true"] label,
.stRadio [data-baseweb="radio"][data-checked="true"] label p,
.stRadio [data-baseweb="radio"][data-checked="true"] label span { color:#b78a00 !important; font-weight:700 !important; }
.stRadio [data-baseweb="radio"] div[data-checked="true"] { background:#b78a00 !important; border-color:#b78a00 !important; }

/* Radio horizontal — Streamlit lo renderiza con el componente tab de BasewUI */
[data-testid="stRadio"] [data-baseweb="tab-list"] { background:#FDFAF5 !important; border:1px solid rgba(50,43,73,0.15) !important; box-shadow:none !important; border-radius:12px !important; }
[data-testid="stRadio"] [data-baseweb="tab"] { color:#322b49 !important; font-size:14px !important; font-weight:500 !important; background:transparent !important; }
[data-testid="stRadio"] [data-baseweb="tab"] p,
[data-testid="stRadio"] [data-baseweb="tab"] span,
[data-testid="stRadio"] [data-baseweb="tab"] div { color:#322b49 !important; }
[data-testid="stRadio"] [aria-selected="true"][data-baseweb="tab"] { color:#b78a00 !important; font-weight:700 !important; background:rgba(183,138,0,0.1) !important; }
[data-testid="stRadio"] [aria-selected="true"][data-baseweb="tab"] p,
[data-testid="stRadio"] [aria-selected="true"][data-baseweb="tab"] span,
[data-testid="stRadio"] [aria-selected="true"][data-baseweb="tab"] div { color:#b78a00 !important; }

/* Number input step buttons */
[data-testid="stNumberInputStepUp"],[data-testid="stNumberInputStepDown"] { display:none !important; }
.stNumberInput > div > div { border-radius:12px !important; }

/* Alerts */
.stSuccess > div { background:rgba(74,124,89,0.1) !important; border-color:#4A7C59 !important; color:#4A7C59 !important; border-radius:12px !important; }
.stError > div { background:rgba(192,57,43,0.1) !important; border-color:#C0392B !important; color:#C0392B !important; border-radius:12px !important; }
.stInfo > div { background:rgba(45,106,143,0.1) !important; border-color:#2D6A8F !important; color:#2D6A8F !important; border-radius:12px !important; }

/* Expander */
.streamlit-expanderHeader { background:#FDFAF5 !important; border-radius:12px !important; color:#322b49 !important; border:1px solid rgba(50,43,73,0.1) !important; }
.streamlit-expanderContent { background:#FFFFFF !important; border-radius:0 0 12px 12px !important; border:1px solid rgba(50,43,73,0.1) !important; border-top:none !important; }
[data-testid="stExpander"] details summary { color:#322b49 !important; }
[data-testid="stExpander"] details summary p,
[data-testid="stExpander"] details summary span,
[data-testid="stExpander"] details summary div { color:#322b49 !important; }
[data-testid="stExpander"] details { background:#FDFAF5 !important; border:1px solid rgba(50,43,73,0.1) !important; border-radius:12px !important; }
[data-testid="stExpander"] details > div { background:#FFFFFF !important; color:#322b49 !important; }
[data-testid="stExpander"] details > div label,
[data-testid="stExpander"] details > div p { color:#322b49 !important; }

/* Header logout button — small, discrete, top-right */
[data-testid="stHorizontalBlock"]:first-of-type [data-testid="column"]:last-child .stButton button {
    background: transparent !important;
    color: #322b49 !important;
    border: 1px solid rgba(183,138,0,0.5) !important;
    box-shadow: none !important;
    font-size: 12px !important;
    padding: 5px 14px !important;
    font-weight: 500 !important;
    width: auto !important;
    transform: none !important;
}
[data-testid="stHorizontalBlock"]:first-of-type [data-testid="column"]:last-child .stButton button *,
[data-testid="stHorizontalBlock"]:first-of-type [data-testid="column"]:last-child .stButton button p,
[data-testid="stHorizontalBlock"]:first-of-type [data-testid="column"]:last-child .stButton button span { color: #322b49 !important; }
[data-testid="stHorizontalBlock"]:first-of-type [data-testid="column"]:last-child .stButton button:hover {
    background: rgba(183,138,0,0.08) !important;
    border-color: #b78a00 !important;
}

/* Scrollbar */
::-webkit-scrollbar { width:4px; }
::-webkit-scrollbar-track { background:#F5F0E8; }
::-webkit-scrollbar-thumb { background:#DDD8CC; border-radius:4px; }
hr { border-color:#E8E3D8 !important; }
"""

# ─── HTML Components ───────────────────────────────────────────────────────────
def section_title(text):
    return f'<p style="color:#322b49;font-size:11px;text-transform:uppercase;letter-spacing:0.9px;font-weight:700;margin:20px 0 10px;">{text}</p>'

def card_wrap(content, padding="1.4rem 1.5rem"):
    return f'<div style="background:#FFFFFF;border-radius:20px;padding:{padding};border:1px solid rgba(0,0,0,0.06);margin-bottom:12px;box-shadow:0 2px 16px rgba(0,0,0,0.05);">{content}</div>'

def balance_card_html(balance, ingresos, gastos):
    bal_color = "#4A7C59" if balance >= 0 else "#C0392B"
    sign_lbl  = "↑ Saldo positivo" if balance >= 0 else "↓ Saldo negativo"
    bal_str   = ("" if balance >= 0 else "− ") + cop(balance)
    return f"""
    <div style="background:#FDFAF5;border-radius:24px;
                padding:1.6rem 1.8rem;border:1px solid rgba(183,138,0,0.35);
                box-shadow:0 4px 24px rgba(183,138,0,0.1);margin-bottom:16px;
                display:flex;align-items:center;justify-content:space-between;gap:1rem;">
      <div style="flex:1;">
        <p style="color:#322b49;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;font-weight:600;">Balance Total</p>
        <p style="color:{bal_color};font-size:2.6rem;font-weight:800;margin:0 0 4px;letter-spacing:-1.5px;line-height:1;">{bal_str}</p>
        <p style="color:#6b6285;font-size:12px;margin:0;">{sign_lbl}</p>
      </div>
      <div style="border-left:1px solid rgba(183,138,0,0.3);padding-left:1.4rem;flex-shrink:0;">
        <div style="margin-bottom:12px;">
          <p style="color:#5c5474;font-size:10px;text-transform:uppercase;letter-spacing:0.8px;margin:0 0 3px;font-weight:600;">Ingresos</p>
          <p style="color:#4A7C59;font-size:15px;font-weight:700;margin:0;">+{cop(ingresos)}</p>
        </div>
        <div>
          <p style="color:#5c5474;font-size:10px;text-transform:uppercase;letter-spacing:0.8px;margin:0 0 3px;font-weight:600;">Gastos</p>
          <p style="color:#C0392B;font-size:15px;font-weight:700;margin:0;">−{cop(gastos)}</p>
        </div>
      </div>
    </div>"""

def tx_row(icon, categoria, desc, fecha, monto, is_income):
    color = "#4A7C59" if is_income else "#C0392B"
    sign  = "+" if is_income else "-"
    label = desc if desc else categoria
    return f"""
    <div style="display:flex;align-items:center;padding:11px 0;border-bottom:1px solid rgba(0,0,0,0.04);">
      <div style="width:42px;height:42px;border-radius:13px;background:#F5F0E8;display:flex;align-items:center;justify-content:center;font-size:19px;margin-right:12px;flex-shrink:0;">{icon}</div>
      <div style="flex:1;min-width:0;">
        <p style="color:#1c1829;font-size:13px;font-weight:500;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{label}</p>
        <p style="color:#6b6285;font-size:11px;margin:2px 0 0;">{categoria} · {fecha}</p>
      </div>
      <p style="color:{color};font-size:14px;font-weight:600;margin:0;flex-shrink:0;padding-left:8px;">{sign}{cop(monto)}</p>
    </div>"""

def asset_row(icon, nombre, tipo, valor):
    return f"""
    <div style="display:flex;align-items:center;padding:12px 0;border-bottom:1px solid rgba(0,0,0,0.04);">
      <div style="width:44px;height:44px;border-radius:14px;background:#F5F0E8;display:flex;align-items:center;justify-content:center;font-size:20px;margin-right:13px;flex-shrink:0;">{icon}</div>
      <div style="flex:1;">
        <p style="color:#1c1829;font-size:14px;font-weight:500;margin:0;">{nombre}</p>
        <p style="color:#6b6285;font-size:12px;margin:2px 0 0;">{tipo}</p>
      </div>
      <p style="color:#4A7C59;font-size:14px;font-weight:600;margin:0;">{cop(valor)}</p>
    </div>"""

def debt_card(nombre, tipo, deuda_inicial, saldo, tasa, pago_minimo, fecha_fin=None, total_int=None):
    pagado = max(deuda_inicial - saldo, 0)
    pct    = pagado / deuda_inicial if deuda_inicial > 0 else 0
    bar_w  = int(pct * 100)
    pct_r  = saldo / deuda_inicial if deuda_inicial > 0 else 0
    color  = "#4A7C59" if pct_r < 0.25 else "#b78a00" if pct_r < 0.6 else "#C0392B"
    icon   = DEUDA_ICONS.get(tipo, "📋")
    tasa_s = f"{tasa:.1f}% anual" if tasa > 0 else "Sin interés"

    if fecha_fin and total_int is not None:
        proj_html = (
            f'<div style="background:#F5F0E8;border-radius:12px;padding:10px 12px;margin-top:12px;border:1px solid rgba(192,57,43,0.1);">'
            f'<p style="color:#5c5474;font-size:10px;text-transform:uppercase;letter-spacing:0.7px;font-weight:600;margin:0 0 6px;">📅 Proyección de pago</p>'
            f'<div style="display:flex;justify-content:space-between;">'
            f'<div><p style="color:#5c5474;font-size:11px;margin:0;">Fecha estimada de pago</p>'
            f'<p style="color:#1c1829;font-size:13px;font-weight:600;margin:2px 0 0;">{fecha_fin.strftime("%b %Y")}</p></div>'
            f'<div style="text-align:right;"><p style="color:#5c5474;font-size:11px;margin:0;">Total en intereses</p>'
            f'<p style="color:#C0392B;font-size:13px;font-weight:600;margin:2px 0 0;">{cop(total_int)}</p></div>'
            f'</div></div>'
        )
    elif pago_minimo <= 0:
        proj_html = '<p style="color:#5c5474;font-size:11px;margin:10px 0 0;">Sin pago mínimo registrado para proyectar.</p>'
    else:
        proj_html = '<p style="color:#C0392B;font-size:11px;margin:10px 0 0;">⚠️ El pago mínimo no alcanza a cubrir los intereses.</p>'

    return f"""
    <div style="background:#FFFFFF;border-radius:20px;padding:1.3rem 1.5rem;
                border:1px solid rgba(192,57,43,0.1);margin-bottom:10px;
                box-shadow:0 2px 16px rgba(0,0,0,0.05);">
      <div style="display:flex;align-items:center;margin-bottom:14px;">
        <span style="font-size:20px;background:#F5F0E8;width:44px;height:44px;border-radius:14px;
                     display:inline-flex;align-items:center;justify-content:center;margin-right:12px;flex-shrink:0;">{icon}</span>
        <div style="flex:1;">
          <p style="color:#1c1829;font-size:15px;font-weight:600;margin:0;">{nombre}</p>
          <p style="color:#6b6285;font-size:12px;margin:2px 0 0;">{tipo} · {tasa_s}</p>
        </div>
        <div style="text-align:right;">
          <p style="color:{color};font-size:18px;font-weight:700;margin:0;">{cop(saldo)}</p>
          <p style="color:#6b6285;font-size:11px;margin:2px 0 0;">restante</p>
        </div>
      </div>
      <div style="background:#F5F0E8;border-radius:8px;height:8px;overflow:hidden;margin-bottom:12px;">
        <div style="width:{bar_w}%;height:100%;border-radius:8px;background:linear-gradient(90deg,#4A7C59,#3D6B4A);"></div>
      </div>
      <div style="display:flex;justify-content:space-between;">
        <div>
          <p style="color:#5c5474;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;margin:0;">Pagado</p>
          <p style="color:#4A7C59;font-size:13px;font-weight:600;margin:3px 0 0;">{cop(pagado)} <span style="color:#6b6285;font-weight:400;">({int(pct*100)}%)</span></p>
        </div>
        <div style="text-align:center;">
          <p style="color:#5c5474;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;margin:0;">Pago mínimo</p>
          <p style="color:#1c1829;font-size:13px;font-weight:600;margin:3px 0 0;">{cop(pago_minimo)}/mes</p>
        </div>
        <div style="text-align:right;">
          <p style="color:#5c5474;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;margin:0;">Deuda original</p>
          <p style="color:#1c1829;font-size:13px;font-weight:600;margin:3px 0 0;">{cop(deuda_inicial)}</p>
        </div>
      </div>
      {proj_html}
    </div>"""

def meta_card(emoji, nombre, actual, objetivo, fecha_limite):
    pct      = min(actual / objetivo, 1.0) if objetivo > 0 else 0
    falta    = max(objetivo - actual, 0)
    bar_w    = int(pct * 100)
    deadline = f"Límite: {fecha_limite}" if fecha_limite else "Sin fecha límite"
    color    = "#4A7C59" if pct >= 1 else "#b78a00" if pct >= 0.6 else "#2D6A8F"
    status   = "¡Meta alcanzada! 🎉" if pct >= 1 else f"Falta {cop(falta)}"
    milestones = ""
    for pct_m in [25, 50, 75]:
        dot_color = "#b78a00" if bar_w >= pct_m else "#DDD8CC"
        milestones += f'<div style="position:absolute;left:{pct_m}%;top:-2px;width:2px;height:12px;background:{dot_color};border-radius:1px;"></div>'

    return f"""
    <div style="background:#FFFFFF;border-radius:20px;padding:1.3rem 1.5rem;
                border:1px solid rgba(0,0,0,0.06);margin-bottom:10px;
                box-shadow:0 2px 16px rgba(0,0,0,0.05);">
      <div style="display:flex;align-items:center;margin-bottom:14px;">
        <span style="font-size:26px;margin-right:12px;">{emoji}</span>
        <div style="flex:1;">
          <p style="color:#1c1829;font-size:15px;font-weight:600;margin:0;">{nombre}</p>
          <p style="color:#6b6285;font-size:12px;margin:2px 0 0;">{deadline}</p>
        </div>
        <div style="text-align:right;">
          <p style="color:{color};font-size:18px;font-weight:800;margin:0;">{int(pct*100)}%</p>
        </div>
      </div>
      <div style="position:relative;margin-bottom:6px;">
        <div style="background:#F5F0E8;border-radius:8px;height:12px;overflow:hidden;">
          <div style="width:{bar_w}%;height:100%;border-radius:8px;
                      background:linear-gradient(90deg,{color},{color}BB);
                      transition:width 0.6s ease;"></div>
        </div>
        {milestones}
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;">
        <div>
          <p style="color:#5c5474;font-size:11px;margin:0;">Ahorrado</p>
          <p style="color:#1c1829;font-size:14px;font-weight:700;margin:2px 0 0;">{cop(actual)}</p>
        </div>
        <div style="text-align:center;">
          <p style="color:{color};font-size:12px;font-weight:600;margin:0;
                    background:{"rgba(74,124,89,0.1)" if pct>=1 else "rgba(45,106,143,0.1)"};
                    padding:4px 10px;border-radius:20px;">{status}</p>
        </div>
        <div style="text-align:right;">
          <p style="color:#5c5474;font-size:11px;margin:0;">Objetivo</p>
          <p style="color:#1c1829;font-size:14px;font-weight:700;margin:2px 0 0;">{cop(objetivo)}</p>
        </div>
      </div>
    </div>"""

# ─── Auth Pages ────────────────────────────────────────────────────────────────
def page_auth():
    st.markdown("""
    <div style="text-align:center;padding:3rem 0 2.5rem;">
      <p style="font-family:'Playfair Display',Georgia,serif;font-size:3.2rem;font-weight:700;
                color:#322b49;margin:0;letter-spacing:-1px;line-height:1;">
        Valore<span style="color:#eab000;"> ◆</span>
      </p>
      <p style="color:#5c5474;font-size:13px;margin:10px 0 0;letter-spacing:2px;text-transform:uppercase;font-weight:500;">
        Finanzas que te representan.
      </p>
    </div>
    """, unsafe_allow_html=True)

    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "login"

    # CSS para el botón inactivo según el modo actual
    if st.session_state.auth_mode == "login":
        st.markdown("""<style>
        [data-testid="stHorizontalBlock"] [data-testid="column"]:nth-child(2) .stButton button {
            background: transparent !important; color: #322b49 !important;
            border: 1.5px solid #b78a00 !important; box-shadow: none !important; }
        [data-testid="stHorizontalBlock"] [data-testid="column"]:nth-child(2) .stButton button *,
        [data-testid="stHorizontalBlock"] [data-testid="column"]:nth-child(2) .stButton button p,
        [data-testid="stHorizontalBlock"] [data-testid="column"]:nth-child(2) .stButton button span
            { color: #322b49 !important; }
        </style>""", unsafe_allow_html=True)
    else:
        st.markdown("""<style>
        [data-testid="stHorizontalBlock"] [data-testid="column"]:nth-child(1) .stButton button {
            background: transparent !important; color: #322b49 !important;
            border: 1.5px solid #b78a00 !important; box-shadow: none !important; }
        [data-testid="stHorizontalBlock"] [data-testid="column"]:nth-child(1) .stButton button *,
        [data-testid="stHorizontalBlock"] [data-testid="column"]:nth-child(1) .stButton button p,
        [data-testid="stHorizontalBlock"] [data-testid="column"]:nth-child(1) .stButton button span
            { color: #322b49 !important; }
        </style>""", unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Iniciar sesión", key="tab_login", use_container_width=True):
            st.session_state.auth_mode = "login"
            st.rerun()
    with col_b:
        if st.button("Crear cuenta", key="tab_register", use_container_width=True):
            st.session_state.auth_mode = "register"
            st.rerun()

    if st.session_state.auth_mode == "login":
        with st.form("form_login", clear_on_submit=False):
            email    = st.text_input("Email", placeholder="tu@email.com")
            password = st.text_input("Contraseña", type="password", placeholder="••••••")
            ok = st.form_submit_button("Iniciar sesión", use_container_width=True)
            if ok:
                if not email or not password:
                    st.error("Completa todos los campos.")
                else:
                    user_id, nombre = authenticate_user(email, password)
                    if user_id:
                        st.session_state.user_id   = user_id
                        st.session_state.user_name = nombre
                        st.rerun()
                    else:
                        st.error("Email o contraseña incorrectos.")
    else:  # auth_mode == "register"
        with st.form("form_register", clear_on_submit=False):
            nombre   = st.text_input("Tu nombre", placeholder="Diego")
            email    = st.text_input("Email", placeholder="tu@email.com")
            password = st.text_input("Contraseña", type="password", placeholder="Mínimo 6 caracteres")
            ok = st.form_submit_button("Crear cuenta", use_container_width=True)
            if ok:
                if not nombre or not email or not password:
                    st.error("Completa todos los campos.")
                elif len(password) < 6:
                    st.error("La contraseña debe tener al menos 6 caracteres.")
                else:
                    success, err = create_user(nombre, email, password)
                    if success:
                        user_id, uname = authenticate_user(email, password)
                        st.session_state.user_id   = user_id
                        st.session_state.user_name = uname
                        st.rerun()
                    else:
                        st.error(err)

# ─── Pages ────────────────────────────────────────────────────────────────────
def page_dashboard():
    df = query("SELECT * FROM transacciones WHERE user_id=? ORDER BY fecha DESC, id DESC",
               params=(uid(),))

    if df.empty:
        st.markdown(balance_card_html(0, 0, 0), unsafe_allow_html=True)
        st.markdown(card_wrap(
            '<p style="color:#6b6285;text-align:center;font-size:14px;padding:1rem 0;margin:0;">¡Agrega tu primera transacción en la pestaña Transacciones!</p>'
        ), unsafe_allow_html=True)
        return

    ingresos = df[df["tipo"] == "Ingreso"]["monto"].sum()
    gastos   = df[df["tipo"] == "Gasto"]["monto"].sum()
    balance  = ingresos - gastos

    st.markdown(balance_card_html(balance, ingresos, gastos), unsafe_allow_html=True)

    mes_actual = date.today().strftime("%Y-%m")
    df_mes = df[(df["tipo"] == "Gasto") & (df["fecha"].str.startswith(mes_actual))]
    if not df_mes.empty:
        st.markdown(section_title(f"Gastos de {date.today().strftime('%B %Y')}"), unsafe_allow_html=True)
        df_cat_mes = df_mes.groupby("categoria")["monto"].sum().sort_values(ascending=True).reset_index()
        fig_bar = go.Figure(go.Bar(
            x=df_cat_mes["monto"],
            y=df_cat_mes["categoria"],
            orientation="h",
            marker=dict(color=cat_colors(df_cat_mes["categoria"]), line=dict(width=0)),
            text=[cop(v) for v in df_cat_mes["monto"]],
            textposition="outside",
            textfont=dict(color="#322b49", size=11),
            hovertemplate="<b>%{y}</b><br>%{text}<extra></extra>",
        ))
        fig_bar.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#322b49"),
            margin=dict(l=10, r=90, t=10, b=0),
            height=max(160, len(df_cat_mes) * 40),
            xaxis=dict(visible=False),
            yaxis=dict(color="#322b49", tickfont=dict(color="#322b49", size=12),
                       gridcolor="rgba(0,0,0,0)", automargin=True),
            showlegend=False,
        )
        st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

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
                run("INSERT INTO transacciones (fecha,tipo,categoria,descripcion,monto,cuenta,user_id) VALUES (?,?,?,?,?,?,?)",
                    (str(fecha), tipo, cat_final, descripcion, monto, cuenta, uid()))
                st.success(f"{'Ingreso' if tipo=='Ingreso' else 'Gasto'} de {cop(monto)} guardado.")

    df = query("SELECT * FROM transacciones WHERE user_id=? ORDER BY fecha DESC, id DESC",
               params=(uid(),))
    if df.empty:
        st.info("Sin transacciones aún.")
        return

    # ── Dona de distribución de gastos ──
    df_gas_all = df[df["tipo"] == "Gasto"].groupby("categoria")["monto"].sum().reset_index()
    gastos_total = df_gas_all["monto"].sum()
    if not df_gas_all.empty:
        st.markdown(section_title("Distribución de gastos"), unsafe_allow_html=True)
        fig_dona = go.Figure(go.Pie(
            labels=df_gas_all["categoria"],
            values=df_gas_all["monto"],
            hole=0.58,
            marker=dict(colors=cat_colors(df_gas_all["categoria"]), line=dict(color="#F5F0E8", width=2)),
            textinfo="none",
            hovertemplate="<b>%{label}</b><br>%{percent}<extra></extra>",
        ))
        top = df_gas_all.loc[df_gas_all["monto"].idxmax()]
        fig_dona.add_annotation(
            text=f"<b>{int(top['monto']/gastos_total*100)}%</b>",
            font=dict(size=15, color="#322b49"),
            showarrow=False, x=0.5, y=0.56, xref="paper", yref="paper",
        )
        fig_dona.add_annotation(
            text=top["categoria"],
            font=dict(size=10, color="#322b49"),
            showarrow=False, x=0.5, y=0.40, xref="paper", yref="paper",
        )
        fig_dona.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#322b49"),
            margin=dict(l=0, r=0, t=10, b=0), height=220,
            legend=dict(font=dict(color="#322b49", size=11), bgcolor="rgba(0,0,0,0)"),
        )
        st.plotly_chart(fig_dona, use_container_width=True, config={"displayModeBar": False})

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
        color      = "#4A7C59" if is_income else "#C0392B"
        sign       = "+" if is_income else "-"
        label      = r["descripcion"] if r["descripcion"] else r["categoria"]
        cuenta_val = r["cuenta"] if pd.notna(r.get("cuenta")) else "Efectivo"
        cuenta_ico = CUENTA_ICONS.get(cuenta_val, "🏷️")
        flecha     = "→" if is_income else "←"

        col_info, col_del = st.columns([11, 1])
        with col_info:
            st.markdown(f"""
            <div style="background:#FFFFFF;border-radius:16px;padding:10px 14px;
                        border:1px solid rgba(0,0,0,0.05);margin-bottom:6px;
                        display:flex;align-items:center;gap:12px;box-shadow:0 1px 8px rgba(0,0,0,0.04);">
              <span style="font-size:20px;background:#F5F0E8;width:42px;height:42px;border-radius:12px;
                           display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;">{icon}</span>
              <div style="flex:1;min-width:0;">
                <p style="color:#1c1829;font-size:14px;font-weight:500;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{label}</p>
                <p style="color:#6b6285;font-size:12px;margin:2px 0 0;">{r["categoria"]} · {r["fecha"]}</p>
                <p style="color:#B8A890;font-size:11px;margin:3px 0 0;">{cuenta_ico} {flecha} {cuenta_val}</p>
              </div>
              <p style="color:{color};font-size:14px;font-weight:600;margin:0;flex-shrink:0;">{sign}{cop(r["monto"])}</p>
            </div>""", unsafe_allow_html=True)
        with col_del:
            if st.button("✕", key=f"del_{r['id']}", type="secondary", use_container_width=True, help="Eliminar"):
                run("DELETE FROM transacciones WHERE id=? AND user_id=?", (int(r["id"]), uid()))
                st.rerun()

    st.markdown(f'<p style="color:#6b6285;font-size:12px;text-align:center;margin-top:4px;">{len(dff)} transacciones</p>', unsafe_allow_html=True)


def page_portafolio():
    df    = query("SELECT * FROM portafolio WHERE user_id=? ORDER BY id DESC", params=(uid(),))
    total = df["cantidad"].sum() if not df.empty else 0

    st.markdown(card_wrap(f"""
      <p style="color:#5c5474;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;font-weight:600;">Valor total del portafolio</p>
      <p style="color:#4A7C59;font-size:2.4rem;font-weight:800;margin:0;letter-spacing:-1px;">{cop(total)}</p>
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
                run("INSERT INTO portafolio (nombre,tipo,cantidad,valor_unitario,fecha,user_id) VALUES (?,?,?,?,?,?)",
                    (nombre, tipo, valor, 1.0, str(fecha), uid()))
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
                    min_value=0.0, value=float(r["cantidad"]),
                    step=1000.0, format="%.0f", key=f"val_{r['id']}"
                )
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("💾 Guardar", key=f"save_{r['id']}", use_container_width=True):
                        run("UPDATE portafolio SET cantidad=? WHERE id=? AND user_id=?", (nuevo_valor, r["id"], uid()))
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
        hovertemplate="<b>%{x}</b><br><extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#322b49"),
        margin=dict(l=0, r=0, t=10, b=0), height=180,
        xaxis=dict(color="#322b49", tickfont=dict(color="#322b49"), gridcolor="rgba(0,0,0,0.04)"),
        yaxis=dict(color="#322b49", tickfont=dict(color="#322b49"), gridcolor="rgba(0,0,0,0.04)"),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with st.expander("Eliminar activo"):
        opciones = {f"{r['nombre']} · {r['tipo']} (#{r['id']})": r["id"] for _, r in df.iterrows()}
        sel = st.selectbox("Selecciona", list(opciones.keys()), key="del_activo")
        if st.button("Eliminar activo", key="btn_del_activo"):
            run("DELETE FROM portafolio WHERE id=? AND user_id=?", (opciones[sel], uid()))
            st.rerun()


def page_metas():
    df = query("SELECT * FROM metas WHERE user_id=? ORDER BY id DESC", params=(uid(),))

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
                run("INSERT INTO metas (nombre,objetivo,actual,fecha_limite,emoji,user_id) VALUES (?,?,0,?,?,?)",
                    (nombre, objetivo, str(deadline) if deadline else None, emoji, uid()))
                st.success(f"Meta '{nombre}' creada.")
                st.rerun()

    if df.empty:
        st.info("Crea tu primera meta de ahorro.")
        return

    total_obj  = df["objetivo"].sum()
    total_act  = df["actual"].sum()
    pct_global = int(total_act / total_obj * 100) if total_obj > 0 else 0

    st.markdown(card_wrap(f"""
      <p style="color:#5c5474;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;font-weight:600;">Progreso global</p>
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px;">
        <p style="color:#1c1829;font-size:20px;font-weight:700;margin:0;">{cop(total_act)}</p>
        <p style="color:#6b6285;font-size:13px;margin:0;">de {cop(total_obj)}</p>
      </div>
      <div style="background:#F5F0E8;border-radius:8px;height:10px;overflow:hidden;">
        <div style="width:{pct_global}%;height:100%;border-radius:8px;background:linear-gradient(90deg,#b78a00,#9a7400);"></div>
      </div>
      <p style="color:#b78a00;font-size:12px;font-weight:600;margin:6px 0 0;text-align:right;">{pct_global}% completado</p>
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
                run("UPDATE metas SET actual = MIN(actual + ?, objetivo) WHERE id = ? AND user_id = ?",
                    (add_monto, nombres[sel_meta], uid()))
                st.success(f"+{cop(add_monto)} agregado a '{sel_meta}'.")
                st.rerun()

    with st.expander("Eliminar meta"):
        opciones = {f"{r['emoji']} {r['nombre']}": r["id"] for _, r in df.iterrows()}
        sel = st.selectbox("Selecciona", list(opciones.keys()), key="del_meta")
        if st.button("Eliminar meta", key="btn_del_meta"):
            run("DELETE FROM metas WHERE id=? AND user_id=?", (opciones[sel], uid()))
            st.rerun()


def page_deudas():
    df = query("SELECT * FROM deudas WHERE user_id=? ORDER BY saldo DESC", params=(uid(),))

    total_saldo   = df["saldo"].sum() if not df.empty else 0
    total_inicial = df["deuda_inicial"].sum() if not df.empty else 0
    total_pagado  = max(total_inicial - total_saldo, 0)
    pct_g         = int(total_pagado / total_inicial * 100) if total_inicial > 0 else 0

    st.markdown(card_wrap(f"""
      <p style="color:#5c5474;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;font-weight:600;">Deuda total restante</p>
      <p style="color:#C0392B;font-size:2.4rem;font-weight:800;margin:0 0 4px;letter-spacing:-1px;">{cop(total_saldo)}</p>
      <p style="color:#6b6285;font-size:12px;margin:0 0 16px;">de {cop(total_inicial)} originales</p>
      <div style="background:#F5F0E8;border-radius:8px;height:10px;overflow:hidden;margin-bottom:8px;">
        <div style="width:{pct_g}%;height:100%;border-radius:8px;background:linear-gradient(90deg,#4A7C59,#3D6B4A);"></div>
      </div>
      <div style="display:flex;justify-content:space-between;">
        <p style="color:#4A7C59;font-size:12px;font-weight:600;margin:0;">✓ Pagado: {cop(total_pagado)} ({pct_g}%)</p>
        <p style="color:#6b6285;font-size:12px;margin:0;">{len(df)} deuda(s)</p>
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
                run("INSERT INTO deudas (nombre,tipo,deuda_inicial,saldo,tasa_interes,pago_minimo,fecha_inicio,user_id) VALUES (?,?,?,?,?,?,?,?)",
                    (nombre, tipo, deuda_inicial, deuda_inicial, tasa or 0.0, pago_minimo or 0.0, str(fecha_inicio), uid()))
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
                <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(0,0,0,0.04);">
                  <p style="color:#6b6285;font-size:12px;margin:0;">{p['fecha']}{nota}</p>
                  <p style="color:#4A7C59;font-size:12px;font-weight:600;margin:0;">-{cop(p['monto'])}</p>
                </div>"""
            st.markdown(card_wrap(
                '<p style="color:#5c5474;font-size:11px;text-transform:uppercase;letter-spacing:0.7px;font-weight:600;margin:0 0 8px;">Últimos pagos</p>' + hist_html,
                "0.9rem 1.2rem"
            ), unsafe_allow_html=True)

    with st.expander("Registrar un pago"):
        deudas_map   = {r["nombre"]: (r["id"], r["saldo"]) for _, r in df.iterrows()}
        sel_deuda    = st.selectbox("Deuda", list(deudas_map.keys()), key="sel_deuda_pago")
        did, saldo_s = deudas_map[sel_deuda]
        st.markdown(f'<p style="color:#C0392B;font-size:13px;margin:4px 0 12px;">Saldo actual: <b>{cop(saldo_s)}</b></p>', unsafe_allow_html=True)
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
                run("UPDATE deudas SET saldo=? WHERE id=? AND user_id=?", (nuevo_saldo, int(did), uid()))
                st.success(f"Pago de {cop(pago_monto)} registrado. Saldo: {cop(nuevo_saldo)}")
                st.rerun()

    with st.expander("Eliminar deuda"):
        opciones = {r["nombre"]: r["id"] for _, r in df.iterrows()}
        sel = st.selectbox("Selecciona", list(opciones.keys()), key="del_deuda")
        if st.button("Eliminar deuda", key="btn_del_deuda"):
            run("DELETE FROM pagos_deuda WHERE deuda_id=?", (opciones[sel],))
            run("DELETE FROM deudas WHERE id=? AND user_id=?", (opciones[sel], uid()))
            st.rerun()


# ─── Main ─────────────────────────────────────────────────────────────────────
init_db()
st.set_page_config(page_title="Valore", page_icon="static/icon.png", layout="centered",
                   initial_sidebar_state="collapsed")
st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
st.markdown("""
<link rel="apple-touch-icon" href="app/static/icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Valore">
<meta name="theme-color" content="#322b49">
""", unsafe_allow_html=True)

if "user_id" not in st.session_state:
    page_auth()
else:
    # Header
    col_logo, col_user = st.columns([5, 1])
    with col_logo:
        st.markdown(
            '<p style="font-family:\'Playfair Display\',Georgia,serif;font-size:1.6rem;'
            'font-weight:700;color:#322b49;margin:0 0 4px;letter-spacing:-0.5px;">'
            f'Valore<span style="color:#eab000;"> ◆</span></p>'
            f'<p style="color:#6b6285;font-size:12px;margin:0;">Hola, {st.session_state.user_name}</p>',
            unsafe_allow_html=True
        )
    with col_user:
        st.markdown("<div style='display:flex;justify-content:flex-end;align-items:center;height:100%;padding-top:8px;'>", unsafe_allow_html=True)
        if st.button("Salir", key="logout"):
            del st.session_state["user_id"]
            del st.session_state["user_name"]
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom:1rem;'></div>", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["Dashboard", "Transacciones", "Portafolio", "Metas", "Deudas"]
    )
    with tab1: page_dashboard()
    with tab2: page_transacciones()
    with tab3: page_portafolio()
    with tab4: page_metas()
    with tab5: page_deudas()
