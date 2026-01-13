import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import time
import plotly.graph_objects as go
import base64

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker - Quem está assistindo?", page_icon="🎬", layout="wide")

# --- Lógica de Roteamento (Query Params) ---
# Isso permite que o clique no HTML (imagem) funcione como um botão do Streamlit
query_params = st.query_params
if "user_login" in query_params:
    user_clicado = query_params["user_login"]
    st.session_state['usuario_ativo'] = user_clicado
    st.session_state['pagina_atual'] = 'user_home'
    # Limpa a URL para não logar novamente ao dar refresh
    st.query_params.clear()
    st.rerun()

# --- Funções Auxiliares ---
def get_image_as_base64(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
        encoded = base64.b64encode(data).decode()
        return f"data:image/png;base64,{encoded}"
    except:
        # Retorna uma imagem transparente ou placeholder se falhar
        return "https://upload.wikimedia.org/wikipedia/commons/c/ca/1x1.png"

# --- CSS NETFLIX STYLE ---
st.markdown("""
    <style>
    /* Fundo Geral estilo Netflix */
    .stApp {
        background-color: #141414;
        color: white;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }
    
    /* Esconder Header/Footer padrão do Streamlit para imersão */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {padding-top: 2rem;}

    /* TÍTULO DA HOME */
    .netflix-title {
        text-align: center;
        font-size: 3.5rem;
        font-weight: 500;
        margin-bottom: 50px;
        color: white;
    }

    /* GRID DE PERFIS */
    .profile-container {
        display: flex;
        justify-content: center;
        align-items: flex-start;
        flex-wrap: wrap;
        gap: 2vw;
        margin-top: 20px;
    }

    /* CARD DO PERFIL (Link) */
    .profile-card {
        text-decoration: none;
        display: flex;
        flex-direction: column;
        align-items: center;
        width: 150px;
        transition: transform 0.2s ease-in-out;
    }
    
    .profile-card:hover {
        transform: scale(1.05); /* Zoom ao passar o mouse */
    }

    /* IMAGEM DO PERFIL */
    .profile-img-box {
        width: 150px;
        height: 150px;
        border-radius: 4px; /* Quadrado arredondado estilo Netflix */
        background-size: cover;
        background-position: center;
        border: 3px solid transparent; /* Borda invisível para não pular layout */
        transition: border 0.2s;
    }

    /* EFEITO DE BORDA BRANCA AO PASSAR MOUSE */
    .profile-card:hover .profile-img-box {
        border: 3px solid white;
    }

    /* NOME DO PERFIL */
    .profile-name {
        margin-top: 15px;
        color: #808080; /* Cinza Netflix */
        font-size: 1.2rem;
        text-align: center;
        transition: color 0.2s;
    }

    .profile-card:hover .profile-name {
        color: white; /* Texto fica branco no hover */
    }

    /* AJUSTES NOS CARDS INTERNOS (DASHBOARD) PARA DARK MODE */
    .dashboard-card {
        background-color: #1f1f1f; 
        border-radius: 8px; 
        padding: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3); 
        border: 1px solid #333;
        margin-bottom: 20px;
    }
    .card-title {
        color: #b3b3b3; 
        font-size: 18px; font-weight: 700;
        text-transform: uppercase; letter-spacing: 0.5px;
        margin-bottom: 15px; border-bottom: 1px solid #333; padding-bottom: 10px;
    }
    
    /* CABEÇALHO PERFIL INTERNO */
    .profile-header-img {
        width: 60px; height: 60px; border-radius: 4px;
        object-fit: cover; margin-right: 15px;
    }
    
    /* TEXTOS GERAIS */
    h1, h2, h3, h4, p, span, div { color: white; }
    .stProgress > div > div > div > div { background-color: #e50914; } /* Barra vermelha Netflix */
    
    </style>
""", unsafe_allow_html=True)

# --- Dados ---
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1-i82jvSfNzG2Ri7fu3vmOFnIYqQYglapbQ7x0000_rc/edit?usp=sharing"

USUARIOS_CONFIG = {
    "Ana Clara": {"color": "#e50914", "img": "ana_clara.png"}, # Vermelho Netflix padrão
    "Arthur":    {"color": "#0071eb", "img": "arthur.png"},
    "Gabriel":   {"color": "#f5c518", "img": "gabriel.png"},
    "Lívian":    {"color": "#46d369", "img": "livian.png"},
    "Newton":    {"color": "#b1060f", "img": "newton.png"},
    "Rafa":      {"color": "#ffffff", "img": "rafa.png"}
}
LISTA_USUARIOS = list(USUARIOS_CONFIG.keys())

# --- Conexão ---
@st.cache_resource
def conectar_google_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        return gspread.authorize(credentials)
    except: 
        return None

def carregar_dados():
    gc = conectar_google_sheets()
    if not gc: 
        return pd.DataFrame(), None
    for tentativa in range(3):
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
        return valor.upper() == 'TRUE'
    return False

# --- Navegação ---
if 'pagina_atual' not in st.session_state: 
    st.session_state.update({'pagina_atual': 'dashboard', 'usuario_ativo': None, 'disciplina_ativa': None})

def ir_para_dashboard(): 
    st.session_state.update({'pagina_atual': 'dashboard', 'usuario_ativo': None})
    st.rerun()

def ir_para_disciplina(d): 
    st.session_state.update({'pagina_atual': 'focus', 'disciplina_ativa': d})
    st.rerun()

def voltar_para_usuario(): 
    st.session_state.update({'pagina_atual': 'user_home', 'disciplina_ativa': None})
    st.rerun()

# --- Gráficos (Adaptados para Dark Mode) ---
def renderizar_ranking(df, colunas_validas):
    data = []
    total = len(df)
    for user in colunas_validas:
        pct = df[user].apply(limpar_booleano).sum() / total * 100
        data.append({
            "Nome": user,
            "Progresso": pct,
            "Cor": USUARIOS_CONFIG[user]["color"],
            "Label": f"<b>{user}</b>: {pct:.1f}%"
        })
    df_rank = pd.DataFrame(data).sort_values("Progresso", ascending=True)
    fig = go.Figure(go.Bar(
        x=df_rank["Progresso"],
        y=df_rank["Nome"],
        orientation='h',
        marker=dict(color=df_rank["Cor"]),
        text=df_rank["Label"],
        textposition='inside',
        insidetextanchor='middle',
        textfont=dict(size=14, color='white')
    ))
    fig.update_layout(
        margin=dict(l=0, r=10, t=0, b=0),
        height=300,
        yaxis=dict(showticklabels=False, showgrid=False),
        xaxis=dict(showgrid=False, showticklabels=False),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )
    return fig

# --- APP ---
df, worksheet = carregar_dados()
if df.empty or worksheet is None:
    st.error("Erro de conexão.")
    st.stop()

colunas_validas = [u for u in LISTA_USUARIOS if u in df.columns]

# =========================================================
# 1. TELA DE LOGIN (ESTILO NETFLIX)
# =========================================================
if st.session_state['pagina_atual'] == 'dashboard':

    st.markdown('<div class="netflix-title">Quem está assistindo?</div>', unsafe_allow_html=True)
    
    # Montar o HTML Grid
    html_content = '<div class="profile-container">'
    
    for user in LISTA_USUARIOS:
        # Pega a imagem em base64
        img_b64 = get_image_as_base64(USUARIOS_CONFIG[user]['img'])
        
        # Cria um link <a> que recarrega a página com parâmetro ?user_login=Nome
        # A lógica no topo do script captura isso.
        html_content += f"""
        <a href="?user_login={user}" target="_self" class="profile-card">
            <div class="profile-img-box" style="background-image: url('{img_b64}');"></div>
            <div class="profile-name">{user}</div>
        </a>
        """
    
    html_content += '</div>'
    
    # Renderiza o HTML interativo
    st.markdown(html_content, unsafe_allow_html=True)

    # Botão discreto para gerenciar perfis (Visual apenas)
    st.markdown("""
        <div style="text-align: center; margin-top: 50px;">
            <a href="#" style="border: 1px solid grey; color: grey; padding: 5px 20px; text-decoration: none; text-transform: uppercase; letter-spacing: 2px; font-size: 0.8rem;">
                Gerenciar Perfis
            </a>
        </div>
    """, unsafe_allow_html=True)

# =========================================================
# 2. PERFIL (DASHBOARD DO USUÁRIO)
# =========================================================
elif st.session_state['pagina_atual'] == 'user_home':
    user = st.session_state['usuario_ativo']
    cor = USUARIOS_CONFIG[user]['color']
    img = get_image_as_base64(USUARIOS_CONFIG[user]['img'])

    # Header
    c_back, c_head = st.columns([0.1, 0.9])
    with c_back:
        if st.button("⬅", help="Voltar para seleção de perfis"):
            ir_para_dashboard()
    with c_head:
        img_html = f'<img src="{img}" class="profile-header-img" style="border: 2px solid {cor}">' if img else ""
        st.markdown(
            f"""<div style="display: flex; align-items: center;">
            {img_html}<h1 style="margin: 0; color: white;">Olá, {user}!</h1>
            </div>""",
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    col = df[user].apply(limpar_booleano)
    pct = col.sum() / len(df) if len(df) > 0 else 0

    # Card Principal (Estatísticas)
    st.markdown(
        f"""<div class="dashboard-card" style="border-left: 5px solid {cor};">
        <div class="card-title">Progresso Total</div>
        <div style="display: flex; justify-content: space-between; align-items: baseline;">
        <div style="font-size: 42px; font-weight: 900; color: {cor};">{int(pct*100)}%</div>
        <div style="font-size: 16px; color: #aaa;">
        <strong>{col.sum()}</strong> de {len(df)} aulas</div>
        </div></div>""",
        unsafe_allow_html=True
    )
    st.progress(pct)

    st.markdown("### 📚 Minha Lista (Disciplinas)")

    cols = st.columns(3) # 3 colunas fica melhor no widescreen
    
    disciplinas = sorted(df['Disciplina'].unique())
    
    for i, disc in enumerate(disciplinas):
        with cols[i % 3]:
            # Container estilizado nativo do Streamlit
            with st.container(border=True):
                df_d = df[df['Disciplina'] == disc]
                feitos = df_d[user].apply(limpar_booleano).sum()
                total_d = len(df_d)
                pct_d = feitos / total_d if total_d > 0 else 0
                
                # Título com cor se tiver progresso
                c_tit = cor if pct_d > 0 else "#666"
                
                st.markdown(f"<div style='color:{c_tit}; font-weight:bold; font-size:18px; margin-bottom:5px;'>{disc}</div>", unsafe_allow_html=True)
                st.progress(pct_d)
                
                c1, c2 = st.columns([1, 1])
                c1.caption(f"{int(pct_d*100)}% ({feitos}/{total_d})")
                
                if c2.button("Assistir", key=f"btn_{disc}"):
                    ir_para_disciplina(disc)

    # Ranking Global (Opcional mostrar aqui ou não)
    st.markdown("---")
    st.markdown("### 🏆 Ranking da Galera")
    st.plotly_chart(renderizar_ranking(df, colunas_validas), use_container_width=True)


# =========================================================
# 3. MODO FOCO (Checklist)
# =========================================================
elif st.session_state['pagina_atual'] == 'focus':
    user = st.session_state['usuario_ativo']
    disc = st.session_state['disciplina_ativa']
    cor = USUARIOS_CONFIG[user]['color']

    c_btn, c_tit = st.columns([0.1, 0.9])
    with c_btn:
        if st.button("⬅ Voltar"):
            voltar_para_usuario()
    with c_tit:
        st.markdown(f"<h2 style='color: {cor}'>📖 {disc}</h2>", unsafe_allow_html=True)

    try:
        col_idx = df.columns.get_loc(user) + 1
    except:
        col_idx = 0

    df_d = df[df['Disciplina'] == disc]
    
    # Tabela visualmente mais limpa
    for idx, row in df_d.iterrows():
        chk = limpar_booleano(row[user])
        
        # Container para cada linha
        with st.container():
            c_k, c_t = st.columns([0.05, 0.95])
            with c_k:
                novo = st.checkbox(
                    "x",
                    value=chk,
                    key=f"k_{idx}_{user}",
                    label_visibility="collapsed"
                )
            with c_t:
                txt = f"**Semana {row['Semana']}**: {row['Aula']}"
                if chk:
                    # Estilo riscado e escuro para completado
                    st.markdown(f"<div style='color:#555; text-decoration:line-through'>✅ {txt}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='color:white;'>{txt}</div>", unsafe_allow_html=True)

            if novo != chk:
                atualizar_status(worksheet, idx, col_idx, novo)
                st.toast(f"Status atualizado para {user}!", icon="💾")
                time.sleep(0.5)
                st.rerun()
        st.markdown("<hr style='margin: 5px 0; border-color: #333;'>", unsafe_allow_html=True)
