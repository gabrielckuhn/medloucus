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
from streamlit_cropper import st_cropper # BIBLIOTECA NOVA

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker Pro", page_icon="🩺", layout="centered")

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

# --- Funções de Imagem (Novas) ---

def processar_imagem(img_pil):
    """
    Recebe uma imagem PIL (já recortada), redimensiona para 300x300 
    e converte para string Base64 para salvar no Excel.
    """
    # 1. Redimensionar para no máximo 300x300 mantendo proporção (thumbnail)
    # Como o recorte é 1:1, ela ficará 300x300 exatos ou menos.
    img_pil.thumbnail((300, 300))
    
    # 2. Salvar em buffer de memória como JPEG otimizado
    buffer = BytesIO()
    img_pil.save(buffer, format="JPEG", quality=70) # Qualidade 70 para ficar leve
    
    # 3. Converter para Base64
    img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return img_str

def base64_to_image(base64_string):
    """Converte string do Excel de volta para imagem"""
    if not base64_string:
        return None
    try:
        img_data = base64.b64decode(base64_string)
        return Image.open(BytesIO(img_data))
    except:
        return None

# --- Funções de Segurança ---

def validar_complexidade_senha(senha):
    if len(senha) < 8: return False, "Senha deve ter min. 8 caracteres."
    if not re.search(r"[a-z]", senha): return False, "Falta letra minúscula."
    if not re.search(r"[A-Z]", senha): return False, "Falta letra maiúscula."
    if not re.search(r"[0-9]", senha): return False, "Falta número."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", senha): return False, "Falta caractere especial."
    return True, "Senha válida."

def hash_senha(senha):
    return bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verificar_senha(senha_input, senha_hash):
    return bcrypt.checkpw(senha_input.encode('utf-8'), senha_hash.encode('utf-8'))

# --- Funções de Banco de Dados ---

def buscar_usuario(username):
    gc = get_gspread_client()
    sh = gc.open_by_url(PLANILHA_URL)
    worksheet = sh.worksheet("Usuarios")
    records = worksheet.get_all_records()
    for user in records:
        if user['username'] == username:
            return user
    return None

def criar_usuario(username, nome_completo, senha, foto_base64=""):
    gc = get_gspread_client()
    sh = gc.open_by_url(PLANILHA_URL)
    
    ws_users = sh.worksheet("Usuarios")
    
    if ws_users.find(username):
        return False, "Nome de usuário já existe."
    
    senha_segura = hash_senha(senha)
    # Adiciona a linha com a foto
    ws_users.append_row([username, nome_completo, senha_segura, foto_base64])
    
    try:
        ws_dados = sh.worksheet("Dados")
        headers = ws_dados.row_values(1)
        if nome_completo not in headers:
            col_index = len(headers) + 1
            ws_dados.update_cell(1, col_index, nome_completo)
    except Exception as e:
        return False, f"Erro ao criar coluna de dados: {e}"

    return True, "Conta criada com sucesso!"

# --- Lógica da Interface ---

if 'logado' not in st.session_state:
    st.session_state['logado'] = False
if 'usuario_atual' not in st.session_state:
    st.session_state['usuario_atual'] = None

def tela_login():
    st.title("🔐 MedTracker - Acesso")
    
    tab1, tab2 = st.tabs(["Entrar", "Criar Conta"])
    
    with tab1:
        with st.form("login_form"):
            user_input = st.text_input("Usuário")
            pass_input = st.text_input("Senha", type="password")
            submit_login = st.form_submit_button("Entrar")
            
            if submit_login:
                usuario_db = buscar_usuario(user_input)
                if usuario_db and verificar_senha(pass_input, usuario_db['senha_hash']):
                    st.session_state['logado'] = True
                    st.session_state['usuario_atual'] = usuario_db
                    st.success("Login realizado!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Credenciais inválidas.")

    with tab2:
        st.markdown("### Cadastro")
        
        # Inputs de Texto
        new_user = st.text_input("Usuário (Login)")
        new_name = st.text_input("Nome Completo")
        new_pass = st.text_input("Senha", type="password", help="Min 8 chars, Maiusc, Minusc, Num, Especial")
        confirm_pass = st.text_input("Confirmar Senha", type="password")
        
        # --- Lógica de Upload e Crop da Imagem ---
        st.markdown("---")
        st.markdown("**Foto de Perfil (Opcional)**")
        uploaded_file = st.file_uploader("Escolha uma imagem", type=['png', 'jpg', 'jpeg'])
        foto_processada_b64 = ""

        if uploaded_file:
            st.info("Ajuste a caixa azul para recortar seu rosto:")
            # Carrega a imagem original
            img_original = Image.open(uploaded_file)
            
            # Chama o cortador. aspect_ratio=(1,1) força o quadrado
            cropped_img = st_cropper(
                img_original,
                realtime_update=True,
                box_color='blue',
                aspect_ratio=(1, 1),
                should_resize_image=True # Redimensiona visualização se for muito grande
            )
            
            # Mostra o preview do resultado
            st.write("Pré-visualização:")
            st.image(cropped_img, width=150)
            
            # Processa a imagem cortada para salvar
            foto_processada_b64 = processar_imagem(cropped_img)

        st.markdown("---")
        
        if st.button("Criar Conta"):
            if new_pass != confirm_pass:
                st.error("Senhas não coincidem.")
            else:
                valida, msg = validar_complexidade_senha(new_pass)
                if not valida:
                    st.error(msg)
                elif not new_user or not new_name:
                    st.error("Preencha usuário e nome.")
                else:
                    with st.spinner("Criando perfil..."):
                        sucesso, msg_retorno = criar_usuario(new_user, new_name, new_pass, foto_processada_b64)
                        if sucesso:
                            st.success(msg_retorno)
                            st.info("Faça login na aba 'Entrar'.")
                        else:
                            st.error(msg_retorno)

def tela_principal():
    usuario = st.session_state['usuario_atual']
    nome_na_planilha = usuario['nome_completo']
    
    # --- Sidebar com Foto ---
    foto_str = usuario.get('foto', '')
    if foto_str:
        imagem_perfil = base64_to_image(foto_str)
        if imagem_perfil:
            # Mostra a imagem centralizada e arredondada (simulada pelo layout)
            col_a, col_b, col_c = st.sidebar.columns([1,2,1])
            with col_b:
                st.image(imagem_perfil, width=130, caption=nome_na_planilha)
    else:
        st.sidebar.header(f"Olá, {nome_na_planilha}!")
    
    if st.sidebar.button("Sair"):
        st.session_state['logado'] = False
        st.rerun()
        
    st.sidebar.markdown("---")
    
    # --- Resto do App (Matérias) ---
    st.title("🩺 Acompanhamento de Estudos")
    
    gc = get_gspread_client()
    if not gc: return
    sh = gc.open_by_url(PLANILHA_URL)
    worksheet = sh.worksheet("Dados")
    df = pd.DataFrame(worksheet.get_all_records())

    if nome_na_planilha not in df.columns:
        st.warning("Sincronizando usuário... tente recarregar.")
        return

    # Filtros e Display (Mantido do seu código anterior)
    ordem_disciplinas = [
        "Cardiologia", "Pneumologia", "Endocrinologia", "Nefrologia", "Gastroenterologia", 
        "Hepatologia", "Infectologia", "Hematologia", "Reumatologia", "Neurologia", 
        "Psiquiatria", "Cirurgia", "Ginecologia", "Obstetrícia", "Pediatria", 
        "Preventiva", "Dermatologia", "Ortopedia", "Otorrinolaringologia", "Oftalmologia"
    ]
    
    if "Disciplina" in df.columns:
        disciplinas_existentes = df['Disciplina'].unique()
        disciplinas_para_mostrar = [d for d in ordem_disciplinas if d in disciplinas_existentes]
        extras = [d for d in disciplinas_existentes if d not in ordem_disciplinas]
        disciplinas_para_mostrar.extend(extras)

        for disciplina in disciplinas_para_mostrar:
            df_disc = df[df['Disciplina'] == disciplina]
            coluna_usuario = df_disc[nome_na_planilha].astype(str).str.upper()
            is_completed_series = coluna_usuario.apply(lambda x: True if x == 'TRUE' else False)
            total = len(df_disc)
            assistidas = is_completed_series.sum()
            progresso = assistidas / total if total > 0 else 0
            
            with st.expander(f"**{disciplina}** - {int(progresso*100)}%"):
                st.progress(progresso)
                for idx, row in df_disc.iterrows():
                    checked = str(row[nome_na_planilha]).upper() == 'TRUE'
                    key_check = f"chk_{idx}_{nome_na_planilha}"
                    
                    def salvar(w=worksheet, r=idx, c=nome_na_planilha, k=key_check):
                        w.update_cell(r+2, w.find(c).col, st.session_state[k])
                        
                    st.checkbox("", value=checked, key=key_check, on_change=salvar)
                    st.write(f"**S{row.get('Semana','-')}**: {row.get('Aula','')}")

if st.session_state['logado']:
    tela_principal()
else:
    tela_login()
