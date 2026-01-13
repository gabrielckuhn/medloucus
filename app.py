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

# --- CSS ESTRUTURAL E VISUAL ---
st.markdown("""
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 5rem;}
    
    /* CARDS GERAIS */
    .dashboard-card {
        background-color: white; border-radius: 15px; padding: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05); border: 1px solid #f0f0f0;
        margin-bottom: 20px;
    }
    .card-title {
        color: #555; font-size: 18px; font-weight: 700;
        text-transform: uppercase; letter-spacing: 0.5px;
        margin-bottom: 15px; border-bottom: 2px solid #f0f2f6; padding-bottom: 10px;
    }
    
    /* GRÁFICOS */
    .js-plotly-plot .plotly .modebar { display: none !important; }
    
    /* HEADER PERFIL */
    .profile-header-img {
        width: 80px; height: 80px; border-radius: 50%;
        object-fit: cover; border: 3px solid white;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-right: 15px;
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
        except: time.sleep(1.5)
            
def atualizar_status(worksheet, row_index, col_index_num, novo_valor):
    try: worksheet.update_cell(row_index + 2, col_index_num, novo_valor)
    except: st.error("Erro ao salvar.")

def limpar_booleano(valor):
    if isinstance(valor, bool): return valor
    if isinstance(valor, str): return valor.upper() == 'TRUE'
    return False

# --- Navegação ---
if 'pagina_atual' not in st.session_state: st.session_state.update({'pagina_atual': 'dashboard', 'usuario_ativo': None, 'disciplina_ativa': None})

def ir_para_dashboard(): st.session_state.update({'pagina_atual': 'dashboard', 'usuario_ativo': None}); st.rerun()
def ir_para_usuario(nome): st.session_state.update({'pagina_atual': 'user_home', 'usuario_ativo': nome}); st.rerun()
def ir_para_disciplina(d): st.session_state.update({'pagina_atual': 'focus', 'disciplina_ativa': d}); st.rerun()
def voltar_para_usuario(): st.session_state.update({'pagina_atual': 'user_home', 'disciplina_ativa': None}); st.rerun()

# --- Gráficos ---
def renderizar_ranking(df, colunas_validas):
    data = []
    total = len(df)
    for user in colunas_validas:
        pct = df[user].apply(limpar_booleano).sum() / total * 100
        data.append({"Nome": user, "Progresso": pct, "Cor": USUARIOS_CONFIG[user]["color"], "Label": f"<b>{user}</b>: {pct:.1f}%"})
    df_rank = pd.DataFrame(data).sort_values("Progresso", ascending=True)
    fig = go.Figure(go.Bar(
        x=df_rank["Progresso"], y=df_rank["Nome"], orientation='h', marker=dict(color=df_rank["Cor"]),
        text=df_rank["Label"], textposition='inside', insidetextanchor='middle', textfont=dict(size=14, color='white')
    ))
    fig.update_layout(margin=dict(l=0, r=10, t=0, b=0), height=300, yaxis=dict(showticklabels=False, showgrid=False), xaxis=dict(showgrid=False, showticklabels=False), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    return fig

def renderizar_top_disciplinas(df, colunas_validas):
    df_t = df.copy(); df_t['Total'] = 0
    for u in colunas_validas: df_t['Total'] += df_t[u].apply(limpar_booleano).astype(int)
    agrup = df_t.groupby('Disciplina')['Total'].sum().reset_index().sort_values('Total', ascending=True).tail(8)
    fig = go.Figure(go.Bar(
        x=agrup['Total'], y=agrup['Disciplina'], orientation='h', marker=dict(color=agrup['Total'], colorscale='Teal'),
        text=agrup['Total'], textposition='auto'
    ))
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=300, xaxis=dict(showgrid=False, showticklabels=False), yaxis=dict(showgrid=False, tickfont=dict(size=12)), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    return fig

def renderizar_favoritas(df, colunas_validas):
    data = []
    for user in colunas_validas:
        max_pct = 0; fav_disc = "—"
        temp = df[df['Disciplina'].isin(df['Disciplina'].unique())].copy()
        for disc in temp['Disciplina'].unique():
            df_d = temp[temp['Disciplina'] == disc]
            if len(df_d) > 0:
                pct = df_d[user].apply(limpar_booleano).sum() / len(df_d)
                if pct > max_pct: max_pct = pct; fav_disc = disc
        if max_pct > 0: data.append({"User": user, "Disciplina": fav_disc, "Pct": max_pct * 100, "Cor": USUARIOS_CONFIG[user]["color"]})
    df_fav = pd.DataFrame(data).sort_values("Pct", ascending=True)
    if df_fav.empty: return go.Figure()
    fig = go.Figure(go.Bar(
        x=df_fav["Pct"], y=df_fav["User"], orientation='h', marker=dict(color=df_fav["Cor"]),
        text=df_fav.apply(lambda x: f"<b>{x['User']}</b>: {x['Disciplina']} ({x['Pct']:.0f}%)", axis=1),
        textposition='inside', insidetextanchor='middle', textfont=dict(color='white', size=13)
    ))
    fig.update_layout(margin=dict(l=0, r=10, t=0, b=0), height=300, yaxis=dict(showticklabels=False, showgrid=False), xaxis=dict(showgrid=False, showticklabels=False, range=[0, 105]), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    return fig

# --- APP ---
df, worksheet = carregar_dados()
if df.empty or worksheet is None: st.error("Erro de conexão."); st.stop()
colunas_validas = [u for u in LISTA_USUARIOS if u in df.columns]

# =========================================================
# 1. DASHBOARD
# =========================================================
if st.session_state['pagina_atual'] == 'dashboard':
    
    # CSS AVANÇADO: Resolve o problema do botão visível e alinha a animação
    st.markdown("""
    <style>
    /* 1. Define a coluna como referência de posicionamento */
    div[data-testid="column"] {
        position: relative;
    }

    /* 2. Estilo do Card Visual (Foto + Nome) */
    .avatar-card {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 10px;
        transition: transform 0.3s ease;
        /* Garante que o visual não bloqueie o clique do botão que estará por cima */
        pointer-events: none; 
    }

    /* 3. A Animação de subir (Aplicada ao passar o mouse na coluna inteira) */
    div[data-testid="column"]:hover .avatar-card {
        transform: translateY(-15px) scale(1.05);
    }

    .avatar-img {
        width: 150px; height: 150px;
        border-radius: 50%; object-fit: cover;
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
    }
    
    .avatar-name {
        margin-top: 15px;
        font-weight: 800; font-size: 18px; color: #555; /* Cinza Original */
        transition: color 0.3s ease, text-shadow 0.3s ease;
    }
    
    /* 4. Nome fica Branco Brilhante no Hover */
    div[data-testid="column"]:hover .avatar-name {
        color: white !important;
        /* Sombra na cor do usuário para destacar no fundo branco */
        text-shadow: 0px 0px 8px var(--user-color), 0px 0px 8px var(--user-color); 
    }

    /* 5. O HACK DEFINITIVO DO BOTÃO */
    /* Isso pega o botão do Streamlit dentro da coluna e o estica sobre tudo */
    div[data-testid="column"] .stButton button {
        position: absolute !important;
        top: 0 !important;
        left: 0 !important;
        width: 100% !important;
        height: 100% !important;
        z-index: 99 !important; /* Garante que fique no topo */
        opacity: 0 !important; /* Totalmente invisível */
        cursor: pointer !important;
        display: block !important;
        color: transparent !important; /* Esconde o texto "Entrar Fulano" */
    }
    
    /* Remove espaçamentos extras que o st.button cria */
    div[data-testid="column"] .stButton {
        position: absolute !important;
        top: 0; left: 0; width: 100%; height: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<h1 style='text-align: center; color: #2c3e50;'>🩺 MedTracker Copeiros</h1>", unsafe_allow_html=True)
    
    # KPIs
    total = sum(df[u].apply(limpar_booleano).sum() for u in colunas_validas)
    media = total / len(colunas_validas) if colunas_validas else 0
    k1, k2, k3 = st.columns(3)
    k1.markdown(f"""<div class="dashboard-card" style="text-align:center;"><div class="card-title">Aulas (Total)</div><div style="font-size: 36px; font-weight: 800; color: #3498db;">{total}</div></div>""", unsafe_allow_html=True)
    k2.markdown(f"""<div class="dashboard-card" style="text-align:center;"><div class="card-title">Média/Copeiro</div><div style="font-size: 36px; font-weight: 800; color: #27ae60;">{int(media)}</div></div>""", unsafe_allow_html=True)
    k3.markdown(f"""<div class="dashboard-card" style="text-align:center;"><div class="card-title">Total Aulas</div><div style="font-size: 36px; font-weight: 800; color: #7f8c8d;">{len(df)}</div></div>""", unsafe_allow_html=True)

    # SELEÇÃO DE PERFIL
    st.markdown("### 👤 Quem é você?")
    
    cols = st.columns(6)
    for i, user in enumerate(LISTA_USUARIOS):
        with cols[i]:
            # -- Lógica de Visualização e Botão --
            
            # 1. Configurações
            cor = USUARIOS_CONFIG[user]['color']
            img = get_image_as_base64(USUARIOS_CONFIG[user]['img'])
            style_var = f"--user-color: {cor};" # Passa a cor para o CSS (Hover glow)
            
            # 2. HTML Visual (A imagem e o nome)
            # Nota: pointer-events: none no CSS garante que isso não bloqueie o clique
            html_content = f"""
            <div class="avatar-card" style="{style_var}">
                <img src="{img}" class="avatar-img" style="border: 5px solid {cor};">
                <div class="avatar-name">{user}</div>
            </div>
            """ if img else f"""
            <div class="avatar-card" style="{style_var}">
                <div class="avatar-img" style="border: 5px solid {cor}; background:#eee; display:flex; align-items:center; justify-content:center; font-size:40px;">{user[0]}</div>
                <div class="avatar-name">{user}</div>
            </div>
            """
            st.markdown(html_content, unsafe_allow_html=True)
            
            # 3. O Botão (Interação)
            # Ele vai ficar INVISÍVEL e COBRIR tudo graças ao CSS acima.
            # O label garante que a chave seja única, mas o CSS esconde o texto.
            if st.button(user, key=f"btn_{user}"):
                if user in colunas_validas: ir_para_usuario(user)
                else: st.error("Usuário não encontrado.")

    st.markdown("---")
    
    # Gráficos
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="dashboard-card"><div class="card-title">🏆 Ranking de Progresso</div>', unsafe_allow_html=True)
        st.plotly_chart(renderizar_ranking(df, colunas_validas), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="dashboard-card"><div class="card-title">🔥 Disciplinas Populares</div>', unsafe_allow_html=True)
        st.plotly_chart(renderizar_top_disciplinas(df, colunas_validas), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="dashboard-card"><div class="card-title">❤️ Favorita (Maior %)</div>', unsafe_allow_html=True)
        st.plotly_chart(renderizar_favoritas(df, colunas_validas), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

# =========================================================
# 2. PERFIL
# =========================================================
elif st.session_state['pagina_atual'] == 'user_home':
    user = st.session_state['usuario_ativo']
    cor = USUARIOS_CONFIG[user]['color']
    img = get_image_as_base64(USUARIOS_CONFIG[user]['img'])
    
    c_back, c_head = st.columns([0.1, 0.9])
    with c_back:
        if st.button("⬅", help="Voltar"): ir_para_dashboard()
    with c_head:
        img_html = f'<img src="{img}" class="profile-header-img" style="border-color:{cor}">' if img else ""
        st.markdown(f"""<div style="display: flex; align-items: center;">{img_html}<h1 style="margin: 0; color: {cor};">Olá, {user}!</h1></div>""", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    col = df[user].apply(limpar_booleano)
    pct = col.sum() / len(df) if len(df) > 0 else 0
    st.markdown(f"""<div style="background: white; border-left: 8px solid {cor}; padding: 25px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); margin-bottom: 30px;"><div style="color: #888; font-size: 14px; text-transform: uppercase; font-weight: bold;">Progresso Total</div><div style="display: flex; justify-content: space-between; align-items: baseline;"><div style="font-size: 42px; font-weight: 900; color: {cor};">{int(pct*100)}%</div><div style="font-size: 16px; color: #555;"><strong>{col.sum()}</strong> de {len(df)} aulas</div></div></div>""", unsafe_allow_html=True)
    st.progress(pct)

    st.markdown("### 📚 Suas Disciplinas")
    ordem = ["Cardiologia", "Pneumologia", "Endocrinologia", "Nefrologia", "Gastroenterologia", "Hepatologia", "Infectologia", "Hematologia", "Reumatologia", "Neurologia", "Psiquiatria", "Cirurgia", "Ginecologia", "Obstetrícia", "Pediatria", "Preventiva", "Dermatologia", "Ortopedia", "Otorrinolaringologia", "Oftalmologia"]
    disc_existentes = df['Disciplina'].unique()
    lista = [d for d in ordem if d in disc_existentes] + [d for d in disc_existentes if d not in ordem]
    
    cols = st.columns(2)
    for i, disc in enumerate(lista):
        with cols[i % 2]:
            with st.container(border=True):
                df_d = df[df['Disciplina'] == disc]
                feitos = df_d[user].apply(limpar_booleano).sum(); total_d = len(df_d)
                pct_d = feitos / total_d if total_d > 0 else 0
                c_tit = cor if pct_d > 0 else "#444"
                st.markdown(f"<h4 style='color:{c_tit}; margin-bottom:5px;'>{disc}</h4>", unsafe_allow_html=True)
                st.progress(pct_d)
                c_txt, c_btn = st.columns([0.6, 0.4])
                c_txt.caption(f"{int(pct_d*100)}% ({feitos}/{total_d})")
                if c_btn.button("Abrir ➝", key=f"b_{disc}_{user}"): ir_para_disciplina(disc)

# =========================================================
# 3. MODO FOCO
# =========================================================
elif st.session_state['pagina_atual'] == 'focus':
    user = st.session_state['usuario_ativo']
    disc = st.session_state['disciplina_ativa']
    cor = USUARIOS_CONFIG[user]['color']
    c_btn, c_tit = st.columns([0.1, 0.9])
    with c_btn:
        if st.button("⬅"): voltar_para_usuario()
    with c_tit: st.markdown(f"<h2 style='color: {cor}'>📖 {disc}</h2>", unsafe_allow_html=True)
    
    try: col_idx = df.columns.get_loc(user) + 1
    except: col_idx = 0
    df_d = df[df['Disciplina'] == disc]
    status = df_d[user].apply(limpar_booleano)
    st.info(f"Marcando como **{user}** ({status.sum()}/{len(df_d)} concluídas)")
    
    for idx, row in df_d.iterrows():
        chk = limpar_booleano(row[user])
        c_k, c_t = st.columns([0.05, 0.95])
        with c_k:
            novo = st.checkbox("x", value=chk, key=f"k_{idx}_{user}", label_visibility="collapsed")
        with c_t:
            txt = f"**Semana {row['Semana']}**: {row['Aula']}"
            if chk: st.markdown(f"<span style='color:{cor}; opacity:0.6; text-decoration:line-through'>✅ {txt}</span>", unsafe_allow_html=True)
            else: st.markdown(txt)
        if novo != chk:
            atualizar_status(worksheet, idx, col_idx, novo)
            st.toast("Salvo!"); time.sleep(0.5); st.rerun()
