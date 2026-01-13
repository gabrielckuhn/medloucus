import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import time
import plotly.graph_objects as go
import base64

# --- Funções Auxiliares ---
def get_image_as_base64(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
        encoded = base64.b64encode(data).decode()
        return f"data:image/png;base64,{encoded}"
    except:
        return None

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker Copeiros", page_icon="🩺", layout="wide")

# --- CSS GLOBAL ---
st.markdown("""
<style>
.block-container {padding-top: 2rem; padding-bottom: 5rem;}

.dashboard-card {
    background-color: white;
    border-radius: 15px;
    padding: 20px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    border: 1px solid #f0f0f0;
    margin-bottom: 20px;
}

.card-title {
    color: #555;
    font-size: 18px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 15px;
    border-bottom: 2px solid #f0f2f6;
    padding-bottom: 10px;
}

.js-plotly-plot .plotly .modebar { display: none !important; }

.profile-header-img {
    width: 80px;
    height: 80px;
    border-radius: 50%;
    object-fit: cover;
    border: 3px solid white;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    margin-right: 15px;
}
</style>
""", unsafe_allow_html=True)

# --- Dados ---
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1-i82jvSfNzG2Ri7fu3vmOFnIYqQYglapbQ7x0000_rc/edit?usp=sharing"

USUARIOS_CONFIG = {
    "Ana Clara": {"color": "#400043", "img": "ana_clara.png"},
    "Arthur":    {"color": "#263149", "img": "arthur.png"},
    "Gabriel":   {"color": "#bf7000", "img": "gabriel.png"},
    "Lívian":    {"color": "#0b4c00", "img": "livian.png"},
    "Newton":    {"color": "#002322", "img": "newton.png"},
    "Rafa":      {"color": "#c14121", "img": "rafa.png"}
}

LISTA_USUARIOS = list(USUARIOS_CONFIG.keys())

# --- Conexão ---
@st.cache_resource
def conectar_google_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        credentials = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=scopes
        )
        return gspread.authorize(credentials)
    except:
        return None

def carregar_dados():
    gc = conectar_google_sheets()
    if not gc:
        return pd.DataFrame(), None
    for _ in range(3):
        try:
            sh = gc.open_by_url(PLANILHA_URL)
            worksheet = sh.worksheet("Dados")
            return pd.DataFrame(worksheet.get_all_records()), worksheet
        except:
            time.sleep(1.5)
    return pd.DataFrame(), None

def atualizar_status(worksheet, row_index, col_index_num, novo_valor):
    try:
        worksheet.update_cell(row_index + 2, col_index_num, novo_valor)
    except:
        st.error("Erro ao salvar.")

def limpar_booleano(valor):
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        return valor.upper() == "TRUE"
    return False

# --- Navegação ---
if "pagina_atual" not in st.session_state:
    st.session_state.update({
        "pagina_atual": "dashboard",
        "usuario_ativo": None,
        "disciplina_ativa": None
    })

def ir_para_dashboard():
    st.session_state.update({"pagina_atual": "dashboard", "usuario_ativo": None})
    st.rerun()

def ir_para_usuario(nome):
    st.session_state.update({"pagina_atual": "user_home", "usuario_ativo": nome})
    st.rerun()

def ir_para_disciplina(d):
    st.session_state.update({"pagina_atual": "focus", "disciplina_ativa": d})
    st.rerun()

def voltar_para_usuario():
    st.session_state.update({"pagina_atual": "user_home", "disciplina_ativa": None})
    st.rerun()

# --- APP ---
df, worksheet = carregar_dados()
if df.empty or worksheet is None:
    st.error("Erro de conexão.")
    st.stop()

colunas_validas = [u for u in LISTA_USUARIOS if u in df.columns]

# =========================================================
# DASHBOARD
# =========================================================
if st.session_state["pagina_atual"] == "dashboard":

    st.markdown("""
    <style>
    .avatar-cell {
        position: relative;
        text-align: center;
        margin-bottom: 20px;
        transition: transform 0.3s ease;
    }

    .avatar-cell:hover {
        transform: translateY(-15px) scale(1.05);
    }

    .avatar-img {
        width: 150px;
        height: 150px;
        border-radius: 50%;
        object-fit: cover;
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
    }

    .avatar-name {
        margin-top: 10px;
        font-weight: 800;
        font-size: 18px;
        color: #555;
        transition: all 0.3s ease;
    }

    .avatar-cell:hover .avatar-name {
        color: white !important;
        text-shadow: 0px 0px 8px var(--user-color);
    }

    form {
        position: absolute;
        inset: 0;
        margin: 0;
    }

    form button {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        opacity: 0;
        cursor: pointer;
        z-index: 20;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(
        "<h1 style='text-align:center; color:#2c3e50;'>🩺 MedTracker Copeiros</h1>",
        unsafe_allow_html=True
    )

    st.markdown("### 👤 Quem é você?")

    cols = st.columns(6)

    for i, user in enumerate(LISTA_USUARIOS):
        with cols[i]:
            cor = USUARIOS_CONFIG[user]["color"]
            img = get_image_as_base64(USUARIOS_CONFIG[user]["img"])
            style_var = f"--user-color: {cor};"

            html = f"""
            <div class="avatar-cell" style="{style_var}">
                <img src="{img}" class="avatar-img" style="border:5px solid {cor};">
                <div class="avatar-name">{user}</div>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)

            with st.form(key=f"form_{user}"):
                clicked = st.form_submit_button("")

            if clicked:
                ir_para_usuario(user)

# =========================================================
# PERFIL
# =========================================================
elif st.session_state["pagina_atual"] == "user_home":
    user = st.session_state["usuario_ativo"]
    cor = USUARIOS_CONFIG[user]["color"]
    img = get_image_as_base64(USUARIOS_CONFIG[user]["img"])

    c_back, c_head = st.columns([0.1, 0.9])
    with c_back:
        if st.button("⬅"):
            ir_para_dashboard()
    with c_head:
        img_html = f'<img src="{img}" class="profile-header-img" style="border-color:{cor}">' if img else ""
        st.markdown(
            f"<div style='display:flex;align-items:center'>{img_html}<h1 style='margin:0;color:{cor}'>Olá, {user}!</h1></div>",
            unsafe_allow_html=True
        )

# =========================================================
# MODO FOCO
# =========================================================
elif st.session_state["pagina_atual"] == "focus":
    user = st.session_state["usuario_ativo"]
    disc = st.session_state["disciplina_ativa"]
    cor = USUARIOS_CONFIG[user]["color"]

    if st.button("⬅"):
        voltar_para_usuario()

    st.markdown(f"<h2 style='color:{cor}'>📖 {disc}</h2>", unsafe_allow_html=True)
