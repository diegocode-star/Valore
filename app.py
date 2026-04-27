import streamlit as st
import pandas as pd
from datetime import date
import hashlib
import plotly.graph_objects as go
import os
import anthropic

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from supabase import create_client

# ─── Constants ────────────────────────────────────────────────────────────────
CATEGORIAS_INGRESO = ["Salario", "Préstamo", "Retiro de portafolio", "Otro ingreso"]
CATEGORIAS_GASTO   = ["Alimentación", "Restaurantes", "Transporte", "Vivienda", "Salud",
                      "Educación", "Entretenimiento", "Ropa", "Servicios", "Deudas", "Portafolio", "Obligaciones", "Otro gasto"]
TIPOS_ACTIVO       = ["Acciones", "Crypto", "CDT", "Cuenta de ahorros", "Fondo de inversión",
                      "Bonos", "Inmuebles", "Ahorro", "Otro"]
TIPOS_RENTA_FIJA   = {"CDT", "Cuenta de ahorros", "Bonos"}
MODALIDADES_INT    = ["Compuesto", "Simple"]
TIPOS_DEUDA        = ["Tarjeta de crédito", "Préstamo personal", "Hipoteca", "Auto", "Estudiantil", "Otro"]
CUENTAS            = ["Efectivo", "Cuenta bancaria", "Tarjeta de crédito", "Billetera digital", "Otro"]
TIPOS_CUENTA       = ["Cuenta bancaria", "Billetera digital", "Efectivo", "Tarjeta de crédito", "Inversiones", "Otro"]
META_EMOJIS        = ["🎯", "✈️", "🏠", "🚗", "💍", "🎓", "🏖️", "💪", "🛍️", "🌟"]
ADMIN_EMAIL        = "diegorenba@gmail.com"

MONEDAS         = ["COP", "USD", "EUR", "GBP", "JPY"]
MONEDA_SIMBOLO  = {"COP": "$", "USD": "US$", "EUR": "€", "GBP": "£", "JPY": "¥"}
TASA_A_COP      = {"COP": 1, "USD": 4_100, "EUR": 4_450, "GBP": 5_200, "JPY": 27}

CUENTA_ICONS = {
    "Efectivo":"💵","Cuenta bancaria":"🏦",
    "Tarjeta de crédito":"💳","Billetera digital":"📱","Otro":"🏷️",
}
CAT_ICONS = {
    "Salario":"💼","Préstamo":"🏦","Otro ingreso":"💰",
    "Alimentación":"🛒","Restaurantes":"🍽️","Transporte":"🚗","Vivienda":"🏠","Salud":"💊","Educación":"📚",
    "Entretenimiento":"🎬","Ropa":"👗","Servicios":"⚡","Deudas":"💳","Portafolio":"📈","Obligaciones":"📋","Otro gasto":"📦",
    "Retiro de portafolio":"📉",
    "Acciones":"📊","Crypto":"₿","CDT":"🏛️","Cuenta de ahorros":"💰",
    "Fondo de inversión":"💼","Ahorro":"🏦","Inmuebles":"🏡","Bonos":"📜","Otro":"💎",
}
DEUDA_ICONS = {
    "Tarjeta de crédito":"💳","Préstamo personal":"🤝","Hipoteca":"🏠",
    "Auto":"🚗","Estudiantil":"🎓","Otro":"📋",
}
CHART_COLORS = ["#b78a00","#4A7C59","#2D6A8F","#8B5E3C","#7B6EA0",
                "#C0392B","#D4956A","#5B8A6E","#A07040","#6B7DA8"]

# Colores fijos por categoría — garantiza consistencia entre gráficas
_CATS_ORDERED = [
    "Alimentación","Restaurantes","Transporte","Vivienda","Salud","Educación",
    "Entretenimiento","Ropa","Servicios","Deudas","Otro gasto",
    "Salario","Préstamo","Otro ingreso",
]
CAT_COLOR_MAP = {cat: CHART_COLORS[i % len(CHART_COLORS)] for i, cat in enumerate(_CATS_ORDERED)}

def cat_colors(categories):
    """Devuelve una lista de colores estables para una lista de categorías."""
    return [CAT_COLOR_MAP.get(c, CHART_COLORS[hash(c) % len(CHART_COLORS)]) for c in categories]

# ─── Supabase Client ──────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except (KeyError, FileNotFoundError):
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        st.warning("⚙️ Configura SUPABASE_URL y SUPABASE_KEY en los secrets de Streamlit o en el archivo .env para continuar.")
        st.stop()
    return create_client(url, key)

def sb():
    return get_supabase()

def _df(resp):
    """Convierte respuesta de Supabase a DataFrame vacío o con datos."""
    return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()

# ─── Database Init ────────────────────────────────────────────────────────────
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS usuarios (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cuentas (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL, tipo TEXT NOT NULL,
    moneda TEXT NOT NULL DEFAULT 'COP',
    saldo_inicial DOUBLE PRECISION NOT NULL DEFAULT 0,
    user_id BIGINT NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS transacciones (
    id BIGSERIAL PRIMARY KEY,
    fecha TEXT NOT NULL, tipo TEXT NOT NULL, categoria TEXT NOT NULL,
    descripcion TEXT, monto DOUBLE PRECISION NOT NULL,
    cuenta TEXT DEFAULT 'Efectivo',
    moneda TEXT DEFAULT 'COP',
    cuenta_id BIGINT,
    user_id BIGINT NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS portafolio (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL, tipo TEXT NOT NULL,
    cantidad DOUBLE PRECISION NOT NULL, valor_unitario DOUBLE PRECISION NOT NULL,
    fecha TEXT NOT NULL,
    tasa_interes DOUBLE PRECISION,
    plazo INTEGER,
    fecha_vencimiento TEXT,
    modalidad_interes TEXT DEFAULT 'Compuesto',
    user_id BIGINT NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS deudas (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL, tipo TEXT NOT NULL,
    deuda_inicial DOUBLE PRECISION NOT NULL, saldo DOUBLE PRECISION NOT NULL,
    tasa_interes DOUBLE PRECISION NOT NULL DEFAULT 0,
    pago_minimo DOUBLE PRECISION NOT NULL DEFAULT 0,
    fecha_inicio TEXT NOT NULL,
    cupo_maximo DOUBLE PRECISION,
    num_cuotas INTEGER,
    user_id BIGINT NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS pagos_deuda (
    id BIGSERIAL PRIMARY KEY,
    deuda_id BIGINT NOT NULL, fecha TEXT NOT NULL,
    monto DOUBLE PRECISION NOT NULL, nota TEXT
);
CREATE TABLE IF NOT EXISTS metas (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL, objetivo DOUBLE PRECISION NOT NULL,
    actual DOUBLE PRECISION NOT NULL DEFAULT 0,
    fecha_limite TEXT, emoji TEXT NOT NULL DEFAULT '🎯',
    user_id BIGINT NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS gastos_fijos (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    categoria TEXT NOT NULL,
    monto DOUBLE PRECISION NOT NULL,
    dia_vencimiento INTEGER NOT NULL DEFAULT 1,
    cuenta TEXT NOT NULL DEFAULT 'Efectivo',
    user_id BIGINT NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS pagos_gastos_fijos (
    id BIGSERIAL PRIMARY KEY,
    gasto_fijo_id BIGINT NOT NULL,
    mes INTEGER NOT NULL,
    anio INTEGER NOT NULL,
    pagado BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_pago TEXT
);
"""

_MIGRATION_SQL = """-- Migraciones para versión actual (ejecuta una sola vez en el SQL Editor de Supabase):
ALTER TABLE transacciones ADD COLUMN IF NOT EXISTS moneda TEXT DEFAULT 'COP';
ALTER TABLE transacciones ADD COLUMN IF NOT EXISTS cuenta_id BIGINT;
ALTER TABLE deudas ADD COLUMN IF NOT EXISTS cupo_maximo DOUBLE PRECISION;
ALTER TABLE deudas ADD COLUMN IF NOT EXISTS num_cuotas INTEGER;
ALTER TABLE portafolio ADD COLUMN IF NOT EXISTS tasa_interes DOUBLE PRECISION;
ALTER TABLE portafolio ADD COLUMN IF NOT EXISTS plazo INTEGER;
ALTER TABLE portafolio ADD COLUMN IF NOT EXISTS fecha_vencimiento TEXT;
ALTER TABLE portafolio ADD COLUMN IF NOT EXISTS modalidad_interes TEXT DEFAULT 'Compuesto';
CREATE TABLE IF NOT EXISTS cuentas (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL, tipo TEXT NOT NULL,
    moneda TEXT NOT NULL DEFAULT 'COP',
    saldo_inicial DOUBLE PRECISION NOT NULL DEFAULT 0,
    user_id BIGINT NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS gastos_fijos (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    categoria TEXT NOT NULL,
    monto DOUBLE PRECISION NOT NULL,
    dia_vencimiento INTEGER NOT NULL DEFAULT 1,
    cuenta TEXT NOT NULL DEFAULT 'Efectivo',
    user_id BIGINT NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS pagos_gastos_fijos (
    id BIGSERIAL PRIMARY KEY,
    gasto_fijo_id BIGINT NOT NULL,
    mes INTEGER NOT NULL,
    anio INTEGER NOT NULL,
    pagado BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_pago TEXT
);"""

def _has_column(table, column):
    """Detecta si una columna existe leyendo una fila y viendo las claves."""
    try:
        r = sb().table(table).select(column).limit(1).execute()
        return True
    except Exception:
        return False

def init_db():
    """Verifica la conexión con Supabase y que las tablas existan."""
    try:
        sb().table("usuarios").select("id").limit(1).execute()
    except Exception as e:
        err = str(e)
        if "PGRST205" in err or "schema cache" in err:
            st.warning("⚠️ Las tablas de Supabase no existen todavía.")
            st.markdown("**Paso único de configuración:** Abre el SQL Editor de Supabase, pega y ejecuta el SQL de abajo, luego recarga la página.")
            st.code(_SCHEMA_SQL, language="sql")
        else:
            st.warning("Hubo un problema al conectar con la base de datos. Intenta de nuevo en un momento.")
        st.stop()

    # Mostrar aviso de migración si faltan columnas nuevas
    if (not _has_column("transacciones", "moneda") or
            not _has_column("deudas", "cupo_maximo") or
            not _has_column("portafolio", "tasa_interes")):
        with st.sidebar:
            st.warning("🔧 **Actualización pendiente**")
            st.markdown("Ejecuta este SQL en el [Editor de Supabase](https://supabase.com/dashboard/project/vyhlfosmnbetiohtcxbp/sql/new):")
            st.code(_MIGRATION_SQL, language="sql")

# ─── Auth ─────────────────────────────────────────────────────────────────────
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(nombre, email, password):
    try:
        sb().table("usuarios").insert({
            "nombre": nombre.strip(),
            "email": email.strip().lower(),
            "password_hash": hash_password(password)
        }).execute()
        return True, None
    except Exception as e:
        err = str(e).lower()
        if "duplicate" in err or "unique" in err or "23505" in err:
            return False, "Este email ya está registrado."
        return False, f"Error al crear cuenta: {e}"

def authenticate_user(email, password):
    resp = sb().table("usuarios").select("id, nombre").eq("email", email.strip().lower()).eq("password_hash", hash_password(password)).execute()
    if not resp.data:
        return None, None
    row = resp.data[0]
    return int(row["id"]), row["nombre"]

def email_exists(email):
    resp = sb().table("usuarios").select("id").eq("email", email.strip().lower()).execute()
    return bool(resp.data)

def reset_password(email, new_password):
    sb().table("usuarios").update({"password_hash": hash_password(new_password)}).eq("email", email.strip().lower()).execute()


def uid():
    return st.session_state.get("user_id", 1)

# ─── Helpers ──────────────────────────────────────────────────────────────────
def cop(n):
    n = int(round(float(n or 0)))
    return "$ " + f"{abs(n):,}".replace(",", ".")

def calcular_cuota(saldo, tasa_anual, num_cuotas):
    """Calcula el pago mensual fijo por cuotas (amortización francesa)."""
    if num_cuotas <= 0 or saldo <= 0:
        return 0.0
    tasa_m = tasa_anual / 12 / 100
    if tasa_m > 0:
        return saldo * tasa_m / (1 - (1 + tasa_m) ** (-num_cuotas))
    return saldo / num_cuotas

def calcular_rendimiento_rf(capital, tasa_anual, dias, modalidad="Compuesto"):
    """Retorna los intereses acumulados para un activo de renta fija."""
    if dias <= 0 or tasa_anual <= 0 or capital <= 0:
        return 0.0
    if modalidad == "Compuesto":
        return capital * ((1 + tasa_anual / 100) ** (dias / 365) - 1)
    return capital * (tasa_anual / 100) * (dias / 365)

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

/* Buttons — default = dorado (inactivo / acciones) */
.stButton > button { background:#b78a00 !important; color:#FFFFFF !important; border:none !important; border-radius:14px !important; font-weight:700 !important; font-size:14px !important; padding:13px 20px !important; width:100% !important; box-shadow:0 4px 14px rgba(183,138,0,0.25) !important; transition:all 0.15s ease !important; }
.stButton > button:hover { background:#9a7400 !important; box-shadow:0 6px 20px rgba(183,138,0,0.35) !important; transform:translateY(-1px) !important; }
.stButton > button *, .stButton > button p, .stButton > button span, .stButton > button div { color:#FFFFFF !important; }
/* type="primary" = botón activo en login (#322b49) — mayor especificidad gana */
.stButton > button[data-testid="baseButton-primary"],
.stButton > button[kind="primary"] { background:#322b49 !important; box-shadow:0 2px 10px rgba(50,43,73,0.3) !important; }
.stButton > button[data-testid="baseButton-primary"]:hover,
.stButton > button[kind="primary"]:hover { background:#221e32 !important; }
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

def consilia_response_card(text):
    html_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html_text = html_text.replace("\n\n", '</p><p style="color:#F5F0E8;font-size:15px;line-height:1.75;margin:0.6rem 0 0;">').replace("\n", "<br>")
    return f"""
    <div style="background:linear-gradient(135deg,#322b49 0%,#3e3260 100%);
                border-radius:20px;padding:1.5rem 1.6rem;margin-bottom:12px;
                border:1px solid rgba(183,138,0,0.35);
                box-shadow:0 4px 20px rgba(50,43,73,0.22);">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:1rem;">
        <span style="color:#eab000;font-size:16px;">✦</span>
        <span style="color:#eab000;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;">Consil.ia</span>
      </div>
      <p style="color:#F5F0E8;font-size:15px;line-height:1.75;margin:0;">{html_text}</p>
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

def renta_fija_card(nombre, tipo, capital, tasa_anual, fecha_inicio_str, fecha_venc_str, modalidad):
    today = date.today()
    icon  = CAT_ICONS.get(tipo, "📜")
    tasa_s = f"{tasa_anual:.2f}% E.A." if modalidad == "Compuesto" else f"{tasa_anual:.2f}% anual simple"
    try:
        f_inicio = date.fromisoformat(str(fecha_inicio_str))
    except (ValueError, TypeError):
        f_inicio = today
    f_venc = None
    try:
        if fecha_venc_str:
            f_venc = date.fromisoformat(str(fecha_venc_str))
    except (ValueError, TypeError):
        pass

    dias_trans = max((today - f_inicio).days, 0)
    intereses  = calcular_rendimiento_rf(capital, tasa_anual, dias_trans, modalidad)
    valor_hoy  = capital + intereses

    if f_venc:
        dias_total = max((f_venc - f_inicio).days, 1)
        valor_venc = capital + calcular_rendimiento_rf(capital, tasa_anual, dias_total, modalidad)
        dias_rest  = (f_venc - today).days
        vencido    = dias_rest < 0
        pct_time   = min(dias_trans / dias_total, 1.0)
        bar_color  = "#C0392B" if vencido else "#b78a00"
        tiempo_s   = (f"Vencido hace {abs(dias_rest)} día(s)" if vencido
                      else f"{dias_rest} día(s) restantes · vence {f_venc.strftime('%d/%m/%Y')}")
    else:
        dias_total = 365
        valor_venc = capital + calcular_rendimiento_rf(capital, tasa_anual, 365, modalidad)
        vencido    = False
        pct_time   = min(dias_trans / 365, 1.0)
        bar_color  = "#4A7C59"
        tiempo_s   = f"{dias_trans} día(s) invertido(s) · Sin fecha de vencimiento"

    bar_w = int(pct_time * 100)
    vencido_html = ""
    if vencido and f_venc:
        vencido_html = (
            f'<div style="background:rgba(183,138,0,0.12);border:1.5px solid rgba(183,138,0,0.5);'
            f'border-radius:10px;padding:8px 12px;margin-bottom:12px;">'
            f'<p style="color:#b78a00;font-size:12px;font-weight:700;margin:0;">'
            f'⏰ Este {tipo} venció el {f_venc.strftime("%d/%m/%Y")}. ¿Ya lo renovaste?'
            f'</p></div>'
        )
    intereses_label = f"+{cop(intereses)}" if intereses >= 0 else cop(intereses)
    return f"""
    <div style="background:#FFFFFF;border-radius:20px;padding:1.3rem 1.5rem;
                border:1px solid rgba(74,124,89,0.15);margin-bottom:4px;
                box-shadow:0 2px 16px rgba(0,0,0,0.05);">
      {vencido_html}
      <div style="display:flex;align-items:center;margin-bottom:12px;">
        <span style="font-size:20px;background:#F5F0E8;width:44px;height:44px;border-radius:14px;
                     display:inline-flex;align-items:center;justify-content:center;margin-right:12px;flex-shrink:0;">{icon}</span>
        <div style="flex:1;">
          <p style="color:#1c1829;font-size:15px;font-weight:600;margin:0;">{nombre}</p>
          <p style="color:#6b6285;font-size:12px;margin:2px 0 0;">{tipo} · {tasa_s} · {modalidad}</p>
        </div>
        <div style="text-align:right;">
          <p style="color:#4A7C59;font-size:18px;font-weight:700;margin:0;">{cop(valor_hoy)}</p>
          <p style="color:#6b6285;font-size:11px;margin:2px 0 0;">valor actual</p>
        </div>
      </div>
      <div style="background:#F5F0E8;border-radius:6px;height:6px;overflow:hidden;margin-bottom:5px;">
        <div style="width:{bar_w}%;height:100%;border-radius:6px;background:{bar_color};transition:width 0.4s;"></div>
      </div>
      <p style="color:#6b6285;font-size:11px;margin:0 0 14px;">{tiempo_s}</p>
      <div style="display:flex;justify-content:space-between;">
        <div>
          <p style="color:#5c5474;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;margin:0;">Capital</p>
          <p style="color:#1c1829;font-size:13px;font-weight:600;margin:3px 0 0;">{cop(capital)}</p>
        </div>
        <div style="text-align:center;">
          <p style="color:#5c5474;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;margin:0;">Intereses hoy</p>
          <p style="color:#4A7C59;font-size:13px;font-weight:600;margin:3px 0 0;">{intereses_label}</p>
        </div>
        <div style="text-align:right;">
          <p style="color:#5c5474;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;margin:0;">Al vencimiento</p>
          <p style="color:#b78a00;font-size:13px;font-weight:600;margin:3px 0 0;">{cop(valor_venc)}</p>
        </div>
      </div>
    </div>"""

def debt_card(nombre, tipo, deuda_inicial, saldo, tasa, pago_minimo, fecha_fin=None, total_int=None, cupo_maximo=None, meses_restantes=None):
    pagado = max(deuda_inicial - saldo, 0)
    pct    = pagado / deuda_inicial if deuda_inicial > 0 else 0
    bar_w  = int(pct * 100)
    pct_r  = saldo / deuda_inicial if deuda_inicial > 0 else 0
    color  = "#4A7C59" if pct_r < 0.25 else "#b78a00" if pct_r < 0.6 else "#C0392B"
    icon   = DEUDA_ICONS.get(tipo, "📋")
    tasa_s = f"{tasa:.1f}% anual" if tasa > 0 else "Sin interés"

    # Cupo disponible (solo tarjeta de crédito)
    cupo_html = ""
    if tipo == "Tarjeta de crédito" and cupo_maximo and cupo_maximo > 0:
        cupo_disp = max(cupo_maximo - saldo, 0)
        cupo_usado_pct = min(int(saldo / cupo_maximo * 100), 100)
        cupo_color = "#4A7C59" if cupo_usado_pct < 50 else "#b78a00" if cupo_usado_pct < 80 else "#C0392B"
        cupo_html = (
            f'<div style="background:#F5F0E8;border-radius:12px;padding:10px 12px;margin-top:10px;">'
            f'<div style="display:flex;justify-content:space-between;margin-bottom:6px;">'
            f'<p style="color:#5c5474;font-size:10px;text-transform:uppercase;letter-spacing:0.7px;font-weight:600;margin:0;">💳 Cupo disponible</p>'
            f'<p style="color:{cupo_color};font-size:12px;font-weight:700;margin:0;">{cop(cupo_disp)}</p>'
            f'</div>'
            f'<div style="background:#DDD8CC;border-radius:6px;height:6px;overflow:hidden;">'
            f'<div style="width:{cupo_usado_pct}%;height:100%;border-radius:6px;background:{cupo_color};"></div>'
            f'</div>'
            f'<p style="color:#6b6285;font-size:10px;margin:4px 0 0;">{cupo_usado_pct}% del cupo usado · Total: {cop(cupo_maximo)}</p>'
            f'</div>'
        )

    # Proyección
    if fecha_fin and total_int is not None:
        cuotas_s = f" · {meses_restantes} cuota(s)" if meses_restantes else ""
        proj_html = (
            f'<div style="background:#F5F0E8;border-radius:12px;padding:10px 12px;margin-top:12px;border:1px solid rgba(192,57,43,0.1);">'
            f'<p style="color:#5c5474;font-size:10px;text-transform:uppercase;letter-spacing:0.7px;font-weight:600;margin:0 0 6px;">📅 Proyección de pago</p>'
            f'<div style="display:flex;justify-content:space-between;">'
            f'<div><p style="color:#5c5474;font-size:11px;margin:0;">Fecha estimada{cuotas_s}</p>'
            f'<p style="color:#1c1829;font-size:13px;font-weight:600;margin:2px 0 0;">{fecha_fin.strftime("%b %Y")}</p></div>'
            f'<div style="text-align:right;"><p style="color:#5c5474;font-size:11px;margin:0;">Total en intereses</p>'
            f'<p style="color:#C0392B;font-size:13px;font-weight:600;margin:2px 0 0;">{cop(total_int)}</p></div>'
            f'</div></div>'
        )
    elif pago_minimo <= 0:
        proj_html = '<p style="color:#5c5474;font-size:11px;margin:10px 0 0;">Sin pago mensual registrado para proyectar.</p>'
    else:
        proj_html = '<p style="color:#C0392B;font-size:11px;margin:10px 0 0;">⚠️ El pago mensual no alcanza a cubrir los intereses.</p>'

    pago_label = "Cuota mensual" if tipo == "Tarjeta de crédito" else "Pago mínimo"
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
          <p style="color:#5c5474;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;margin:0;">{pago_label}</p>
          <p style="color:#1c1829;font-size:13px;font-weight:600;margin:3px 0 0;">{cop(pago_minimo)}/mes</p>
        </div>
        <div style="text-align:right;">
          <p style="color:#5c5474;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;margin:0;">Deuda original</p>
          <p style="color:#1c1829;font-size:13px;font-weight:600;margin:3px 0 0;">{cop(deuda_inicial)}</p>
        </div>
      </div>
      {cupo_html}
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

    mode = st.session_state.auth_mode

    # ── Flujo de recuperación de contraseña ──────────────────────────────────
    if mode == "reset_email":
        st.markdown(f'<p style="color:#322b49;font-size:16px;font-weight:600;margin:0 0 4px;">Recuperar contraseña</p>'
                    f'<p style="color:#6b6285;font-size:13px;margin:0 0 20px;">Ingresa tu email y crea una nueva contraseña.</p>',
                    unsafe_allow_html=True)
        with st.form("form_reset", clear_on_submit=False):
            email    = st.text_input("Email registrado", placeholder="tu@email.com")
            new_pass = st.text_input("Nueva contraseña", type="password", placeholder="Mínimo 6 caracteres")
            confirm  = st.text_input("Confirmar contraseña", type="password", placeholder="Repite la contraseña")
            ok = st.form_submit_button("Guardar nueva contraseña", use_container_width=True)
            if ok:
                if not email or not new_pass or not confirm:
                    st.warning("Por favor completa todos los campos.")
                elif not email_exists(email):
                    st.warning("No encontramos una cuenta con ese email. Verifica que esté bien escrito.")
                elif len(new_pass) < 6:
                    st.warning("La contraseña debe tener al menos 6 caracteres.")
                elif new_pass != confirm:
                    st.warning("Las contraseñas no coinciden. Intenta de nuevo.")
                else:
                    reset_password(email, new_pass)
                    st.success("Contraseña actualizada. Ya puedes iniciar sesión.")
                    st.session_state.auth_mode = "login"
                    st.rerun()
        if st.button("← Volver al login", key="back_to_login"):
            st.session_state.auth_mode = "login"
            st.rerun()
        return

    # ── Tabs login / registro — Python puro, type="primary" marca el activo ──
    col_a, col_b = st.columns(2)
    with col_a:
        kw = {"type": "primary"} if mode == "login" else {}
        if st.button("Iniciar sesión", key="tab_login", use_container_width=True, **kw):
            st.session_state.auth_mode = "login"
            st.rerun()
    with col_b:
        kw = {"type": "primary"} if mode == "register" else {}
        if st.button("Crear cuenta", key="tab_register", use_container_width=True, **kw):
            st.session_state.auth_mode = "register"
            st.rerun()

    if mode == "login":
        with st.form("form_login", clear_on_submit=False):
            email    = st.text_input("Email", placeholder="tu@email.com")
            password = st.text_input("Contraseña", type="password", placeholder="••••••")
            ok = st.form_submit_button("Iniciar sesión", use_container_width=True)
            if ok:
                if not email or not password:
                    st.warning("Por favor completa todos los campos.")
                else:
                    user_id, nombre = authenticate_user(email, password)
                    if user_id:
                        st.session_state.user_id    = user_id
                        st.session_state.user_name  = nombre
                        st.session_state.user_email = email.strip().lower()
                        st.rerun()
                    else:
                        if email_exists(email):
                            st.warning("Contraseña incorrecta. Intenta de nuevo o recupera tu contraseña.")
                        else:
                            st.warning("No encontramos una cuenta con ese email. ¿Ya te registraste?")
        _, col_mid, _ = st.columns([1, 2, 1])
        with col_mid:
            if st.button("¿Olvidaste tu contraseña?", key="go_reset", use_container_width=True):
                st.session_state.auth_mode = "reset_email"
                st.rerun()

    else:  # register
        with st.form("form_register", clear_on_submit=False):
            nombre   = st.text_input("Tu nombre", placeholder="Diego")
            email    = st.text_input("Email", placeholder="tu@email.com")
            password = st.text_input("Contraseña", type="password", placeholder="Mínimo 6 caracteres")
            ok = st.form_submit_button("Crear cuenta", use_container_width=True)
            if ok:
                if not nombre or not email or not password:
                    st.warning("Por favor completa todos los campos.")
                elif len(password) < 6:
                    st.warning("La contraseña debe tener al menos 6 caracteres.")
                else:
                    success, err = create_user(nombre, email, password)
                    if success:
                        user_id, uname = authenticate_user(email, password)
                        if user_id:
                            st.session_state.user_id    = user_id
                            st.session_state.user_name  = uname
                            st.session_state.user_email = email.strip().lower()
                            st.rerun()
                        else:
                            st.success("¡Cuenta creada! Por favor inicia sesión.")
                            st.session_state.auth_mode = "login"
                            st.rerun()
                    else:
                        st.warning(err)

# ─── Consil.ia ────────────────────────────────────────────────────────────────
def _get_anthropic_key():
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        key = ""
    return key or os.environ.get("ANTHROPIC_API_KEY", "")

def consilia_section(df, ingresos_total, gastos_total, balance_total):
    st.markdown(section_title("✦ Consil.ia — Tu asesora financiera"), unsafe_allow_html=True)

    # ── Construir contexto del usuario ──────────────────────────────────────
    mes_actual = date.today().strftime("%Y-%m")
    nombre_mes = date.today().strftime("%B %Y")
    df_mes_gastos  = df[(df["tipo"] == "Gasto") & (df["fecha"].str.startswith(mes_actual))]
    df_mes_ingresos = df[(df["tipo"] == "Ingreso") & (df["fecha"].str.startswith(mes_actual))]
    ingresos_mes = df_mes_ingresos["monto"].sum()
    gastos_mes   = df_mes_gastos["monto"].sum()
    top_cats = df_mes_gastos.groupby("categoria")["monto"].sum().sort_values(ascending=False).head(5)

    deudas_resp = sb().table("deudas").select("nombre, tipo, saldo, tasa_interes, pago_minimo").eq("user_id", uid()).execute()
    metas_resp  = sb().table("metas").select("nombre, objetivo, actual, fecha_limite").eq("user_id", uid()).execute()
    deudas = deudas_resp.data or []
    metas  = metas_resp.data or []

    ctx = [
        f"Fecha actual: {date.today().strftime('%d/%m/%Y')}",
        f"Balance histórico acumulado: {cop(balance_total)}",
        f"Ingresos históricos totales: {cop(ingresos_total)}",
        f"Gastos históricos totales: {cop(gastos_total)}",
        f"\nEste mes ({nombre_mes}):",
        f"  Ingresos: {cop(ingresos_mes)}",
        f"  Gastos: {cop(gastos_mes)}",
        f"  Balance del mes: {cop(ingresos_mes - gastos_mes)}",
    ]
    if not top_cats.empty:
        ctx.append(f"\nTop categorías de gasto este mes:")
        for cat, monto in top_cats.items():
            pct = (monto / gastos_mes * 100) if gastos_mes > 0 else 0
            ctx.append(f"  - {cat}: {cop(monto)} ({pct:.0f}% del gasto mensual)")
    if deudas:
        ctx.append(f"\nDeudas activas ({len(deudas)}):")
        for d in deudas:
            ctx.append(f"  - {d['nombre']} ({d['tipo']}): saldo {cop(d['saldo'])}, tasa {d.get('tasa_interes') or 0}% anual, pago mínimo {cop(d.get('pago_minimo') or 0)}")
    else:
        ctx.append("\nDeudas activas: ninguna")
    if metas:
        ctx.append(f"\nMetas de ahorro ({len(metas)}):")
        for m in metas:
            prog = float(m["actual"] or 0) / float(m["objetivo"]) * 100 if m.get("objetivo") else 0
            limite = f", fecha límite: {m['fecha_limite']}" if m.get("fecha_limite") else ""
            ctx.append(f"  - {m['nombre']}: {cop(m['actual'])} de {cop(m['objetivo'])} ({prog:.0f}%){limite}")
    else:
        ctx.append("\nMetas de ahorro: ninguna")

    contexto_financiero = "\n".join(ctx)

    SYSTEM_PROMPT = """Eres Consil.ia, asesora financiera personal para jóvenes profesionales colombianos.
Tu misión es analizar los datos reales del usuario y darle recomendaciones concretas, claras y motivadoras.
Reglas:
- Responde siempre en español colombiano, tono cercano y profesional.
- Usa los números exactos que te dan (en pesos colombianos).
- Máximo 4 puntos o párrafos. Sé concisa y práctica.
- Cada recomendación debe ser accionable esta semana.
- Usa emojis con moderación para hacer el texto más visual.
- Nunca inventes datos que no estén en el contexto."""

    # ── UI ───────────────────────────────────────────────────────────────────
    pregunta = st.text_input(
        "O hazle una pregunta específica",
        placeholder="¿En qué estoy gastando más? ¿Cuándo puedo pagar mi deuda? ¿Cómo ahorro más rápido?",
        key="consilia_question",
        label_visibility="collapsed",
    )
    c1, c2 = st.columns(2)
    with c1:
        btn_analizar  = st.button("✦ Analizar mis finanzas", use_container_width=True, key="btn_consilia_analizar")
    with c2:
        btn_preguntar = st.button("Enviar pregunta →", use_container_width=True, key="btn_consilia_preguntar",
                                   disabled=not pregunta.strip())

    if not (btn_analizar or btn_preguntar):
        return

    api_key = _get_anthropic_key()
    if not api_key:
        st.warning("🔑 Falta la clave de Consil.ia. Agrégala en Streamlit Cloud → Settings → Secrets como ANTHROPIC_API_KEY.")
        return

    if btn_analizar:
        user_msg = (
            f"Analiza mis finanzas y dame tus recomendaciones más importantes.\n\n"
            f"Mis datos financieros:\n{contexto_financiero}"
        )
    else:
        user_msg = (
            f"Datos financieros del usuario:\n{contexto_financiero}\n\n"
            f"Pregunta: {pregunta.strip()}"
        )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        with st.spinner("Consil.ia está analizando..."):
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
        respuesta = response.content[0].text
        st.markdown(consilia_response_card(respuesta), unsafe_allow_html=True)
    except anthropic.AuthenticationError:
        st.warning("La API key de Anthropic no es válida. Verifica tu configuración en Secrets.")
    except anthropic.RateLimitError:
        st.warning("Consil.ia está muy ocupada ahora mismo. Intenta de nuevo en unos minutos ⏳")
    except Exception:
        st.warning("Hubo un problema al conectar con Consil.ia. Intenta de nuevo en un momento.")


# ─── Pages ────────────────────────────────────────────────────────────────────
def page_dashboard():
    resp = sb().table("transacciones").select("*").eq("user_id", uid()).order("fecha", desc=True).order("id", desc=True).execute()
    df = _df(resp)

    if df.empty:
        st.markdown(balance_card_html(0, 0, 0), unsafe_allow_html=True)
        st.markdown(card_wrap(
            '<p style="color:#6b6285;text-align:center;font-size:14px;padding:1rem 0;margin:0;">¡Agrega tu primera transacción en la pestaña Transacciones!</p>'
        ), unsafe_allow_html=True)
        return

    # Conversión a COP si hay múltiples monedas
    def monto_cop(row):
        m = row.get("moneda") or "COP"
        return float(row["monto"]) * TASA_A_COP.get(m, 1)

    df["monto_cop"] = df.apply(monto_cop, axis=1)
    multi_moneda = "moneda" in df.columns and df["moneda"].notna().any() and df["moneda"].nunique() > 1

    ingresos = df[df["tipo"] == "Ingreso"]["monto_cop"].sum()
    gastos   = df[df["tipo"] == "Gasto"]["monto_cop"].sum()
    balance  = ingresos - gastos

    st.markdown(balance_card_html(balance, ingresos, gastos), unsafe_allow_html=True)
    if multi_moneda:
        st.markdown('<p style="color:#b78a00;font-size:11px;text-align:center;margin:-8px 0 8px;">Totales convertidos a COP (tasas aproximadas)</p>', unsafe_allow_html=True)

    mes_actual = date.today().strftime("%Y-%m")
    df_mes = df[(df["tipo"] == "Gasto") & (df["fecha"].str.startswith(mes_actual))]
    if not df_mes.empty:
        st.markdown(section_title(f"Gastos de {date.today().strftime('%B %Y')}"), unsafe_allow_html=True)
        df_cat_mes = df_mes.groupby("categoria")["monto_cop"].sum().sort_values(ascending=True).reset_index()
        fig_bar = go.Figure(go.Bar(
            x=df_cat_mes["monto_cop"],
            y=df_cat_mes["categoria"],
            orientation="h",
            marker=dict(color=cat_colors(df_cat_mes["categoria"]), line=dict(width=0)),
            text=[cop(v) for v in df_cat_mes["monto_cop"]],
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


def _load_tarjetas_credito():
    """Devuelve lista de dicts de deudas tipo Tarjeta de crédito del usuario."""
    try:
        r = sb().table("deudas").select("id, nombre, saldo, cupo_maximo").eq("user_id", uid()).eq("tipo", "Tarjeta de crédito").order("nombre").execute()
        return r.data or []
    except Exception:
        return []

def _load_activos():
    r = sb().table("portafolio").select("id, nombre, cantidad").eq("user_id", uid()).order("nombre").execute()
    return {a["nombre"]: a for a in r.data} if r.data else {}

def _load_cuentas_usuario():
    """Devuelve dict {label: {id, nombre, tipo, moneda}} o {} si no hay cuentas definidas."""
    try:
        r = sb().table("cuentas").select("*").eq("user_id", uid()).order("nombre").execute()
        if r.data:
            return {f"{c['nombre']} ({c['tipo']})": c for c in r.data}
    except Exception:
        pass
    return {}

def page_transacciones():
    hoy = date.today()
    # ── Sección "Mis Cuentas" ──────────────────────────────────────────────
    st.markdown(section_title("Mis cuentas"), unsafe_allow_html=True)
    cuentas_usuario = _load_cuentas_usuario()

    if cuentas_usuario:
        # Calcular balance por cuenta
        tx_resp = sb().table("transacciones").select("tipo, monto, cuenta_id, moneda").eq("user_id", uid()).execute()
        tx_all  = tx_resp.data or []
        rows_html = ""
        for label, c in cuentas_usuario.items():
            cid = int(c["id"])
            movs = [t for t in tx_all if t.get("cuenta_id") == cid]
            tasa = TASA_A_COP.get(c.get("moneda", "COP"), 1)
            ing  = sum(float(t["monto"]) for t in movs if t["tipo"] == "Ingreso")
            gas  = sum(float(t["monto"]) for t in movs if t["tipo"] == "Gasto")
            saldo = float(c.get("saldo_inicial", 0)) + ing - gas
            mon   = c.get("moneda", "COP")
            sim   = MONEDA_SIMBOLO.get(mon, "$")
            color = "#4A7C59" if saldo >= 0 else "#C0392B"
            tipo_ico = {"Cuenta bancaria":"🏦","Billetera digital":"📱","Efectivo":"💵","Inversiones":"📊","Otro":"🏷️"}.get(c["tipo"], "🏷️")
            rows_html += f"""
            <div style="display:flex;align-items:center;padding:10px 0;border-bottom:1px solid rgba(0,0,0,0.04);">
              <span style="font-size:20px;margin-right:12px;">{tipo_ico}</span>
              <div style="flex:1;">
                <p style="color:#1c1829;font-size:13px;font-weight:500;margin:0;">{c['nombre']}</p>
                <p style="color:#6b6285;font-size:11px;margin:2px 0 0;">{c['tipo']} · {mon}</p>
              </div>
              <p style="color:{color};font-size:14px;font-weight:600;margin:0;">{sim} {abs(saldo):,.0f}</p>
            </div>"""
        st.markdown(card_wrap(rows_html, "0.6rem 1.2rem"), unsafe_allow_html=True)
    else:
        st.markdown(card_wrap('<p style="color:#6b6285;font-size:13px;text-align:center;padding:0.5rem 0;margin:0;">Aún no tienes cuentas. Agrégalas abajo 👇</p>'), unsafe_allow_html=True)

    with st.expander("➕ Agregar cuenta"):
        with st.form("form_cuenta", clear_on_submit=True):
            nc1, nc2 = st.columns(2)
            with nc1:
                c_nombre = st.text_input("Nombre", placeholder="Bancolombia, Nequi…")
                c_tipo   = st.selectbox("Tipo", TIPOS_CUENTA)
            with nc2:
                c_moneda  = st.selectbox("Moneda", MONEDAS)
                c_saldo_i = st.number_input("Saldo inicial ($)", min_value=0.0, value=None,
                                             placeholder="0", step=10000.0, format="%.0f")
            if st.form_submit_button("Guardar cuenta", use_container_width=True):
                if not c_nombre:
                    st.warning("Escribe un nombre para la cuenta.")
                else:
                    try:
                        sb().table("cuentas").insert({
                            "nombre": c_nombre, "tipo": c_tipo,
                            "moneda": c_moneda, "saldo_inicial": c_saldo_i or 0.0,
                            "user_id": uid()
                        }).execute()
                        st.rerun()
                    except Exception:
                        st.warning("Hubo un problema al guardar la cuenta. Intenta de nuevo.")

    # ── Formulario de nueva transacción ───────────────────────────────────
    st.markdown(section_title("Nueva transacción"), unsafe_allow_html=True)
    tipo      = st.selectbox("Tipo", ["Gasto", "Ingreso"], key="new_tipo")
    cats      = CATEGORIAS_GASTO if tipo == "Gasto" else CATEGORIAS_INGRESO
    categoria = st.selectbox("Categoría", cats, key="new_cat")
    moneda    = st.selectbox("Moneda", MONEDAS, key="new_moneda")

    # ── Selector de gasto fijo: Obligaciones ──────────────────────────────────
    gastos_fijos_dict = {}
    needs_obligacion  = (tipo == "Gasto" and categoria == "Obligaciones")
    if needs_obligacion:
        gf_list = _load_gastos_fijos()
        if gf_list:
            gastos_fijos_dict = {g["nombre"]: g for g in gf_list}
            st.selectbox("Gasto fijo", list(gastos_fijos_dict.keys()), key="new_gasto_fijo",
                         help="Al guardar se marcará como pagado en el checklist del mes")
        else:
            st.info("Primero agrega gastos fijos en la pestaña Obligaciones 📋")

    # ── Selector de activo: Portafolio (gasto) o Retiro de portafolio (ingreso)
    activos_dict    = {}
    needs_activo    = (tipo == "Gasto" and categoria == "Portafolio") or \
                      (tipo == "Ingreso" and categoria == "Retiro de portafolio")
    if needs_activo:
        activos_dict = _load_activos()
        if activos_dict:
            st.selectbox("Activo del portafolio", list(activos_dict.keys()), key="new_activo")
        else:
            st.info("Primero agrega activos en tu portafolio para poder asignarles transacciones 📈")

    # ── Selector de tarjeta de crédito cuando la cuenta origen es TC ──────
    tarjetas_list   = []
    cuenta_prev_val = st.session_state.get("form_cuenta_sel", "")
    cuentas_u_prev  = _load_cuentas_usuario()
    es_cuenta_tc    = (
        cuenta_prev_val == "Tarjeta de crédito" or
        (cuenta_prev_val in cuentas_u_prev and
         cuentas_u_prev[cuenta_prev_val].get("tipo") == "Tarjeta de crédito")
    )
    needs_tarjeta = (tipo == "Gasto") and es_cuenta_tc
    if needs_tarjeta:
        tarjetas_list = _load_tarjetas_credito()
        if tarjetas_list:
            tc_opts = [t["nombre"] for t in tarjetas_list]
            st.selectbox("Tarjeta de crédito", tc_opts, key="new_tarjeta_tc",
                         help="Se sumará el gasto al saldo de esta tarjeta en Deudas")
        else:
            st.info("Registra tus tarjetas en la pestaña Deudas para vincularlas aquí 💳")

    with st.form("form_tx", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            fecha = st.date_input("Fecha", value=date.today())
        with c2:
            # Cuentas: usar las del usuario si las hay, sino la lista por defecto
            cuenta_label = "Cuenta de destino" if tipo == "Ingreso" else "Cuenta de origen"
            cuentas_usuario_form = _load_cuentas_usuario()
            if cuentas_usuario_form:
                cuenta_opts = list(cuentas_usuario_form.keys())
                cuenta_sel  = st.selectbox(cuenta_label, cuenta_opts, key="form_cuenta_sel")
            else:
                cuenta_sel  = st.selectbox(cuenta_label, CUENTAS, key="form_cuenta_sel")
                cuentas_usuario_form = {}
        desc_obligatorio = (categoria == "Otro ingreso")
        desc_label       = "Descripción *" if desc_obligatorio else "Descripción"
        desc_placeholder = "Obligatorio — describe el ingreso…" if desc_obligatorio else "Opcional…"
        descripcion = st.text_input(desc_label, placeholder=desc_placeholder)
        sim = MONEDA_SIMBOLO.get(st.session_state.get("new_moneda", "COP"), "$")
        monto = st.number_input(f"Monto ({sim})", min_value=0.0, value=None,
                                placeholder="0", step=1000.0, format="%.0f")
        ok = st.form_submit_button("Guardar transacción", use_container_width=True)
        if ok:
            cat_val    = st.session_state.get("new_cat", categoria)
            mon_val    = st.session_state.get("new_moneda", "COP")
            activo_nom = st.session_state.get("new_activo") if needs_activo else None
            cuenta_nom = cuenta_sel
            cuenta_id_val = None
            if cuenta_sel in cuentas_usuario_form:
                cuenta_id_val = int(cuentas_usuario_form[cuenta_sel]["id"])
                cuenta_nom    = cuentas_usuario_form[cuenta_sel]["nombre"]

            # Resolve gasto fijo (Obligaciones)
            gasto_fijo_nom = st.session_state.get("new_gasto_fijo") if needs_obligacion else None
            gasto_fijo_rec = gastos_fijos_dict.get(gasto_fijo_nom) if gasto_fijo_nom else None

            # Resolve tarjeta seleccionada
            tarjeta_nom = st.session_state.get("new_tarjeta_tc") if needs_tarjeta else None
            tarjeta_rec = next((t for t in tarjetas_list if t["nombre"] == tarjeta_nom), None) if tarjeta_nom else None

            # Validaciones
            if desc_obligatorio and not descripcion.strip():
                st.warning("La descripción es necesaria para 'Otro ingreso'. Cuéntanos de qué se trata 📝")
            elif not monto or monto <= 0:
                st.warning("El monto debe ser mayor a cero.")
            elif needs_activo and not activo_nom:
                st.warning("Selecciona un activo del portafolio para continuar.")
            elif needs_activo and activo_nom and activo_nom in activos_dict and \
                 cat_val == "Retiro de portafolio" and monto > float(activos_dict[activo_nom]["cantidad"]):
                st.warning(f"El retiro ({sim} {monto:,.0f}) supera el valor del activo ({cop(activos_dict[activo_nom]['cantidad'])}). Ajusta el monto.")
            else:
                # Advertencia cupo (no bloquea)
                if tarjeta_rec:
                    cupo_max = tarjeta_rec.get("cupo_maximo") or 0
                    saldo_tc = float(tarjeta_rec.get("saldo") or 0)
                    if cupo_max > 0 and (saldo_tc + monto) > cupo_max:
                        cupo_disp = max(cupo_max - saldo_tc, 0)
                        st.warning(f"⚠️ Este gasto supera el cupo disponible de {cop(cupo_disp)}. Se registrará de todas formas.")

                desc_auto = descripcion
                if not desc_auto:
                    if cat_val == "Portafolio" and activo_nom:
                        desc_auto = f"Inversión en {activo_nom}"
                    elif cat_val == "Retiro de portafolio" and activo_nom:
                        desc_auto = f"Retiro de {activo_nom}"
                    elif cat_val == "Obligaciones" and gasto_fijo_rec:
                        desc_auto = f"Pago: {gasto_fijo_rec['nombre']}"
                    elif tarjeta_rec:
                        desc_auto = f"Cargo a {tarjeta_rec['nombre']}"
                payload = {
                    "fecha": str(fecha), "tipo": tipo, "categoria": cat_val,
                    "descripcion": desc_auto, "monto": monto,
                    "cuenta": cuenta_nom, "user_id": uid()
                }
                try:
                    payload["moneda"]    = mon_val
                    payload["cuenta_id"] = cuenta_id_val
                    sb().table("transacciones").insert(payload).execute()
                except Exception:
                    # Columnas nuevas aún no existen en la BD — guardar sin ellas
                    payload.pop("moneda", None)
                    payload.pop("cuenta_id", None)
                    sb().table("transacciones").insert(payload).execute()

                # Actualizar portafolio
                if activo_nom and activo_nom in activos_dict:
                    activo = activos_dict[activo_nom]
                    if cat_val == "Portafolio":
                        nuevo_val = float(activo["cantidad"]) + float(monto)
                    else:  # Retiro de portafolio
                        nuevo_val = max(0.0, float(activo["cantidad"]) - float(monto))
                    sb().table("portafolio").update({"cantidad": nuevo_val}).eq("id", int(activo["id"])).eq("user_id", uid()).execute()

                # Actualizar saldo de la tarjeta de crédito en Deudas
                if tarjeta_rec:
                    nuevo_saldo_tc = round(float(tarjeta_rec["saldo"]) + monto, 2)
                    try:
                        sb().table("deudas").update({"saldo": nuevo_saldo_tc}).eq("id", int(tarjeta_rec["id"])).eq("user_id", uid()).execute()
                    except Exception:
                        pass

                # Marcar gasto fijo como pagado en Obligaciones
                if gasto_fijo_rec:
                    _marcar_gasto_fijo_pagado(int(gasto_fijo_rec["id"]), hoy.month, hoy.year)

                nota_activo    = f" → {activo_nom} actualizado" if activo_nom else ""
                nota_tarjeta   = f" · Saldo {tarjeta_rec['nombre']} actualizado" if tarjeta_rec else ""
                nota_obligacion = f" · {gasto_fijo_rec['nombre']} marcado como pagado ✓" if gasto_fijo_rec else ""
                st.success(f"{'Ingreso' if tipo=='Ingreso' else 'Gasto'} de {sim} {monto:,.0f} guardado{nota_activo}{nota_tarjeta}{nota_obligacion} ✓")
                st.rerun()

    resp = sb().table("transacciones").select("*").eq("user_id", uid()).order("fecha", desc=True).order("id", desc=True).execute()
    df = _df(resp)
    if df.empty:
        st.info("Aún no tienes transacciones. ¡Registra tu primera aquí arriba! 💸")
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
        tx_id      = int(r["id"])
        editing    = st.session_state.get("editing_tx_id") == tx_id

        col_info, col_edit, col_del = st.columns([10, 1, 1])
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
        with col_edit:
            if st.button("✏️", key=f"edit_trans_{tx_id}", type="secondary", use_container_width=True, help="Editar"):
                if editing:
                    del st.session_state["editing_tx_id"]
                else:
                    st.session_state["editing_tx_id"] = tx_id
                st.rerun()
        with col_del:
            if st.button("✕", key=f"del_trans_{tx_id}", type="secondary", use_container_width=True, help="Eliminar"):
                sb().table("transacciones").delete().eq("id", tx_id).eq("user_id", uid()).execute()
                if st.session_state.get("editing_tx_id") == tx_id:
                    del st.session_state["editing_tx_id"]
                st.rerun()

        if editing:
            cats_edit = CATEGORIAS_GASTO if r["tipo"] == "Gasto" else CATEGORIAS_INGRESO
            cat_idx   = cats_edit.index(r["categoria"]) if r["categoria"] in cats_edit else 0
            cta_idx   = CUENTAS.index(cuenta_val) if cuenta_val in CUENTAS else 0
            with st.form(key=f"form_edit_trans_{tx_id}", clear_on_submit=False):
                st.markdown('<p style="color:#322b49;font-size:12px;font-weight:700;margin:0 0 8px;">Editar transacción</p>', unsafe_allow_html=True)
                ec1, ec2 = st.columns(2)
                with ec1:
                    e_fecha = st.date_input("Fecha", value=date.fromisoformat(r["fecha"]), key=f"ef_trans_{tx_id}")
                with ec2:
                    e_cat = st.selectbox("Categoría", cats_edit, index=cat_idx, key=f"ec_trans_{tx_id}")
                e_cuenta = st.selectbox("Cuenta", CUENTAS, index=cta_idx, key=f"ect_trans_{tx_id}")
                e_desc   = st.text_input("Descripción", value=r["descripcion"] or "", key=f"ed_trans_{tx_id}")
                e_monto  = st.number_input("Monto ($)", min_value=0.0, value=float(r["monto"]),
                                           step=1000.0, format="%.0f", key=f"em_trans_{tx_id}")
                sc1, sc2 = st.columns(2)
                with sc1:
                    guardar = st.form_submit_button("Guardar", use_container_width=True)
                with sc2:
                    cancelar = st.form_submit_button("Cancelar", use_container_width=True)
                if guardar:
                    if not e_monto or e_monto <= 0:
                        st.warning("El monto debe ser mayor a 0.")
                    else:
                        sb().table("transacciones").update({
                            "fecha": str(e_fecha), "categoria": e_cat,
                            "cuenta": e_cuenta, "descripcion": e_desc, "monto": e_monto,
                        }).eq("id", tx_id).eq("user_id", uid()).execute()
                        del st.session_state["editing_tx_id"]
                        st.rerun()
                if cancelar:
                    del st.session_state["editing_tx_id"]
                    st.rerun()

    st.markdown(f'<p style="color:#6b6285;font-size:12px;text-align:center;margin-top:4px;">{len(dff)} transacciones</p>', unsafe_allow_html=True)


def _valor_actual_activo(r):
    """Valor actual de un activo incluyendo rendimientos para renta fija."""
    capital = float(r.get("cantidad", 0))
    tipo    = r.get("tipo", "")
    tasa    = float(r.get("tasa_interes") or 0)
    if tipo not in TIPOS_RENTA_FIJA or tasa <= 0:
        return capital
    try:
        f_inicio = date.fromisoformat(str(r.get("fecha") or date.today()))
    except (ValueError, TypeError):
        return capital
    dias      = max((date.today() - f_inicio).days, 0)
    modalidad = r.get("modalidad_interes") or "Compuesto"
    return capital + calcular_rendimiento_rf(capital, tasa, dias, modalidad)


def page_portafolio():
    resp = sb().table("portafolio").select("*").eq("user_id", uid()).order("id", desc=True).execute()
    df   = _df(resp)

    # Total incluye rendimientos de renta fija
    total = sum(_valor_actual_activo(r) for _, r in df.iterrows()) if not df.empty else 0

    st.markdown(card_wrap(f"""
      <p style="color:#5c5474;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;font-weight:600;">Valor total del portafolio</p>
      <p style="color:#4A7C59;font-size:2.4rem;font-weight:800;margin:0;letter-spacing:-1px;">{cop(total)}</p>
    """), unsafe_allow_html=True)

    st.markdown(section_title("Agregar activo"), unsafe_allow_html=True)
    # tipo fuera del form para mostrar campos condicionales de renta fija
    tipo_nuevo   = st.selectbox("Tipo", TIPOS_ACTIVO, key="new_activo_tipo")
    es_renta_fija = tipo_nuevo in TIPOS_RENTA_FIJA

    with st.form("form_activo", clear_on_submit=True):
        nombre = st.text_input("Nombre del activo", placeholder="CDT Bancolombia, TES 2026…")
        c1, c2 = st.columns(2)
        with c1:
            fecha = st.date_input("Fecha de inicio", value=date.today())
        with c2:
            valor = st.number_input("Capital invertido ($)", min_value=0.0, value=None,
                                    placeholder="0", step=1000.0, format="%.0f")
        if es_renta_fija:
            rf1, rf2 = st.columns(2)
            with rf1:
                tasa_rf     = st.number_input("Tasa de interés anual (%)", min_value=0.0,
                                               value=None, placeholder="12.5", step=0.1, format="%.2f")
                modalidad_rf = st.selectbox("Modalidad", MODALIDADES_INT)
            with rf2:
                tiene_venc   = tipo_nuevo in {"CDT", "Bonos"}
                venc_label   = "Fecha de vencimiento" + (" *" if tiene_venc else " (opcional)")
                fecha_venc_rf = st.date_input(venc_label, value=None)
        else:
            tasa_rf = None; modalidad_rf = "Compuesto"; fecha_venc_rf = None

        ok = st.form_submit_button("Agregar al portafolio", use_container_width=True)
        if ok:
            tipo_val = st.session_state.get("new_activo_tipo", tipo_nuevo)
            if not nombre:
                st.warning("Dale un nombre a tu activo para identificarlo.")
            elif not valor or valor <= 0:
                st.warning("El capital invertido debe ser mayor a 0.")
            elif tipo_val in TIPOS_RENTA_FIJA and (not tasa_rf or tasa_rf <= 0):
                st.warning("Ingresa la tasa de interés anual para este tipo de activo.")
            else:
                plazo_dias = None
                venc_str   = None
                if fecha_venc_rf:
                    plazo_dias = max((fecha_venc_rf - fecha).days, 0)
                    venc_str   = str(fecha_venc_rf)
                payload = {
                    "nombre": nombre, "tipo": tipo_val, "cantidad": valor,
                    "valor_unitario": 1.0, "fecha": str(fecha), "user_id": uid()
                }
                try:
                    payload["tasa_interes"]      = float(tasa_rf) if tasa_rf else None
                    payload["plazo"]             = plazo_dias
                    payload["fecha_vencimiento"] = venc_str
                    payload["modalidad_interes"] = modalidad_rf
                    sb().table("portafolio").insert(payload).execute()
                except Exception:
                    payload.pop("tasa_interes", None); payload.pop("plazo", None)
                    payload.pop("fecha_vencimiento", None); payload.pop("modalidad_interes", None)
                    sb().table("portafolio").insert(payload).execute()
                st.success(f"{nombre} agregado al portafolio.")
                st.rerun()

    if df.empty:
        return

    st.markdown(section_title("Mis activos"), unsafe_allow_html=True)

    if "editing_asset_id" not in st.session_state:
        st.session_state.editing_asset_id = None
    if "withdrawing_asset_id" not in st.session_state:
        st.session_state.withdrawing_asset_id = None

    for _, r in df.iterrows():
        asset_id    = int(r["id"])
        icon        = CAT_ICONS.get(r["tipo"], "💎")
        editing     = st.session_state.editing_asset_id    == asset_id
        withdrawing = st.session_state.withdrawing_asset_id == asset_id
        tasa_row    = float(r.get("tasa_interes") or 0)
        es_rf       = r.get("tipo") in TIPOS_RENTA_FIJA and tasa_row > 0

        col_info, col_ret, col_edit, col_del = st.columns([8, 1, 1, 1])
        with col_info:
            if es_rf:
                st.markdown(renta_fija_card(
                    r["nombre"], r["tipo"], float(r["cantidad"]), tasa_row,
                    r.get("fecha"), r.get("fecha_vencimiento"),
                    r.get("modalidad_interes") or "Compuesto"
                ), unsafe_allow_html=True)
            else:
                st.markdown(card_wrap(asset_row(icon, r["nombre"], r["tipo"], r["cantidad"]), "0 1.2rem"), unsafe_allow_html=True)
        with col_ret:
            st.markdown("<div style='height:44px'></div>", unsafe_allow_html=True)
            if st.button("↩", key=f"ret_port_{asset_id}", help="Retirar fondos"):
                st.session_state.withdrawing_asset_id = None if withdrawing else asset_id
                if not withdrawing:
                    st.session_state.editing_asset_id = None
                st.rerun()
        with col_edit:
            st.markdown("<div style='height:44px'></div>", unsafe_allow_html=True)
            if st.button("✏️", key=f"edit_port_{asset_id}", help="Editar valor"):
                st.session_state.editing_asset_id = None if editing else asset_id
                if not editing:
                    st.session_state.withdrawing_asset_id = None
                st.rerun()
        with col_del:
            st.markdown("<div style='height:44px'></div>", unsafe_allow_html=True)
            if st.button("✕", key=f"del_port_{asset_id}", help="Eliminar activo"):
                sb().table("portafolio").delete().eq("id", asset_id).eq("user_id", uid()).execute()
                if st.session_state.editing_asset_id    == asset_id: st.session_state.editing_asset_id    = None
                if st.session_state.withdrawing_asset_id == asset_id: st.session_state.withdrawing_asset_id = None
                st.rerun()

        # ── Panel de retiro ──────────────────────────────────────────────
        if withdrawing:
            saldo_act = float(r["cantidad"])
            with st.form(key=f"form_ret_port_{asset_id}", clear_on_submit=True):
                st.markdown(f'<p style="color:#322b49;font-size:12px;font-weight:700;margin:0 0 8px;">Retirar de {r["nombre"]} — capital: <b>{cop(saldo_act)}</b></p>', unsafe_allow_html=True)
                ret_monto = st.number_input(
                    "Monto a retirar ($)", min_value=0.0, max_value=saldo_act,
                    value=None, placeholder="0", step=1000.0, format="%.0f",
                    key=f"ret_monto_{asset_id}"
                )
                r1, r2 = st.columns(2)
                with r1:
                    confirmar = st.form_submit_button("Retirar", use_container_width=True)
                with r2:
                    cancelar_ret = st.form_submit_button("Cancelar", use_container_width=True)

                if confirmar:
                    if not ret_monto or ret_monto <= 0:
                        st.warning("Ingresa un monto válido para retirar.")
                    elif ret_monto > saldo_act:
                        st.warning(f"No puedes retirar más del capital ({cop(saldo_act)}).")
                    else:
                        nuevo_val = round(saldo_act - ret_monto, 2)
                        sb().table("portafolio").update({"cantidad": nuevo_val}).eq("id", asset_id).eq("user_id", uid()).execute()
                        sb().table("transacciones").insert({
                            "fecha": str(date.today()), "tipo": "Ingreso",
                            "categoria": "Portafolio",
                            "descripcion": f"Retiro de {r['nombre']}",
                            "monto": ret_monto, "cuenta": "Cuenta bancaria", "user_id": uid()
                        }).execute()
                        st.session_state.withdrawing_asset_id = None
                        if nuevo_val <= 0:
                            st.session_state[f"confirm_del_port_{asset_id}"] = True
                        st.rerun()
                if cancelar_ret:
                    st.session_state.withdrawing_asset_id = None
                    st.rerun()

        # ── Confirmar eliminación si el activo quedó en 0 ────────────────
        if st.session_state.get(f"confirm_del_port_{asset_id}"):
            st.warning(f"**{r['nombre']}** quedó en $0. ¿Deseas eliminarlo del portafolio?")
            cd1, cd2 = st.columns(2)
            with cd1:
                if st.button("Sí, eliminar", key=f"confirm_yes_port_{asset_id}", use_container_width=True):
                    sb().table("portafolio").delete().eq("id", asset_id).eq("user_id", uid()).execute()
                    del st.session_state[f"confirm_del_port_{asset_id}"]
                    st.rerun()
            with cd2:
                if st.button("No, conservar", key=f"confirm_no_port_{asset_id}", use_container_width=True):
                    del st.session_state[f"confirm_del_port_{asset_id}"]
                    st.rerun()

        # ── Panel de edición ─────────────────────────────────────────────
        if editing:
            with st.form(key=f"form_edit_port_{asset_id}", clear_on_submit=False):
                nuevo_valor = st.number_input(
                    f"Nuevo capital para {r['nombre']} ($)",
                    min_value=0.0, value=float(r["cantidad"]),
                    step=1000.0, format="%.0f", key=f"val_port_{asset_id}"
                )
                s1, s2 = st.columns(2)
                with s1:
                    guardar = st.form_submit_button("💾 Guardar", use_container_width=True)
                with s2:
                    cancelar = st.form_submit_button("Cancelar", use_container_width=True)
                if guardar:
                    sb().table("portafolio").update({"cantidad": nuevo_valor}).eq("id", asset_id).eq("user_id", uid()).execute()
                    st.session_state.editing_asset_id = None
                    st.rerun()
                if cancelar:
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


def page_metas():
    resp = sb().table("metas").select("*").eq("user_id", uid()).order("id", desc=True).execute()
    df   = _df(resp)

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
                st.warning("Ponle un nombre a tu meta para identificarla.")
            elif not objetivo or objetivo <= 0:
                st.warning("El monto objetivo debe ser mayor a 0.")
            else:
                sb().table("metas").insert({
                    "nombre": nombre, "objetivo": objetivo, "actual": 0,
                    "fecha_limite": str(deadline) if deadline else None,
                    "emoji": emoji, "user_id": uid()
                }).execute()
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
        meta_id      = int(r["id"])
        adding_funds = st.session_state.get("adding_funds_meta_id") == meta_id

        st.markdown(meta_card(r["emoji"], r["nombre"], r["actual"], r["objetivo"], r["fecha_limite"]), unsafe_allow_html=True)

        ca, cb = st.columns(2)
        with ca:
            lbl_funds = "✕ Cerrar" if adding_funds else "💰 Agregar fondos"
            if st.button(lbl_funds, key=f"show_funds_meta_{meta_id}", use_container_width=True):
                st.session_state["adding_funds_meta_id"] = None if adding_funds else meta_id
                st.rerun()
        with cb:
            if st.button("🗑 Eliminar meta", key=f"del_meta_{meta_id}", use_container_width=True):
                sb().table("metas").delete().eq("id", meta_id).eq("user_id", uid()).execute()
                if st.session_state.get("adding_funds_meta_id") == meta_id:
                    st.session_state["adding_funds_meta_id"] = None
                st.rerun()

        if adding_funds:
            with st.form(key=f"form_funds_meta_{meta_id}", clear_on_submit=True):
                add_monto = st.number_input(
                    "Monto a agregar ($)", min_value=0.0, value=None,
                    placeholder="0", step=10000.0, format="%.0f",
                    key=f"funds_monto_meta_{meta_id}"
                )
                if st.form_submit_button("Agregar fondos", use_container_width=True):
                    if not add_monto or add_monto <= 0:
                        st.warning("Ingresa un monto mayor a 0 para agregar fondos.")
                    else:
                        nuevo_actual = min(float(r["actual"]) + add_monto, float(r["objetivo"]))
                        sb().table("metas").update({"actual": nuevo_actual}).eq("id", meta_id).eq("user_id", uid()).execute()
                        st.session_state["adding_funds_meta_id"] = None
                        st.rerun()


def page_deudas():
    resp = sb().table("deudas").select("*").eq("user_id", uid()).order("saldo", desc=True).execute()
    df   = _df(resp)

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
    tipo_deuda_nuevo = st.selectbox("Tipo", TIPOS_DEUDA, key="new_deuda_tipo")
    es_tarjeta_nuevo = tipo_deuda_nuevo == "Tarjeta de crédito"
    with st.form("form_deuda", clear_on_submit=True):
        nombre = st.text_input("Nombre", placeholder="Tarjeta Visa, Préstamo banco…")
        c1, c2 = st.columns(2)
        with c1:
            deuda_inicial = st.number_input("Deuda / saldo actual ($)", min_value=0.0, value=None,
                                            placeholder="0", step=100000.0, format="%.0f")
        with c2:
            tasa = st.number_input("Tasa de interés anual (%)", min_value=0.0,
                                   value=None, placeholder="18.5", step=0.1, format="%.2f")
        if es_tarjeta_nuevo:
            tc1, tc2 = st.columns(2)
            with tc1:
                cupo_maximo_inp = st.number_input("Cupo máximo ($) — opcional", min_value=0.0, value=None,
                                                  placeholder="0", step=100000.0, format="%.0f")
            with tc2:
                num_cuotas_inp = st.number_input("Nº de cuotas — opcional", min_value=0, value=None,
                                                 placeholder="0", step=1, format="%d")
            pago_minimo_inp = st.number_input("Pago mínimo mensual ($) — opcional si usas cuotas",
                                              min_value=0.0, value=None, placeholder="0",
                                              step=10000.0, format="%.0f")
        else:
            cupo_maximo_inp = None
            num_cuotas_inp  = None
            pago_minimo_inp = st.number_input("Pago mínimo mensual ($)", min_value=0.0,
                                              value=None, placeholder="0", step=10000.0, format="%.0f")
        fecha_inicio = st.date_input("Fecha de inicio", value=date.today())
        ok = st.form_submit_button("Agregar deuda", use_container_width=True)
        if ok:
            tipo_val = st.session_state.get("new_deuda_tipo", tipo_deuda_nuevo)
            if not nombre:
                st.warning("Dale un nombre a la deuda para identificarla.")
            elif not deuda_inicial or deuda_inicial <= 0:
                st.warning("El monto de la deuda debe ser mayor a 0.")
            else:
                # Si hay cuotas, calcular el pago mensual automáticamente
                pago_final = float(pago_minimo_inp or 0.0)
                nc = int(num_cuotas_inp or 0)
                if nc > 0 and pago_final == 0:
                    pago_final = round(calcular_cuota(deuda_inicial, float(tasa or 0), nc), 0)
                payload = {
                    "nombre": nombre, "tipo": tipo_val, "deuda_inicial": deuda_inicial,
                    "saldo": deuda_inicial, "tasa_interes": float(tasa or 0.0),
                    "pago_minimo": pago_final,
                    "fecha_inicio": str(fecha_inicio), "user_id": uid()
                }
                try:
                    payload["cupo_maximo"] = float(cupo_maximo_inp) if cupo_maximo_inp else None
                    payload["num_cuotas"]  = nc if nc > 0 else None
                    sb().table("deudas").insert(payload).execute()
                except Exception:
                    payload.pop("cupo_maximo", None)
                    payload.pop("num_cuotas", None)
                    sb().table("deudas").insert(payload).execute()
                st.success(f"Deuda '{nombre}' registrada." + (f" Cuota calculada: {cop(pago_final)}/mes." if nc > 0 and pago_final > 0 else ""))
                st.rerun()

    if df.empty:
        st.info("Sin deudas registradas. ¡Eso es buena señal!")
        return

    st.markdown(section_title("Mis deudas"), unsafe_allow_html=True)
    for _, r in df.iterrows():
        deuda_id  = int(r["id"])
        saldo_val = float(r["saldo"])
        paying    = st.session_state.get("paying_deuda_id") == deuda_id

        fecha_fin, total_int = proyectar_deuda(saldo_val, r["tasa_interes"], r["pago_minimo"])
        meses_rest = None
        if fecha_fin:
            today = date.today()
            meses_rest = (fecha_fin.year - today.year) * 12 + (fecha_fin.month - today.month)
            meses_rest = max(meses_rest, 1)
        cupo_max_val = r.get("cupo_maximo") if "cupo_maximo" in r else None
        st.markdown(debt_card(r["nombre"], r["tipo"], r["deuda_inicial"], saldo_val,
                              r["tasa_interes"], r["pago_minimo"], fecha_fin, total_int,
                              cupo_maximo=cupo_max_val, meses_restantes=meses_rest),
                    unsafe_allow_html=True)

        pagos_resp = sb().table("pagos_deuda").select("*").eq("deuda_id", deuda_id).order("fecha", desc=True).limit(5).execute()
        pagos = _df(pagos_resp)
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

        cp, cd = st.columns(2)
        with cp:
            lbl_pago = "✕ Cerrar" if paying else "💳 Registrar pago"
            if st.button(lbl_pago, key=f"show_pay_deuda_{deuda_id}", use_container_width=True):
                st.session_state["paying_deuda_id"] = None if paying else deuda_id
                st.rerun()
        with cd:
            if st.button("🗑 Eliminar deuda", key=f"del_deuda_{deuda_id}", use_container_width=True):
                sb().table("pagos_deuda").delete().eq("deuda_id", deuda_id).execute()
                sb().table("deudas").delete().eq("id", deuda_id).eq("user_id", uid()).execute()
                if st.session_state.get("paying_deuda_id") == deuda_id:
                    st.session_state["paying_deuda_id"] = None
                st.rerun()

        if paying:
            with st.form(key=f"form_pay_deuda_{deuda_id}", clear_on_submit=True):
                pc1, pc2 = st.columns(2)
                with pc1:
                    pago_fecha = st.date_input("Fecha", value=date.today(), key=f"pago_fecha_{deuda_id}")
                with pc2:
                    pago_monto = st.number_input(
                        "Monto ($)", min_value=0.0, value=None,
                        placeholder="0", step=10000.0, format="%.0f",
                        key=f"pago_monto_{deuda_id}"
                    )
                pago_nota = st.text_input("Nota (opcional)", placeholder="Pago mensual, abono extra…",
                                          key=f"pago_nota_{deuda_id}")
                if st.form_submit_button("Registrar pago", use_container_width=True):
                    if not pago_monto or pago_monto <= 0:
                        st.warning("Ingresa un monto mayor a 0 para registrar el pago.")
                    elif pago_monto > saldo_val:
                        st.warning(f"El monto del pago ({cop(pago_monto)}) supera el saldo restante ({cop(saldo_val)}).")
                    else:
                        nuevo_saldo = round(saldo_val - pago_monto, 2)
                        sb().table("pagos_deuda").insert({
                            "deuda_id": deuda_id, "fecha": str(pago_fecha),
                            "monto": pago_monto, "nota": pago_nota or None
                        }).execute()
                        sb().table("deudas").update({"saldo": nuevo_saldo}).eq("id", deuda_id).eq("user_id", uid()).execute()
                        st.session_state["paying_deuda_id"] = None
                        st.rerun()


# ─── Obligaciones Page ────────────────────────────────────────────────────────
CATS_GASTO_FIJO = ["Arriendo", "Servicios", "Suscripciones", "Créditos", "Seguros", "Otro"]

def _load_gastos_fijos():
    resp = sb().table("gastos_fijos").select("*").eq("user_id", uid()).order("dia_vencimiento").execute()
    return resp.data or []

def _load_pagos_mes(mes, anio):
    """Devuelve dict {gasto_fijo_id: registro_pago} para el mes/año dado."""
    ids_resp = sb().table("gastos_fijos").select("id").eq("user_id", uid()).execute()
    ids = [r["id"] for r in (ids_resp.data or [])]
    if not ids:
        return {}
    resp = sb().table("pagos_gastos_fijos").select("*").in_("gasto_fijo_id", ids).eq("mes", mes).eq("anio", anio).execute()
    return {r["gasto_fijo_id"]: r for r in (resp.data or [])}

def _ensure_pago(gasto_id, mes, anio):
    """Crea registro de pago si no existe; retorna el registro."""
    pagos = _load_pagos_mes(mes, anio)
    if gasto_id in pagos:
        return pagos[gasto_id]
    sb().table("pagos_gastos_fijos").insert({
        "gasto_fijo_id": gasto_id, "mes": mes, "anio": anio,
        "pagado": False, "fecha_pago": None
    }).execute()
    pagos2 = _load_pagos_mes(mes, anio)
    return pagos2.get(gasto_id, {})

def _marcar_gasto_fijo_pagado(gasto_id, mes, anio):
    """Marca un gasto fijo como pagado en el mes actual."""
    pagos = _load_pagos_mes(mes, anio)
    hoy   = str(date.today())
    if gasto_id in pagos:
        sb().table("pagos_gastos_fijos").update({
            "pagado": True, "fecha_pago": hoy
        }).eq("id", pagos[gasto_id]["id"]).execute()
    else:
        sb().table("pagos_gastos_fijos").insert({
            "gasto_fijo_id": gasto_id, "mes": mes, "anio": anio,
            "pagado": True, "fecha_pago": hoy
        }).execute()

def page_obligaciones():
    hoy   = date.today()
    mes   = hoy.month
    anio  = hoy.year

    st.markdown("""
    <div style="background:linear-gradient(135deg,#322b49 0%,#3e3260 100%);
                border-radius:20px;padding:1.4rem 1.6rem;margin-bottom:16px;">
      <p style="color:rgba(255,255,255,0.5);font-size:10px;text-transform:uppercase;
                letter-spacing:1.2px;margin:0 0 4px;font-weight:600;">Compromisos del mes</p>
      <p style="color:#eab000;font-size:1.5rem;font-weight:800;margin:0;letter-spacing:-0.5px;">
        📋 Obligaciones</p>
    </div>""", unsafe_allow_html=True)

    gastos = _load_gastos_fijos()
    pagos  = _load_pagos_mes(mes, anio)

    total      = sum(float(g["monto"]) for g in gastos)
    pagado_sum = sum(float(g["monto"]) for g in gastos if pagos.get(g["id"], {}).get("pagado"))
    pendiente  = total - pagado_sum

    # ── Resumen ──────────────────────────────────────────────────────────────
    if gastos:
        st.markdown(card_wrap(f"""
          <p style="color:#5c5474;font-size:10px;text-transform:uppercase;letter-spacing:1px;
                    margin:0 0 10px;font-weight:600;">Resumen del mes</p>
          <div style="display:flex;gap:12px;flex-wrap:wrap;">
            <div style="flex:1;min-width:80px;background:#F5F0E8;border-radius:14px;padding:12px;">
              <p style="color:#6b6285;font-size:10px;text-transform:uppercase;letter-spacing:0.8px;
                        margin:0 0 4px;font-weight:600;">Total</p>
              <p style="color:#322b49;font-size:18px;font-weight:800;margin:0;">{cop(total)}</p>
            </div>
            <div style="flex:1;min-width:80px;background:rgba(74,124,89,0.08);border-radius:14px;padding:12px;">
              <p style="color:#6b6285;font-size:10px;text-transform:uppercase;letter-spacing:0.8px;
                        margin:0 0 4px;font-weight:600;">Pagado</p>
              <p style="color:#4A7C59;font-size:18px;font-weight:800;margin:0;">{cop(pagado_sum)}</p>
            </div>
            <div style="flex:1;min-width:80px;background:rgba(192,57,43,0.08);border-radius:14px;padding:12px;">
              <p style="color:#6b6285;font-size:10px;text-transform:uppercase;letter-spacing:0.8px;
                        margin:0 0 4px;font-weight:600;">Pendiente</p>
              <p style="color:#C0392B;font-size:18px;font-weight:800;margin:0;">{cop(pendiente)}</p>
            </div>
          </div>
        """), unsafe_allow_html=True)

    # ── Checklist mensual ────────────────────────────────────────────────────
    st.markdown(section_title(f"Gastos fijos — {hoy.strftime('%B %Y').capitalize()}"), unsafe_allow_html=True)

    if not gastos:
        st.markdown(card_wrap('<p style="color:#6b6285;font-size:13px;text-align:center;padding:0.5rem 0;margin:0;">Aún no tienes gastos fijos. Agrégalos abajo 👇</p>'), unsafe_allow_html=True)
    else:
        cat_icons_ob = {"Arriendo":"🏠","Servicios":"⚡","Suscripciones":"📺","Créditos":"💳","Seguros":"🛡️","Otro":"📋"}
        for g in gastos:
            gid     = g["id"]
            pago    = pagos.get(gid, {})
            pagado  = pago.get("pagado", False)
            vence   = int(g["dia_vencimiento"])
            vencido = (not pagado) and (hoy.day > vence)
            icon    = cat_icons_ob.get(g["categoria"], "📋")

            if pagado:
                color_borde = "#4A7C59"
                color_bg    = "rgba(74,124,89,0.06)"
                estado_html = '<span style="color:#4A7C59;font-size:11px;font-weight:700;">✓ Pagado</span>'
                nombre_style = "color:#6b6285;text-decoration:line-through;"
            elif vencido:
                color_borde = "#C0392B"
                color_bg    = "rgba(192,57,43,0.04)"
                estado_html = f'<span style="color:#C0392B;font-size:11px;font-weight:700;">⚠ Vencido (día {vence})</span>'
                nombre_style = "color:#1c1829;"
            else:
                color_borde = "rgba(0,0,0,0.06)"
                color_bg    = "#FFFFFF"
                estado_html = f'<span style="color:#6b6285;font-size:11px;">Vence día {vence}</span>'
                nombre_style = "color:#1c1829;"

            col_info, col_btn = st.columns([5, 1])
            with col_info:
                st.markdown(f"""
                <div style="background:{color_bg};border:1.5px solid {color_borde};border-radius:16px;
                            padding:12px 16px;display:flex;align-items:center;gap:12px;margin-bottom:8px;">
                  <span style="font-size:22px;">{icon}</span>
                  <div style="flex:1;">
                    <p style="{nombre_style}font-size:14px;font-weight:600;margin:0;">{g['nombre']}</p>
                    <p style="color:#6b6285;font-size:11px;margin:2px 0 0;">{g['categoria']} · {g['cuenta']}</p>
                    <div style="margin-top:3px;">{estado_html}</div>
                  </div>
                  <p style="color:#322b49;font-size:15px;font-weight:700;margin:0;">{cop(g['monto'])}</p>
                </div>""", unsafe_allow_html=True)
            with col_btn:
                if not pagado:
                    if st.button("✓", key=f"pagar_{gid}", help="Marcar como pagado",
                                 use_container_width=True):
                        _marcar_gasto_fijo_pagado(gid, mes, anio)
                        st.rerun()
                else:
                    if st.button("↩", key=f"desmarcar_{gid}", help="Desmarcar",
                                 use_container_width=True):
                        pago_rec = pagos.get(gid)
                        if pago_rec:
                            sb().table("pagos_gastos_fijos").update({
                                "pagado": False, "fecha_pago": None
                            }).eq("id", pago_rec["id"]).execute()
                        st.rerun()

    # ── Formulario para agregar gasto fijo ───────────────────────────────────
    st.markdown(section_title("Agregar gasto fijo"), unsafe_allow_html=True)
    with st.expander("➕ Nuevo gasto fijo"):
        with st.form("form_gasto_fijo", clear_on_submit=True):
            gf_nombre = st.text_input("Nombre", placeholder="Arriendo, Netflix, Seguro de vida…")
            gf_c1, gf_c2 = st.columns(2)
            with gf_c1:
                gf_cat  = st.selectbox("Categoría", CATS_GASTO_FIJO)
                gf_dia  = st.number_input("Día de vencimiento", min_value=1, max_value=31, value=1, step=1, format="%d")
            with gf_c2:
                gf_monto = st.number_input("Monto ($)", min_value=0.0, value=None,
                                            placeholder="0", step=10000.0, format="%.0f")
                cuentas_usuario_ob = _load_cuentas_usuario()
                gf_cuenta_opts     = list(cuentas_usuario_ob.keys()) if cuentas_usuario_ob else CUENTAS
                gf_cuenta = st.selectbox("Cuenta de pago", gf_cuenta_opts)
            if st.form_submit_button("Guardar gasto fijo", use_container_width=True):
                if not gf_nombre:
                    st.warning("Escribe un nombre para el gasto fijo.")
                elif not gf_monto or gf_monto <= 0:
                    st.warning("El monto debe ser mayor a cero.")
                else:
                    try:
                        sb().table("gastos_fijos").insert({
                            "nombre": gf_nombre.strip(),
                            "categoria": gf_cat,
                            "monto": gf_monto,
                            "dia_vencimiento": int(gf_dia),
                            "cuenta": gf_cuenta,
                            "user_id": uid()
                        }).execute()
                        st.success(f"Gasto fijo '{gf_nombre}' guardado ✓")
                        st.rerun()
                    except Exception as e:
                        st.warning(f"Hubo un problema al guardar. Intenta de nuevo. ({e})")

    # ── Eliminar gasto fijo ───────────────────────────────────────────────────
    if gastos:
        st.markdown(section_title("Eliminar gasto fijo"), unsafe_allow_html=True)
        with st.expander("🗑️ Eliminar"):
            nombres_gastos = {g["nombre"]: g["id"] for g in gastos}
            sel_eliminar = st.selectbox("Selecciona el gasto a eliminar", list(nombres_gastos.keys()), key="sel_del_gf")
            if st.button("Eliminar", key="btn_del_gf"):
                gid_del = nombres_gastos[sel_eliminar]
                sb().table("pagos_gastos_fijos").delete().eq("gasto_fijo_id", gid_del).execute()
                sb().table("gastos_fijos").delete().eq("id", gid_del).eq("user_id", uid()).execute()
                st.rerun()


# ─── Consil.ia Page ───────────────────────────────────────────────────────────
def page_consilia():
    resp = sb().table("transacciones").select("*").eq("user_id", uid()).order("fecha", desc=True).execute()
    df = _df(resp)
    if df.empty:
        st.info("📊 Registra tus transacciones para que Consil.ia pueda darte un análisis personalizado.")
        return
    ingresos = float(df[df["tipo"] == "Ingreso"]["monto"].sum())
    gastos   = float(df[df["tipo"] == "Gasto"]["monto"].sum())
    balance  = ingresos - gastos
    consilia_section(df, ingresos, gastos, balance)


# ─── Admin Page ───────────────────────────────────────────────────────────────
def page_admin():
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#322b49,#221e32);border-radius:20px;
                padding:1.4rem 1.6rem;margin-bottom:16px;">
      <p style="color:rgba(255,255,255,0.5);font-size:10px;text-transform:uppercase;
                letter-spacing:1.2px;margin:0 0 4px;font-weight:600;">Panel privado</p>
      <p style="color:#eab000;font-size:1.5rem;font-weight:800;margin:0;letter-spacing:-0.5px;">
        Administración ◆</p>
    </div>""", unsafe_allow_html=True)

    # ── Usuarios ──────────────────────────────────────────────────────────────
    resp_u = sb().table("usuarios").select("id, nombre, email").order("id").execute()
    usuarios_df = _df(resp_u)
    total_u = len(usuarios_df)

    st.markdown(section_title("Usuarios"), unsafe_allow_html=True)
    st.markdown(card_wrap(f"""
      <p style="color:#5c5474;font-size:11px;text-transform:uppercase;letter-spacing:1px;
                margin:0 0 6px;font-weight:600;">Total registrados</p>
      <p style="color:#322b49;font-size:2.8rem;font-weight:800;margin:0;letter-spacing:-1.5px;
                line-height:1;">{total_u}</p>
      <p style="color:#6b6285;font-size:12px;margin:4px 0 0;">usuarios en la plataforma</p>
    """), unsafe_allow_html=True)

    if not usuarios_df.empty:
        rows_html = ""
        for _, r in usuarios_df.iterrows():
            rows_html += f"""
            <div style="display:flex;align-items:center;padding:10px 0;
                        border-bottom:1px solid rgba(0,0,0,0.05);">
              <div style="width:38px;height:38px;border-radius:12px;background:#F5F0E8;
                          display:flex;align-items:center;justify-content:center;
                          font-size:16px;margin-right:12px;flex-shrink:0;">👤</div>
              <div style="flex:1;min-width:0;">
                <p style="color:#1c1829;font-size:13px;font-weight:600;margin:0;
                           overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{r['nombre']}</p>
                <p style="color:#6b6285;font-size:11px;margin:2px 0 0;
                           overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{r['email']}</p>
              </div>
              <p style="color:#b78a00;font-size:11px;font-weight:600;margin:0;
                        flex-shrink:0;padding-left:8px;">#{int(r['id'])}</p>
            </div>"""
        st.markdown(card_wrap(rows_html, "0.6rem 1.2rem"), unsafe_allow_html=True)

    # ── Actividad ─────────────────────────────────────────────────────────────
    st.markdown(section_title("Actividad global"), unsafe_allow_html=True)

    resp_tx   = sb().table("transacciones").select("id").execute()
    resp_mt   = sb().table("metas").select("id").execute()
    resp_deu  = sb().table("deudas").select("id").execute()
    total_tx  = len(resp_tx.data)  if resp_tx.data  else 0
    total_mt  = len(resp_mt.data)  if resp_mt.data  else 0
    total_deu = len(resp_deu.data) if resp_deu.data else 0

    def metric_card(label, value, icon):
        return card_wrap(f"""
          <p style="font-size:22px;margin:0 0 8px;">{icon}</p>
          <p style="color:#5c5474;font-size:10px;text-transform:uppercase;letter-spacing:0.8px;
                    margin:0 0 4px;font-weight:600;">{label}</p>
          <p style="color:#322b49;font-size:1.8rem;font-weight:800;margin:0;
                    letter-spacing:-1px;line-height:1;">{value}</p>
        """, padding="1rem 1.2rem")

    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(metric_card("Transacciones", total_tx, "💸"), unsafe_allow_html=True)
    with c2: st.markdown(metric_card("Metas", total_mt, "🎯"), unsafe_allow_html=True)
    with c3: st.markdown(metric_card("Deudas", total_deu, "💳"), unsafe_allow_html=True)

    # ── Crecimiento ───────────────────────────────────────────────────────────
    st.markdown(section_title("Crecimiento de usuarios"), unsafe_allow_html=True)

    st.info("La gráfica de crecimiento estará disponible una vez que se agregue la columna `created_at` a la tabla `usuarios`.")


# ─── Main ─────────────────────────────────────────────────────────────────────
init_db()
st.set_page_config(page_title="Valore", page_icon="static/icon.png", layout="centered",
                   initial_sidebar_state="collapsed")
st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
st.markdown("""
<script>
(function(){
  var h = document.head;
  function meta(n, c) {
    var el = document.createElement('meta'); el.name = n; el.content = c; h.appendChild(el);
  }
  function link(r, href, extra) {
    var el = document.createElement('link'); el.rel = r; el.href = href;
    if (extra) Object.assign(el, extra);
    h.appendChild(el);
  }
  link('manifest', '/app/static/manifest.json');
  link('apple-touch-icon', '/app/static/icon.png');
  meta('apple-mobile-web-app-capable', 'yes');
  meta('apple-mobile-web-app-status-bar-style', 'black-translucent');
  meta('apple-mobile-web-app-title', 'Valore');
  meta('theme-color', '#322b49');
})();
</script>
""", unsafe_allow_html=True)

if not st.session_state.get("user_id"):
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

    is_admin = st.session_state.get("user_email", "").lower() == ADMIN_EMAIL
    tab_names = ["Dashboard", "Transacciones", "Portafolio", "Metas", "✨ Consil.ia", "Deudas", "📋 Obligaciones"]
    if is_admin:
        tab_names.append("Admin")

    tabs = st.tabs(tab_names)
    with tabs[0]: page_dashboard()
    with tabs[1]: page_transacciones()
    with tabs[2]: page_portafolio()
    with tabs[3]: page_metas()
    with tabs[4]: page_consilia()
    with tabs[5]: page_deudas()
    with tabs[6]: page_obligaciones()
    if is_admin:
        with tabs[7]: page_admin()
