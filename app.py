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

def ordenar_disciplinas(disciplinas_todas, ultima_clicada):
    """Ordena alfabeticamente e move a última clicada para o topo."""
    lista_ordenada = sorted([str(d) for d in disciplinas_todas])
    if ultima_clicada in lista_ordenada:
        lista_ordenada.insert(0, lista_ordenada.pop(lista_ordenada.index(ultima_clicada)))
    return lista_ordenada

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker Copeiros", page_icon="🩺", layout="wide")

# --- LÓGICA DE PERSISTÊNCIA E NAVEGAÇÃO ---
if 'pagina_atual' not in st.session_state: 
    st.session_state.update({'pagina_atual': 'dashboard', 'usuario_ativo': None, 'disciplina_ativa': None})

# Captura parâmetros da URL para manter a disciplina no topo mesmo após F5
params = st.query_params
if "user_login" in params and st.session_state['usuario_ativo'] is None:
    st.session_state['usuario_ativo'] = params["user_login"]
    st.session_state['pagina_atual'] = 'user_home'
    if "last_disc" in params:
        st.session_state['disciplina_ativa'] = params["last_disc"]

# --- CSS ESTRUTURAL ---
st.markdown("""
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 5rem;}
    .main-wrapper { margin-top: 30px; }
    .main-title {
        text-align: center; color: white; font-size: 3rem; font-weight: 800;
        transition: all 0.4s ease; cursor: default; margin-bottom: 20px;
    }
    .main-title:hover {
        transform: scale(1.05);
        text-shadow: 0 0 20px rgba(255, 255, 255, 0.6);
    }
    .dashboard-card {
        background-color: white; border-radius: 15px; padding: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05); border: 1px solid #f0f0f0;
        margin-bottom: 10px;
    }
    .card-title {
        color: #555; font-size: 18px; font-weight: 700;
        text-transform: uppercase; letter-spacing: 0.5px;
        margin-bottom: 15px; border-bottom: 2px solid #f0f2f6; padding-bottom: 10px;
    }
    .footer-signature {
        position: fixed; bottom: 10px; right: 20px;
        color: rgba(255, 255, 255, 0.4); font-size: 0.8rem; z-index: 100;
    }
    .profile-container-wrapper { margin-top: 50px; }
    .profile-header-img {
        width: 80px; height: 80px; border-radius: 50%;
        object-fit: cover; border: 3px solid white;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-right: 15px;
    }
    .netflix-link { text-decoration: none !important; display: block; }
    .netflix-card { text-align: center; transition: transform 0.3s ease; cursor: pointer; }
    .netflix-card:hover { transform: scale(1.08); }
    .netflix-img {
        width: 100%; aspect-ratio: 1/1; border-radius: 4px;
        object-fit: cover; border: 3px solid transparent; transition: border 0.3s ease;
    }
    .netflix-card:hover .netflix-img { border: 3px solid white; }
    .netflix-name {
        margin-top: 10px; color: #808080; font-size: 1.2rem;
        transition: color 0.3s ease; text-decoration: none !important;
    }
    .netflix-card:hover .netflix-name { color: white; }
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
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        return gspread.authorize(credentials)
    except: return None

def carregar_dados():
    gc = conectar_google_sheets()
    if not gc: return pd.DataFrame(), None
    sh = gc.open_by_url(PLANILHA_URL)
    try: worksheet = sh.worksheet("Dados")
    except: worksheet = sh.get_worksheet(0)
    return pd.DataFrame(worksheet.get_all_records()), worksheet

def limpar_booleano(valor):
    if isinstance(valor, bool): return valor
    if isinstance(valor, str): return valor.upper() == 'TRUE'
    return False

def atualizar_status(worksheet, row_index, col_index_num, novo_valor):
    try: worksheet.update_cell(row_index + 2, col_index_num, novo_valor)
    except: st.error("Erro ao salvar.")

# --- Navegação ---
def ir_para_dashboard(): 
    st.query_params.clear()
    st.session_state.update({'pagina_atual': 'dashboard', 'usuario_ativo': None, 'disciplina_ativa': None})
    st.rerun()

def ir_para_disciplina(d): 
    st.query_params.update({"user_login": st.session_state['usuario_ativo'], "last_disc": d})
    st.session_state.update({'pagina_atual': 'focus', 'disciplina_ativa': d})
    st.rerun()

def voltar_para_usuario(): 
    st.session_state.update({'pagina_atual': 'user_home'})
    st.rerun()

# --- Gráficos ---
def renderizar_ranking(df, colunas_validas):
    data = []
    total = len(df)
    for user in colunas_validas:
        pct = df[user].apply(limpar_booleano).sum() / total * 100
        data.append({"Nome": user, "Progresso": pct, "Cor": USUARIOS_CONFIG[user]["color"], "Label": f"<b>{user}</b>: {pct:.1f}%"})
    df_rank = pd.DataFrame(data).sort_values("Progresso", ascending=True)
    fig = go.Figure(go.Bar(x=df_rank["Progresso"], y=df_rank["Nome"], orientation='h', marker=dict(color=df_rank["Cor"]), text=df_rank["Label"], textposition='inside', insidetextanchor='middle', textfont=dict(size=14, color='white')))
    fig.update_layout(margin=dict(l=0, r=10, t=0, b=0), height=300, yaxis=dict(showticklabels=False, showgrid=False), xaxis=dict(showgrid=False, showticklabels=False), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    return fig

# --- Execução Principal ---
df, worksheet = carregar_dados()
if df.empty or worksheet is None: st.error("Erro de conexão."); st.stop()
colunas_validas = [u for u in LISTA_USUARIOS if u in df.columns]

# =========================================================
# 1. DASHBOARD
# =========================================================
if st.session_state['pagina_atual'] == 'dashboard':
    st.markdown('<div class="main-wrapper">', unsafe_allow_html=True)
    st.markdown('<div class="main-title">🩺 MedTracker Copeiros</div>', unsafe_allow_html=True)
    
    k1, k2, k3 = st.columns(3)
    total_aulas = sum(df[u].apply(limpar_booleano).sum() for u in colunas_validas)
    k1.markdown(f'<div class="dashboard-card"><div class="card-title">Aulas (Total)</div><div style="font-size:36px; font-weight:800; color:#3498db;">{total_aulas}</div></div>', unsafe_allow_html=True)
    k2.markdown(f'<div class="dashboard-card"><div class="card-title">Média/Copeiro</div><div style="font-size:36px; font-weight:800; color:#27ae60;">{int(total_aulas/len(colunas_validas))}</div></div>', unsafe_allow_html=True)
    k3.markdown(f'<div class="dashboard-card"><div class="card-title">Total Base</div><div style="font-size:36px; font-weight:800; color:#7f8c8d;">{len(df)}</div></div>', unsafe_allow_html=True)

    st.markdown("<h2 style='text-align:center; color:#555;'>Escolha seu perfil</h2>", unsafe_allow_html=True)
    cols = st.columns(6)
    for i, user in enumerate(LISTA_USUARIOS):
        with cols[i]:
            img_b64 = get_image_as_base64(USUARIOS_CONFIG[user]['img'])
            if img_b64:
                card_html = f'<a href="?user_login={user}" target="_self" class="netflix-link"><div class="netflix-card"><img src="{img_b64}" class="netflix-img"><div class="netflix-name">{user}</div></div></a>'
            else:
                card_html = f'<a href="?user_login={user}" target="_self" class="netflix-link"><div class="netflix-card"><div class="netflix-img" style="background:{USUARIOS_CONFIG[user]["color"]}; display:flex; align-items:center; justify-content:center; color:white; font-size:40px;">{user[0]}</div><div class="netflix-name">{user}</div></div></a>'
            st.markdown(card_html, unsafe_allow_html=True)

    st.plotly_chart(renderizar_ranking(df, colunas_validas), use_container_width=True)
    st.markdown('<div class="footer-signature">Criado por Gabriel Kuhn®</div>', unsafe_allow_html=True)

# =========================================================
# 2. PERFIL (Alfabético + Última no Topo Permanente)
# =========================================================
elif st.session_state['pagina_atual'] == 'user_home':
    user = st.session_state['usuario_ativo']
    cor = USUARIOS_CONFIG[user]['color']
    img = get_image_as_base64(USUARIOS_CONFIG[user]['img'])
    
    c_back, c_head = st.columns([0.1, 0.9])
    with c_back:
        if st.button("⬅"): ir_para_dashboard()
    with c_head:
        img_html = f'<img src="{img}" class="profile-header-img" style="border-color:{cor}">' if img else ""
        st.markdown(f'<div style="display:flex; align-items:center;">{img_html}<h1 style="color:{cor}; margin:0;">Olá, {user}!</h1></div>', unsafe_allow_html=True)

    col_user = df[user].apply(limpar_booleano)
    pct = col_user.sum() / len(df) if len(df) > 0 else 0
    st.progress(pct)
    
    st.markdown("### 📚 Suas Disciplinas")
    
    # ORDENAÇÃO
    disc_existentes = df['Disciplina'].unique()
    ultima_disc = st.session_state.get('disciplina_ativa')
    lista_organizada = ordenar_disciplinas(disc_existentes, ultima_disc)
    
    cols = st.columns(2)
    for i, disc in enumerate(lista_organizada):
        with cols[i % 2]:
            with st.container(border=True):
                df_d = df[df['Disciplina'] == disc]
                feitos = df_d[user].apply(limpar_booleano).sum()
                total_d = len(df_d)
                pct_d = feitos / total_d if total_d > 0 else 0
                
                label_pino = " 📍" if disc == ultima_disc else ""
                st.markdown(f"**{disc}{label_pino}**")
                st.progress(pct_d)
                c_txt, c_btn = st.columns([0.7, 0.3])
                c_txt.caption(f"{int(pct_d*100)}% ({feitos}/{total_d})")
                if c_btn.button("Abrir", key=f"btn_{disc}"): 
                    ir_para_disciplina(disc)

# =========================================================
# 3. MODO FOCO (Aulas)
# =========================================================
elif st.session_state['pagina_atual'] == 'focus':
    user = st.session_state['usuario_ativo']
    disc = st.session_state['disciplina_ativa']
    cor = USUARIOS_CONFIG[user]['color']
    
    if st.button("⬅ Voltar"): voltar_para_usuario()
    st.markdown(f"<h2 style='color:{cor}'>📖 {disc}</h2>", unsafe_allow_html=True)
    
    col_idx = df.columns.get_loc(user) + 1
    df_d = df[df['Disciplina'] == disc]
    
    for idx, row in df_d.iterrows():
        chk = limpar_booleano(row[user])
        c_k, c_t = st.columns([0.1, 0.9])
        with c_k:
            novo = st.checkbox(" ", value=chk, key=f"foc_{idx}")
        with c_t:
            if chk: st.markdown(f"~~Semana {row['Semana']}: {row['Aula']}~~")
            else: st.markdown(f"**Semana {row['Semana']}**: {row['Aula']}")
        
        if novo != chk:
            atualizar_status(worksheet, idx, col_idx, novo)
            st.toast("Progresso Salvo!")
            time.sleep(0.4)
            st.rerun()
