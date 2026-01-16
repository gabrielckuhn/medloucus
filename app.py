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
from datetime import datetime # IMPORT NOVO

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker Pro", page_icon="🩺", layout="wide")

# --- Constantes ---
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1-i82jvSfNzG2Ri7fu3vmOFnIYqQYglapbQ7x0000_rc/edit?usp=sharing"

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

# --- Funções de Imagem ---
def processar_imagem(img_pil):
    img_pil.thumbnail((300, 300))
    buffer = BytesIO()
    img_pil.save(buffer, format="JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

# --- Funções de Segurança ---
def validar_complexidade_senha(senha):
    if len(senha) < 8: return False, "A senha deve ter pelo menos 8 caracteres."
    if not re.search(r"[a-z]", senha): return False, "Precisa de letra minúscula."
    if not re.search(r"[A-Z]", senha): return False, "Precisa de letra maiúscula."
    if not re.search(r"[0-9]", senha): return False, "Precisa de número."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", senha): return False, "Precisa de caractere especial."
    return True, "Senha válida."

def hash_senha(senha):
    return bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verificar_senha(senha_input, senha_hash):
    return bcrypt.checkpw(senha_input.encode('utf-8'), senha_hash.encode('utf-8'))

# --- Funções de Histórico (Suas funções adaptadas) ---

def registrar_acesso(worksheet, df, username, disciplina):
    """
    Registra que o usuario mexeu na disciplina X agora.
    Salva na coluna 'LastSeen' na linha 2.
    """
    if 'LastSeen' not in df.columns: 
        return # Se não criou a coluna na planilha, ignora sem dar erro
        
    tag = str(username).upper() # Usa o username como TAG
    agora = datetime.now().strftime("%d/%m/%Y_%H:%M")
    novo_codigo = f"{tag}_{agora}_{disciplina.upper()}"
    
    # Pega o índice da coluna (gspread é base 1, df é base 0, mas precisamos somar 1)
    col_idx = df.columns.get_loc('LastSeen') + 1
    
    # Lê o valor atual da célula (Linha 2 da planilha = índice 0 do DF)
    valor_atual = str(df.iloc[0]['LastSeen']) if not df.empty else ""
    
    # Remove logs antigos DESSE usuário para não duplicar, mantendo os de outros
    logs_existentes = [v for v in valor_atual.split(';') if v and not v.startswith(tag)]
    
    # Cria nova lista: [Novo Log] + [Logs de Outros]
    historico = [novo_codigo] + logs_existentes
    
    # Limita tamanho total para não estourar a célula (opcional, 20 logs totais)
    valor_final = ";".join(historico[:50]) 
    
    try: 
        # Atualiza a célula na linha 2 (logo abaixo do cabeçalho)
        worksheet.update_cell(2, col_idx, valor_final)
    except Exception as e: 
        print(f"Erro ao salvar log: {e}")

def obter_ultima_disciplina(df, username):
    """Lê onde o usuário parou pela última vez"""
    if 'LastSeen' not in df.columns or df.empty: return None
    
    tag = str(username).upper()
    logs = str(df.iloc[0]['LastSeen']).split(';')
    
    for log in logs:
        if log.startswith(tag):
            partes = log.split('_')
            # Formato esperado: TAG_DATA_HORA_DISCIPLINA (4 partes)
            if len(partes) >= 4: 
                disciplina_raw = partes[3]
                # Pequeno ajuste de formatação
                return disciplina_raw.replace("OTORRINOLARINGOLOGIA", "Otorrino").title()
    return None

# --- Funções de Banco de Dados ---
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
    except: return False, "Aba Usuarios inexistente"
    
    if ws_users.find(username): return False, "Usuário já existe."
    
    ws_users.append_row([username, nome_completo, hash_senha(senha), foto_base64])
    
    try:
        ws_dados = sh.worksheet("Dados")
        headers = ws_dados.row_values(1)
        if nome_completo not in headers:
            ws_dados.update_cell(1, len(headers)+1, nome_completo)
    except: pass
    return True, "Sucesso"

# --- Interface ---
def tela_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>🔐 MedTracker</h1>", unsafe_allow_html=True)
        tab_entrar, tab_criar = st.tabs(["Entrar", "Criar Conta"])
        
        with tab_entrar:
            with st.form("login"):
                u = st.text_input("Usuário")
                p = st.text_input("Senha", type="password")
                if st.form_submit_button("Acessar", use_container_width=True):
                    user_db = buscar_usuario(u)
                    if user_db and verificar_senha(p, user_db['senha_hash']):
                        st.session_state['logado'] = True
                        st.session_state['usuario_atual'] = user_db
                        st.rerun()
                    else: st.error("Dados incorretos.")
        
        with tab_criar:
            nu = st.text_input("Novo Usuário")
            nn = st.text_input("Nome Completo")
            np = st.text_input("Senha", type="password")
            cp = st.text_input("Confirmar", type="password")
            
            uploaded = st.file_uploader("Foto", type=['jpg','png'])
            foto_b64 = ""
            if uploaded:
                img = st_cropper(Image.open(uploaded), aspect_ratio=(1,1), box_color='blue')
                foto_b64 = processar_imagem(img)
            
            if st.button("Cadastrar", use_container_width=True):
                valida, msg = validar_complexidade_senha(np)
                if np != cp: st.error("Senhas diferem.")
                elif not valida: st.error(msg)
                else:
                    ok, m = criar_usuario(nu, nn, np, foto_b64)
                    if ok: st.success(m); time.sleep(1); st.rerun()
                    else: st.error(m)

def tela_principal():
    user_dic = st.session_state['usuario_atual']
    nome = user_dic['nome_completo']
    username = user_dic['username'] # Usaremos isso para o log
    primeiro_nome = nome.split()[0].title()
    foto = user_dic.get('foto', '')

    # Sidebar
    if foto:
        st.sidebar.markdown(f"""
            <style>
                .p-img {{width: 140px; height: 140px; border-radius: 50%; object-fit: cover; border: 3px solid white; box-shadow: 0 5px 15px rgba(0,0,0,0.2);}}
                .p-box {{display: flex; flex-direction: column; align-items: center; margin-bottom: 20px;}}
            </style>
            <div class="p-box"><img src="data:image/jpeg;base64,{foto}" class="p-img"><div style="margin-top:15px;font-weight:bold;font-size:22px;">Olá, {primeiro_nome}!</div></div>
        """, unsafe_allow_html=True)
    else:
        st.sidebar.markdown(f"<div style='text-align:center;font-size:80px;'>👤</div><h3 style='text-align:center'>Olá, {primeiro_nome}!</h3>", unsafe_allow_html=True)
    
    if st.sidebar.button("Sair", use_container_width=True):
        st.session_state['logado'] = False; st.rerun()

    st.title("🩺 Acompanhamento de Estudos")

    gc = get_gspread_client()
    if not gc: return
    try:
        sh = gc.open_by_url(PLANILHA_URL)
        ws = sh.worksheet("Dados")
        df = pd.DataFrame(ws.get_all_records())
    except Exception as e: st.error(f"Erro planilha: {e}"); return

    if nome not in df.columns: st.warning("Atualizando dados..."); st.rerun(); return

    # --- MOSTRAR ÚLTIMO ACESSO ---
    ultima_disc = obter_ultima_disciplina(df, username)
    if ultima_disc:
        st.info(f"📍 **Continue de onde parou:** Você interagiu recentemente com **{ultima_disc}**.")

    ordem = ["Cardiologia", "Pneumologia", "Endocrinologia", "Nefrologia", "Gastroenterologia", "Hepatologia", "Infectologia", "Hematologia", "Reumatologia", "Neurologia", "Psiquiatria", "Cirurgia", "Ginecologia", "Obstetrícia", "Pediatria", "Preventiva", "Dermatologia", "Ortopedia", "Otorrinolaringologia", "Oftalmologia"]
    
    if "Disciplina" in df.columns:
        discs = [d for d in ordem if d in df['Disciplina'].unique()]
        extras = [d for d in df['Disciplina'].unique() if d not in ordem]
        
        for disc in discs + extras:
            df_d = df[df['Disciplina'] == disc]
            col_user = df_d[nome].astype(str).str.upper()
            concluidos = col_user.apply(lambda x: True if x == 'TRUE' else False).sum()
            total = len(df_d)
            prog = concluidos/total if total > 0 else 0
            
            with st.expander(f"**{disc}** - {int(prog*100)}%"):
                st.progress(prog)
                for idx, row in df_d.iterrows():
                    chk_val = str(row[nome]).upper() == 'TRUE'
                    key = f"chk_{idx}_{nome}"
                    
                    # Callback unificado: Salva valor E registra log
                    def acao(w=ws, r=idx, c=nome, k=key, d=disc, u=username, full_df=df):
                        # 1. Salvar o Checkbox
                        novo = st.session_state[k]
                        try:
                            w.update_cell(r+2, w.find(c).col, novo)
                            # 2. Registrar Log de Acesso (LastSeen)
                            # Só registra se marcou como TRUE (opcional, ou pode registrar sempre que mexer)
                            if novo: 
                                registrar_acesso(w, full_df, u, d)
                        except Exception as e: st.toast(f"Erro: {e}")

                    st.checkbox("", value=chk_val, key=key, on_change=acao)
                    st.write(f"**S{row.get('Semana','-')}**: {row.get('Aula','')}")

if 'logado' not in st.session_state: st.session_state['logado'] = False
if 'usuario_atual' not in st.session_state: st.session_state['usuario_atual'] = None

if st.session_state['logado']: tela_principal()
else: tela_login()
