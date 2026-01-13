import streamlit as st
import pandas as pd
import os

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker", page_icon="🩺", layout="wide")

# --- Nome do Arquivo de Dados ---
# Para testar localmente, crie um arquivo Excel com as colunas corretas
DATA_FILE = 'dados.xlsx'


# --- Funções de Carregamento e Salvamento ---
def load_data():
    if os.path.exists(DATA_FILE):
        # Tenta ler como Excel, se falhar tenta CSV
        try:
            df = pd.read_excel(DATA_FILE)
        except:
            df = pd.read_csv(DATA_FILE)

        # Garante que as colunas de usuários sejam booleanas (True/False)
        users = ["Ana Clara", "Gabriel", "Newton"]
        for user in users:
            if user in df.columns:
                df[user] = df[user].astype(bool)
        return df
    else:
        st.error(f"Arquivo {DATA_FILE} não encontrado!")
        return pd.DataFrame()


def save_data(df):
    # Salva no arquivo local (Para versão online, aqui entraria o código do Google Sheets)
    df.to_excel(DATA_FILE, index=False)


# --- Interface Principal ---
def main():
    st.title("🩺 MedTracker - Acompanhamento de Estudos")
    st.markdown("---")

    # Carregar dados
    if 'df' not in st.session_state:
        st.session_state.df = load_data()

    df = st.session_state.df

    if df.empty:
        st.warning("A planilha está vazia ou não foi carregada.")
        return

    # 1. Escolha do Usuário
    users = ["Ana Clara", "Gabriel", "Newton"]
    selected_user = st.sidebar.selectbox("Quem é você?", users)

    st.sidebar.markdown(f"## Olá, **{selected_user}**!")
    st.sidebar.info("Marque as aulas conforme for assistindo. O progresso é salvo automaticamente.")

    # 2. Ordem das Disciplinas (conforme solicitado)
    ordem_disciplinas = [
        "Cardiologia", "Pneumologia", "Endocrinologia", "Nefrologia",
        "Gastroenterologia", "Hepatologia", "Infectologia", "Hematologia",
        "Reumatologia", "Neurologia", "Psiquiatria", "Cirurgia",
        "Ginecologia", "Obstetrícia", "Pediatria", "Preventiva",
        "Dermatologia", "Ortopedia", "Otorrinolaringologia", "Oftalmologia"
    ]

    # Filtrar apenas disciplinas que existem na planilha para evitar erros
    disciplinas_existentes = [d for d in ordem_disciplinas if d in df['Disciplina'].unique()]

    # Se houver disciplinas na planilha que não estão na lista fixa, adicione-as no final
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
    for disciplina in disciplinas_finais:
        # Filtrar o dataframe para esta disciplina
        df_disc = df[df['Disciplina'] == disciplina]

        # Calcular progresso da disciplina
        total_disc = len(df_disc)
        completed_disc = df_disc[selected_user].sum()
        prog_disc_val = completed_disc / total_disc if total_disc > 0 else 0

        # Cor do ícone baseada no progresso
        icon = "✅" if prog_disc_val == 1.0 else "📚"

        # Expander para a disciplina
        with st.expander(f"{icon} {disciplina} ({completed_disc}/{total_disc})"):

            # Barra de progresso interna
            st.progress(prog_disc_val)

            # Criamos colunas para organizar melhor
            # Usaremos st.data_editor para permitir edição rápida em massa,
            # ou checkbox individual. O data_editor é mais limpo visualmente.

            cols_to_show = ['Semana', 'Aula', selected_user]

            # Exibe tabela editável
            edited_df = st.data_editor(
                df_disc[cols_to_show],
                column_config={
                    selected_user: st.column_config.CheckboxColumn(
                        "Assistida?",
                        help="Marque se já assistiu a aula",
                        default=False,
                    ),
                    "Semana": st.column_config.NumberColumn(format="%d"),
                },
                disabled=["Semana", "Aula"],  # Não deixa editar nome da aula nem semana
                hide_index=True,
                key=f"editor_{disciplina}_{selected_user}"  # Chave única
            )

            # Lógica de Salvamento
            # Se houve alteração na tabela editada, atualizamos o DF principal
            if not edited_df.equals(df_disc[cols_to_show]):
                # Atualiza os valores no dataframe principal usando o índice
                st.session_state.df.update(edited_df)
                save_data(st.session_state.df)  # Salva no arquivo físico
                st.rerun()  # Recarrega a página para atualizar as barras de progresso


if __name__ == "__main__":
    main()