import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import time
import plotly.graph_objects as go
import base64
import os

# =========================================================
# CONFIGURAÇÃO INICIAL
# =========================================================
st.set_page_config(
    page_title="MedTracker Copeiros",
    page_icon="🩺",
    layout="wide"
)

# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================
def get_image_as_base64(path):
    try:
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            data = f.read()
        return f"data:image/png;base64,{base64.b64encode(data).decode()}"
    except:
        return None


def limpar_booleano(valor):
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        return valor.upper() == "TRUE"
    return False


# =========================================================
# USUÁRIOS (ID SEGURO + NOME REAL)
# =========================================================
USUARIOS_CONFIG = {
    "ana": {
        "nome": "Ana Clara",
        "color": "#400043",
        "img": "ana_clara.png",
    },
    "arthur": {
        "nome": "Arthur",
        "color": "#263149",
        "img": "arthur.png",
    },
    "gabriel": {
        "nome": "Gabriel",
        "color": "#bf7000",
        "img": "gabriel.png",
    },
    "livian": {
        "nome": "Lívian",
        "color": "#0b4c00",
        "img": "livian.png",
    },
    "newton": {
        "nome": "Newton",
        "color": "#002322",
        "img": "newton.png",
    },
    "rafa": {
        "nome": "Rafa",
        "color": "#c14121",
        "img": "rafa.png",
    },
}

LISTA_USUARIOS = list(USUARIOS_CONFIG.keys())

# =========================================================
# LOGIN VIA QUERY PARAM (ROBUSTO)
# =========================================================
if "user_login" in st.query_params:
    user_id = st.query_params["user_login"]
    if user_id in USUARIOS_CONFIG:
        st.session_state.update(
            {
                "pagina_atual": "user_home",
                "usuario_ativo": user_id,
                "disciplina_ativa": None,
            }
        )
    st.query_params.clear()
    st.rerun()

# =========================================================
# ESTADO INICIAL
# =========================================================
if "pagina_atual" not in st.session_state:
    st.session_state.update(
        {
            "pagina_atual": "dashboard",
            "usuario_ativo": None,
            "disciplina_ativa": None,
        }
    )

# =========================================================
# CONEXÃO GOOGLE SHEETS
# =========================================================
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1-i82jvSfNzG2Ri7fu3vmOFnIYqQYglapbQ7x0000_rc/edit?usp=sharing"


@st.cache_resource
def conectar_google_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes
    )
    return gspread.authorize(credentials)


def carregar_dados():
    gc = conectar_google_sheets()
    sh = gc.open_by_url(PLANILHA_URL)
    try:
        ws = sh.worksheet("Dados")
    except:
        ws = sh.get_worksheet(0)
    return pd.DataFrame(ws.get_all_records()), ws


def atualizar_status(ws, row_idx, col_idx, valor):
    ws.update_cell(row_idx + 2, col_idx, valor)


# =========================================================
# CSS GLOBAL
# =========================================================
st.markdown(
    """
<style>
.block-container { padding-top: 2rem; padding-bottom: 4rem; }

.netflix-container {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 2vw;
    padding: 40px 0;
    background-color: #141414;
    border-radius: 12px;
}

.netflix-profile-link {
    text-decoration: none;
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 110px;
    cursor: pointer;
    transition: transform .3s;
}

.netflix-profile-link:hover {
    transform: scale(1.1);
}

.netflix-avatar {
    width: 100px;
    height: 100px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 40px;
    font-weight: bold;
    color: white;
    object-fit: cover;
    border: 2px solid transparent;
}

.netflix-profile-link:hover .netflix-avatar {
    border-color: white;
}

.netflix-name {
    margin-top: 10px;
    color: #808080;
    font-size: 14px;
    text-align: center;
}

.netflix-profile-link:hover .netflix-name {
    color: white;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================================================
# DADOS
# =========================================================
df, worksheet = carregar_dados()
colunas_validas = [
    USUARIOS_CONFIG[u]["nome"] for u in LISTA_USUARIOS if USUARIOS_CONFIG[u]["nome"] in df.columns
]

# =========================================================
# DASHBOARD
# =========================================================
if st.session_state["pagina_atual"] == "dashboard":

    st.markdown(
        "<h1 style='text-align:center'>🩺 MedTracker Copeiros</h1>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<h3 style='text-align:center'>Quem está assistindo?</h3>",
        unsafe_allow_html=True,
    )

    html = '<div class="netflix-container">'

    for user_id in LISTA_USUARIOS:
        cfg = USUARIOS_CONFIG[user_id]
        img = get_image_as_base64(cfg["img"])

        if img:
            avatar = f'<img src="{img}" class="netflix-avatar">'
        else:
            avatar = f'<div class="netflix-avatar" style="background:{cfg["color"]}">{cfg["nome"][0]}</div>'

        html += f"""
        <a href="?user_login={user_id}" target="_self" class="netflix-profile-link">
            {avatar}
            <div class="netflix-name">{cfg["nome"]}</div>
        </a>
        """

    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

# =========================================================
# PERFIL DO USUÁRIO
# =========================================================
elif st.session_state["pagina_atual"] == "user_home":

    user_id = st.session_state["usuario_ativo"]
    cfg = USUARIOS_CONFIG[user_id]
    nome = cfg["nome"]
    cor = cfg["color"]

    if st.button("⬅ Voltar"):
        st.session_state["pagina_atual"] = "dashboard"
        st.rerun()

    st.markdown(
        f"<h1 style='color:{cor}'>Olá, {nome}!</h1>",
        unsafe_allow_html=True,
    )

    col = df[nome].apply(limpar_booleano)
    pct = col.sum() / len(df)

    st.progress(pct)
    st.write(f"**{int(pct*100)}%** de progresso geral")

# =========================================================
# OBSERVAÇÃO FINAL
# =========================================================
# • IDs seguros para navegação
# • Nomes com acento apenas para exibição
# • Nenhuma quebra de HTML
# • Query params 100% confiáveis
