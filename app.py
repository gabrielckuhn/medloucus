import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import time

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker Residência", page_icon="🩺", layout="wide")

# --- CSS Personalizado (Cards e Botões) ---
st.markdown("""
    <style>
    /* Ajuste do container */
    .block-container {padding-top: 2rem; padding-bottom: 5rem;}
    
    /* Estilo do Card na Grid */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: white;
        border-radius: 12px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: transform 0.2s;
    }
    
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: #3498db;
        transform: translateY(-2px);
        box-shadow: 0 8px 12px rgba(0,0,0,0.1);
    }
    
    /* Botão de "Voltar" */
    div.stButton > button {
        width: 100%;
        border-radius: 8px;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

# --- Configurações da Planilha ---
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1-i82jvSfNzG2Ri7fu3vmOFnIYqQYglapbQ7x0000_rc/edit?usp=sharing"

# --- Conexão Google Sheets ---
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
    try:
        sh = gc.open_by_url(PLANILHA_URL)
        try: worksheet = sh.worksheet("Dados")
        except: worksheet = sh.get_worksheet(0)
        return pd.DataFrame(worksheet.get_all_records()), worksheet
    except: return pd.DataFrame(), None

def atualizar_status(worksheet, row_index, col_name, novo_valor):
    try:
        col_index = worksheet.find(col_name).col
        worksheet.update_cell(row_index + 2, col_index, novo_valor)
        st.toast("✅ Salvo!", icon="💾")
    except: st.error("Erro ao salvar.")

def limpar_booleano(valor):
    if isinstance(valor, bool): return valor
    if isinstance(valor, str): return valor.upper() == 'TRUE'
    return False

# --- Inicialização de Estado (Session State) ---
if 'disciplina_ativa' not in st.session_state:
    st.session_state['disciplina_ativa'] = None

# --- App Principal ---

df, worksheet = carregar_dados()

if not df.empty and worksheet is not None:
    usuarios = ["Ana Clara", "Gabriel", "Newton"]
    
    # --- Sidebar ---
    st.sidebar.title("🩺 MedTracker")
    usuario_selecionado = st.sidebar.selectbox("Perfil", usuarios)
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("🏆 Ranking")
    
    ranking_data = []
    total_global = len(df)
    for user in usuarios:
        pct = df[user].apply(limpar_booleano).sum() / total_global if total_global > 0 else 0
        ranking_data.append({"nome": user, "pct": pct})
    ranking_data.sort(key=lambda x: (-x['pct'], x['nome']))
    
    for i, data in enumerate(ranking_data):
        medalha = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}º"
        col_rk1, col_rk2 = st.sidebar.columns([0.8, 0.2])
        col_rk1.write(f"{medalha} {data['nome']}")
        col_rk1.progress(data['pct'])
        col_rk2.write(f"{int(data['pct']*100)}%")

    # --- Lógica de Visualização (Grade vs Foco) ---
    
    # 1. Modo FOCO (Disciplina Aberta em Tela Cheia)
    if st.session_state['disciplina_ativa']:
        disciplina_atual = st.session_state['disciplina_ativa']
        
        # Botão para voltar
        if st.button("⬅️ Voltar para todas as disciplinas"):
            st.session_state['disciplina_ativa'] = None
            st.rerun()
            
        st.markdown(f"## 📖 {disciplina_atual}")
        
        df_disc = df[df['Disciplina'] == disciplina_atual]
        status = df_disc[usuario_selecionado].apply(limpar_booleano)
        feitos = status.sum()
        total = len(df_disc)
        pct = feitos / total if total > 0 else 0
        
        st.progress(pct)
        st.caption(f"Progresso: {int(pct*100)}% ({feitos}/{total} aulas)")
        st.markdown("---")
        
        # Lista de Aulas (Checkboxes)
        for idx, row in df_disc.iterrows():
            checked = limpar_booleano(row[usuario_selecionado])
            
            c_check, c_text = st.columns([0.05, 0.95])
            with c_check:
                key = f"chk_focus_{idx}_{usuario_selecionado}"
                
                # --- CORREÇÃO AQUI ---
                # Adicionamos um rótulo ("Marcar") e usamos label_visibility="collapsed"
                # Isso satisfaz o sistema e esconde o texto para o usuário
                novo = st.checkbox(
                    "Marcar", 
                    value=checked, 
                    key=key, 
                    label_visibility="collapsed"
                )
                
            with c_text:
                txt = f"**Semana {row['Semana']}**: {row['Aula']}"
                if checked:
                    st.markdown(f"<span style='color:gray; text-decoration:line-through; opacity:0.6'>{txt}</span>", unsafe_allow_html=True)
                else:
                    st.markdown(txt)
            
            if novo != checked:
                atualizar_status(worksheet, idx, usuario_selecionado, novo)
                time.sleep(0.5)
                st.rerun()

    # 2. Modo GRADE (Cards 2 por linha)
    else:
        # Cabeçalho do usuário
        coluna_user = df[usuario_selecionado].apply(limpar_booleano)
        pct_total = coluna_user.sum() / len(df) if len(df) > 0 else 0
        
        st.title(f"Painel de {usuario_selecionado}")
        st.metric("Progresso Geral da Residência", f"{int(pct_total*100)}%")
        st.progress(pct_total)
        st.markdown("---")
        
        # Preparação das Disciplinas
        ordem = [
            "Cardiologia", "Pneumologia", "Endocrinologia", "Nefrologia", "Gastroenterologia", 
            "Hepatologia", "Infectologia", "Hematologia", "Reumatologia", "Neurologia", 
            "Psiquiatria", "Cirurgia", "Ginecologia", "Obstetrícia", "Pediatria", 
            "Preventiva", "Dermatologia", "Ortopedia", "Otorrinolaringologia", "Oftalmologia"
        ]
        disc_existentes = df['Disciplina'].unique()
        lista_final = [d for d in ordem if d in disc_existentes] + [d for d in disc_existentes if d not in ordem]
        
        # Criação das colunas (Grid 2xN)
        cols = st.columns(2)
        
        for i, disciplina in enumerate(lista_final):
            # Alterna entre coluna 0 e 1
            col_atual = cols[i % 2]
            
            df_d = df[df['Disciplina'] == disciplina]
            feitos_d = df_d[usuario_selecionado].apply(limpar_booleano).sum()
            total_d = len(df_d)
            pct_d = feitos_d / total_d if total_d > 0 else 0
            
            with col_atual:
                # Container com borda (Card Visual)
                with st.container(border=True):
                    # Cabeçalho do Card
                    st.markdown(f"### {disciplina}")
                    st.progress(pct_d)
                    
                    c1, c2 = st.columns([0.7, 0.3])
                    c1.caption(f"{int(pct_d*100)}% concluído")
                    
                    if c2.button("Abrir ➝", key=f"btn_{disciplina}"):
                        st.session_state['disciplina_ativa'] = disciplina
                        st.rerun()

else:
    st.error("Erro ao carregar dados.")
