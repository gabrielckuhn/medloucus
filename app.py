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
    "Arthur": {"color": "#263149", "img": "arthur.png"},
    "Gabriel": {"color": "#bf7000", "img": "gabriel.png"},
    "Lívian": {"color": "#0b4c00", "img": "livian.png"},
    "Newton": {"color": "#002322", "img": "newton.png"},
    "Rafa": {"color": "#c14121", "img": "rafa.png"}
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
            st.secrets["gcp_service_account"], scopes=scopes
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
            try:
                worksheet = sh.worksheet("Dados")
            except:
                worksheet = sh.get_worksheet(0)
            return pd.DataFrame(worksheet.get_all_records()), worksheet
        except:
            time.sleep(1.5)

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
    .avatar-wrapper {
        position: relative;
        text-align: center;
        margin-bottom: 25px;
    }

    .avatar-img {
        width: 140px;
        height: 140px;
        border-radius: 50%;
        object-fit: cover;
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        display: block;
        margin: 0 auto;
    }

    .avatar-img:hover {
        transform: translateY(-10px) scale(1.08);
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
        z-index: 10;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<h1 style='text-align:center; color:#2c3e50;'>🩺 MedTracker Copeiros</h1>", unsafe_allow_html=True)
    st.markdown("### 👤 Selecione seu Perfil")

    cols = st.columns(6)

    for i, user in enumerate(LISTA_USUARIOS):
        with cols[i]:
            cor = USUARIOS_CONFIG[user]["color"]
            img = get_image_as_base64(USUARIOS_CONFIG[user]["img"])

            st.markdown(f"""
            <div class="avatar-wrapper">
                <img src="{img}" class="avatar-img" style="border:4px solid {cor};">
            </div>
            """, unsafe_allow_html=True)

            with st.form(key=f"form_{user}"):
                clicked = st.form_submit_button("")

            if clicked:
                ir_para_usuario(user)
