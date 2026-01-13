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
st.set_page_config(page_title="MedTracker Residência", page_icon="🩺", layout="wide")

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
    st.session_state.update({'pagina_atual': 'dashboard', 'usuario_ativo': None, 'disciplina_ativa': None})
    st.rerun()

def ir_para_usuario(nome):
    st.session_state.update({'pagina_atual': 'user_home', 'usuario_ativo': nome})
    st.rerun()

def ir_para_disciplina(disciplina):
    st.session_state.update({'pagina_atual': 'focus', 'disciplina_ativa': disciplina})
    st.rerun()

def voltar_para_usuario():
    st.session_state.update({'pagina_atual': 'user_home', 'disciplina_ativa': None})
    st.rerun()

# --- Visualização de Gráficos Otimizada ---
def renderizar_ranking_clean(df, colunas_validas):
    ranking_data = []
    total_linhas = len(df)
    for user in colunas_validas:
        pct = df[user].apply(limpar_booleano).sum() / total_linhas * 100
        ranking_data.append({"Nome": user, "Progresso": pct, "Cor": USUARIOS_CONFIG[user]["color"]})
    
    df_rank = pd.DataFrame(ranking_data).sort_values("Progresso", ascending=True)
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_rank["Progresso"], y=df_rank["Nome"], orientation='h',
        marker=dict(color=df_rank["Cor"], opacity=0.9, showscale=False),
        text=df_rank["Progresso"].apply(lambda x: f"{x:.0f}%"), # Removi decimal para limpar
        textposition='outside', textfont=dict(size=14, color='#333'),
        hovertemplate='%{y}: %{x:.1f}%<extra></extra>'
    ))
    fig.update_layout(
        margin=dict(l=0, r=35, t=0, b=0), height=300,
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False, tickfont=dict(size=14, family="Arial Black")),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
    )
    return fig

def renderizar_top_disciplinas(df, colunas_validas):
    df_temp = df.copy()
    df_temp['Total_Views'] = 0
    for user in colunas_validas:
        df_temp['Total_Views'] += df_temp[user].apply(limpar_booleano).astype(int)
            
    agrupado = df_temp.groupby('Disciplina')['Total_Views'].sum().reset_index()
    agrupado = agrupado.sort_values('Total_Views', ascending=True).tail(8)
    
    fig = go.Figure(go.Bar(
        x=agrupado['Total_Views'], y=agrupado['Disciplina'], orientation='h',
        marker=dict(color=agrupado['Total_Views'], colorscale='Blues'),
        text=agrupado['Total_Views'], textposition='auto',
    ))
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0), height=300,
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False, tickfont=dict(size=12)),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
    )
    return fig

# --- APP PRINCIPAL ---

df, worksheet = carregar_dados()

if df.empty or worksheet is None:
    st.error("Erro ao conectar. Tente recarregar.")
    st.stop()

colunas_validas = [u for u in LISTA_USUARIOS if u in df.columns]

# ==========================================================
# 1. DASHBOARD GERAL
# ==========================================================
if st.session_state['pagina_atual'] == 'dashboard':
    
    total_aulas = len(df) * len(colunas_validas)
    aulas_assistidas_total = 0
    for u in colunas_validas:
        aulas_assistidas_total += df[u].apply(limpar_booleano).sum()
    
    st.markdown("<h1 style='text-align: center; color: #2c3e50; margin-bottom: 0px;'>🩺 MedTracker Residência</h1>", unsafe_allow_html=True)
    
    # KPIs
    k1, k2, k3 = st.columns(3)
    k1.markdown(f"""<div class="dashboard-card" style="text-align:center;"><div class="card-title">Aulas Assistidas (Grupo)</div><div style="font-size: 32px; font-weight: bold; color: #3498db;">{aulas_assistidas_total}</div></div>""", unsafe_allow_html=True)
    media = aulas_assistidas_total / len(colunas_validas) if colunas_validas else 0
    k2.markdown(f"""<div class="dashboard-card" style="text-align:center;"><div class="card-title">Média por Aluno</div><div style="font-size: 32px; font-weight: bold; color: #27ae60;">{int(media)}</div></div>""", unsafe_allow_html=True)
    k3.markdown(f"""<div class="dashboard-card" style="text-align:center;"><div class="card-title">Total de Aulas</div><div style="font-size: 32px; font-weight: bold; color: #7f8c8d;">{len(df)}</div></div>""", unsafe_allow_html=True)

    # SELEÇÃO DE PERFIL (AVATARS CORRIGIDOS)
    st.markdown("### 👤 Selecione seu Perfil")
    
    cols_avatar = st.columns(6)
    for i, user in enumerate(LISTA_USUARIOS):
        with cols_avatar[i]:
            cor = USUARIOS_CONFIG[user]['color']
            img_filename = USUARIOS_CONFIG[user]['img']
            
            # --- CORREÇÃO: Lê a imagem e converte para Base64 ---
            img_base64 = get_image_as_base64(img_filename)
            
            if img_base64:
                # Se a imagem existe e foi lida com sucesso
                st.markdown(f"""
                <div class="avatar-container">
                    <img src="{img_base64}" class="avatar-img" style="border: 5px solid {cor};">
                    <div class="avatar-name">{user}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                # Placeholder visual caso a imagem não seja encontrada
                st.markdown(f"""
                <div class="avatar-container">
                    <div class="avatar-placeholder" style="border: 5px solid {cor};">{user[0]}</div>
                    <div class="avatar-name">{user}</div>
                </div>
                """, unsafe_allow_html=True)
            
            if st.button("Acessar", key=f"btn_login_{user}"):
                if user in colunas_validas: ir_para_usuario(user)
                else: st.toast(f"Usuário {user} não encontrado na planilha!", icon="⚠️")

    st.markdown("---")

    # Gráficos
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="dashboard-card"><div class="card-title">🏆 Ranking de Progresso</div>', unsafe_allow_html=True)
        st.plotly_chart(renderizar_ranking_clean(df, colunas_validas), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="dashboard-card"><div class="card-title">🔥 Disciplinas Mais Populares (Top 8)</div>', unsafe_allow_html=True)
        st.plotly_chart(renderizar_top_disciplinas(df, colunas_validas), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

# ==========================================================
# 2. ÁREA DO USUÁRIO
# ==========================================================
elif st.session_state['pagina_atual'] == 'user_home':
    user = st.session_state['usuario_ativo']
    cor_user = USUARIOS_CONFIG[user]['color']
    
    c_back, c_info = st.columns([0.1, 0.9])
    with c_back:
        if st.button("🏠", help="Voltar ao Dashboard"): ir_para_dashboard()
    with c_info:
        st.markdown(f"<h2 style='margin:0; color:{cor_user}'>Olá, {user}!</h2>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    coluna_user = df[user].apply(limpar_booleano)
    pct_total = coluna_user.sum() / len(df) if len(df) > 0 else 0
    
    st.markdown(f"""
    <div style="background-color: white; border-left: 6px solid {cor_user}; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 25px;">
        <span style="font-size: 18px; color: #777;">Progresso Total da Residência</span>
        <div style="display: flex; justify-content: space-between; align-items: flex-end;">
            <span style="font-size: 36px; font-weight: bold; color: {cor_user};">{int(pct_total*100)}%</span>
            <span style="font-size: 14px; color: #999;">{coluna_user.sum()} de {len(df)} aulas</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.progress(pct_total)
    
    st.markdown("### Suas Disciplinas")
    ordem = ["Cardiologia", "Pneumologia", "Endocrinologia", "Nefrologia", "Gastroenterologia", "Hepatologia", "Infectologia", "Hematologia", "Reumatologia", "Neurologia", "Psiquiatria", "Cirurgia", "Ginecologia", "Obstetrícia", "Pediatria", "Preventiva", "Dermatologia", "Ortopedia", "Otorrinolaringologia", "Oftalmologia"]
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
                cor_titulo = cor_user if pct_d > 0 else "#333"
                st.markdown(f"<h4 style='margin-bottom:0; color:{cor_titulo}'>{disciplina}</h4>", unsafe_allow_html=True)
                st.progress(pct_d)
                c_meta, c_act = st.columns([0.6, 0.4])
                c_meta.caption(f"{int(pct_d*100)}% ({feitos_d}/{total_d})")
                if c_act.button("Abrir ➝", key=f"btn_{disciplina}_{user}"):
                    ir_para_disciplina(disciplina)

# ==========================================================
# 3. MODO FOCO
# ==========================================================
elif st.session_state['pagina_atual'] == 'focus':
    user = st.session_state['usuario_ativo']
    disciplina = st.session_state['disciplina_ativa']
    cor_user = USUARIOS_CONFIG[user]['color']
    
    c_btn, c_tit = st.columns([0.15, 0.85])
    with c_btn:
        if st.button("⬅ Voltar"): voltar_para_usuario()
    with c_tit:
        st.markdown(f"<h2 style='color: {cor_user}'>📖 {disciplina}</h2>", unsafe_allow_html=True)

    try: col_idx = df.columns.get_loc(user) + 1
    except: col_idx = 0

    df_disc = df[df['Disciplina'] == disciplina]
    status = df_disc[user].apply(limpar_booleano)
    
    st.info(f"Visualizando como **{user}** • {status.sum()} / {len(df_disc)} aulas concluídas")
    
    for idx, row in df_disc.iterrows():
        checked = limpar_booleano(row[user])
        c_chk, c_txt = st.columns([0.05, 0.95])
        with c_chk:
            key = f"chk_{idx}_{user}"
            novo = st.checkbox("Marcar", value=checked, key=key, label_visibility="collapsed")
        with c_txt:
            txt = f"**Semana {row['Semana']}**: {row['Aula']}"
            if checked:
                st.markdown(f"<span style='color:{cor_user}; opacity:0.6; text-decoration:line-through'>✅ {txt}</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"<span style='color: #333;'>{txt}</span>", unsafe_allow_html=True)
        
        if novo != checked:
            atualizar_status(worksheet, idx, col_idx, novo)
            st.toast("Salvo com sucesso!", icon="✨")
            time.sleep(0.5)
            st.rerun()
