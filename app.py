import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker Estudo", page_icon="🩺", layout="wide")

# --- Configurações da Planilha ---
# URL fornecida
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1-i82jvSfNzG2Ri7fu3vmOFnIYqQYglapbQ7x0000_rc/edit?usp=sharing"

# --- Conexão com Google Sheets ---
@st.cache_resource
def conectar_google_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Tenta carregar as credenciais dos segredos do Streamlit
    try:
        credentials = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=scopes
        )
        gc = gspread.authorize(credentials)
        return gc
    except Exception as e:
        st.error(f"Erro nas credenciais: {e}. Verifique se o segredo 'gcp_service_account' está configurado corretamente no Streamlit Cloud.")
        return None

# Função para carregar dados
def carregar_dados():
    gc = conectar_google_sheets()
    if not gc:
        return pd.DataFrame(), None

    try:
        # Abre a planilha pelo URL direto (mais robusto)
        sh = gc.open_by_url(PLANILHA_URL)
        
        # Tenta pegar a aba "Dados", se não existir, pega a primeira aba (índice 0)
        try:
            worksheet = sh.worksheet("Dados")
        except gspread.WorksheetNotFound:
            worksheet = sh.get_worksheet(0)
            
        dados = worksheet.get_all_records()
        df = pd.DataFrame(dados)
        return df, worksheet
    except Exception as e:
        st.error(f"Erro ao acessar a planilha. Verifique se o bot (medtracker10bot@...) é Editor no compartilhamento. Detalhe: {e}")
        return pd.DataFrame(), None

# Função para salvar a alteração (checkbox)
def atualizar_status(worksheet, row_index, col_name, novo_valor):
    try:
        # Encontra o índice da coluna (gspread usa base 1)
        col_index = worksheet.find(col_name).col
        # A linha é row_index + 2 (1 pelo cabeçalho + 1 porque gspread é base 1 e dataframe é base 0)
        gspread_row = row_index + 2
        
        # Atualiza a célula no Google Sheets
        worksheet.update_cell(gspread_row, col_index, novo_valor)
        st.toast(f"Salvo com sucesso!", icon="✅")
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

# --- Interface Principal ---

st.title("🩺 Acompanhamento de Estudos - Residência")

df, worksheet = carregar_dados()

if not df.empty and worksheet is not None:
    # Definição dos usuários
    usuarios = ["Ana Clara", "Gabriel", "Newton"]
    
    # Verifica se as colunas dos usuários existem no dataframe
    if not all(u in df.columns for u in usuarios):
        st.error(f"As colunas {usuarios} não foram encontradas na planilha. Verifique os cabeçalhos.")
    else:
        st.sidebar.header("Perfil")
        usuario_selecionado = st.sidebar.radio("Selecione quem está estudando:", usuarios)
        
        st.sidebar.markdown("---")
        st.sidebar.info(f"Bem-vindo(a), **{usuario_selecionado}**! Seu progresso é salvo automaticamente.")

        # Lista de Disciplinas na ordem solicitada
        ordem_disciplinas = [
            "Cardiologia", "Pneumologia", "Endocrinologia", "Nefrologia", "Gastroenterologia", 
            "Hepatologia", "Infectologia", "Hematologia", "Reumatologia", "Neurologia", 
            "Psiquiatria", "Cirurgia", "Ginecologia", "Obstetrícia", "Pediatria", 
            "Preventiva", "Dermatologia", "Ortopedia", "Otorrinolaringologia", "Oftalmologia"
        ]
        
        # Filtra disciplinas presentes na planilha
        if "Disciplina" in df.columns:
            disciplinas_existentes = df['Disciplina'].unique()
            disciplinas_para_mostrar = [d for d in ordem_disciplinas if d in disciplinas_existentes]
            # Adiciona disciplinas extras se houver na planilha
            extras = [d for d in disciplinas_existentes if d not in ordem_disciplinas]
            disciplinas_para_mostrar.extend(extras)

            # --- Loop das Disciplinas ---
            for disciplina in disciplinas_para_mostrar:
                # Filtra os dados apenas dessa disciplina
                df_disc = df[df['Disciplina'] == disciplina]
                
                # Tratamento de dados: Converte "TRUE"/"FALSE" texto para booleano real para fazer a conta
                coluna_usuario = df_disc[usuario_selecionado].astype(str).str.upper()
                # Cria uma série booleana temporária apenas para cálculo
                is_completed_series = coluna_usuario.apply(lambda x: True if x == 'TRUE' else False)

                total_aulas = len(df_disc)
                aulas_assistidas = is_completed_series.sum()
                progresso = aulas_assistidas / total_aulas if total_aulas > 0 else 0
                
                texto_progresso = f"{int(progresso * 100)}% ({aulas_assistidas}/{total_aulas})"

                # Expander da disciplina
                with st.expander(f"**{disciplina}** - {texto_progresso}"):
                    st.progress(progresso)
                    
                    # Itera sobre cada aula da disciplina
                    for idx, row in df_disc.iterrows():
                        # Valor atual na célula (pode ser bool ou string 'FALSE')
                        valor_atual = row[usuario_selecionado]
                        
                        # Normaliza para booleano do Python para o checkbox entender
                        checked = False
                        if isinstance(valor_atual, bool):
                            checked = valor_atual
                        elif isinstance(valor_atual, str):
                            checked = (valor_atual.upper() == 'TRUE')
                        
                        col1, col2 = st.columns([0.05, 0.95])
                        
                        with col1:
                            # Checkbox
                            key_check = f"chk_{idx}_{usuario_selecionado}"
                            novo_valor = st.checkbox(
                                label="",
                                value=checked,
                                key=key_check
                            )

                        with col2:
                            semana = row.get('Semana', '-')
                            aula_nome = row.get('Aula', 'Sem nome')
                            # Exibe info da aula
                            st.write(f"**Semana {semana}**: {aula_nome}")

                        # Se o usuário clicou, o valor muda e salvamos
                        if novo_valor != checked:
                            atualizar_status(worksheet, idx, usuario_selecionado, novo_valor)
                            st.rerun() # Recarrega para atualizar a barra de progresso
        else:
            st.error("Coluna 'Disciplina' não encontrada na planilha.")

elif worksheet is None:
    st.warning("Tentativa de conexão finalizada, mas a planilha não retornou dados.")
else:
    st.warning("A planilha está vazia.")
