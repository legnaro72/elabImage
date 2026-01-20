import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
import json

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="KPI Log Viewer Pro", layout="wide", page_icon="📈")

# --- 1. CORE PARSING LOGIC ---
def parse_kpi_file(uploaded_file):
    """
    Parser aggiornato per file .KPI.
    Tenta di leggere formati standard (CSV/JSON).
    Se il formato è custom (testo), usa la logica legacy o necessita adattamento.
    """
    content = uploaded_file.getvalue()
    filename = uploaded_file.name.lower()
    
    # TENTATIVO 1: È un JSON standard?
    try:
        data = json.loads(content)
        # Se è una lista di dizionari, è perfetto
        if isinstance(data, list):
            return pd.DataFrame(data)
        # Se è un dizionario con una chiave "data" o "logs"
        elif isinstance(data, dict):
            return pd.DataFrame(data.get('data', [data]))
    except:
        pass

    # TENTATIVO 2: È un CSV standard?
    try:
        return pd.read_csv(io.BytesIO(content))
    except:
        pass

    # TENTATIVO 3: Formato Custom (Legacy KKK adattato)
    # Se il file KPI mantiene la struttura "IMAGE_START" / "IMAGE_END"
    try:
        lines = content.decode("utf-8", errors='ignore').splitlines()
        data = []
        session_info = {"folder": "Unknown", "session_start": None}
        current_image = {}
        in_image_block = False

        for line in lines:
            line = line.strip()
            
            if line.startswith("folder="):
                session_info["folder"] = line.split("=")[1]
            
            # Adattare qui se i tag sono cambiati (es. KPI_START invece di IMAGE_START)
            elif line.startswith("IMAGE_START") or line.startswith("KPI_START"):
                in_image_block = True
                parts = line.split()
                # Gestione robusta se mancano pezzi
                filename_img = parts[1] if len(parts) > 1 else "unknown"
                
                current_image = {
                    "session_folder": session_info["folder"],
                    "filename": filename_img,
                    # Default values per KPI
                    "actions": 0, "undos": 0, "time_spent_sec": 0.0,
                    "complexity_score": 0, "is_anomaly": False
                }

            elif in_image_block and "=" in line and not (line.startswith("IMAGE_END") or line.startswith("KPI_END")):
                try:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    
                    if val.lower() == "true": val = True
                    elif val.lower() == "false": val = False
                    elif val.replace('.', '', 1).isdigit(): val = float(val) if '.' in val else int(val)
                    
                    current_image[key] = val
                except:
                    pass

            elif line.startswith("IMAGE_END") or line.startswith("KPI_END"):
                if current_image:
                    data.append(current_image)
                in_image_block = False
                current_image = {}
        
        if data:
            return pd.DataFrame(data)
            
    except Exception as e:
        st.error(f"Errore nel parsing custom: {e}")

    # Se tutto fallisce
    st.error("Formato file non riconosciuto. Assicurati che sia un CSV, JSON o il formato Custom corretto.")
    return pd.DataFrame()

# --- 2. DATA ENRICHMENT (KPIs) ---
def enrich_data(df):
    if df.empty:
        return df
    
    # Normalizzazione nomi colonne (se il file KPI usa nomi diversi)
    # Esempio: se nel nuovo file si chiama 'duration' invece di 'time_spent_sec'
    if 'duration' in df.columns and 'time_spent_sec' not in df.columns:
        df['time_spent_sec'] = df['duration']
    
    # Assicuriamo che le colonne esistano per evitare crash
    required_cols = ['actions', 'undos', 'redos', 'ocr_edits', 'time_spent_sec']
    for col in required_cols:
        if col not in df.columns:
            df[col] = 0

    # 4.1 Indice di Difficoltà
    df['complexity_score'] = df['actions'] + df['undos'] + df['redos'] + df['ocr_edits']
    
    # 4.5 Efficienza
    df['efficiency_sec_per_action'] = df.apply(
        lambda x: x['time_spent_sec'] / x['actions'] if x['actions'] > 0 else 0, axis=1
    )

    # Flag Anomalie
    df['is_anomaly'] = (
        ((df['time_spent_sec'] > 60) & (df['actions'] < 3)) | 
        (df['undos'] > 5) |
        (df['time_spent_sec'] > 120)
    )
    
    return df

# --- 3. UI DASHBOARD ---
st.title("📈 KPI Viewer Analitico")
st.markdown("Analisi Performance e Metriche Operative (File .KPI)")

# Accetta .kpi, .csv, .json, .txt
uploaded_file = st.sidebar.file_uploader("Carica file KPI", type=["kpi", "txt", "csv", "json"])

if uploaded_file is not None:
    # 1. Parsing
    raw_df = parse_kpi_file(uploaded_file)
    
    if not raw_df.empty:
        df = enrich_data(raw_df)

        # Sidebar Filtri
        st.sidebar.header("Filtri")
        if 'session_folder' in df.columns:
            folders = df['session_folder'].unique()
            selected_folder = st.sidebar.multiselect("Seleziona Sessione", folders, default=folders)
            if selected_folder:
                df = df[df['session_folder'].isin(selected_folder)]

        # --- SEZIONE 1: KPI PRINCIPALI ---
        st.header("1. Performance Generali")
        
        col1, col2, col3, col4 = st.columns(4)
        
        total_time = df['time_spent_sec'].sum()
        avg_time = df['time_spent_sec'].mean()
        total_items = len(df)
        total_actions = df['actions'].sum()

        with col1:
            st.metric("⏱️ Tempo Totale", f"{total_time/60:.1f} min")
        with col2:
            st.metric("📄 Elementi Analizzati", f"{total_items}")
        with col3:
            st.metric("⚡ Media Sec/Item", f"{avg_time:.2f} s")
        with col4:
            st.metric("🖱️ Totale Azioni", f"{total_actions}")

        st.markdown("---")

        # --- SEZIONE 2: ANOMALIE & QUALITÀ ---
        st.header("2. Qualità & Anomalie")
        
        col_q1, col_q2 = st.columns([1, 2])
        
        with col_q1:
            st.subheader("⚠️ Alert Anomalie")
            anomalies = df[df['is_anomaly'] == True]
            if not anomalies.empty:
                st.error(f"Rilevati {len(anomalies)} casi anomali")
                # Mostra colonne rilevanti se esistono
                cols_to_show = [c for c in ['filename', 'time_spent_sec', 'actions', 'complexity_score'] if c in df.columns]
                st.dataframe(anomalies[cols_to_show], hide_index=True)
            else:
                st.success("Nessuna anomalia rilevata.")

        with col_q2:
            st.subheader("🔍 Performance: Tempo vs Azioni")
            if 'complexity_score' in df.columns and 'time_spent_sec' in df.columns:
                fig_scatter = px.scatter(
                    df, 
                    x="time_spent_sec", 
                    y="complexity_score", 
                    color="is_anomaly",
                    hover_data=[c for c in ['filename', 'undos'] if c in df.columns],
                    title="Distribuzione Sforzo Operativo",
                    color_discrete_map={False: "blue", True: "red"}
                )
                st.plotly_chart(fig_scatter, use_container_width=True)
            else:
                st.info("Dati insufficienti per il grafico (mancano colonne tempo/azioni).")

        # --- SEZIONE 3: DATA TABLE & EXPORT ---
        st.markdown("---")
        st.header("3. Dati Dettagliati")
        
        st.dataframe(df, use_container_width=True)
        
        col_exp1, col_exp2 = st.columns(2)
        
        # Export CSV
        csv = df.to_csv(index=False).encode('utf-8')
        col_exp1.download_button(
            label="📥 Download CSV Report",
            data=csv,
            file_name='kpi_export.csv',
            mime='text/csv',
        )
        
        # Export JSON
        json_str = df.to_json(orient="records", date_format="iso")
        col_exp2.download_button(
            label="📥 Download JSON Report",
            data=json_str,
            file_name='kpi_export.json',
            mime='application/json',
        )
    else:
        st.warning("Il file sembra vuoto o il formato non è stato riconosciuto.")
else:
    st.info("Carica un file .KPI (o .csv/.json) per iniziare.")