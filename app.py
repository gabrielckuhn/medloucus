import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import bcrypt
import re
import time
import base64
from io import BytesIO
from PIL import Image
from streamlit_cropper import st_cropper
from datetime import datetime, timedelta
import plotly.express as px
import numpy as np

# --- Configuração da Página (MedTracker Beta) ---
st.set_page_config(page_title="MedTracker Beta", page_icon="🩺", layout="centered")

# --- Constantes e CSS ---
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1-i82jvSfNzG2Ri7fu3vmOFnIYqQYglapbQ7x0000_rc/edit?usp=sharing"
WORKSHEET_NAME = "novas_aulas" 
COR_PRINCIPAL = "#bf7000" # Laranja padrão (apenas para fallback)

# Mapeamento de Cores por Grande Área
CORES_AREAS = {
    "Clínica Médica": "#ade082", # Verde
    "Ginecologia": "#e082c6",    # Rosa
    "Pediatria": "#f1ee90",      # Amarelo
    "Preventiva": "#90d3f1",     # Azul
    "Cirurgia": "#f1a790"        # Laranja claro
}

# Cores de UI
COR_TEXTO_ATIVO = "white"
COR_TEXTO_INATIVO = "#444444"

# CSS Personalizado
st.markdown(f"""
    <style>
        .stButton>button {{ width: 100%; border-radius: 8px; font-weight: 600; }}
        
        .profile-header-img {{
            width: 120px; height: 120px;
            border-radius: 50%;
            object-fit: cover;
            border: 4px solid {COR_PRINCIPAL};
            box-shadow: 0 4px 10px rgba(0,0,0,0.2);
        }}
        
        .profile-big-img {{
            width: 180px; height: 180px;
            border-radius: 50%;
            object-fit: cover;
            border: 6px solid {COR_PRINCIPAL};
            box-shadow: 0 6px 15px rgba(0,0,0,0.2);
            display: block;
            margin-left: auto;
            margin-right: auto;
        }}
        
        .block-container {{ 
            padding-top: 40px !important; 
        }}

        .text-gradient {{
            background: linear-gradient(to top right, #bf7000, #bf4a00);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800;
        }}
        
        .metric-card {{
            background-color: #f9f9f9;
            border: 1px solid #eee;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        }}
        
        h2, h3 {{ color: #333; }}
        
        .streamlit-expanderHeader {{
            font-weight: bold;
            color: #333;
        }}
    </style>
""", unsafe_allow_html=True)

# --- Conexão Google Sheets ---
@st.cache_resource
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        credentials = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=scopes
        )
        return gspread.authorize(credentials)
    except Exception as e:
        st.error(f"Erro de credenciais: {e}")
        return None

# --- Funções Auxiliares ---

def limpar_booleano(valor):
    return str(valor).upper() == 'TRUE'

def processar_imagem(img_pil):
    img_pil.thumbnail((300, 300))
    buffer = BytesIO()
    img_pil.save(buffer, format="JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def preparar_imagem_para_crop(uploaded_file):
    image = Image.open(uploaded_file)
    largura_base = 400
    w_percent = (largura_base / float(image.size[0]))
    h_size = int((float(image.size[1]) * float(w_percent)))
    return image.resize((largura_base, h_size))

def validar_complexidade_senha(senha):
    if len(senha) < 8: return False, "Mínimo 8 caracteres."
    if not re.search(r"[a-z]", senha): return False, "Falta minúscula."
    if not re.search(r"[A-Z]", senha): return False, "Falta maiúscula."
    if not re.search(r"[0-9]", senha): return False, "Falta número."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", senha): return False, "Falta caractere especial."
    return True, "Senha válida."

def hash_senha(senha):
    return bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verificar_senha(senha_input, senha_hash):
    return bcrypt.checkpw(senha_input.encode('utf-8'), senha_hash.encode('utf-8'))

# --- Funções de Banco de Dados e Lógica ---

def buscar_usuario(username):
    gc = get_gspread_client()
    if not gc: return None
    try:
        sh = gc.open_by_url(PLANILHA_URL)
        worksheet = sh.worksheet("Usuarios")
        records = worksheet.get_all_records()
        for user in records:
            if user['username'] == username:
                return user
    except: pass
    return None

def sincronizar_colunas_usuarios():
    """
    Verifica se todos os usuários cadastrados na aba 'Usuarios' 
    possuem uma coluna correspondente (pelo username) na aba 'novas_aulas'.
    Se não tiver, cria.
    """
    gc = get_gspread_client()
    if not gc: return False
    
    sh = gc.open_by_url(PLANILHA_URL)
    
    try:
        ws_users = sh.worksheet("Usuarios")
        users_records = ws_users.get_all_records()
        lista_usernames = [u['username'] for u in users_records if u['username']]
        
        ws_aulas = sh.worksheet(WORKSHEET_NAME)
        headers_aulas = ws_aulas.row_values(1)
        
        cols_adicionadas = False
        
        for user in lista_usernames:
            if user not in headers_aulas:
                # Adiciona coluna nova
                next_col = len(headers_aulas) + 1
                ws_aulas.update_cell(1, next_col, user)
                headers_aulas.append(user) # Atualiza lista local
                cols_adicionadas = True
                
        return cols_adicionadas
    except Exception as e:
        st.error(f"Erro na sincronização de colunas: {e}")
        return False

def criar_usuario(username, nome_completo, senha, foto_base64=""):
    gc = get_gspread_client()
    sh = gc.open_by_url(PLANILHA_URL)
    try:
        ws_users = sh.worksheet("Usuarios")
    except: return False, "Erro na aba Usuarios"
    
    if ws_users.find(username): return False, "Usuário já existe."
    
    senha_segura = hash_senha(senha)
    ws_users.append_row([username, nome_completo, senha_segura, foto_base64])
    
    # Cria coluna na aba de aulas imediatamente usando o USERNAME
    try:
        ws_dados = sh.worksheet(WORKSHEET_NAME)
        headers = ws_dados.row_values(1)
        if username not in headers:
            ws_dados.update_cell(1, len(headers)+1, username)
    except Exception as e:
        return False, f"Erro ao criar coluna de dados: {e}"
    
    return True, senha_segura

def atualizar_nome_usuario(username, novo_nome):
    # Apenas atualiza o nome de exibição na aba Usuarios
    # A coluna de dados continua sendo o username (imutável)
    gc = get_gspread_client()
    sh = gc.open_by_url(PLANILHA_URL)
    ws_users = sh.worksheet("Usuarios")
    cell = ws_users.find(username)
    ws_users.update_cell(cell.row, 2, novo_nome)
    return True

def atualizar_foto_usuario(username, nova_foto_b64):
    gc = get_gspread_client()
    sh = gc.open_by_url(PLANILHA_URL)
    ws_users = sh.worksheet("Usuarios")
    cell = ws_users.find(username)
    ws_users.update_cell(cell.row, 4, nova_foto_b64)
    return True

def atualizar_senha_usuario(username, nova_senha_hash):
    gc = get_gspread_client()
    sh = gc.open_by_url(PLANILHA_URL)
    ws_users = sh.worksheet("Usuarios")
    cell = ws_users.find(username)
    ws_users.update_cell(cell.row, 3, nova_senha_hash)
    return True

def atualizar_status(worksheet, row_idx, col_idx, novo_valor, username, disciplina, df_completo):
    try:
        worksheet.update_cell(row_idx + 2, col_idx, novo_valor)
        if novo_valor:
            registrar_acesso(worksheet, df_completo, username, disciplina, row_idx)
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

def registrar_acesso(worksheet, df, username, disciplina, row_idx):
    if 'LastSeen' not in df.columns: 
        return
        
    tag = str(username).upper()
    agora = datetime.now().strftime("%d/%m/%Y_%H:%M")
    novo_codigo = f"{tag}_{agora}_{disciplina.upper()}"
    
    try:
        col_idx_last_seen = df.columns.get_loc('LastSeen') + 1
        valor_atual = str(df.iloc[row_idx]['LastSeen']) if not df.empty else ""
        
        logs_existentes = [v for v in valor_atual.split(';') if v and not v.startswith(tag)]
        historico = [novo_codigo] + logs_existentes
        valor_final = ";".join(historico)
        
        worksheet.update_cell(row_idx + 2, col_idx_last_seen, valor_final)
    except Exception as e:
        print(f"Erro log: {e}")

def obter_dados_ultima_interacao(df, username):
    if 'LastSeen' not in df.columns or df.empty: return None, None
    tag = str(username).upper()
    
    ultima_data = None
    ultima_esp = None
    ultima_area = None
    
    for idx, row in df.iterrows():
        val = str(row['LastSeen'])
        if tag in val:
            partes = val.split(';')
            for log in partes:
                if log.startswith(tag):
                    try:
                        dados = log.split('_')
                        if len(dados) >= 4:
                            data_str = f"{dados[1]}_{dados[2]}"
                            data_obj = datetime.strptime(data_str, "%d/%m/%Y_%H:%M")
                            if ultima_data is None or data_obj > ultima_data:
                                ultima_data = data_obj
                                ultima_esp = row['especialidade']
                                ultima_area = row['grande_area']
                    except: continue
                    
    if ultima_esp and ultima_area:
        return ultima_esp, ultima_area
    return None, None

def identificar_colunas_usuarios(df):
    cols_sistema = ['cod_aula', 'grande_area', 'especialidade', 'tema_maior', 'titulo_aula', 'semana_media', 'LastSeen', 'Link', 'ID', 'Material']
    return [c for c in df.columns if c not in cols_sistema and "Unnamed" not in c]

# --- Cálculo de Métricas ---

def calcular_streak(df, username):
    if 'LastSeen' not in df.columns: return 0
    
    tag = str(username).upper()
    datas_estudo = set()
    
    series_logs = df['LastSeen'].astype(str)
    for val in series_logs:
        if tag in val:
            partes = val.split(';')
            for log in partes:
                if log.startswith(tag):
                    try:
                        data_str = log.split('_')[1]
                        datas_estudo.add(datetime.strptime(data_str, "%d/%m/%Y").date())
                    except: continue
    
    if not datas_estudo: return 0
    
    datas_ordenadas = sorted(list(datas_estudo), reverse=True)
    streak = 0
    
    hoje = datetime.now().date()
    ontem = hoje - timedelta(days=1)
    
    if hoje in datas_ordenadas:
        current = hoje
    elif ontem in datas_ordenadas:
        current = ontem
    else:
        return 0 
        
    for d in datas_ordenadas:
        if d == current:
            streak += 1
            current -= timedelta(days=1)
        elif d > current: continue 
        else: break 
        
    return streak

def extrair_horas_gerais(df):
    horas = []
    if 'LastSeen' not in df.columns: return horas
    
    for val in df['LastSeen'].astype(str):
        if not val or val == 'nan': continue
        logs = val.split(';')
        for log in logs:
            try:
                hora_str = log.split('_')[2]
                h = int(hora_str.split(':')[0])
                horas.append(h)
            except: continue
    return horas

# --- Estado e Navegação ---

if 'pagina_atual' not in st.session_state: st.session_state['pagina_atual'] = 'home'
if 'disciplina_ativa' not in st.session_state: st.session_state['disciplina_ativa'] = None
if 'area_ativa' not in st.session_state: st.session_state['area_ativa'] = None 
if 'logado' not in st.session_state: st.session_state['logado'] = False
if 'usuario_atual' not in st.session_state: st.session_state['usuario_atual'] = None

def ir_para_dashboard():
    st.session_state['pagina_atual'] = 'dashboard'
    st.rerun()

def ir_para_home():
    st.session_state['pagina_atual'] = 'home'
    st.rerun()

def ir_para_disciplina(disciplina, area):
    st.session_state['pagina_atual'] = 'focus'
    st.session_state['disciplina_ativa'] = disciplina
    st.session_state['area_ativa'] = area
    st.rerun()
    
def ir_para_perfil():
    st.session_state['pagina_atual'] = 'perfil'
    st.rerun()

def realizar_logout():
    st.session_state['logado'] = False
    st.session_state['usuario_atual'] = None
    st.session_state['pagina_atual'] = 'home'
    st.rerun()

# --- INTERFACE ---

def tela_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            "<h1 style='text-align: center; margin-bottom: -15px; line-height: 1.2;'>"
            "🩺 <span class='text-gradient'>MedTracker</span>"
            "</h1>", 
            unsafe_allow_html=True
        )
        st.markdown("<p style='text-align: center; color: #666; margin-top: 0px;'>Gestor de estudos para medicina</p>", unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["Entrar", "Criar Conta"])
        
        with tab1:
            with st.form("login"):
                u = st.text_input("Usuário")
                p = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar", use_container_width=True):
                    user_db = buscar_usuario(u)
                    if user_db and verificar_senha(p, user_db['senha_hash']):
                        st.session_state['logado'] = True
                        st.session_state['usuario_atual'] = user_db
                        st.session_state['pagina_atual'] = 'home'
                        st.rerun()
                    else: st.error("Erro no login.")
        
        with tab2:
            st.info("Preencha os dados abaixo:")
            nu = st.text_input("Usuário (Login)")
            nn = st.text_input("Nome Completo (Apenas Exibição)")
            np = st.text_input("Senha", type="password")
            cp = st.text_input("Confirmar Senha", type="password")
            
            uploaded = st.file_uploader("Foto de Perfil", type=['jpg','png'])
            foto_b64 = ""
            if uploaded:
                st.write("Ajuste o recorte:")
                img_to_crop = preparar_imagem_para_crop(uploaded)
                c_crop_log, _ = st.columns([0.8, 0.2])
                with c_crop_log:
                    img = st_cropper(img_to_crop, aspect_ratio=(1,1), box_color=COR_PRINCIPAL, key="cropper_signup")
                foto_b64 = processar_imagem(img)
            
            if st.button("Cadastrar", use_container_width=True):
                val, msg = validar_complexidade_senha(np)
                if np != cp: st.error("Senhas não conferem.")
                elif not val: st.error(msg)
                else:
                    status, resultado = criar_usuario(nu, nn, np, foto_b64)
                    if status:
                        st.success("Conta criada! Entrando...")
                        time.sleep(0.3)
                        novo_user_session = {
                            'username': nu, 'nome_completo': nn,
                            'senha_hash': resultado, 'foto': foto_b64
                        }
                        st.session_state['usuario_atual'] = novo_user_session
                        st.session_state['logado'] = True
                        st.session_state['pagina_atual'] = 'home'
                        st.rerun()
                    else: st.error(resultado)

def pagina_inicial():
    # --- AUTO-RECUPERAÇÃO DE COLUNAS ---
    # Se você apagou as colunas no Sheets, isso vai recriar baseada nos usuarios
    sincronizar_colunas_usuarios()

    gc = get_gspread_client()
    if not gc: return
    sh = gc.open_by_url(PLANILHA_URL)
    worksheet = sh.worksheet(WORKSHEET_NAME)
    df = pd.DataFrame(worksheet.get_all_records())
    
    if 'grande_area' in df.columns:
        df['grande_area'] = df['grande_area'].astype(str).str.strip()

    user = st.session_state['usuario_atual']
    username = user['username'] # CHAVE PRINCIPAL AGORA
    nome_exibicao = user['nome_completo']
    primeiro_nome = nome_exibicao.split()[0].title()
    foto_str = user.get('foto', '')
    cor = COR_PRINCIPAL
    
    if username not in df.columns:
        st.warning(f"Coluna do usuário '{username}' não encontrada. Tente recarregar.")
        if st.button("Recarregar"):
            sincronizar_colunas_usuarios()
            st.rerun()
        return

    # --- CABEÇALHO ---
    c_head, c_btn = st.columns([0.7, 0.3])
    with c_head:
        img_html = ""
        if foto_str:
            src = f"data:image/jpeg;base64,{foto_str}"
            img_html = f'<img src="{src}" class="profile-header-img">'
        else:
            img_html = f'<div class="profile-header-img" style="background:#eee; display:flex; align-items:center; justify-content:center; font-size:40px; color:{cor};">👤</div>'

        st.markdown(f'''
            <div style="display: flex; align-items: center; gap: 20px;">
                {img_html}
                <div>
                    <h4 style="margin:0; margin-bottom:-5px; color: #777;">Bem-vindo(a),</h4>
                    <h1 style="margin: 0; color: {cor}; line-height: 1.1;">{primeiro_nome}</h1>
                </div>
            </div>
        ''', unsafe_allow_html=True)
        
    with c_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Ir para o meu cronograma ➝", type="primary"):
            ir_para_dashboard()

    st.markdown("<hr style='margin: 25px 0;'>", unsafe_allow_html=True)

    # --- PROGRESSO GERAL ---
    col = df[username].apply(limpar_booleano) # Usa username
    total_aulas = len(df)
    pct = col.sum() / total_aulas if total_aulas > 0 else 0
    
    st.markdown(f'''
        <div style="background: white; border-left: 8px solid {cor}; padding: 25px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
            <div style="color: #888; font-size: 14px; text-transform: uppercase; font-weight: bold;">Progresso Geral</div>
            <div style="display: flex; justify-content: space-between; align-items: baseline;">
                <div style="font-size: 42px; font-weight: 900; color: {cor};">{int(pct*100)}%</div>
                <div style="font-size: 16px; color: #555;"><strong>{col.sum()}</strong> de {total_aulas} aulas</div>
            </div>
        </div>
    ''', unsafe_allow_html=True)
    st.progress(pct)

    # --- ESPAÇO ---
    st.markdown("<div style='height: 30px'></div>", unsafe_allow_html=True)

    # --- 1. MEU DESEMPENHO ---
    st.markdown("### 🤓 Meu Desempenho")
    st.markdown("<div style='height: 30px'></div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**🕸️ Radar de Especialidades**")
        df_radar = df.groupby("especialidade")[username].apply(lambda x: x.apply(limpar_booleano).sum() / len(x) if len(x)>0 else 0).reset_index()
        df_radar.columns = ['Especialidade', 'Score']
        df_radar = df_radar.sort_values('Score', ascending=False).head(6)
        
        fig = px.line_polar(df_radar, r='Score', theta='Especialidade', line_close=True)
        fig.update_traces(fill='toself', line_color=cor)
        fig.update_layout(height=300, margin=dict(t=20, b=20, l=40, r=40))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("**📅 Velocidade Semanal**")
        df['SemanaInt'] = pd.to_numeric(df['semana_media'], errors='coerce')
        df_sem = df.dropna(subset=['SemanaInt'])
        df_line = df_sem.groupby("SemanaInt")[username].apply(lambda x: x.apply(limpar_booleano).sum() / len(x) if len(x)>0 else 0).reset_index()
        
        fig2 = px.line(df_line, x='SemanaInt', y=username, markers=True)
        fig2.update_traces(line_color=cor, line_width=3)
        fig2.update_layout(
            xaxis_title="Semana", yaxis_title="% Conclusão",
            height=300, margin=dict(t=20, b=20, l=20, r=20),
            yaxis=dict(tickformat=".0%")
        )
        st.plotly_chart(fig2, use_container_width=True)
    
    st.markdown("**🔥 Consistência (Streak)**")
    dias_seguidos = calcular_streak(df, username)
    st.markdown(f"""
        <div class="metric-card">
            <h2 style="margin:0; color:{cor}; font-size: 40px;">{dias_seguidos} Dias</h2>
            <p style="margin:0; color:#666;">Seguidos de estudo</p>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height: 30px'></div>", unsafe_allow_html=True)

    # --- 2. DESEMPENHO GLOBAL ---
    st.markdown("### 🌍 Desempenho Global")
    st.markdown("<div style='height: 30px'></div>", unsafe_allow_html=True)

    cols_usuarios = identificar_colunas_usuarios(df)
    
    scores_globais = {}
    for c in cols_usuarios:
        scores_globais[c] = df[c].apply(limpar_booleano).sum()
    
    ranking_sorted = sorted(scores_globais.items(), key=lambda item: item[1], reverse=True)
    
    codinomes = [
        "Golfinho Dedicado", "Águia Focada", "Leão Destemido", "Coruja Sábia", 
        "Tigre Incansável", "Lobo Estratégico", "Urso Persistente", "Falcão Veloz",
        "Elefante Memorável", "Panda Zen", "Raposa Astuta", "Lince Atento"
    ]
    
    c_glob1, c_glob2 = st.columns(2)
    
    with c_glob1:
        st.markdown("**🏆 Top Alunos (Ranking)**")
        txt_ranking = ""
        for i, (u_col, score) in enumerate(ranking_sorted[:5]):
            nome_exibicao = "Você" if u_col == username else codinomes[i % len(codinomes)]
            medalha = "🥇" if i==0 else "🥈" if i==1 else "🥉" if i==2 else f"{i+1}º"
            peso = "bold" if u_col == username else "normal"
            cor_txt = cor if u_col == username else "#333"
            txt_ranking += f"<div style='margin-bottom:8px; font-weight:{peso}; color:{cor_txt}'>{medalha} {nome_exibicao}: <b>{score}</b> aulas</div>"
        
        st.markdown(f"<div class='metric-card' style='text-align:left;'>{txt_ranking}</div>", unsafe_allow_html=True)

    with c_glob2:
        st.markdown("**👥 Média da Turma**")
        media_turma = int(sum(scores_globais.values()) / len(scores_globais)) if scores_globais else 0
        meu_score = scores_globais.get(username, 0)
        
        delta = meu_score - media_turma
        cor_delta = "green" if delta >= 0 else "red"
        sinal = "+" if delta > 0 else ""
        
        st.markdown(f"""
            <div class="metric-card">
                <div style="font-size: 14px; color:#888;">Você completou</div>
                <div style="font-size: 32px; font-weight:bold; color:{cor};">{meu_score}</div>
                <div style="font-size: 14px; color:#888; margin-top:5px;">Média da turma: <b>{media_turma}</b></div>
                <div style="font-size: 14px; color:{cor_delta}; margin-top:5px;">({sinal}{delta} em relação à média)</div>
            </div>
        """, unsafe_allow_html=True)
        
    st.markdown("<div style='height: 20px'></div>", unsafe_allow_html=True)
    
    st.markdown("**🕒 Horários de Pico**")
    horas_estudo = extrair_horas_gerais(df)
    if horas_estudo:
        counts = pd.Series(horas_estudo).value_counts().sort_index()
        df_hist = pd.DataFrame({'Hora': counts.index, 'Atividade': counts.values})
        fig4 = px.bar(df_hist, x='Hora', y='Atividade')
        fig4.update_traces(marker_color=cor)
        fig4.update_layout(height=250, margin=dict(t=20, b=20, l=20, r=20), xaxis=dict(dtick=2))
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("Sem dados suficientes ainda.")

def pagina_perfil():
    user = st.session_state['usuario_atual']
    cor = COR_PRINCIPAL
    username = user['username']
    
    cb, ct = st.columns([0.15, 0.85])
    with cb:
        if st.button("⬅ Voltar"): ir_para_dashboard()
    with ct:
        st.markdown(f"<h2 style='text-align:center; color:{cor}; margin:0;'>Meu Perfil</h2>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

    foto_str = user.get('foto', '')
    if foto_str:
        src = f"data:image/jpeg;base64,{foto_str}"
        st.markdown(f'<img src="{src}" class="profile-big-img">', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="profile-big-img" style="background:#eee; display:flex; align-items:center; justify-content:center; font-size:80px; color:{cor};">👤</div>', unsafe_allow_html=True)
    
    st.markdown(f"<h3 style='text-align:center; margin-top:15px;'>{user['nome_completo']}</h3>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center; color:#666; margin-top:-10px;'>@{username}</p>", unsafe_allow_html=True)
    st.markdown("---")
    
    with st.expander("📝 Alterar Nome de Exibição"):
        novo_nome = st.text_input("Novo Nome", value=user['nome_completo'])
        if st.button("Salvar Nome"):
            if not novo_nome.strip(): st.error("Nome vazio.")
            else:
                atualizar_nome_usuario(username, novo_nome)
                st.session_state['usuario_atual']['nome_completo'] = novo_nome
                st.success("Atualizado!")
                time.sleep(1)
                st.rerun()

    with st.expander("📷 Alterar Foto"):
        uploaded_new = st.file_uploader("Nova Foto", type=['jpg','png'], key='new_photo')
        if uploaded_new:
            st.write("Ajuste o recorte:")
            img_to_crop = preparar_imagem_para_crop(uploaded_new)
            c_crop, _ = st.columns([0.6, 0.4]) 
            with c_crop:
                img_new = st_cropper(img_to_crop, aspect_ratio=(1,1), box_color='#bf7000', key='cropper_new')
            if st.button("Salvar Foto"):
                nova_b64 = processar_imagem(img_new)
                atualizar_foto_usuario(username, nova_b64)
                st.session_state['usuario_atual']['foto'] = nova_b64
                st.success("Foto atualizada!")
                time.sleep(1)
                st.rerun()

    with st.expander("🔐 Alterar Senha"):
        senha_atual = st.text_input("Senha Atual", type="password")
        nova_senha = st.text_input("Nova Senha", type="password")
        conf_senha = st.text_input("Confirmar Nova Senha", type="password")
        if st.button("Atualizar Senha"):
            if not verificar_senha(senha_atual, user['senha_hash']): st.error("Senha incorreta.")
            elif nova_senha != conf_senha: st.error("Senhas não conferem.")
            else:
                val, msg = validar_complexidade_senha(nova_senha)
                if not val: st.error(msg)
                else:
                    novo_hash = hash_senha(nova_senha)
                    atualizar_senha_usuario(username, novo_hash)
                    st.session_state['usuario_atual']['senha_hash'] = novo_hash
                    st.success("Senha alterada!")
                    time.sleep(1)

def pagina_dashboard():
    # --- AUTO-RECUPERAÇÃO DE COLUNAS ---
    sincronizar_colunas_usuarios()

    gc = get_gspread_client()
    if not gc: return
    sh = gc.open_by_url(PLANILHA_URL)
    worksheet = sh.worksheet(WORKSHEET_NAME)
    df = pd.DataFrame(worksheet.get_all_records())
    
    if 'grande_area' in df.columns:
        df['grande_area'] = df['grande_area'].astype(str).str.strip()
    
    user_data = st.session_state['usuario_atual']
    nome_exibicao = user_data['nome_completo']
    username = user_data['username'] # USAR USERNAME
    
    if username not in df.columns:
        st.info(f"🆕 Criando coluna para o usuário '{username}'... Aguarde.")
        try:
            sincronizar_colunas_usuarios()
            st.success("Sincronizado! Recarregando...")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao sincronizar usuário: {e}")
            return

    primeiro_nome = nome_exibicao.split()[0].title()
    foto_str = user_data.get('foto', '')
    cor = COR_PRINCIPAL
    
    try: col_idx_gs = worksheet.find(username).col
    except: st.error("Erro: Coluna do usuário não encontrada na planilha."); return

    # --- Header Dashboard ---
    c_head, c_logout = st.columns([0.8, 0.2])
    with c_head:
        img_html = ""
        if foto_str:
            src = f"data:image/jpeg;base64,{foto_str}"
            img_html = f'<img src="{src}" class="profile-header-img">'
        else:
            img_html = f'<div class="profile-header-img" style="background:#eee; display:flex; align-items:center; justify-content:center; font-size:40px; color:{cor};">👤</div>'

        st.markdown(f'''
            <div style="display: flex; align-items: center; gap: 20px;">
                {img_html}
                <div>
                    <h4 style="margin:0; color: #777;">Meu Cronograma</h4>
                    <h1 style="margin: 0; color: {cor}; line-height: 1.1;">{primeiro_nome}</h1>
                </div>
            </div>
        ''', unsafe_allow_html=True)
        
    with c_logout:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Sair 🔒"): realizar_logout()
        if st.button("Perfil 👤"): ir_para_perfil()
        if st.button("🏠 Home"): ir_para_home()

    st.markdown("<hr style='margin: 25px 0;'>", unsafe_allow_html=True)
    
    # --- BOTÃO CONTINUAR DE ONDE PAROU ---
    ult_esp, ult_area = obter_dados_ultima_interacao(df, username)
    
    if ult_esp and ult_area:
        match = df[(df['especialidade'] == ult_esp) & (df['grande_area'] == ult_area)]
        if not match.empty:
            st.markdown(f"**📍 Continuar de onde parou:**")
            if st.button(f"🎬 Ir para {ult_esp} ({ult_area})", type="primary"):
                ir_para_disciplina(ult_esp, ult_area)
            st.markdown("<br>", unsafe_allow_html=True)

    col = df[username].apply(limpar_booleano) # Usa username
    total_aulas = len(df)
    pct = col.sum() / total_aulas if total_aulas > 0 else 0
    st.progress(pct)

    # --- Título e Filtro ---
    col_titulo, col_filtro = st.columns([0.6, 0.4])
    
    with col_titulo:
        st.markdown("### 📚 Suas Disciplinas")
    
    lista_grandes_areas = sorted([ga for ga in df['grande_area'].unique() if ga])
    opcoes_filtro = ["Todas"] + lista_grandes_areas
    
    with col_filtro:
        filtro_selecionado = st.selectbox("Filtrar por Área", options=opcoes_filtro, label_visibility="collapsed")

    # --- Lógica de Filtragem e Exibição ---
    if filtro_selecionado != "Todas":
        df_filtrado = df[df['grande_area'] == filtro_selecionado].copy()
    else:
        df_filtrado = df.copy()

    df_cards = df_filtrado.drop_duplicates(subset=['especialidade', 'grande_area'])
    df_cards = df_cards.sort_values(by=['grande_area', 'especialidade'])
    
    lista_cards = list(zip(df_cards['especialidade'], df_cards['grande_area']))
    
    cols = st.columns(2)
    for i, (especialidade, grande_area_card) in enumerate(lista_cards):
        if not especialidade: continue
        
        df_esp = df[(df['especialidade'] == especialidade) & (df['grande_area'] == grande_area_card)]
        
        if df_esp.empty: continue
        
        feitos = df_esp[username].apply(limpar_booleano).sum() # Usa username
        pct_d = feitos / len(df_esp) if len(df_esp) > 0 else 0
        
        cor_area = CORES_AREAS.get(grande_area_card, COR_PRINCIPAL)

        if pct_d > 0:
            style = f"background: {cor_area}; padding: 5px 10px; border-radius: 5px; color: {COR_TEXTO_ATIVO}; text-shadow: 0 0 10px {cor_area}cc;"
        else:
            style = f"background: transparent; padding: 5px 10px; padding-left: 10px; border-left: 5px solid {cor_area}; color: {COR_TEXTO_INATIVO};"

        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(f"<h4 style='{style} margin-bottom:5px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;'>{especialidade}</h4>", unsafe_allow_html=True)
                st.caption(f"{grande_area_card}")
                st.progress(pct_d)
                
                ct, cb = st.columns([0.6, 0.4])
                ct.caption(f"{int(pct_d*100)}% ({feitos}/{len(df_esp)})")
                
                if cb.button("Abrir ➝", key=f"b_{especialidade}_{grande_area_card}"): 
                    ir_para_disciplina(especialidade, grande_area_card)

def pagina_focus():
    gc = get_gspread_client()
    if not gc: return
    sh = gc.open_by_url(PLANILHA_URL)
    worksheet = sh.worksheet(WORKSHEET_NAME)
    
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    
    if 'grande_area' in df.columns:
        df['grande_area'] = df['grande_area'].astype(str).str.strip()

    df['original_row_idx'] = df.index 
    
    user = st.session_state['usuario_atual']
    username = user['username'] # CHAVE PRINCIPAL
    
    try: col_idx_gs = worksheet.find(username).col
    except: return

    especialidade_ativa = st.session_state.get('disciplina_ativa')
    area_ativa = st.session_state.get('area_ativa')

    if area_ativa:
        df_active = df[(df['especialidade'] == especialidade_ativa) & (df['grande_area'] == area_ativa)].copy()
    else:
        df_active = df[df['especialidade'] == especialidade_ativa].copy()
    
    grande_area = area_ativa if area_ativa else (df_active.iloc[0]['grande_area'] if not df_active.empty else "Geral")
    cor_area = CORES_AREAS.get(grande_area.strip(), COR_PRINCIPAL)
    glow = f"color: white; text-shadow: 0 0 12px {cor_area}, 0 0 6px {cor_area}80;"

    # --- INJEÇÃO DE CSS: Cores da Barra de Progresso ---
    st.markdown(f"""
        <style>
        .stProgress > div > div > div > div {{
            background-color: {cor_area} !important;
        }}
        </style>
    """, unsafe_allow_html=True)

    cb, ct = st.columns([0.15, 0.85])
    with cb:
        if st.button("⬅ Voltar"): ir_para_dashboard()
    with ct:
        st.markdown(f"<h2 style='background: {cor_area}; padding: 8px 15px; border-radius: 10px; {glow} text-align:center;'>📖 {especialidade_ativa}</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align:center; color:#666; margin-top:-10px; font-size:12px;'>{grande_area}</p>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    feitos_esp = df_active[username].apply(limpar_booleano).sum() # Usa username
    pct_esp = feitos_esp / len(df_active) if len(df_active) > 0 else 0
    st.progress(pct_esp)
    st.caption(f"Progresso: {int(pct_esp*100)}% concluído")
    st.markdown("---")

    df_active['semana_media'] = pd.to_numeric(df_active['semana_media'], errors='coerce')
    df_active = df_active.sort_values(by=['semana_media', 'cod_aula'])

    temas_ordenados = df_active['tema_maior'].unique()

    for tema in temas_ordenados:
        df_tema = df_active[df_active['tema_maior'] == tema]
        qtd_aulas = len(df_tema)
        
        if qtd_aulas > 1:
            aulas_feitas_tema = df_tema[username].apply(limpar_booleano).sum() # Usa username
            pct_tema = int((aulas_feitas_tema / qtd_aulas) * 100)
            icon_check = "✅" if pct_tema == 100 else ""
            
            with st.expander(f"{tema} ({pct_tema}%) {icon_check}"):
                for idx, row in df_tema.iterrows():
                    chk = limpar_booleano(row[username]) # Usa username
                    original_idx = row['original_row_idx']
                    
                    c_chk, c_txt = st.columns([0.1, 0.9])
                    key = f"chk_{original_idx}_{username}"
                    
                    with c_chk:
                        novo = st.checkbox("x", value=chk, key=key, label_visibility="collapsed")
                    with c_txt:
                        txt_aula = row['titulo_aula']
                        if chk: st.markdown(f"<span style='opacity:0.6; text-decoration:line-through'>{txt_aula}</span>", unsafe_allow_html=True)
                        else: st.markdown(f"{txt_aula}")
                        
                    if novo != chk:
                        atualizar_status(worksheet, original_idx, col_idx_gs, novo, username, especialidade_ativa, df)
                        time.sleep(0.5)
                        st.rerun()
        else:
            row = df_tema.iloc[0]
            chk = limpar_booleano(row[username]) # Usa username
            original_idx = row['original_row_idx']
            
            c_chk, c_txt = st.columns([0.1, 0.9])
            key = f"chk_{original_idx}_{username}"
            
            with c_chk:
                novo = st.checkbox("x", value=chk, key=key, label_visibility="collapsed")
            with c_txt:
                titulo_formatado = f"**{tema}:** {row['titulo_aula']}"
                if chk: 
                    st.markdown(f"<span style='opacity:0.6; text-decoration:line-through'>✅ {titulo_formatado}</span>", unsafe_allow_html=True)
                else: 
                    st.markdown(titulo_formatado)
            
            if novo != chk:
                atualizar_status(worksheet, original_idx, col_idx_gs, novo, username, especialidade_ativa, df)
                time.sleep(0.5)
                st.rerun()

def app_principal():
    if st.session_state['pagina_atual'] == 'home':
        pagina_inicial()
    elif st.session_state['pagina_atual'] == 'dashboard':
        pagina_dashboard()
    elif st.session_state['pagina_atual'] == 'perfil':
        pagina_perfil()
    elif st.session_state['pagina_atual'] == 'focus':
        pagina_focus()

if st.session_state['logado']: app_principal()
else: tela_login()
