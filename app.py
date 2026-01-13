import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker", page_icon="🩺", layout="wide")

# --- Conexão e Funções de Dados ---
def load_data():
    """Carrega os dados diretamente do Google Sheets sem cache (ttl=0)"""
    # Cria a conexão
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # Lê a planilha. O ttl=0 garante que os dados estejam sempre frescos
    try:
        df = conn.read(worksheet="Página1", usecols=[0,1,2,3,4,5], ttl=0)
        
        # Garante que as colunas dos usuários sejam booleanas (True/False)
        # Isso evita erros se a planilha tiver 'FALSE' como texto
        users = ["Ana Clara", "Gabriel", "Newton"]
        for user in users:
            if user in df.columns:
                df[user] = df[user].fillna(False).astype(bool)
        return df
    except Exception as e:
        st.error(f"Erro ao conectar com a planilha: {e}")
        return pd.DataFrame()

def save_data(df):
    """Salva o dataframe atualizado de volta no Google Sheets"""
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        conn.update(worksheet="Página1", data=df)
        # Recarrega a página para atualizar as barras de progresso visualmente
        st.rerun() 
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

# --- Interface Principal ---
def main():
    st.title("🩺 MedTracker - Acompanhamento de Estudos")
    st.markdown("---")

    # Carregar dados
    # Não usamos session_state complexo aqui para forçar a leitura fresca sempre que interagir
    df = load_data()

    if df.empty:
        st.warning("Não foi possível carregar a planilha. Verifique a conexão.")
        return

    # 1. Escolha do Usuário
    users = ["Ana Clara", "Gabriel", "Newton"]
    selected_user = st.sidebar.selectbox("Quem é você?", users)
    
    st.sidebar.markdown(f"## Olá, **{selected_user}**!")
    st.sidebar.info("Marque as aulas conforme for assistindo. O progresso é salvo na nuvem automaticamente. ☁️")

    # 2. Ordem das Disciplinas
    ordem_disciplinas = [
        "Cardiologia", "Pneumologia", "Endocrinologia", "Nefrologia", 
        "Gastroenterologia", "Hepatologia", "Infectologia", "Hematologia", 
        "Reumatologia", "Neurologia", "Psiquiatria", "Cirurgia", 
        "Ginecologia", "Obstetrícia", "Pediatria", "Preventiva", 
        "Dermatologia", "Ortopedia", "Otorrinolaringologia", "Oftalmologia"
    ]

    # Organiza disciplinas existentes e extras
    disciplinas_existentes = [d for d in ordem_disciplinas if d in df['Disciplina'].unique()]
    outras = [d for d in df['Disciplina'].unique() if d not in ordem_disciplinas]
    disciplinas_finais = disciplinas_existentes + outras

    # --- Área de Progresso Geral ---
    total_aulas = len(df)
    aulas_assistidas = df[selected_user].sum()
    progresso_geral = aulas_assistidas / total_aulas if total_aulas > 0 else 0
    
    st.metric(label="Progresso Total", value=f"{progresso_geral:.1%}", delta=f"{aulas_assistidas}/{total_aulas} Aulas")
    st.progress(progresso_geral)
    
    st.markdown("---")

    # 3. Exibição por Disciplina
    # Criamos um container para as disciplinas
    for disciplina in disciplinas_finais:
        # Filtrar o dataframe para esta disciplina
        df_disc_index = df[df['Disciplina'] == disciplina].index
        df_disc = df.loc[df_disc_index]
        
        # Calcular progresso da disciplina
        total_disc = len(df_disc)
        completed_disc = df_disc[selected_user].sum()
        prog_disc_val = completed_disc / total_disc if total_disc > 0 else 0
        
        icon = "✅" if prog_disc_val == 1.0 else "📚"
        
        with st.expander(f"{icon} {disciplina} ({completed_disc}/{total_disc})"):
            st.progress(prog_disc_val)
            
            # Configuração das colunas para edição
            cols_to_show = ['Semana', 'Aula', selected_user]
            
            # Tabela Editável
            edited_df_disc = st.data_editor(
                df_disc[cols_to_show],
                column_config={
                    selected_user: st.column_config.CheckboxColumn(
                        "Assistida?",
                        help="Marque para salvar no Google Sheets",
                        default=False,
                    ),
                    "Semana": st.column_config.NumberColumn(format="%d"),
                },
                disabled=["Semana", "Aula"], 
                hide_index=True,
                key=f"editor_{disciplina}_{selected_user}"
            )

            # Lógica de Salvamento
            # Comparamos se houve mudança entre o original e o editado
            # Precisamos comparar
