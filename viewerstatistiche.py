import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
import json
from datetime import datetime

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="KKK Log Viewer Pro", layout="wide", page_icon="📊")

# --- 1. CORE PARSING LOGIC ---
def parse_kkk_file(uploaded_file):
    """
    Parser robusto per il formato .KKK che gestisce sessioni e stream di immagini.
    """
    lines = uploaded_file.getvalue().decode("utf-8").splitlines()
    
    data = []
    session_info = {"folder": "Unknown", "tool_version": "Unknown", "session_start": None}
    current_image = {}
    in_image_block = False

    for line in lines:
        line = line.strip()
        
        # Gestione Sessione
        if line.startswith("SESSION_START"):
            # Reset session info
            pass 
        elif line.startswith("folder="):
            session_info["folder"] = line.split("=")[1]
        elif line.startswith("start_time="):
            session_info["session_start"] = line.split("=")[1]

        # Gestione Immagine Start
        elif line.startswith("IMAGE_START"):
            in_image_block = True
            parts = line.split()
            filename = parts[1]
            # Estrazione timestamp se presente nella riga START
            img_time = parts[2].split("=")[1] if len(parts) > 2 else None
            
            current_image = {
                "session_folder": session_info["folder"],
                "filename": filename,
                "timestamp_start": img_time,
                # Default values (per gestire campi mancanti)
                "actions": 0, "undos": 0, "redos": 0, "ocr_edits": 0,
                "num_letta_plate": 0, "num_ocr": 0, "ocr_validated": 0,
                "ocr_not_validated": 0, "time_spent_sec": 0.0,
                "modified": "False", "saved": "False"
            }

        # Parsing Key-Value dentro il blocco immagine
        elif in_image_block and "=" in line and not line.startswith("IMAGE_END"):
            try:
                key, val = line.split("=")
                # Parsing intelligente dei tipi
                if val.lower() == "true": val = True
                elif val.lower() == "false": val = False
                elif val.replace('.', '', 1).isdigit(): val = float(val) if '.' in val else int(val)
                
                current_image[key] = val
            except Exception:
                pass # Ignora righe malformate

        # Gestione Immagine End
        elif line.startswith("IMAGE_END"):
            if current_image:
                data.append(current_image)
            in_image_block = False
            current_image = {}

    return pd.DataFrame(data)

# --- 2. DATA ENRICHMENT (KPIs) ---
def enrich_data(df):
    if df.empty:
        return df
    
    # 4.1 Indice di Difficoltà (Actions + Undos + Redos + OCR Edits)
    df['complexity_score'] = df['actions'] + df['undos'] + df['redos'] + df['ocr_edits']
    
    # 4.5 Efficienza (Tempo speso / Azioni). Gestione divisione per zero.
    df['efficiency_sec_per_action'] = df.apply(
        lambda x: x['time_spent_sec'] / x['actions'] if x['actions'] > 0 else 0, axis=1
    )

    # Flag Anomalie
    # Esempio: Tempo > 60s ma poche azioni (<3), oppure troppi Undo (>5)
    df['is_anomaly'] = (
        ((df['time_spent_sec'] > 60) & (df['actions'] < 3)) | 
        (df['undos'] > 5) |
        (df['time_spent_sec'] > 120)
    )
    
    return df

# --- 3. UI DASHBOARD ---
st.title("📊 Viewer Analitico Log Annotazione (.KKK)")
st.markdown("Analisi KPI Operatore, Quality Gate e Anomalie")

uploaded_file = st.sidebar.file_uploader("Carica file .KKK", type=["kkk", "txt"])

if uploaded_file is not None:
    # 1. Parsing
    raw_df = parse_kkk_file(uploaded_file)
    df = enrich_data(raw_df)

    # Sidebar Filtri
    st.sidebar.header("Filtri")
    if 'session_folder' in df.columns:
        folders = df['session_folder'].unique()
        selected_folder = st.sidebar.multiselect("Seleziona Cartella/Sessione", folders, default=folders)
        if selected_folder:
            df = df[df['session_folder'].isin(selected_folder)]

    # --- SEZIONE 1: STATISTICHE DI SESSIONE (Il "Must Have") ---
    st.header("1. Panoramica Sessione (KPI Alti)")
    
    col1, col2, col3, col4 = st.columns(4)
    
    total_time = df['time_spent_sec'].sum()
    avg_time = df['time_spent_sec'].mean()
    total_imgs = len(df)
    total_actions = df['actions'].sum()

    with col1:
        st.metric("⏱️ Tempo Totale", f"{total_time/60:.1f} min")
    with col2:
        st.metric("🖼️ Immagini Elaborate", f"{total_imgs}")
    with col3:
        st.metric("⚡ Media Sec/Img", f"{avg_time:.2f} s", delta_color="inverse", delta=f"{avg_time - 30:.1f} vs Target 30s")
    with col4:
        st.metric("🖱️ Totale Azioni", f"{total_actions}")

    st.markdown("---")

    # --- SEZIONE 2: QUALITY GATE AUTOMATICI ---
    st.header("2. Quality Gates & Anomalie")
    
    col_q1, col_q2 = st.columns([1, 2])
    
    with col_q1:
        st.subheader("⚠️ Alert Anomalie")
        anomalies = df[df['is_anomaly'] == True]
        if not anomalies.empty:
            st.error(f"Trovate {len(anomalies)} immagini sospette!")
            st.dataframe(anomalies[['filename', 'time_spent_sec', 'actions', 'undos', 'complexity_score']], hide_index=True)
        else:
            st.success("Nessuna anomalia rilevata. Flusso pulito.")

    with col_q2:
        st.subheader("🔍 Distribuzione Tempo vs Complessità")
        # Scatter plot: Asse X = Tempo, Asse Y = Complessità (Azioni)
        # Se un punto è in basso a destra (Tanto tempo, poche azioni) = Distrazione
        # Se un punto è in alto a sinistra (Poco tempo, tante azioni) = Operatore veloce/esperto
        fig_scatter = px.scatter(
            df, 
            x="time_spent_sec", 
            y="complexity_score", 
            color="is_anomaly",
            hover_data=['filename', 'undos', 'ocr_validated'],
            title="Analisi Performance: Tempo vs Azioni",
            color_discrete_map={False: "blue", True: "red"}
        )
        # Linee di soglia (Quality Gate visivi)
        fig_scatter.add_vline(x=60, line_dash="dash", line_color="orange", annotation_text="Warning Time")
        st.plotly_chart(fig_scatter, use_container_width=True)

    # --- SEZIONE 3: STATISTICHE OCR (Se presenti) ---
    st.markdown("---")
    st.header("3. Dettaglio OCR & Validazione")
    
    # Aggregazione dati OCR
    ocr_cols = ['num_ocr', 'ocr_validated', 'ocr_not_validated', 'num_letta_plate']
    if all(col in df.columns for col in ocr_cols):
        ocr_sums = df[ocr_cols].sum()
        
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("🔢 Targhe Totali OCR", int(ocr_sums['num_ocr']))
        with c2:
            st.metric("✅ Validate", int(ocr_sums['ocr_validated']))
        with c3:
            # Calcolo % Validazione
            val_rate = (ocr_sums['ocr_validated'] / ocr_sums['num_ocr'] * 100) if ocr_sums['num_ocr'] > 0 else 0
            st.metric("📊 Tasso Validazione", f"{val_rate:.1f}%")
            
        # Grafico a barre impilate per immagine (mostra solo le prime 50 per leggibilità)
        st.caption("Dettaglio validazione per le ultime 30 immagini elaborate:")
        df_chart = df.tail(30)
        fig_ocr = go.Figure(data=[
            go.Bar(name='Validate', x=df_chart['filename'], y=df_chart['ocr_validated'], marker_color='green'),
            go.Bar(name='Non Validate', x=df_chart['filename'], y=df_chart['ocr_not_validated'], marker_color='red')
        ])
        fig_ocr.update_layout(barmode='stack', title="Validazione OCR per Immagine", xaxis_tickangle=-45)
        st.plotly_chart(fig_ocr, use_container_width=True)

    # --- SEZIONE 4: DATA TABLE & EXPORT ---
    st.markdown("---")
    st.header("4. Export Dati")
    
    st.dataframe(df, use_container_width=True)
    
    col_exp1, col_exp2 = st.columns(2)
    
    # Export CSV
    csv = df.to_csv(index=False).encode('utf-8')
    col_exp1.download_button(
        label="📥 Download CSV Report",
        data=csv,
        file_name='kpi_report.csv',
        mime='text/csv',
    )
    
    # Export JSON
    json_str = df.to_json(orient="records", date_format="iso")
    col_exp2.download_button(
        label="📥 Download JSON Report",
        data=json_str,
        file_name='kpi_report.json',
        mime='application/json',
    )

else:
    st.info("Carica un file .KKK per iniziare l'analisi.")
    # Esempio di struttura attesa per l'utente
    st.markdown("""
    ### Struttura file supportata
    Il sistema si aspetta blocchi `IMAGE_START` ... `IMAGE_END` contenenti chiavi come:
    - `time_spent_sec`
    - `actions`
    - `undos` / `redos`
    - Dati OCR (`ocr_validated`, ecc.)
    """)