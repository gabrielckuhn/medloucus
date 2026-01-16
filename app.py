import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import bcrypt
import re
import time

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

# --- Funções de Autenticação e Segurança ---

def validar_complexidade_senha(senha):
    """
    Verifica: Mínimo 8 chars, 1 maiúscula, 1 minúscula, 1 número, 1 caractere especial.
    """
    if len(senha) < 8:
        return False, "A senha deve ter pelo menos 8 caracteres."
    if not re.search(r"[a-z]", senha):
        return False, "A senha deve ter pelo menos uma letra minúscula."
    if not re.search(r"[A-Z]", senha):
        return False, "A senha deve ter pelo menos uma letra maiúscula."
    if not re.search(r"[0-9]", senha):
        return False, "A senha deve ter pelo menos um número."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", senha):
        return False, "A senha deve ter pelo menos um caractere especial (!@#$%)."
    return True, "Senha válida."

def hash_senha(senha):
    # Gera um hash seguro da senha
    return bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verificar_senha(senha_input, senha_hash):
    # Compara a senha digitada com o hash salvo
    return bcrypt.checkpw(senha_input.encode('utf-8'), senha_hash.encode('utf-8'))

# --- Funções de Banco de Dados (Sheets) ---

def buscar_usuario(username):
    gc = get_gspread_client()
    sh = gc.open_by_url(PLANILHA_URL)
    worksheet = sh.worksheet("Usuarios")
    records = worksheet.get_all_records()
    
    for user in records:
        if user['username'] == username:
            return user
    return None

def criar_usuario(username, nome_completo, senha):
    gc = get_gspread_client()
    sh = gc.open_by_url(PLANILHA_URL)
    
    # 1. Salvar na aba Usuarios
    ws_users = sh.worksheet("Usuarios")
    
    # Verifica se já existe
    cell = ws_users.find(username)
    if cell:
        return False, "Nome de usuário já existe."
    
    senha_segura = hash_senha(senha)
    ws_users.append_row([username, nome_completo, senha_segura])
    
    # 2. Criar coluna na aba Dados para marcar progresso
    try:
        ws_dados = sh.worksheet("Dados")
        # Verifica se o cabeçalho já existe
        headers = ws_dados.row_values(1)
        if nome_completo not in headers:
            # Adiciona o nome na primeira linha da próxima coluna vazia
            col_index = len(headers) + 1
            ws_dados.update_cell(1, col_index, nome_completo)
            # Preenche com FALSE para todas as linhas existentes (opcional, mas bom para evitar vazios)
            # O gspread não tem "fill column" fácil, então vamos deixar o app tratar vazios como False
    except Exception as e:
        return False, f"Usuário criado, mas erro ao criar coluna de dados: {e}"

    return True, "Conta criada com sucesso!"

# --- Lógica da Interface ---

# Inicializa Session State
if 'logado' not in st.session_state:
    st.session_state['logado'] = False
if 'usuario_atual' not in st.session_state:
    st.session_state['usuario_atual'] = None # Guarda o dicionário do usuário

def tela_login():
    st.title("🔐 MedTracker - Acesso")
    
    tab1, tab2 = st.tabs(["Entrar (Login)", "Criar Conta (Sign Up)"])
    
    with tab1:
        with st.form("login_form"):
            user_input = st.text_input("Usuário")
            pass_input = st.text_input("Senha", type="password")
            submit_login = st.form_submit_button("Entrar")
            
            if submit_login:
                if not user_input or not pass_input:
                    st.warning("Preencha todos os campos.")
                else:
                    usuario_db = buscar_usuario(user_input)
                    if usuario_db and verificar_senha(pass_input, usuario_db['senha_hash']):
                        st.session_state['logado'] = True
                        st.session_state['usuario_atual'] = usuario_db
                        st.success("Login realizado!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos.")

    with tab2:
        st.markdown("### Novo por aqui?")
        with st.form("signup_form"):
            new_user = st.text_input("Escolha um Usuário (Login)")
            new_name = st.text_input("Seu Nome (como aparecerá na planilha)")
            new_pass = st.text_input("Senha", type="password")
            confirm_pass = st.text_input("Confirmar Senha", type="password")
            
            submit_signup = st.form_submit_button("Criar Conta")
            
            if submit_signup:
                if new_pass != confirm_pass:
                    st.error("As senhas não coincidem.")
                else:
                    valida, msg = validar_complexidade_senha(new_pass)
                    if not valida:
                        st.error(msg)
                    elif not new_user or not new_name:
                        st.error("Preencha todos os campos.")
                    else:
                        with st.spinner("Criando sua área de estudos..."):
                            sucesso, msg_retorno = criar_usuario(new_user, new_name, new_pass)
                            if sucesso:
                                st.success(msg_retorno)
                                st.info("Agora faça login na aba 'Entrar'.")
                            else:
                                st.error(msg_retorno)

def tela_principal():
    # Muda layout para wide quando logado para caber as tabelas
    # (Streamlit não permite mudar layout dinamicamente fácil, então mantemos o set_page_config, 
    # mas usamos CSS ou containers para expandir se necessário)
    
    usuario = st.session_state['usuario_atual']
    nome_na_planilha = usuario['nome_completo']
    
    # Sidebar
    st.sidebar.title(f"Olá, {nome_na_planilha}!")
    if st.sidebar.button("Sair / Logout"):
        st.session_state['logado'] = False
        st.session_state['usuario_atual'] = None
        st.rerun()
    
    st.title("🩺 Acompanhamento de Estudos")
    
    # Carregar dados
    gc = get_gspread_client()
    if not gc: return
    
    sh = gc.open_by_url(PLANILHA_URL)
    worksheet = sh.worksheet("Dados")
    df = pd.DataFrame(worksheet.get_all_records())

    # Verifica se a coluna do usuário existe no DF
    if nome_na_planilha not in df.columns:
        st.warning(f"Sua coluna de dados ('{nome_na_planilha}') ainda não foi sincronizada. Tente recarregar a página em alguns instantes.")
        if st.button("Forçar Recarregamento"):
            st.rerun()
        return

    # --- Lógica de Exibição das Matérias (Igual ao seu código original) ---
    ordem_disciplinas = [
        "Cardiologia", "Pneumologia", "Endocrinologia", "Nefrologia", "Gastroenterologia", 
        "Hepatologia", "Infectologia", "Hematologia", "Reumatologia", "Neurologia", 
        "Psiquiatria", "Cirurgia", "Ginecologia", "Obstetrícia", "Pediatria", 
        "Preventiva", "Dermatologia", "Ortopedia", "Otorrinolaringologia", "Oftalmologia"
    ]
    
    if "Disciplina" in df.columns:
        disciplinas_existentes = df['Disciplina'].unique()
        # Ordenação
        disciplinas_para_mostrar = [d for d in ordem_disciplinas if d in disciplinas_existentes]
        extras = [d for d in disciplinas_existentes if d not in ordem_disciplinas]
        disciplinas_para_mostrar.extend(extras)

        for disciplina in disciplinas_para_mostrar:
            df_disc = df[df['Disciplina'] == disciplina]
            
            # Cálculo de Progresso
            coluna_usuario = df_disc[nome_na_planilha].astype(str).str.upper()
            is_completed_series = coluna_usuario.apply(lambda x: True if x == 'TRUE' else False)
            total_aulas = len(df_disc)
            aulas_assistidas = is_completed_series.sum()
            progresso = aulas_assistidas / total_aulas if total_aulas > 0 else 0
            
            texto_progresso = f"{int(progresso * 100)}% ({aulas_assistidas}/{total_aulas})"

            with st.expander(f"**{disciplina}** - {texto_progresso}"):
                st.progress(progresso)
                
                for idx, row in df_disc.iterrows():
                    # Lógica do Checkbox
                    valor_atual = row[nome_na_planilha]
                    checked = str(valor_atual).upper() == 'TRUE'
                    
                    col1, col2 = st.columns([0.05, 0.95])
                    with col1:
                        key_check = f"chk_{idx}_{nome_na_planilha}"
                        # Callback para salvar assim que clicar
                        def salvar_alteracao(w=worksheet, r=idx, c=nome_na_planilha, k=key_check):
                            novo_val = st.session_state[k]
                            col_index = w.find(c).col
                            gspread_row = r + 2
                            w.update_cell(gspread_row, col_index, novo_val)
                            st.toast("Salvo!", icon="✅")

                        st.checkbox(
                            "", 
                            value=checked, 
                            key=key_check, 
                            on_change=salvar_alteracao
                        )

                    with col2:
                        semana = row.get('Semana', '-')
                        aula_nome = row.get('Aula', 'Sem nome')
                        st.write(f"**S{semana}**: {aula_nome}")
    else:
        st.error("Coluna 'Disciplina' não encontrada na planilha 'Dados'.")

# --- Controlador Principal ---
if st.session_state['logado']:
    tela_principal()
else:
    tela_login()
