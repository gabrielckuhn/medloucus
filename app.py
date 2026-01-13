import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import time

# --- Configuração da Página ---
st.set_page_config(page_title="MedTracker Residência", page_icon="🩺", layout="wide")

# --- CSS Personalizado ---
st.markdown("""
    <style>
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
    
    /* Botão dentro do Card */
    div.stButton > button {
        width: 100%; 
        border-radius: 8px; 
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

# --- Configurações ---
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1-i82jvSfNzG2Ri7fu3vmOFnIYqQYglapbQ7x0000_rc/edit?usp=sharing"

# --- Conexão Google Sheets ---
@st.cache_resource
def conectar_google_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        credentials = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        return gspread.authorize(credentials)
    except: return None

# Função de carregamento com RETRY (Anti-Erro)
def carregar_dados():
    gc = conectar_google_sheets()
    if not gc: return pd.DataFrame(), None
    
    # Tenta ler até 3 vezes se der erro de conexão
    for tentativa in range(3):
        try:
            sh = gc.open_by_url(PLANILHA_URL)
            try: worksheet = sh.worksheet("Dados")
            except: worksheet = sh.get_worksheet(0)
            
            return pd.DataFrame(worksheet.get_all_records()), worksheet
        except Exception as e:
            time.sleep(1.5) # Espera um pouco
            if tentativa == 2:
                st.error(f"O servidor do Google está instável. Erro: {e}")
                return pd.DataFrame(), None

# Salvar Otimizado (Usa índice numérico da coluna)
def atualizar_status(worksheet, row_index, col_index_num, novo_valor):
    try:
        # row_index + 2 (cabeçalho + base 1 do gspread)
        worksheet.update_cell(row_index + 2, col_index_num, novo_valor)
    except Exception as e:
        st.warning("Tentando salvar novamente...")
        time.sleep(1)
        try:
            worksheet.update_cell(row_index + 2, col_index_num, novo_valor)
        except:
            st.error("Erro ao salvar. Verifique sua internet.")

def limpar_booleano(valor):
    if isinstance(valor, bool): return valor
    if isinstance(valor, str): return valor.upper() == 'TRUE'
    return False

# --- Inicialização de Estado ---
if 'disciplina_ativa' not in st.session_state:
    st.session_state['disciplina_ativa'] = None

# --- App Principal ---

df, worksheet = carregar_dados()

if not df.empty and worksheet is not None:
    # --- LISTA DE USUÁRIOS ATUALIZADA ---
    usuarios = ["Ana Clara", "Arthur", "Gabriel", "Lívian", "Newton", "Rafa"]
    
    # Sidebar
    st.sidebar.title("🩺 MedTracker")
    
    # Verifica se os novos usuários estão na planilha antes de mostrar o seletor
    # Se algum nome não estiver no cabeçalho da planilha, o código avisa para evitar crash
    colunas_presentes = [u for u in usuarios if u in df.columns]
    
    if len(colunas_presentes) < len(usuarios):
        st.sidebar.error("Atenção: Alguns nomes do código não foram encontrados na planilha. Verifique o cabeçalho do Google Sheets.")
    
    usuario_selecionado = st.sidebar.selectbox("Perfil", colunas_presentes if colunas_presentes else usuarios)
    
    # Otimização: Índice da coluna do usuário
    try:
        if usuario_selecionado in df.columns:
            coluna_usuario_idx = df.columns.get_loc(usuario_selecionado) + 1
        else:
            coluna_usuario_idx = 0
    except:
        coluna_usuario_idx = 0

    st.sidebar.markdown("---")
    st.sidebar.subheader("🏆 Ranking")
    
    ranking_data = []
    total_global = len(df)
    
    # Calcula ranking apenas para colunas que existem
    for user in colunas_presentes:
        pct = df[user].apply(limpar_booleano).sum() / total_global if total_global > 0 else 0
        ranking_data.append({"nome": user, "pct": pct})
    ranking_data.sort(key=lambda x: (-x['pct'], x['nome']))
    
    for i, data in enumerate(ranking_data):
        medalha = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}º"
        c1, c2 = st.sidebar.columns([0.8, 0.2])
        c1.write(f"{medalha} {data['nome']}")
        c1.progress(data['pct'])
        c2.write(f"{int(data['pct']*100)}%")

    # --- Lógica de Visualização ---
    
    # 1. Modo FOCO (Disciplina Aberta)
    if st.session_state['disciplina_ativa']:
        disciplina_atual = st.session_state['disciplina_ativa']
        
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
        # Texto detalhado
        st.caption(f"**Status:** {int(pct*100)}% concluído — {feitos} de {total} aulas assistidas")
        st.markdown("---")
        
        for idx, row in df_disc.iterrows():
            checked = limpar_booleano(row[usuario_selecionado])
            
            c_chk, c_txt = st.columns([0.05, 0.95])
            with c_chk:
                key = f"chk_focus_{idx}_{usuario_selecionado}"
                novo = st.checkbox("Marcar", value=checked, key=key, label_visibility="collapsed")
                
            with c_txt:
                txt = f"**Semana {row['Semana']}**: {row['Aula']}"
                if checked:
                    st.markdown(f"<span style='color:gray; text-decoration:line-through; opacity:0.6'>{txt}</span>", unsafe_allow_html=True)
                else:
                    st.markdown(txt)
            
            if novo != checked:
                atualizar_status(worksheet, idx, coluna_usuario_idx, novo)
                st.toast("✅ Salvo!", icon="💾")
                time.sleep(0.5) 
                st.rerun()

    # 2. Modo GRADE (Cards)
    else:
        coluna_user = df[usuario_selecionado].apply(limpar_booleano)
        pct_total = coluna_user.sum() / len(df) if len(df) > 0 else 0
        
        st.title(f"Painel de {usuario_selecionado}")
        st.metric("Progresso Geral da Residência", f"{int(pct_total*100)}%")
        st.progress(pct_total)
        st.markdown("---")
        
        ordem = [
            "Cardiologia", "Pneumologia", "Endocrinologia", "Nefrologia", "Gastroenterologia", 
            "Hepatologia", "Infectologia", "Hematologia", "Reumatologia", "Neurologia", 
            "Psiquiatria", "Cirurgia", "Ginecologia", "Obstetrícia", "Pediatria", 
            "Preventiva", "Dermatologia", "Ortopedia", "Otorrinolaringologia", "Oftalmologia"
        ]
        disc_existentes = df['Disciplina'].unique()
        lista_final = [d for d in ordem if d in disc_existentes] + [d for d in disc_existentes if d not in ordem]
        
        cols = st.columns(2)
        
        for i, disciplina in enumerate(lista_final):
            col_atual = cols[i % 2]
            df_d = df[df['Disciplina'] == disciplina]
            feitos_d = df_d[usuario_selecionado].apply(limpar_booleano).sum()
            total_d = len(df_d)
            pct_d = feitos_d / total_d if total_d > 0 else 0
            
            with col_atual:
                with st.container(border=True):
                    st.markdown(f"### {disciplina}")
                    st.progress(pct_d)
                    
                    # Layout Coluna: Texto Informativo | Botão
                    c1, c2 = st.columns([0.65, 0.35])
                    
                    c1.caption(f"**{int(pct_d*100)}%** — {feitos_d} de {total_d} aulas")
                    
                    if c2.button("Abrir ➝", key=f"btn_{disciplina}"):
                        st.session_state['disciplina_ativa'] = disciplina
                        st.rerun()

else:
    st.error("Aguardando conexão com o Google...")
