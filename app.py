import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker Estudo", page_icon="🩺", layout="wide")

# --- Conexão com Google Sheets ---
# Usamos @st.cache_resource para não reconectar a cada clique, mas a leitura dos dados será atualizada.
@st.cache_resource
def conectar_google_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Carrega as credenciais dos segredos do Streamlit
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    
    gc = gspread.authorize(credentials)
    return gc

# Função para carregar dados
def carregar_dados(sheet_url_or_name):
    gc = conectar_google_sheets()
    try:
        sh = gc.open(sheet_url_or_name)
        worksheet = sh.worksheet("Dados") # Nome da aba na planilha
        dados = worksheet.get_all_records()
        df = pd.DataFrame(dados)
        return df, worksheet
    except Exception as e:
        st.error(f"Erro ao conectar na planilha: {e}")
        return pd.DataFrame(), None

# Função de callback para atualizar a planilha imediatamente
def atualizar_status(worksheet, row_index, col_name, novo_valor):
    try:
        # Encontra o índice da coluna (gspread usa base 1)
        col_index = worksheet.find(col_name).col
        # A linha é row_index + 2 (1 pelo cabeçalho + 1 porque gspread é base 1 e dataframe é base 0)
        gspread_row = row_index + 2
        
        # Atualiza a célula no Google Sheets
        worksheet.update_cell(gspread_row, col_index, novo_valor)
        st.toast(f"Salvo: Aula marcada como {novo_valor}!", icon="✅")
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

# --- Interface Principal ---

# 1. Título e Seleção de Usuário
st.title("🩺 Acompanhamento de Estudos - Residência")

# Nome da sua planilha (pode ser o nome exato ou a URL completa)
NOME_PLANILHA = "MedTracker Planilha" # <--- ALTERE AQUI PARA O NOME DA SUA PLANILHA

df, worksheet = carregar_dados(NOME_PLANILHA)

if not df.empty:
    usuarios = ["Ana Clara", "Gabriel", "Newton"]
    
    st.sidebar.header("Perfil")
    usuario_selecionado = st.sidebar.radio("Selecione quem está estudando:", usuarios)
    
    st.sidebar.markdown("---")
    st.sidebar.info(f"Bem-vindo(a), **{usuario_selecionado}**! Marque as aulas conforme for assistindo. O progresso é salvo automaticamente.")

    # 2. Lista de Disciplinas (Ordem Definida)
    ordem_disciplinas = [
        "Cardiologia", "Pneumologia", "Endocrinologia", "Nefrologia", "Gastroenterologia", 
        "Hepatologia", "Infectologia", "Hematologia", "Reumatologia", "Neurologia", 
        "Psiquiatria", "Cirurgia", "Ginecologia", "Obstetrícia", "Pediatria", 
        "Preventiva", "Dermatologia", "Ortopedia", "Otorrinolaringologia", "Oftalmologia"
    ]
    
    # Filtra apenas disciplinas que existem na planilha para evitar erros
    disciplinas_existentes = df['Disciplina'].unique()
    disciplinas_para_mostrar = [d for d in ordem_disciplinas if d in disciplinas_existentes]
    
    # Adiciona disciplinas que estão na planilha mas não na lista fixa (caso haja extras)
    extras = [d for d in disciplinas_existentes if d not in ordem_disciplinas]
    disciplinas_para_mostrar.extend(extras)

    # 3. Exibição das Disciplinas e Aulas
    for disciplina in disciplinas_para_mostrar:
        # Filtra o dataframe pela disciplina atual
        df_disc = df[df['Disciplina'] == disciplina]
        
        # Tratamento de erro caso a coluna do usuário não seja booleana pura (ex: string "TRUE")
        # Forçamos converter para booleano para cálculo
        status_usuario = df_disc[usuario_selecionado].astype(str).str.upper().replace({'TRUE': True, 'FALSE': False})
        
        # Cálculo do Progresso
        total_aulas = len(df_disc)
        aulas_assistidas = status_usuario.sum() # Soma os Trues
        progresso = aulas_assistidas / total_aulas if total_aulas > 0 else 0
        
        # Define a cor do progresso
        cor_progresso = "green" if progresso == 1.0 else "blue"
        texto_progresso = f"{int(progresso * 100)}% Concluído ({aulas_assistidas}/{total_aulas})"

        # Cria o Expander
        with st.expander(f"**{disciplina}** - {texto_progresso}"):
            st.progress(progresso)
            
            # Cria colunas para organizar melhor a lista
            # Itera sobre as linhas dessa disciplina
            for idx, row in df_disc.iterrows():
                # Checkbox
                # A chave (key) deve ser única. Usamos o índice original do dataframe.
                is_checked = row[usuario_selecionado]
                
                # Normalização do valor booleano vindo da planilha
                if isinstance(is_checked, str):
                    is_checked = True if is_checked.upper() == 'TRUE' else False
                
                col1, col2 = st.columns([0.05, 0.95])
                
                with col1:
                    # O Checkbox dispara a atualização assim que clicado
                    novo_valor = st.checkbox(
                        label="",
                        value=bool(is_checked),
                        key=f"chk_{idx}_{usuario_selecionado}",
                    )

                with col2:
                    st.write(f"**Semana {row['Semana']}**: {row['Aula']}")

                # Lógica de Atualização (Detecta mudança)
                if novo_valor != bool(is_checked):
                    # Se mudou, atualiza no Google Sheets
                    # Passamos 'TRUE' ou 'FALSE' string para garantir compatibilidade com Sheets,
                    # ou boolean python dependendo de como você prefere na planilha. 
                    # Sheets entende boolean Python.
                    atualizar_status(worksheet, idx, usuario_selecionado, novo_valor)
                    # Força recarregar a página para atualizar visualmente os gráficos
                    st.rerun()

else:
    st.warning("A planilha parece estar vazia ou não foi possível carregá-la.")
