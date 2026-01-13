import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import time
import plotly.express as px
import plotly.graph_objects as go
import base64
import os

# --- Funções Auxiliares (Imagens) ---
def get_image_as_base64(path):
    """Lê uma imagem local e converte para string Base64 para embutir no HTML"""
    try:
        with open(path, "rb") as f:
            data = f.read()
        encoded = base64.b64encode(data).decode()
        # Assume que são PNGs baseado na sua descrição
        return f"data:image/png;base64,{encoded}"
    except Exception as e:
        # Se não achar a imagem, retorna None
        return None

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker Copeiros", page_icon="🩺", layout="wide")

# --- CSS PRO (Visual Refinado) ---
st.markdown("""
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 5rem;}
    
    /* CARDS */
    .dashboard-card {
        background-color: white;
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        border: 1px solid #f0f0f0;
        margin-bottom: 20px;
    }
    .card-title {
        color: #555; font-size: 14px; font-weight: 600;
        text-transform: uppercase; letter-spacing: 1px; margin-bottom: 15px;
    }
    
    /* AVATARS (Tamanho aumentado para 150px) */
    .avatar-container {
        display: flex; flex-direction: column; align-items: center;
        justify-content: center; padding: 10px; transition: transform 0.2s;
    }
    .avatar-container:hover { transform: translateY(-5px); }
    
    .avatar-img {
        border-radius: 50%;
        width: 150px;  /* AUMENTADO DE 100px PARA 150px */
        height: 150px; /* AUMENTADO DE 100px PARA 150px */
        object-fit: cover;
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        margin-bottom: 15px;
    }
    
    /* Placeholder caso a imagem falhe */
    .avatar-placeholder {
        width: 150px; height: 150px; border-radius: 50%;
        background-color: #eee; color: #888;
        display: flex; align-items: center; justify-content: center;
        font-size: 36px; font-weight: bold; margin-bottom: 15px;
        box-shadow: inset 0 0 10px rgba(0,0,0,0.1);
    }

    .avatar-name {
        font-weight: bold; font-size: 18px; margin-bottom: 5px; color: #333;
    }
    
    /* Botões */
    div.stButton > button {
        width: 100%; border-radius: 8px; font-weight: 600;
        border: none; box-shadow: 0 2px 4px rgba(0,0,0,0.1); transition: all 0.2s;
    }
    div.stButton > button:hover { box-shadow: 0 4px 8px rgba(0,0,0,0.2); }

    /* Plotly Clean */
    .js-plotly-plot .plotly .modebar { display: none !important; }
    </style>
""", unsafe_allow_html=True)

# --- Dados e Configurações ---
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

# --- Conexão Google Sheets ---
@st.cache_resource
def conectar_google_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        return gspread.authorize(credentials)
    except: return None

def carregar_dados():
    gc = conectar_google_sheets()
    if not gc: return pd.DataFrame(), None
    for tentativa in range(3):
        try:
            sh = gc.open_by_url(PLANILHA_URL)
            try: worksheet = sh.worksheet("Dados")
            except: worksheet = sh.get_worksheet(0)
            return pd.DataFrame(worksheet.get_all_records()), worksheet
        except Exception as e:
            time.sleep(1.5)
            if tentativa == 2: return pd.DataFrame(), None

def atualizar_status(worksheet, row_index, col_index_num, novo_valor):
    try: worksheet.update_cell(row_index + 2, col_index_num, novo_valor)
    except:
        time.sleep(1)
        try: worksheet.update_cell(row_index + 2, col_index_num, novo_valor)
        except: st.error("Erro de conexão ao salvar.")

def limpar_booleano(valor):
    if isinstance(valor, bool): return valor
    if isinstance(valor, str): return valor.upper() == 'TRUE'
    return False

# --- Navegação e Estado ---
if 'pagina_atual' not in st.session_state: st.session_state['pagina_atual'] = 'dashboard'
if 'usuario_ativo' not in st.session_state: st.session_state['usuario_ativo'] = None
if 'disciplina_ativa' not in st.session_state: st.session_state['disciplina_ativa'] = None

def ir_para_dashboard():
    st.session_state.update({'pagina_atual': 'dashboard', 'usuario_ativo': None, 'disciplina_ativa
