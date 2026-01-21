import streamlit as st
import pandas as pd
import plotly.express as px
import os
import json
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="KPI Manager v6 - Dead Time Analysis", layout="wide", page_icon="⏱️")

# --- 1. PARSER AVANZATO CON TIMESTAMPS ---
@st.cache_data
def parse_kpi_file(uploaded_file):
    lines = uploaded_file.getvalue().decode("utf-8").splitlines()
    data = []
    session_info = {"folder": "", "start_time": None}
    current_image = {}
    in_image_block = False

    for line in lines:
        line = line.strip()
        
        if line.startswith("folder="):
            session_info["folder"] = line.split("=", 1)[1]
        
        elif line.startswith("IMAGE_START"):
            in_image_block = True
            parts = line.split()
            # Esempio: IMAGE_START nomefile.jpg time=2026-01-20T23:15:12
            filename = parts[1] if len(parts) > 1 else "Unknown"
            
            # Estrazione Timestamp Start Immagine
            img_start_time = None
            for part in parts:
                if part.startswith("time="):
                    try:
                        iso_str = part.split("=", 1)[1]
                        img_start_time = datetime.fromisoformat(iso_str)
                    except:
                        pass

            current_image = {
                "session_folder": session_info["folder"],
                "filename": filename,
                "timestamp_obj": img_start_time, # Cruciale per il tempo morto
                "actions": 0, "undos": 0, "redos": 0, "ocr_edits": 0,
                "num_ocr": 0, "ocr_validated": 0, "ocr_not_validated": 0,
                "time_spent_sec": 0.0, "modified": False, "saved": False
            }

        elif in_image_block and "=" in line and not line.startswith("IMAGE_END"):
            try:
                key, val = line.split("=", 1)
                if val.lower() == "true": val = True
                elif val.lower() == "false": val = False
                elif val.replace('.', '', 1).isdigit(): val = float(val) if '.' in val else int(val)
                current_image[key] = val
            except: pass

        elif line.startswith("IMAGE_END"):
            if current_image:
                data.append(current_image)
            in_image_block = False
            current_image = {}

    return pd.DataFrame(data)

def enrich_data(df):
    if df.empty: return df
    
    # 1. Calcolo TEMPO MORTO (Inter-Image Gap)
    # Ordiniamo per timestamp se presente
    if 'timestamp_obj' in df.columns:
        df = df.sort_values(by='timestamp_obj')
        
        # Shiftiamo per prendere il tempo della riga precedente
        df['prev_start'] = df['timestamp_obj'].shift(1)
        df['prev_work_duration'] = df['time_spent_sec'].shift(1)
        
        # Calcolo: (Inizio Ora - Inizio Prima) - Lavoro Prima = Tempo Morto
        def calc_dead_time(row):
            if pd.isnull(row['prev_start']) or pd.isnull(row['timestamp_obj']):
                return 0.0
            total_gap = (row['timestamp_obj'] - row['prev_start']).total_seconds()
            dead_time = total_gap - row['prev_work_duration']
            return max(0.0, dead_time) # Non può essere negativo

        df['dead_time_sec'] = df.apply(calc_dead_time, axis=1)
    else:
        df['dead_time_sec'] = 0.0

    # 2. Complessità e Anomalie
    cols_sum = [c for c in ['actions', 'undos', 'redos', 'ocr_edits'] if c in df.columns]
    df['complexity_score'] = df[cols_sum].sum(axis=1) if cols_sum else 0
    
    # Flag Anomalie (incluso dead time eccessivo)
    df['is_anomaly'] = (
        ((df['time_spent_sec'] > 45) & (df['actions'] < 2)) | 
        (df['undos'] > 4) |
        (df['dead_time_sec'] > 10) # Più di 10s tra una foto e l'altra è sospetto
    )
    
    return df

# --- 2. CARICAMENTO IMMAGINI "SMART" ---
def load_image_smart(filename, original_folder, override_path, use_override):
    """
    Tenta di trovare l'immagine in vari modi per evitare FileNotFoundError.
    """
    candidates = []
    
    # 1. Se Override è attivo, cerca SOLO lì dentro (basename)
    if use_override and override_path:
        candidates.append(os.path.join(override_path, filename))
    
    # 2. Percorso originale assoluto (dal log)
    candidates.append(os.path.join(original_folder, filename))
    
    # 3. Cartella corrente dello script
    candidates.append(os.path.join(os.getcwd(), filename))

    for path in candidates:
        if os.path.exists(path):
            return path
            
    return None

def draw_overlay(image, json_path):
    # (Stessa logica v5.0 per disegnare i box)
    ocr_results = []
    if not os.path.exists(json_path): return image, None
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            js = json.load(f)
        draw = ImageDraw.Draw(image)
        try: font = ImageFont.truetype("arial.ttf", 24)
        except: font = ImageFont.load_default()
        
        boxes = js.get('boxes', [])
        for item in boxes:
            cls = item.get('class', 'unk')
            if cls == "OCR":
                val = item.get('value', [""])[0]
                status = "✅" if item.get('validated') else "⚠️"
                ocr_results.append((f"OCR {status}", val))
                continue
            
            coords = item.get('coords', [])
            if len(coords) == 4:
                color = "red" if "plate" in cls.lower() or "targa" in cls.lower() else "#00FF00"
                x1,y1,x2,y2 = coords
                draw.rectangle(coords, outline=color, width=4)
                # Label background
                tb = draw.textbbox((x1,y1), cls, font=font)
                draw.rectangle([x1, y1-(tb[3]-tb[1]), x1+(tb[2]-tb[0]), y1], fill=color)
                draw.text((x1, y1-(tb[3]-tb[1])), cls, fill="white", font=font)
        return image, ocr_results
    except: return image, []

# --- 3. DASHBOARD UI ---
st.title("⏱️ KPI Manager v6 - Analisi Tempi & Produttività")

with st.sidebar:
    st.header("1. Log File")
    upl_file = st.file_uploader("Carica .KPI o .KKK", type=["kpi", "kkk", "txt"])
    
    st.divider()
    st.header("2. Gestione Errori Percorso")
    st.info("Se vedi 'File non trovato', attiva l'override e incolla il percorso dove hai le foto ORA.")
    use_override = st.checkbox("Attiva Override Percorso", value=True)
    path_override = st.text_input("Cartella Immagini Locale:", value=r"C:\Users\...")

if upl_file:
    df = enrich_data(parse_kpi_file(upl_file))
    
    t1, t2 = st.tabs(["📊 Statistiche Avanzate", "👁️ Ispezione Visiva"])
    
    with t1:
        # METRICHE DI SESSIONE
        st.subheader("Performance Operatore")
        k1, k2, k3, k4 = st.columns(4)
        
        tot_time_work = df['time_spent_sec'].sum()
        tot_dead_time = df['dead_time_sec'].sum()
        tot_actions = df['actions'].sum()
        
        k1.metric("Tempo Lavoro Effettivo", f"{tot_time_work/60:.1f} min")
        k2.metric("💤 Tempo Morto Totale", f"{tot_dead_time/60:.1f} min", 
                  delta="-spreco", delta_color="inverse")
        k3.metric("Azioni Totali", int(tot_actions))
        
        # Calcolo APM (Actions Per Minute)
        total_minutes = (tot_time_work + tot_dead_time) / 60
        apm = tot_actions / total_minutes if total_minutes > 0 else 0
        k4.metric("APM (Velocità)", f"{apm:.1f}", help="Azioni per Minuto")
        
        st.divider()
        
        # GRAFICI
        c_chart1, c_chart2 = st.columns(2)
        with c_chart1:
            # Istogramma Tempi Morti
            fig_dead = px.bar(df, x='filename', y='dead_time_sec', 
                              title="Tempo Perso tra Immagini (Dead Time)",
                              labels={'dead_time_sec': 'Secondi di pausa'},
                              color='dead_time_sec', color_continuous_scale='Reds')
            st.plotly_chart(fig_dead, use_container_width=True)
            
        with c_chart2:
            # Scatter Tempo vs Azioni
            fig_perf = px.scatter(df, x='time_spent_sec', y='actions', 
                                  color='is_anomaly', size='complexity_score',
                                  title="Efficienza: Tempo vs Azioni",
                                  hover_data=['filename', 'undos'])
            st.plotly_chart(fig_perf, use_container_width=True)

    with t2:
        col_list, col_img = st.columns([1, 2])
        
        with col_list:
            st.subheader("Lista File")
            show_anom = st.toggle("Solo Anomalie / Lente", value=False)
            df_v = df[df['is_anomaly']] if show_anom else df
            
            sel_file = st.selectbox("Scegli:", df_v['filename'], 
                format_func=lambda x: f"{'🔴' if df[df['filename']==x]['is_anomaly'].values[0] else '🟢'} {x}")
        
        with col_img:
            if sel_file:
                row = df[df['filename'] == sel_file].iloc[0]
                
                # STATISTICHE SINGOLA FOTO
                m1, m2, m3 = st.columns(3)
                m1.info(f"Lavoro: {row['time_spent_sec']}s")
                m2.warning(f"Attesa Precedente: {row['dead_time_sec']:.1f}s")
                m3.metric("Azioni", row['actions'])
                
                # CARICAMENTO SMART
                orig_folder = row['session_folder']
                actual_path = load_image_smart(sel_file, orig_folder, path_override, use_override)
                
                if actual_path:
                    st.caption(f"File caricato da: `{actual_path}`")
                    try:
                        pil_img = Image.open(actual_path).convert("RGB")
                        # Cerca json (stesso nome .json)
                        json_path = os.path.splitext(actual_path)[0] + ".json"
                        
                        final_img, ocr_data = draw_overlay(pil_img.copy(), json_path)
                        st.image(final_img, use_column_width=True)
                        
                        if ocr_data:
                            st.subheader("Letture OCR")
                            oc_cols = st.columns(len(ocr_data))
                            for i, (l, v) in enumerate(ocr_data):
                                oc_cols[i].success(f"{l}\n## `{v}`")
                    except Exception as e:
                        st.error(f"Errore apertura immagine: {e}")
                else:
                    st.error("❌ FILE NON TROVATO")
                    st.markdown(f"""
                    Il sistema ha cercato in:
                    1. Override: `{os.path.join(path_override, sel_file)}`
                    2. Log Path: `{os.path.join(orig_folder, sel_file)}`
                    
                    **Soluzione:** Assicurati che nella casella 'Cartella Immagini Locale' ci sia il percorso ESATTO dove si trovano ora i file `.jpeg`.
                    """)
