import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import time
import plotly.graph_objects as go
import base64
import os

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker - Quem está assistindo?", page_icon="🎬", layout="wide")

# =========================================================
# 0. LÓGICA DE LOGIN VIA URL (O "Pulo do Gato")
# =========================================================
# Verifica se o link HTML enviou um parametro na URL (ex: ?user_login=Gabriel)
if "user_login" in st.query_params:
    usuario_clicado = st.query_params["user_login"]
    # Define o usuário e a página
    st.session_state['usuario_ativo'] = usuario_clicado
    st.session_state['pagina_atual'] = 'user_home'
    # Limpa a URL para não ficar "presa" no login
    st.query_params.clear()

# Inicializa variaveis de sessão se não existirem
if 'pagina_atual' not in st.session_state: 
    st.session_state.update({'pagina_atual': 'dashboard', 'usuario_ativo': None, 'disciplina_ativa': None})

# =========================================================
# FUNÇÕES E DADOS
# =========================================================

# --- CSS GLOBAL (ESTILO NETFLIX) ---
st.markdown("""
    <style>
    /* Fundo Geral Escuro estilo Netflix */
    .stApp {
        background-color: #141414;
        color: white;
    }
    
    .block-container {padding-top: 2rem; padding-bottom: 5rem;}

    /* Título "Quem está assistindo?" */
    .netflix-title {
        text-align: center;
        color: white;
        font-size: 3.5vw;
        font-weight: 500;
        margin-bottom: 30px;
        margin-top: 50px;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }

    /* Container dos Perfis */
    .profile-container {
        display: flex;
        justify-content: center;
        flex-wrap: wrap;
        gap: 2vw;
        max-width: 1200px;
        margin: 0 auto;
    }

    /* O Card do Perfil (Link) */
    .profile-card {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-decoration: none !important; /* Remove sublinhado padrão */
        group: profile; /* Agrupador para hover */
        width: 10vw;
        min-width: 100px;
        max-width: 200px;
        transition: transform 0.2s;
    }
    
    .profile-card:hover {
        transform: scale(1.05); /* Leve zoom no card todo */
    }

    /* A Imagem do Perfil */
    .profile-img-box {
        width: 100%;
        aspect-ratio: 1 / 1; /* Garante que seja quadrado */
        background-size: cover;
        background-position: center;
        border-radius: 4px; /* Borda levemente arredondada (Netflix style) */
        border: 3px solid transparent; /* Borda invisível para não pular no hover */
        margin-bottom: 10px;
        transition: border 0.2s ease-in-out;
        background-color: #333; /* Cor de fundo se imagem falhar */
    }

    /* Efeito Hover na Imagem */
    .profile-card:hover .profile-img-box {
        border: 3px solid white;
    }

    /* O Nome do Perfil */
    .profile-name {
        color: grey;
        font-size: 1.3vw;
        text-align: center;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        transition: color 0.2s;
        font-weight: 400;
    }
    
    /* Efeito Hover no Nome */
    .profile-card:hover .profile-name {
        color: white;
        font-weight: 700;
    }

    /* Ajuste para mobile */
    @media (max-width: 768px) {
        .netflix-title { font-size: 30px; }
        .profile-card { width: 40vw; margin-bottom: 20px;}
        .profile-name { font-size: 16px; }
    }
    
    /* Esconde elementos padrão do Streamlit para imersão */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
    </style>
""", unsafe_allow_html=True)

# --- Dados e Imagens ---
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

# --- Função de Imagem ---
def get_image_as_base64(filename):
    pasta_script = os.path.dirname(os.path.abspath(__file__))
    caminho = os.path.join(pasta_script, filename)
    try:
        with open(caminho, "rb") as f:
            data = f.read()
        encoded = base64.b64encode(data).decode()
        return f"data:image/png;base64,{encoded}"
    except:
        # Retorna uma imagem de fallback (rosto cinza genérico) se não achar
        return "https://upload.wikimedia.org/wikipedia/commons/0/0b/Netflix-avatar.png"

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
    try:
        sh = gc.open_by_url(PLANILHA_URL)
        worksheet = sh.get_worksheet(0)
        return pd.DataFrame(worksheet.get_all_records()), worksheet
    except: return pd.DataFrame(), None

def atualizar_status(worksheet, row_index, col_index_num, novo_valor):
    try: worksheet.update_cell(row_index + 2, col_index_num, novo_valor)
    except: st.error("Erro ao salvar.")

def limpar_booleano(valor):
    if isinstance(valor, bool): return valor
    if isinstance(valor, str): return valor.upper() == 'TRUE'
    return False

# --- Navegação Interna ---
def ir_para_dashboard(): st.session_state.update({'pagina_atual': 'dashboard', 'usuario_ativo': None}); st.rerun()
def ir_para_disciplina(d): st.session_state.update({'pagina_atual': 'focus', 'disciplina_ativa': d}); st.rerun()
def voltar_para_usuario(): st.session_state.update({'pagina_atual': 'user_home', 'disciplina_ativa': None}); st.rerun()

# =========================================================
# APP MAIN
# =========================================================

df, worksheet = carregar_dados()
if df.empty: st.warning("Conectando à base de dados...") # Evita erro crash na primeira carga

# ---------------------------------------------------------
# 1. TELA "QUEM ESTÁ ASSISTINDO?" (Estilo Netflix)
# ---------------------------------------------------------
if st.session_state['pagina_atual'] == 'dashboard':
    
    # Título Estilizado
    st.markdown('<div class="netflix-title">Quem está assistindo?</div>', unsafe_allow_html=True)
    
    # Montagem da Grid HTML
    html_content = '<div class="profile-container">'
    
    for user in LISTA_USUARIOS:
        img_b64 = get_image_as_base64(USUARIOS_CONFIG[user]['img'])
        
        # Link HTML com parametro GET. 
        # O target="_self" garante que abra na mesma aba.
        # A lógica no topo do script captura o ?user_login=...
        html_content += f"""
        <a href="?user_login={user}" target="_self" class="profile-card">
            <div class="profile-img-box" style="background-image: url('{img_b64}');"></div>
            <div class="profile-name">{user}</div>
        </a>
        """
    
    html_content += '</div>'
    
    # Renderiza
    st.markdown(html_content, unsafe_allow_html=True)

    # Botão "Gerenciar Perfis" (Visual apenas por enquanto)
    st.markdown("""
        <div style="text-align: center; margin-top: 60px;">
            <span style="border: 1px solid grey; color: grey; padding: 8px 25px; cursor: pointer; text-transform: uppercase; letter-spacing: 2px; font-size: 0.8rem; font-family: sans-serif;">
                Gerenciar Perfis
            </span>
        </div>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. PERFIL DO USUÁRIO (Visual Limpo)
# ---------------------------------------------------------
elif st.session_state['pagina_atual'] == 'user_home':
    user = st.session_state['usuario_ativo']
    cor = USUARIOS_CONFIG[user]['color']
    
    # Botão Voltar Customizado
    if st.button("⬅ Sair / Trocar Perfil"):
        ir_para_dashboard()

    st.markdown(f"<h1 style='color: white;'>Olá, <span style='color:{cor}'>{user}</span>.</h1>", unsafe_allow_html=True)
    
    if not df.empty:
        col = df[user].apply(limpar_booleano)
        pct = col.sum() / len(df)
        
        # Barra de progresso customizada
        st.markdown(f"""
        <div style="background-color: #333; border-radius: 10px; padding: 20px; margin-bottom: 20px;">
            <div style="color: #999; margin-bottom: 5px;">Progresso Geral</div>
            <div style="font-size: 24px; font-weight: bold; color: white;">{int(pct*100)}% Concluído</div>
            <div style="width: 100%; background-color: #555; height: 10px; border-radius: 5px; margin-top: 10px;">
                <div style="width: {pct*100}%; background-color: {cor}; height: 10px; border-radius: 5px;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Grid de Disciplinas
        st.markdown("### 🍿 Continue Estudando")
        
        disciplinas = df['Disciplina'].unique()
        cols = st.columns(3)
        
        for i, disc in enumerate(disciplinas):
            with cols[i % 3]:
                df_d = df[df['Disciplina'] == disc]
                feitos = df_d[user].apply(limpar_booleano).sum()
                total = len(df_d)
                pct_d = feitos/total if total > 0 else 0
                
                # Card de Disciplina Escuro
                with st.container(border=True):
                    st.markdown(f"**{disc}**")
                    st.progress(pct_d)
                    st.caption(f"{feitos}/{total} aulas")
                    if st.button("Assistir", key=f"btn_{disc}"):
                        ir_para_disciplina(disc)

# ---------------------------------------------------------
# 3. MODO FOCO (Checklist)
# ---------------------------------------------------------
elif st.session_state['pagina_atual'] == 'focus':
    user = st.session_state['usuario_ativo']
    disc = st.session_state['disciplina_ativa']
    cor = USUARIOS_CONFIG[user]['color']

    c1, c2 = st.columns([0.1, 0.9])
    with c1:
        if st.button("⬅"): voltar_para_usuario()
    with c2:
        st.markdown(f"## 📺 {disc}")
    
    if not df.empty:
        try: col_idx = df.columns.get_loc(user) + 1
        except: col_idx = 0
        df_d = df[df['Disciplina'] == disc]
        
        # Estilização da tabela de checkbox para fundo escuro
        st.markdown("""
        <style>
            .stCheckbox label { color: white !important; }
            p { color: #e0e0e0; }
        </style>
        """, unsafe_allow_html=True)

        for idx, row in df_d.iterrows():
            chk = limpar_booleano(row[user])
            c_check, c_text = st.columns([0.05, 0.95])
            
            with c_check:
                novo = st.checkbox("x", value=chk, key=f"k_{idx}", label_visibility="collapsed")
            
            with c_text:
                txt_style = f"color: {cor}; opacity: 0.5; text-decoration: line-through;" if chk else "color: white;"
                st.markdown(f"<div style='{txt_style} padding-top: 5px;'>S{row['Semana']} - {row['Aula']}</div>", unsafe_allow_html=True)
            
            if novo != chk:
                atualizar_status(worksheet, idx, col_idx, novo)
                st.rerun()
