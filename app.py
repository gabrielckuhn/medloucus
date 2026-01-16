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
from datetime import datetime

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker Pro", page_icon="🩺", layout="centered")

# --- Constantes e CSS ---
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1-i82jvSfNzG2Ri7fu3vmOFnIYqQYglapbQ7x0000_rc/edit?usp=sharing"
COR_PRINCIPAL = "#bf7000" 

# CSS Personalizado
st.markdown(f"""
    <style>
        .stButton>button {{ width: 100%; }}
        
        .profile-header-img {{
            width: 120px; height: 120px;
            border-radius: 50%;
            object-fit: cover;
            border: 4px solid {COR_PRINCIPAL};
            box-shadow: 0 4px 10px rgba(0,0,0,0.2);
        }}
        
        /* Foto Grande na página de perfil */
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
        
        /* Margem superior de 40px em todas as páginas */
        .block-container {{ 
            padding-top: 40px !important; 
        }}

        .text-gradient {{
            background: linear-gradient(to top right, #bf7000, #bf4a00);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800;
        }}
        
        /* Estilo para a barra de progresso dentro do Expander */
        .stProgress > div > div > div > div {{
            background-color: {COR_PRINCIPAL};
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
    # Garante que a imagem final salva seja leve (300x300)
    img_pil.thumbnail((300, 300))
    buffer = BytesIO()
    img_pil.save(buffer, format="JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

# FUNÇÃO REMOVIDA: preparar_imagem_para_crop (não é mais necessária)

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

# --- Funções de Banco de Dados (Leitura) ---

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

def criar_usuario(username, nome_completo, senha, foto_base64=""):
    gc = get_gspread_client()
    sh = gc.open_by_url(PLANILHA_URL)
    try:
        ws_users = sh.worksheet("Usuarios")
    except: return False, "Erro na aba Usuarios"
    
    if ws_users.find(username): return False, "Usuário já existe."
    
    senha_segura = hash_senha(senha)
    ws_users.append_row([username, nome_completo, senha_segura, foto_base64])
    
    try:
        ws_dados = sh.worksheet("Dados")
        headers = ws_dados.row_values(1)
        if nome_completo not in headers:
            ws_dados.update_cell(1, len(headers)+1, nome_completo)
    except: pass
    
    return True, senha_segura

# --- Funções de Atualização de Perfil (Escrita) ---

def atualizar_nome_usuario(username, nome_antigo, novo_nome):
    gc = get_gspread_client()
    sh = gc.open_by_url(PLANILHA_URL)
    ws_users = sh.worksheet("Usuarios")
    
    cell = ws_users.find(username)
    ws_users.update_cell(cell.row, 2, novo_nome) 
    
    try:
        ws_dados = sh.worksheet("Dados")
        cell_header = ws_dados.find(nome_antigo)
        ws_dados.update_cell(cell_header.row, cell_header.col, novo_nome)
    except:
        pass 
        
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
            registrar_acesso(worksheet, df_completo, username, disciplina)
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

# --- Funções de Histórico ---

def registrar_acesso(worksheet, df, username, disciplina):
    if 'LastSeen' not in df.columns: return
    tag = str(username).upper()
    agora = datetime.now().strftime("%d/%m/%Y_%H:%M")
    novo_codigo = f"{tag}_{agora}_{disciplina.upper()}"
    col_idx = df.columns.get_loc('LastSeen') + 1
    valor_atual = str(df.iloc[0]['LastSeen']) if not df.empty else ""
    logs_existentes = [v for v in valor_atual.split(';') if v and not v.startswith(tag)]
    historico = [novo_codigo] + logs_existentes
    valor_final = ";".join(historico[:50])
    try: worksheet.update_cell(2, col_idx, valor_final)
    except: pass

def obter_ultima_disciplina(df, username):
    if 'LastSeen' not in df.columns or df.empty: return None
    tag = str(username).upper()
    logs = str(df.iloc[0]['LastSeen']).split(';')
    for log in logs:
        if log.startswith(tag):
            partes = log.split('_')
            if len(partes) >= 4: return partes[3].title().replace("Otorrinolaringologia", "Otorrino")
    return None

# --- Estado e Navegação ---

if 'pagina_atual' not in st.session_state: st.session_state['pagina_atual'] = 'dashboard'
if 'disciplina_ativa' not in st.session_state: st.session_state['disciplina_ativa'] = None
if 'logado' not in st.session_state: st.session_state['logado'] = False
if 'usuario_atual' not in st.session_state: st.session_state['usuario_atual'] = None

def ir_para_dashboard():
    st.session_state['pagina_atual'] = 'dashboard'
    st.rerun()

def ir_para_disciplina(disciplina):
    st.session_state['pagina_atual'] = 'focus'
    st.session_state['disciplina_ativa'] = disciplina
    st.rerun()
    
def ir_para_perfil():
    st.session_state['pagina_atual'] = 'perfil'
    st.rerun()

def realizar_logout():
    st.session_state['logado'] = False
    st.session_state['usuario_atual'] = None
    st.session_state['pagina_atual'] = 'dashboard'
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
                        st.rerun()
                    else: st.error("Erro no login.")
        
        with tab2:
            st.info("Preencha os dados abaixo:")
            nu = st.text_input("Usuário (Login)")
            nn = st.text_input("Nome Completo (Coluna da Planilha)")
            np = st.text_input("Senha", type="password")
            cp = st.text_input("Confirmar Senha", type="password")
            
            uploaded = st.file_uploader("Foto de Perfil", type=['jpg','png'])
            foto_b64 = ""
            if uploaded:
                st.write("Ajuste o recorte:")
                
                # CORREÇÃO: Usar colunas para restringir largura e should_resize_image nativo
                c_crop_log, _ = st.columns([0.8, 0.2])
                with c_crop_log:
                    img = st_cropper(
                        Image.open(uploaded), # Passa a imagem original direto
                        aspect_ratio=(1,1), 
                        box_color='#bf7000',
                        should_resize_image=True, # Deixa a lib lidar com o tamanho
                        key="cropper_signup"
                    )
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
                            'username': nu,
                            'nome_completo': nn,
                            'senha_hash': resultado, 
                            'foto': foto_b64
                        }
                        st.session_state['usuario_atual'] = novo_user_session
                        st.session_state['logado'] = True
                        st.rerun()
                    else: st.error(resultado)

def pagina_perfil():
    user = st.session_state['usuario_atual']
    cor = COR_PRINCIPAL
    
    cb, ct = st.columns([0.15, 0.85])
    with cb:
        if st.button("⬅ Voltar"): ir_para_dashboard()
    with ct:
        st.markdown(f"<h2 style='text-align:center; color:{cor}; margin:0;'>Meu Perfil</h2>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

    # Exibição dos Dados
    foto_str = user.get('foto', '')
    if foto_str:
        src = f"data:image/jpeg;base64,{foto_str}"
        st.markdown(f'<img src="{src}" class="profile-big-img">', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="profile-big-img" style="background:#eee; display:flex; align-items:center; justify-content:center; font-size:80px; color:{cor};">👤</div>', unsafe_allow_html=True)
    
    st.markdown(f"<h3 style='text-align:center; margin-top:15px;'>{user['nome_completo']}</h3>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center; color:#666; margin-top:-10px;'>@{user['username']}</p>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # --- ÁREA DE EDIÇÃO ---
    
    with st.expander("📝 Alterar Nome Completo"):
        novo_nome = st.text_input("Novo Nome", value=user['nome_completo'])
        if st.button("Salvar Nome"):
            if not novo_nome.strip():
                st.error("Nome não pode ser vazio.")
            else:
                with st.spinner("Atualizando..."):
                    atualizar_nome_usuario(user['username'], user['nome_completo'], novo_nome)
                    st.session_state['usuario_atual']['nome_completo'] = novo_nome
                    st.success("Nome atualizado com sucesso!")
                    time.sleep(1)
                    st.rerun()

    with st.expander("📷 Alterar Foto"):
        uploaded_new = st.file_uploader("Nova Foto", type=['jpg','png'], key='new_photo')
        if uploaded_new:
            st.write("Ajuste o recorte:")
            
            # CORREÇÃO: Usar colunas para restringir largura e should_resize_image nativo
            c_crop, _ = st.columns([0.8, 0.2]) 
            with c_crop:
                img_new = st_cropper(
                    Image.open(uploaded_new), # Passa a imagem original direto
                    aspect_ratio=(1,1), 
                    box_color='#bf7000',
                    should_resize_image=True, # Deixa a lib lidar com o tamanho
                    key='cropper_new'
                )
            
            if st.button("Salvar Foto"):
                with st.spinner("Processando imagem..."):
                    nova_b64 = processar_imagem(img_new)
                    atualizar_foto_usuario(user['username'], nova_b64)
                    st.session_state['usuario_atual']['foto'] = nova_b64
                    st.success("Foto atualizada!")
                    time.sleep(1)
                    st.rerun()

    with st.expander("🔐 Alterar Senha"):
        senha_atual = st.text_input("Senha Atual", type="password")
        nova_senha = st.text_input("Nova Senha", type="password")
        conf_senha = st.text_input("Confirmar Nova Senha", type="password")
        
        if st.button("Atualizar Senha"):
            if not verificar_senha(senha_atual, user['senha_hash']):
                st.error("Senha atual incorreta.")
            elif nova_senha != conf_senha:
                st.error("As novas senhas não conferem.")
            else:
                val, msg = validar_complexidade_senha(nova_senha)
                if not val:
                    st.error(msg)
                else:
                    with st.spinner("Criptografando..."):
                        novo_hash = hash_senha(nova_senha)
                        atualizar_senha_usuario(user['username'], novo_hash)
                        st.session_state['usuario_atual']['senha_hash'] = novo_hash
                        st.success("Senha alterada com sucesso!")
                        time.sleep(1)

def app_principal():
    gc = get_gspread_client()
    if not gc: return
    sh = gc.open_by_url(PLANILHA_URL)
    worksheet = sh.worksheet("Dados")
    df = pd.DataFrame(worksheet.get_all_records())
    
    user_data = st.session_state['usuario_atual']
    nome_coluna = user_data['nome_completo']
    username = user_data['username']
    
    # Roteamento para página de perfil
    if st.session_state['pagina_atual'] == 'perfil':
        pagina_perfil()
        return

    if nome_coluna not in df.columns:
        st.warning(f"Sincronizando '{nome_coluna}'... aguarde.")
        if st.button("Atualizar Página"): st.rerun()
        return

    primeiro_nome = nome_coluna.split()[0].title()
    foto_str = user_data.get('foto', '')
    cor = COR_PRINCIPAL
    glow_style = f"color: white; text-shadow: 0 0 10px {cor}cc, 0 0 5px {cor}80;"
    
    try: col_idx_gs = worksheet.find(nome_coluna).col
    except: st.error("Erro: Coluna do usuário não encontrada."); return

    # === DASHBOARD ===
    if st.session_state['pagina_atual'] == 'dashboard':
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
                        <h4 style="margin:0; color: #777;">Bem-vindo(a),</h4>
                        <h1 style="margin: 0; color: {cor}; line-height: 1.1;">{primeiro_nome}</h1>
                    </div>
                </div>
            ''', unsafe_allow_html=True)
            
        with c_logout:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Sair 🔒"): realizar_logout()
            if st.button("Perfil 👤"): ir_para_perfil()

        st.markdown("<hr style='margin: 25px 0;'>", unsafe_allow_html=True)
        
        # Último acesso
        ultima_disc = obter_ultima_disciplina(df, username)
        if ultima_disc:
            validas = [d for d in df['Disciplina'].unique() if d]
            match = next((d for d in validas if d.upper() == ultima_disc.upper()), None)
            if match:
                st.markdown(f"**📍 Continuar de onde parou:**")
                if st.button(f"🎬 Ir para {match}", type="primary"):
                    ir_para_disciplina(match)
                st.markdown("<br>", unsafe_allow_html=True)

        # Progresso Total
        col = df[nome_coluna].apply(limpar_booleano)
        total_aulas = len(df)
        pct = col.sum() / total_aulas if total_aulas > 0 else 0
        
        st.markdown(f'''
            <div style="background: white; border-left: 8px solid {cor}; padding: 25px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); margin-bottom: 30px;">
                <div style="color: #888; font-size: 14px; text-transform: uppercase; font-weight: bold;">Progresso Geral</div>
                <div style="display: flex; justify-content: space-between; align-items: baseline;">
                    <div style="font-size: 42px; font-weight: 900; color: {cor};">{int(pct*100)}%</div>
                    <div style="font-size: 16px; color: #555;"><strong>{col.sum()}</strong> de {total_aulas} aulas</div>
                </div>
            </div>
        ''', unsafe_allow_html=True)
        st.progress(pct)

        # Cards Disciplinas
        st.markdown("### 📚 Suas Disciplinas")
        ordem_pref = ["Cardiologia", "Pneumologia", "Endocrinologia", "Nefrologia", "Gastroenterologia", "Hepatologia", "Infectologia", "Hematologia", "Reumatologia", "Neurologia", "Psiquiatria", "Cirurgia", "Ginecologia", "Obstetrícia", "Pediatria", "Preventiva", "Dermatologia", "Ortopedia", "Otorrinolaringologia", "Oftalmologia"]
        todas = sorted(list(df['Disciplina'].unique()))
        
        lista = ["Por Semana"] + [d for d in ordem_pref if d in todas] + [d for d in todas if d not in ordem_pref]
        
        cols = st.columns(2)
        for i, disc in enumerate(lista):
            if not disc: continue
            with cols[i % 2]:
                with st.container(border=True):
                    if disc == "Por Semana":
                        df_d = df
                        titulo_card = "📅 Por Semana"
                    else:
                        df_d = df[df['Disciplina'] == disc]
                        titulo_card = disc

                    feitos = df_d[nome_coluna].apply(limpar_booleano).sum()
                    pct_d = feitos / len(df_d) if len(df_d) > 0 else 0
                    
                    style = f"background: {cor}; padding: 5px 10px; border-radius: 5px; {glow_style}" if pct_d > 0 else "color:#444;"
                    
                    st.markdown(f"<h4 style='{style} margin-bottom:5px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;'>{titulo_card}</h4>", unsafe_allow_html=True)
                    st.progress(pct_d)
                    ct, cb = st.columns([0.6, 0.4])
                    ct.caption(f"{int(pct_d*100)}% ({feitos}/{len(df_d)})")
                    if cb.button("Abrir ➝", key=f"b_{disc}"): ir_para_disciplina(disc)

    # === MODO FOCO ===
    elif st.session_state['pagina_atual'] == 'focus':
        disc = st.session_state['disciplina_ativa']
        glow = f"color: white; text-shadow: 0 0 12px {cor}, 0 0 6px {cor}80;"

        cb, ct = st.columns([0.15, 0.85])
        with cb:
            if st.button("⬅ Voltar"): ir_para_dashboard()
        with ct:
            titulo_header = "📅 Visão Semanal" if disc == "Por Semana" else f"📖 {disc}"
            st.markdown(f"<h2 style='background: {cor}; padding: 8px 15px; border-radius: 10px; {glow} text-align:center;'>{titulo_header}</h2>", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if disc == "Por Semana":
            # Filtra apenas valores numéricos da coluna Semana
            semanas_unicas = sorted([int(x) for x in df['Semana'].unique() if str(x).strip().isdigit()])
            
            for sem in semanas_unicas:
                df_s = df[df['Semana'] == sem]
                feitos_s = df_s[nome_coluna].apply(limpar_booleano).sum()
                total_s = len(df_s)
                pct_s = feitos_s / total_s if total_s > 0 else 0
                
                titulo_acc = f"Semana {sem} ({int(pct_s*100)}%)"
                
                with st.expander(titulo_acc):
                    st.progress(pct_s)
                    for idx, row in df_s.iterrows():
                        chk = limpar_booleano(row[nome_coluna])
                        ck, ct = st.columns([0.1, 0.9])
                        key = f"chk_{idx}_{nome_coluna}_sem"
                        with ck: novo = st.checkbox("x", value=chk, key=key, label_visibility="collapsed")
                        with ct:
                            txt = f"**{row['Disciplina']}**: {row.get('Aula','-')}"
                            if chk: st.markdown(f"<span style='opacity:0.6; text-decoration:line-through'>✅ {txt}</span>", unsafe_allow_html=True)
                            else: st.markdown(txt)
                        if novo != chk:
                            atualizar_status(worksheet, idx, col_idx_gs, novo, username, disc, df)
                            time.sleep(0.5)
                            st.rerun()
        else:
            df_d = df[df['Disciplina'] == disc]
            st.info(f"Concluídas: **{df_d[nome_coluna].apply(limpar_booleano).sum()}/{len(df_d)}**")
            for idx, row in df_d.iterrows():
                chk = limpar_booleano(row[nome_coluna])
                ck, ct = st.columns([0.1, 0.9])
                key = f"chk_{idx}_{nome_coluna}"
                with ck: novo = st.checkbox("x", value=chk, key=key, label_visibility="collapsed")
                with ct:
                    txt = f"{row.get('Aula','-')}"
                    if chk: st.markdown(f"<span style='opacity:0.6; text-decoration:line-through'>✅ {txt}</span>", unsafe_allow_html=True)
                    else: st.markdown(txt)
                if novo != chk:
                    atualizar_status(worksheet, idx, col_idx_gs, novo, username, disc, df)
                    time.sleep(0.5)
                    st.rerun()

if st.session_state['logado']: app_principal()
else: tela_login()
