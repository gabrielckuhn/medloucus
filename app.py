import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import time
import plotly.express as px
import plotly.graph_objects as go

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker Residência", page_icon="🩺", layout="wide")

# --- CSS Personalizado (Avatars e Dashboard) ---
st.markdown("""
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 5rem;}
    
    /* Estilo dos Cards de Disciplina */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: white;
        border-radius: 12px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: transform 0.2s;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 12px rgba(0,0,0,0.1);
    }
    
    /* Estilo para imagens circulares (Avatars) */
    .avatar-img {
        border-radius: 50%;
        width: 120px;
        height: 120px;
        object-fit: cover;
        margin-bottom: 10px;
        border: 3px solid #f0f2f6;
        transition: transform 0.2s;
    }
    .avatar-container:hover .avatar-img {
        transform: scale(1.05);
        border-color: #ff4b4b;
    }

    /* Botões personalizados */
    div.stButton > button {
        width: 100%; 
        border-radius: 8px; 
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

# --- Configurações e Dados ---
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1-i82jvSfNzG2Ri7fu3vmOFnIYqQYglapbQ7x0000_rc/edit?usp=sharing"

# Mapeamento de Cores e Imagens
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
    try:
        worksheet.update_cell(row_index + 2, col_index_num, novo_valor)
    except:
        time.sleep(1)
        try: worksheet.update_cell(row_index + 2, col_index_num, novo_valor)
        except: st.error("Erro de conexão ao salvar.")

def limpar_booleano(valor):
    if isinstance(valor, bool): return valor
    if isinstance(valor, str): return valor.upper() == 'TRUE'
    return False

# --- Inicialização de Estado (Navegação) ---
if 'pagina_atual' not in st.session_state:
    st.session_state['pagina_atual'] = 'dashboard' # dashboard, user_home, focus
if 'usuario_ativo' not in st.session_state:
    st.session_state['usuario_ativo'] = None
if 'disciplina_ativa' not in st.session_state:
    st.session_state['disciplina_ativa'] = None

# --- Funções de Navegação ---
def ir_para_dashboard():
    st.session_state['pagina_atual'] = 'dashboard'
    st.session_state['usuario_ativo'] = None
    st.session_state['disciplina_ativa'] = None
    st.rerun()

def ir_para_usuario(nome):
    st.session_state['pagina_atual'] = 'user_home'
    st.session_state['usuario_ativo'] = nome
    st.rerun()

def ir_para_disciplina(disciplina):
    st.session_state['pagina_atual'] = 'focus'
    st.session_state['disciplina_ativa'] = disciplina
    st.rerun()

def voltar_para_usuario():
    st.session_state['pagina_atual'] = 'user_home'
    st.session_state['disciplina_ativa'] = None
    st.rerun()

# --- Funções de Gráficos do Dashboard ---
def renderizar_grafico_ranking(df):
    ranking_data = []
    total_linhas = len(df)
    
    for user in LISTA_USUARIOS:
        if user in df.columns:
            pct = df[user].apply(limpar_booleano).sum() / total_linhas * 100
            ranking_data.append({"Nome": user, "Progresso (%)": pct, "Cor": USUARIOS_CONFIG[user]["color"]})
    
    df_rank = pd.DataFrame(ranking_data).sort_values("Progresso (%)", ascending=True)
    
    fig = px.bar(
        df_rank, 
        x="Progresso (%)", 
        y="Nome", 
        orientation='h', 
        text_auto='.1f',
        color="Nome",
        color_discrete_map={row["Nome"]: row["Cor"] for _, row in df_rank.iterrows()}
    )
    fig.update_layout(showlegend=False, margin=dict(l=0, r=0, t=30, b=0), height=300)
    fig.update_traces(textfont_size=14, textangle=0, textposition="outside", cliponaxis=False)
    return fig

def get_disciplina_mais_estudada(df, user):
    if user not in df.columns: return "N/A", 0
    df_temp = df.copy()
    df_temp['Check'] = df_temp[user].apply(limpar_booleano)
    agrupado = df_temp.groupby('Disciplina')['Check'].sum().reset_index()
    top = agrupado.sort_values('Check', ascending=False).iloc[0]
    return top['Disciplina'], top['Check']

def renderizar_heatmap_disciplinas(df):
    # Soma de checks de TODOS os usuários por disciplina
    df_temp = df.copy()
    df_temp['Total_Views'] = 0
    for user in LISTA_USUARIOS:
        if user in df_temp.columns:
            df_temp['Total_Views'] += df_temp[user].apply(limpar_booleano).astype(int)
            
    agrupado = df_temp.groupby('Disciplina')['Total_Views'].sum().reset_index().sort_values('Total_Views', ascending=False).head(10)
    
    fig = px.bar(
        agrupado, 
        x='Disciplina', 
        y='Total_Views',
        color='Total_Views',
        color_continuous_scale='Bluered',
        title="Top 10 Disciplinas Mais Estudadas (Grupo)"
    )
    fig.update_layout(height=350)
    return fig

# --- APP PRINCIPAL ---

df, worksheet = carregar_dados()

if df.empty or worksheet is None:
    st.error("Erro ao conectar. Tente recarregar.")
    st.stop()

# Verificar colunas
colunas_validas = [u for u in LISTA_USUARIOS if u in df.columns]

# --- 1. DASHBOARD GERAL ---
if st.session_state['pagina_atual'] == 'dashboard':
    st.title("📊 MedTracker Dashboard")
    st.markdown("Bem-vindo ao painel de controle da residência.")
    st.markdown("---")

    # SELEÇÃO DE USUÁRIO (AVATARS)
    st.subheader("Quem é você?")
    colunas_avatar = st.columns(len(LISTA_USUARIOS))
    
    for i, user in enumerate(LISTA_USUARIOS):
        with colunas_avatar[i]:
            # Tenta carregar a imagem, se falhar usa um emoji
            try:
                st.image(USUARIOS_CONFIG[user]["img"], use_container_width=True)
            except:
                st.markdown(f"👤 **{user}**") # Fallback se imagem não existir
            
            # Botão com a cor do usuário
            cor_btn = USUARIOS_CONFIG[user]['color']
            if st.button(f"Entrar", key=f"login_{user}"):
                if user in colunas_validas:
                    ir_para_usuario(user)
                else:
                    st.error("Usuário não encontrado na planilha.")

    st.markdown("---")
    
    # ESTATÍSTICAS
    c1, c2 = st.columns([0.4, 0.6])
    
    with c1:
        st.subheader("🏆 Ranking Geral")
        st.plotly_chart(renderizar_grafico_ranking(df), use_container_width=True)
        
    with c2:
        st.subheader("📚 Disciplinas Populares")
        st.plotly_chart(renderizar_heatmap_disciplinas(df), use_container_width=True)

    st.markdown("---")
    st.subheader("🧠 Foco de Cada Aluno (Disciplina Favorita)")
    
    cols_stats = st.columns(len(colunas_validas))
    for i, user in enumerate(colunas_validas):
        disc_top, qtd = get_disciplina_mais_estudada(df, user)
        with cols_stats[i]:
            st.markdown(f"<div style='border-top: 4px solid {USUARIOS_CONFIG[user]['color']}; padding-top: 5px;'><strong>{user}</strong></div>", unsafe_allow_html=True)
            st.caption(f"{disc_top}")
            st.markdown(f"**{qtd}** aulas")

# --- 2. ÁREA DO USUÁRIO (HOME) ---
elif st.session_state['pagina_atual'] == 'user_home':
    user = st.session_state['usuario_ativo']
    
    # Header com botão de voltar
    c_back, c_title = st.columns([0.15, 0.85])
    with c_back:
        if st.button("⬅ Dashboard"): ir_para_dashboard()
    with c_title:
        st.title(f"Olá, {user}!")

    # Progresso Pessoal
    coluna_user = df[user].apply(limpar_booleano)
    pct_total = coluna_user.sum() / len(df) if len(df) > 0 else 0
    
    st.markdown(
        f"""
        <div style="background-color: {USUARIOS_CONFIG[user]['color']}20; padding: 15px; border-radius: 10px; border-left: 5px solid {USUARIOS_CONFIG[user]['color']}">
        <h3 style="margin:0; color: {USUARIOS_CONFIG[user]['color']}">Progresso Total: {int(pct_total*100)}%</h3>
        </div>
        <br>
        """, unsafe_allow_html=True
    )
    st.progress(pct_total)

    # Grid de Disciplinas
    ordem = [
        "Cardiologia", "Pneumologia", "Endocrinologia", "Nefrologia", "Gastroenterologia", 
        "Hepatologia", "Infectologia", "Hematologia", "Reumatologia", "Neurologia", 
        "Psiquiatria", "Cirurgia", "Ginecologia", "Obstetrícia", "Pediatria", 
        "Preventiva", "Dermatologia", "Ortopedia", "Otorrinolaringologia", "Oftalmologia"
    ]
    disc_existentes = df['Disciplina'].unique()
    lista_final = [d for d in ordem if d in disc_existentes] + [d for d in disc_existentes if d not in ordem]
    
    cols = st.columns(2)
    for i, disciplina in enumerate(lista_final):
        col_atual = cols[i % 2]
        df_d = df[df['Disciplina'] == disciplina]
        feitos_d = df_d[user].apply(limpar_booleano).sum()
        total_d = len(df_d)
        pct_d = feitos_d / total_d if total_d > 0 else 0
        
        with col_atual:
            with st.container(border=True):
                # Título Colorido se concluído
                cor_titulo = USUARIOS_CONFIG[user]['color'] if pct_d > 0 else "black"
                st.markdown(f"### <span style='color:{cor_titulo}'>{disciplina}</span>", unsafe_allow_html=True)
                
                st.progress(pct_d)
                c1, c2 = st.columns([0.7, 0.3])
                c1.caption(f"**{int(pct_d*100)}%** — {feitos_d}/{total_d} aulas")
                
                if c2.button("Abrir ➝", key=f"btn_{disciplina}_{user}"):
                    ir_para_disciplina(disciplina)

# --- 3. MODO FOCO (DISCIPLINA) ---
elif st.session_state['pagina_atual'] == 'focus':
    user = st.session_state['usuario_ativo']
    disciplina = st.session_state['disciplina_ativa']
    
    c_back, c_title = st.columns([0.2, 0.8])
    with c_back:
        if st.button(f"⬅ Voltar"): voltar_para_usuario()
    with c_title:
        st.markdown(f"## 📖 {disciplina}")

    # Índice da coluna para salvar
    try: col_idx = df.columns.get_loc(user) + 1
    except: col_idx = 0

    df_disc = df[df['Disciplina'] == disciplina]
    status = df_disc[user].apply(limpar_booleano)
    feitos = status.sum()
    total = len(df_disc)
    pct = feitos / total if total > 0 else 0
    
    st.progress(pct)
    st.caption(f"**{user}**, você viu {feitos} de {total} aulas.")
    st.markdown("---")
    
    for idx, row in df_disc.iterrows():
        checked = limpar_booleano(row[user])
        
        c_chk, c_txt = st.columns([0.05, 0.95])
        with c_chk:
            key = f"chk_{idx}_{user}"
            # Checkbox com cor personalizada via CSS hack ou padrão
            novo = st.checkbox("Marcar", value=checked, key=key, label_visibility="collapsed")
            
        with c_txt:
            txt = f"**Semana {row['Semana']}**: {row['Aula']}"
            if checked:
                st.markdown(f"<span style='color:{USUARIOS_CONFIG[user]['color']}; opacity:0.7; text-decoration:line-through'>✅ {txt}</span>", unsafe_allow_html=True)
            else:
                st.markdown(txt)
        
        if novo != checked:
            atualizar_status(worksheet, idx, col_idx, novo)
            st.toast("Status atualizado!", icon="💾")
            time.sleep(0.5)
            st.rerun()
