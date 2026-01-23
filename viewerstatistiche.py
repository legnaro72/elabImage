import streamlit as st
import pandas as pd
import plotly.express as px
import os
import json
import re
import numpy as np
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from fpdf import FPDF
import tempfile
import uuid  # <--- AGGIUNGI QUESTO IMPORT
from io import BytesIO  # Import necessario per leggere il file di default
# ==========================================================
# CONFIGURAZIONE PAGINA
# ==========================================================
st.set_page_config(
    page_title="KPI Manager v3 – FINAL PDF",
    layout="wide",
    page_icon="📊"
)

# ==========================================================
# GESTIONE STATO PER IL PATH
# ==========================================================
if "current_folder_path" not in st.session_state:
    st.session_state.current_folder_path = ""

# ==========================================================
# 1. PARSER KPI
# ==========================================================
@st.cache_data
def parse_kpi_file(uploaded_file):
    lines = uploaded_file.getvalue().decode("utf-8", errors="ignore").splitlines()
    data = []
    
    current_session_id = 0
    session_folder = "Unknown"
    current_image = {}
    in_image_block = False

    for line in lines:
        line = line.strip()

        if line.startswith("SESSION_START"):
            current_session_id += 1
        
        elif line.startswith("folder="):
            try:
                # Estrae il path scritto nel file di log
                session_folder = line.split("=", 1)[1].strip()
            except IndexError:
                session_folder = "Unknown"

        elif line.startswith("IMAGE_START"):
            in_image_block = True
            # Lunghezza di "IMAGE_START " (con lo spazio finale) è 12
            prefix_len = 12 
            marker_time = " time="
            
            # Valori di default
            filename = "Unknown"
            img_start_time = None

            # Caso 1: C'è il marcatore temporale (file nuovi)
            if marker_time in line:
                idx_time = line.rfind(marker_time)
                if idx_time > prefix_len:
                    # Prende tutto ciò che c'è tra il prefisso e " time="
                    filename = line[prefix_len:idx_time].strip()
                
                # Tentativo di estrazione data
                try:
                    time_str = line[idx_time + len(marker_time):].strip()
                    # Prende solo la prima parte (data-ora) ignorando eventuali extra
                    time_str = time_str.split(" ")[0] 
                    img_start_time = datetime.fromisoformat(time_str)
                except: 
                    pass
            
            # Caso 2: NON c'è il marcatore temporale (file vecchi o errore scrittura)
            else:
                # CORREZIONE: Prende tutto il resto della riga dopo il prefisso
                # Invece di fare split() che tagliava i nomi con spazi
                filename = line[prefix_len:].strip()

            current_image = {
                "session_id": current_session_id,
                "session_folder": session_folder,
                "filename": filename,   # Nota: usiamo la chiave "filename"
                "timestamp_obj": img_start_time,
                "actions": 0, "undos": 0, "redos": 0, "ocr_edits": 0,
                "num_letta_plate": 0, "num_ocr": 0,
                "ocr_validated": 0, "ocr_not_validated": 0,
                "time_spent_sec": 0.0, 
                "modified": False, "saved": False
            }

        elif in_image_block and "=" in line and not line.startswith("IMAGE_END"):
            try:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if v.lower() == "true": v = True
                elif v.lower() == "false": v = False
                elif v.replace(".", "", 1).isdigit(): 
                    v = float(v) if "." in v else int(v)
                current_image[k] = v
            except: pass

        elif line.startswith("IMAGE_END"):
            if current_image:
                data.append(current_image)
            in_image_block = False
            current_image = {}

    return pd.DataFrame(data)
    
    
def normalize_session_ids(df):
    """Rinormalizza gli ID sessione per partire da 1 in modo sequenziale."""
    if df is None or 'session_id' not in df.columns:
        return df
    
    # Trova gli ID unici attuali e li ordina
    unique_ids = sorted(df['session_id'].unique())
    # Crea un dizionario {Vecchio_ID: 1, Vecchio_ID_2: 2, ...}
    mapping = {old_id: new_id for new_id, old_id in enumerate(unique_ids, 1)}
    
    # Applica la mappatura
    df['session_id'] = df['session_id'].map(mapping)
    return df

# ==========================================================
# 2. DATA ENRICHMENT
# ==========================================================
def enrich_data(df):
    if df.empty: return df, df
    
    df = df.sort_values("timestamp_obj")
    df["prev_start"] = df["timestamp_obj"].shift(1)
    df["prev_work"] = df["time_spent_sec"].shift(1)
    df["prev_session"] = df["session_id"].shift(1)

    def calc_dead(row):
        if pd.isna(row["prev_start"]) or pd.isna(row["timestamp_obj"]): return 0.0
        if row["session_id"] != row["prev_session"]: return 0.0
        gap = (row["timestamp_obj"] - row["prev_start"]).total_seconds()
        return max(0.0, gap - row["prev_work"])

    df["dead_time_sec"] = df.apply(calc_dead, axis=1)
    df["Session Label"] = "Sessione " + df["session_id"].astype(str)
    
    df["is_anomaly"] = (
        ((df["time_spent_sec"] > 45) & (df["actions"] < 2)) | 
        (df["undos"] > 4) | 
        (df["dead_time_sec"] > 30)
    )

    # --- MODIFICA FONDAMENTALE: Raggruppa anche per SESSIONE ---
    df_unique = df.groupby(['session_id', 'session_folder', 'filename']).agg({
        'time_spent_sec': 'sum',
        'actions': 'sum',
        'undos': 'sum',
        'redos': 'sum',
        'ocr_edits': 'sum',
        'num_ocr': 'last',
        'ocr_validated': 'last',
        'ocr_not_validated': 'last',
        'dead_time_sec': 'sum',
        'timestamp_obj': 'min'
    }).reset_index()

    df_unique["undo_rate"] = df_unique.apply(lambda x: (x["undos"] / x["actions"] * 100) if x["actions"] > 0 else 0, axis=1)
    df_unique["redo_rate"] = df_unique.apply(lambda x: (x["redos"] / x["undos"] * 100) if x["undos"] > 0 else 0, axis=1)
    df_unique["complexity_score"] = df_unique["actions"] + df_unique["ocr_edits"] + (df_unique["undos"] * 1.5)

    return df, df_unique

# ==========================================================
# 3. PDF REPORT GENERATOR (AGGIORNATO CON CONFRONTI)
# ==========================================================
class PDF(FPDF):
    def header(self):
        # Header Colorato
        self.set_fill_color(44, 62, 80) # Dark Blue
        self.rect(0, 0, 210, 25, 'F')
        self.set_y(8)
        self.set_font('Arial', 'B', 18)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, 'REPORT ANALISI KPI', 0, 1, 'C')
        self.set_text_color(0, 0, 0) # Reset color

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

    def section_header(self, text):
        self.set_font('Arial', 'B', 14)
        self.set_fill_color(236, 240, 241) # Light Grey
        self.set_text_color(44, 62, 80)
        self.cell(0, 10, self.clean_text(text), 0, 1, 'L', 1)
        self.ln(4)

    def clean_text(self, text):
        # Converte in Latin-1 e rimpiazza caratteri non supportati
        return str(text).encode('latin-1', 'replace').decode('latin-1')

    # --- MODIFICATO: Aggiunto parametro sub_text per il confronto ---
    def kpi_box(self, label, value, x, y, w=45, sub_text=None):
        self.set_xy(x, y)
        self.set_fill_color(255, 255, 255)
        self.set_draw_color(200, 200, 200)
        # Rettangolo principale
        self.rect(x, y, w, 22, 'DF') # Leggermente più alto per farci stare tutto
        
        # Etichetta (Label)
        self.set_font('Arial', 'B', 7)
        self.set_text_color(127, 140, 141)
        self.cell(w, 6, self.clean_text(label), 0, 1, 'C')
        
        # Valore Principale
        self.set_font('Arial', 'B', 11)
        self.set_text_color(44, 62, 80)
        self.set_x(x)
        self.cell(w, 6, self.clean_text(value), 0, 1, 'C')

        # Sottotitolo (Confronto)
        if sub_text:
            self.set_font('Arial', 'I', 7)
            self.set_text_color(100, 100, 100) # Grigio
            self.set_x(x)
            self.cell(w, 5, self.clean_text(sub_text), 0, 0, 'C')

def create_full_pdf(df_aggregated, df_raw_logs, figures, df_compare_grouped=None, df_compare_raw=None):
    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # Helper per grafici
    def add_plot_safe(fig_key, x_pos, y_pos=None, w_size=190):
        if fig_key in figures:
            tmp_filename = os.path.join(tempfile.gettempdir(), f"kpi_{uuid.uuid4()}.png")
            try:
                figures[fig_key].write_image(tmp_filename, width=1000, height=500, scale=1.5)
                if y_pos: pdf.image(tmp_filename, x=x_pos, y=y_pos, w=w_size)
                else: pdf.image(tmp_filename, x=x_pos, w=w_size)
            except: pass
            finally:
                if os.path.exists(tmp_filename):
                    try: os.remove(tmp_filename)
                    except: pass
        else:
            if y_pos: pdf.set_y(y_pos)
            pdf.cell(0, 10, f"Grafico non disponibile.", 0, 1)

    # --- DATI FILE 1 (PRINCIPALE) ---
    tot_imgs_unique = len(df_aggregated)
    tot_work_sec = df_aggregated["time_spent_sec"].sum()
    tot_actions = df_aggregated["actions"].sum()
    avg_time_img = tot_work_sec / tot_imgs_unique if tot_imgs_unique > 0 else 0
    avg_time_action = tot_work_sec / tot_actions if tot_actions > 0 else 0
    
    # Qualità File 1
    tot_ocr = df_aggregated['real_ocr'].sum() if 'real_ocr' in df_aggregated.columns else 0
    tot_valid = df_aggregated['ocr_validated'].sum() if 'ocr_validated' in df_aggregated.columns else 0
    tot_not_valid = df_aggregated['ocr_not_validated'].sum() if 'ocr_not_validated' in df_aggregated.columns else 0

    # --- DATI FILE 2 (CONFRONTO) ---
    c_unique = c_time = c_avg_time = c_time_action = None
    c_actions = 0
    c_ocr_valid = c_ocr_not_valid = c_ocr_found = 0 # Default a 0 se non abbiamo dati JSON per il secondo file
    
    if df_compare_grouped is not None and df_compare_raw is not None:
        c_unique = df_compare_raw['filename'].nunique()
        c_time = df_compare_grouped["time_spent_sec"].sum()
        c_actions = df_compare_grouped["actions"].sum()
        c_avg_time = c_time / c_unique if c_unique > 0 else 0
        c_time_action = c_time / c_actions if c_actions > 0 else 0
        
        # Nota: Di solito il file di confronto non ha i dati JSON (real_ocr), quindi mettiamo 0 o stimiamo
        # Se volessimo stimare i "Non Validati" come totali unici (assumendo 0 validati):
        c_ocr_not_valid = c_unique 
        c_ocr_valid = 0

    # ==========================
    # SEZIONE 1: FILE PRINCIPALE
    # ==========================
    pdf.section_header("1. PANORAMICA ESECUTIVA (GLOBALE)")
    y = pdf.get_y()
    
    # RIGA 1 (PRINCIPALE)
    sub_1 = f"vs {c_unique}" if c_unique is not None else ""
    pdf.kpi_box("IMM. UNICHE", f"{tot_imgs_unique}", 10, y, sub_text=sub_1)
    
    sub_2 = f"vs {c_avg_time:.1f} s" if c_avg_time is not None else ""
    pdf.kpi_box("MEDIA/IMM", f"{avg_time_img:.1f} s", 60, y, sub_text=sub_2)
    
    sub_3 = f"vs {c_time_action:.2f} s" if c_time_action is not None else ""
    pdf.kpi_box("SEC/AZIONE", f"{avg_time_action:.2f} s", 110, y, sub_text=sub_3)
    
    sub_4 = f"vs {c_time/60:.1f} m" if c_time is not None else ""
    pdf.kpi_box("TEMPO TOT", f"{tot_work_sec/60:.1f} min", 160, y, sub_text=sub_4)
    
    # RIGA 2 (PRINCIPALE)
    y_row2 = y + 28
    pdf.kpi_box("OCR VALIDATI", f"{int(tot_valid)}", 10, y_row2)
    pdf.kpi_box("OCR NON VALIDATI", f"{int(tot_not_valid)}", 60, y_row2)
    pdf.kpi_box("OCR TROVATI", f"{int(tot_ocr)}", 110, y_row2)
    pdf.kpi_box("AZIONI TOT", f"{int(tot_actions)}", 160, y_row2)
    
    # Testo descrittivo File 1
    pdf.set_y(y_row2 + 30)
    pdf.set_font('Arial', '', 10)
    txt = (f"Analisi su {tot_imgs_unique} immagini uniche. "
           f"Tempo medio: {avg_time_img:.1f} s. ")
    if c_unique:
        diff = avg_time_img - c_avg_time
        segno = "+" if diff > 0 else ""
        txt += f" | Delta vs Target: {segno}{diff:.1f} sec/img"
    pdf.multi_cell(0, 5, pdf.clean_text(txt))
    pdf.ln(5)

    # ==========================
    # SEZIONE 1.1: FILE CONFRONTO (Se esiste)
    # ==========================
    if c_unique is not None:
        pdf.ln(5) # Spazio extra
        pdf.section_header("1.1 PANORAMICA ESECUTIVA (KPI CONFRONTO)")
        y_c = pdf.get_y()
        
        # RIGA 1 (CONFRONTO - SENZA DELTA)
        pdf.kpi_box("IMM. UNICHE", f"{c_unique}", 10, y_c)
        pdf.kpi_box("MEDIA/IMM", f"{c_avg_time:.1f} s", 60, y_c)
        pdf.kpi_box("SEC/AZIONE", f"{c_time_action:.2f} s", 110, y_c)
        pdf.kpi_box("TEMPO TOT", f"{c_time/60:.1f} min", 160, y_c)
        
        # RIGA 2 (CONFRONTO)
        # Usiamo i dati calcolati per il secondo file. 
        # Se non c'è validazione, mettiamo 0 su validati e Totale su Non Validati (come default)
        y_c_row2 = y_c + 28
        pdf.kpi_box("OCR VALIDATI", f"{int(c_ocr_valid)}", 10, y_c_row2)
        pdf.kpi_box("OCR NON VALIDATI", f"{int(c_ocr_not_valid)}", 60, y_c_row2)
        pdf.kpi_box("OCR TROVATI", f"{int(c_ocr_found)}", 110, y_c_row2) # Solitamente 0 se non caricato JSON
        pdf.kpi_box("AZIONI TOT", f"{int(c_actions)}", 160, y_c_row2)
        
        pdf.set_y(y_c_row2 + 30)

    # --- GRAFICI ---
    pdf.add_page()
    pdf.section_header("2. EFFICIENZA GLOBALE")
    add_plot_safe("scatter", 10)

    pdf.add_page()
    pdf.section_header("3. TOP 20 PIU LENTE")
    add_plot_safe("bar_chart", 10, y_pos=pdf.get_y()+5)

    pdf.add_page()
    pdf.section_header("4. FLUSSO TEMPORALE (SESSIONI)")
    add_plot_safe("timeline", 10)
    
    # --- DETTAGLIO SESSIONI ---
    # Usiamo df_raw_logs che ora ha gli ID normalizzati (1, 2, 3...)
    unique_sessions = sorted(df_raw_logs['session_id'].unique())
    
    for s_id in unique_sessions:
        pdf.add_page()
        df_sess = df_raw_logs[df_raw_logs['session_id'] == s_id]
        
        pdf.section_header(f"SESSIONE {s_id}")
        
        s_imgs = len(df_sess)
        s_time = df_sess["time_spent_sec"].sum()
        s_avg = s_time / s_imgs if s_imgs > 0 else 0
        
        y = pdf.get_y()
        pdf.kpi_box("LOGS SESS", str(s_imgs), 10, y)
        pdf.kpi_box("DURATA", f"{s_time/60:.1f} m", 60, y)
        pdf.kpi_box("MEDIA/LOG", f"{s_avg:.1f} s", 110, y)
        pdf.kpi_box("AZIONI", str(int(df_sess["actions"].sum())), 160, y)
        
        pdf.set_y(y + 30)
        sess_key = f"timeline_sess_{s_id}" # Nota: assicurati che le chiavi del grafico usino gli ID nuovi se rigenerati
        add_plot_safe(sess_key, 10)

    return pdf.output(dest='S').encode('latin-1')

# ==========================================================
# 4. IMAGE UTILS
# ==========================================================
def load_image_smart(filename, original_folder, override_path, use_override):
    name, ext = os.path.splitext(filename)
    exts = [ext, ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".JPG", ".JPEG", ".PNG"]
    search_dirs = []
    if use_override and override_path: search_dirs.append(override_path)
    if original_folder: search_dirs.append(original_folder)
    search_dirs.append(os.getcwd())
    for d in search_dirs:
        for e in exts:
            p = os.path.join(d, name + e)
            if os.path.exists(p): return p
    return None

CLASS_COLORS = {
    'car': 'red', 'van': 'blue', 'plate': 'green', 'bus': 'magenta',
    'motorcycle': 'orange', 'truck': 'cyan', 'bicycle': 'lime green',
    'person': 'yellow green', 'handbag': 'purple', 'backpack': 'teal',
    'suitcase': 'brown', 'ocr': 'grey', 'pickup': 'lightcoral'
}
PIL_SAFE_COLORS = {
    "red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255),
    "yellow": (255, 255, 0), "orange": (255, 165, 0), "cyan": (0, 255, 255),
    "magenta": (255, 0, 255), "white": (255, 255, 255), "black": (0, 0, 0),
    "yellow green": (154, 205, 50), "light green": (144, 238, 144),
    "lime green": (50, 205, 50), "purple": (128, 0, 128), "teal": (0, 128, 128),
    "brown": (165, 42, 42), "grey": (128, 128, 128), "lightcoral": (240, 128, 128)
}

# --- FUNZIONE HELPER: Legge i contatori dal JSON (Versione PER IL TUO FORMATO) ---
def get_json_stats(filename, folder_path):
    if not folder_path: return 0, 0
    
    # 1. Costruiamo il percorso (gestisce sia nome.json che nome.jpg.json)
    base_name = os.path.splitext(filename)[0]
    path_v1 = os.path.join(folder_path, base_name + ".json")
    path_v2 = os.path.join(folder_path, filename + ".json")

    final_path = None
    if os.path.exists(path_v1):
        final_path = path_v1
    elif os.path.exists(path_v2):
        final_path = path_v2
            
    if final_path:
        try:
            with open(final_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # ADATTAMENTO AL TUO JSON: 
                # La lista principale si chiama "boxes"
                boxes_list = data.get('boxes', [])
                
                num_bb = 0
                num_ocr = 0
                
                for item in boxes_list:
                    # Leggiamo il nome della classe (es. "person", "OCR_1")
                    c_name = item.get('class', '')
                    
                    # LOGICA DI CONTEGGIO
                    # Se inizia con OCR (case insensitive) è un dato OCR
                    if c_name.upper().startswith("OCR"):
                        num_ocr += 1
                    else:
                        # Tutto il resto (person, car, Letta_plate, etc.) è un BB geometrico
                        num_bb += 1
                        
                return num_bb, num_ocr
        except: 
            return 0, 0 # Errore lettura file o formato non valido
            
    return 0, 0 # File non trovato


def get_class_color(class_name):
    cls_lower = class_name.lower()
    base_name = re.sub(r'_\d+$', '', cls_lower)
    if "plate" in base_name or "targa" in base_name: color_key = 'green'
    elif "ocr" in base_name: color_key = 'grey'
    else: color_key = CLASS_COLORS.get(base_name, 'cyan')
    return PIL_SAFE_COLORS.get(color_key, (0, 255, 255))

def draw_overlay(image, json_path):
    if not json_path or not os.path.exists(json_path): return image, []
    try:
        font = ImageFont.truetype("arial.ttf", 22)
        font_footer = ImageFont.truetype("arial.ttf", 36)
    except:
        font = ImageFont.load_default()
        font_footer = ImageFont.load_default()

    draw = ImageDraw.Draw(image)
    ocr_results = []
    footer_texts = []

    with open(json_path, "r", encoding="utf-8") as f: js = json.load(f)
    detections = js.get("detections", js.get("boxes", []))

    for det in detections:
        cls = det.get("class", "unknown")
        if cls.lower().startswith("ocr"):
            vals = det.get("value", [])
            text_val = vals[0] if isinstance(vals, list) and len(vals) > 0 else det.get("text", "")
            label_targa = cls.replace("OCR", "TARGA").replace("ocr", "TARGA")
            if text_val:
                footer_texts.append(f"{label_targa} = {text_val}")

        bbox = det.get("bbox") or det.get("coords")
        if not bbox or len(bbox) != 4: continue
        x1, y1, x2, y2 = map(int, bbox)
        color_rgb = get_class_color(cls)
        draw.rectangle([x1, y1, x2, y2], outline=color_rgb, width=4)
        label = cls.upper()
        tb = draw.textbbox((x1, y1), label, font=font)
        draw.rectangle([x1, y1 - (tb[3]-tb[1]) - 4, x1 + (tb[2]-tb[0]) + 6, y1], fill=color_rgb)
        draw.text((x1 + 3, y1 - (tb[3]-tb[1]) - 2), label, fill="black", font=font)

    if footer_texts:
        full_footer_text = " , ".join(footer_texts)
        footer_height = 60 
        new_width = image.width
        new_height = image.height + footer_height
        final_image = Image.new("RGB", (new_width, new_height), (0, 0, 0))
        final_image.paste(image, (0, 0))
        draw_final = ImageDraw.Draw(final_image)
        tb_f = draw_final.textbbox((0, 0), full_footer_text, font=font_footer)
        text_w = tb_f[2] - tb_f[0]
        text_h = tb_f[3] - tb_f[1]
        x_pos = (new_width - text_w) // 2
        y_pos = image.height + (footer_height - text_h) // 2 - 5
        draw_final.text((x_pos, y_pos), full_footer_text, fill="white", font=font_footer)
        image = final_image

    if not ocr_results:
        for det in detections:
            if det.get("class", "").lower().startswith("ocr"):
                vals = det.get("value", [])
                text = vals[0] if isinstance(vals, list) and vals else ""
                val_icon = "✅" if det.get("validated") else "⚠️"
                ocr_results.append((det.get("class"), f"{text} {val_icon}"))
    return image, ocr_results

# ==========================================================
# SIDEBAR
# ==========================================================
with st.sidebar:
    st.markdown("## 📂 Dati & Percorsi")
    upl_file = st.file_uploader("Carica File KPI (Principale)", type=["kpi", "txt", "kkk"])
    
    # --- ### NUOVO: SEZIONE CONFRONTO ---
    st.markdown("---")
    st.write("⚖️ **Confronto (Opzionale)**")
    uploaded_file_compare = st.file_uploader("Carica secondo File per confronto", type=["kpi", "txt", "kkk"], key="compare_upload")
    st.divider()
    # ------------------------------------

    

    # FIX PATH: Aggiornamento automatico con path dal log
    if upl_file and not st.session_state.current_folder_path:
        st.info("📁 Seleziona la cartella che contiene le immagini del KPI caricato")
        
    # FIX PATH: Se siamo in modalità default e il path è vuoto, forziamo AnnProva
    if not st.session_state.current_folder_path and os.path.exists("AnnProva"):
         st.session_state.current_folder_path = "AnnProva"
    use_override = st.toggle("Usa percorso locale", value=True)
    
    path_override = st.text_input(
        "Cartella Immagini", 
        value=st.session_state.current_folder_path
    )
    if path_override != st.session_state.current_folder_path:
         st.session_state.current_folder_path = path_override

# ==========================================================
# MAIN
# ==========================================================


st.title("🧠 KPI Manager v3 – FINAL")

pdf_figures = {}

# --- COSTANTI CLOUD / DEFAULT ---
DEFAULT_FOLDER = "AnnProva"
DEFAULT_KPI_FILE = "KPIEsempio.kpi"

# Variabili di stato per il file
file_content = None
source_name = ""

# --- SIDEBAR: GESTIONE INPUT E PATH ---
with st.sidebar:
    st.markdown("## 📂 Sorgente Dati")

    # 1. Caricamento File KPI (Sovrascrive il default)
    upl_file = st.file_uploader("Carica File KPI (Opzionale)", type=["kpi", "txt", "kkk"])

    st.markdown("---")
    st.write("🖼️ **Sorgente Immagini & JSON**")

    # 2. Scelta Modalità Percorso (Cloud vs Locale)
    # Seleziona da dove l'app deve cercare le immagini
    path_mode = st.radio(
        "Dove sono le immagini?",
        ["Cloud (GitHub Repo)", "Locale (Il tuo PC)"],
        index=0
    )

    if path_mode == "Cloud (GitHub Repo)":
        # Imposta il percorso fisso della repo
        st.session_state.current_folder_path = DEFAULT_FOLDER
        path_override = DEFAULT_FOLDER
        use_override = True
        st.info(f"📂 Cartella attiva: `{DEFAULT_FOLDER}/`")
    else:
        # Permette all'utente di scrivere il percorso locale
        # Recuperiamo il valore precedente se diverso dal default cloud
        curr_val = st.session_state.current_folder_path if st.session_state.current_folder_path != DEFAULT_FOLDER else ""
        
        path_input = st.text_input("Inserisci Path locale (es. C:/Dati):", value=curr_val)
        st.session_state.current_folder_path = path_input
        path_override = path_input
        use_override = True
        
        if path_input:
            st.warning("⚠️ Nota: In 'Locale', le immagini nel Tab 4 si vedono solo se esegui l'app in locale (localhost).")

    # 3. File di Confronto
    st.markdown("---")
    st.write("⚖️ **Confronto (Opzionale)**")
    uploaded_file_compare = st.file_uploader("Carica file per confronto", type=["kpi", "txt", "kkk"])

# --- LOGICA CARICAMENTO FILE (PRIORITÀ ALL'UTENTE) ---
file_content = None

# 1. CASO FILE UTENTE: Priorità Assoluta
if upl_file is not None:
    file_content = upl_file
    # FONDAMENTALE: Resettiamo il puntatore del file per sicurezza
    file_content.seek(0)
    source_name = upl_file.name
    st.toast(f"✅ Usando il TUO file: {source_name}", icon="📂")

# 2. CASO DEMO: Solo se NON c'è file utente
else:
    default_path = os.path.join(DEFAULT_FOLDER, DEFAULT_KPI_FILE)
    
    if os.path.exists(default_path):
        try:
            with open(default_path, "rb") as f:
                content = f.read()
                file_content = BytesIO(content)
                
                # FIX PER LA CACHE (Evita l'errore getmtime)
                file_content.name = os.path.abspath(default_path)
                
                source_name = DEFAULT_KPI_FILE
            st.toast(f"⚠️ Nessun file caricato. Modalità DEMO attiva.", icon="☁️")
        except Exception as e:
            st.error(f"Errore caricamento Demo: {e}")

# --- ELABORAZIONE DATI (Eseguita solo se abbiamo un contenuto) ---
if file_content:
    # Parsing del file
    try:
        # Passiamo il file al parser
        df_raw, df_unique = enrich_data(parse_kpi_file(file_content))
        
        # --- CORREZIONE SESSIONI (Start from 1) ---
        df_raw = normalize_session_ids(df_raw)
        if 'session_id' in df_unique.columns:
            df_unique = normalize_session_ids(df_unique)
            
    except Exception as e:
        st.error(f"Errore nella lettura del file KPI: {e}")
        st.stop() # Ferma l'esecuzione se il file è corrotto

    # Parsing del file CONFRONTO (Se esiste)
    df_compare_raw = None
    df_compare_grouped = None
    
    if uploaded_file_compare:
        try:
            df_compare_raw, df_compare_grouped = enrich_data(parse_kpi_file(uploaded_file_compare))
            st.toast(f"Confronto attivo", icon="⚖️")
        except Exception as e:
            st.error(f"Errore nel file di confronto: {e}")

    # --- INIZIO TABS ---
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Dashboard",
        "📈 Analisi Efficienza",
        "🕒 Timeline",
        "👁️ Ispezione"
    ])
    
    # ... (Il resto del codice dentro i tab rimane uguale) ...

# --- ELABORAZIONE PRINCIPALE ---
if file_content:
    # Parsing del file PRINCIPALE (upl_file O file_content)
    df_raw, df_unique = enrich_data(parse_kpi_file(file_content))
    
    # --- CORREZIONE SESSIONI (Start from 1) ---
    df_raw = normalize_session_ids(df_raw)
    
    # Aggiorniamo anche df_unique
    if 'session_id' in df_unique.columns:
        df_unique = normalize_session_ids(df_unique)
    
    # Parsing del file CONFRONTO (Se esiste)
    df_compare_raw = None
    df_compare_grouped = None
    
    if uploaded_file_compare:
        try:
            # CORREZIONE: Prendiamo anche il _raw per contare i file unici globali!
            df_compare_raw, df_compare_grouped = enrich_data(parse_kpi_file(uploaded_file_compare))
            st.toast(f"File confronto caricato correttamente", icon="✅")
        except Exception as e:
            st.error(f"Errore nel file di confronto: {e}")

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Dashboard",
        "📈 Analisi Efficienza",
        "🕒 Timeline",
        "👁️ Ispezione"
    ])

    with tab1:
        # ==========================================
        # 1. CALCOLI DATI PRINCIPALI
        # ==========================================
        # Immagini uniche globali (su tutto il raw log, indipendentemente dalle sessioni)
        tot_unique = df_raw['filename'].nunique() 
        tot_logs = len(df_raw)
        
        tot_work = df_unique["time_spent_sec"].sum()
        tot_actions = df_unique["actions"].sum()
        
        avg_time = tot_work / tot_unique if tot_unique > 0 else 0
        time_per_action = tot_work / tot_actions if tot_actions > 0 else 0
        undo_rate = (df_unique["undos"].sum() / tot_actions * 100) if tot_actions > 0 else 0

        # ==========================================
        # 2. CALCOLI DATI CONFRONTO (Se presenti)
        # ==========================================
        c_unique = c_time = c_actions = c_avg_time = c_time_action = None
        c_ocr_valid = c_ocr_not = 0 # Valori default per qualità confronto
        
        if df_compare_raw is not None and df_compare_grouped is not None:
            # CORREZIONE FONDAMENTALE: 
            # Contiamo i file unici sul RAW globale (come nel file principale)
            c_unique = df_compare_raw['filename'].nunique()
            
            c_time = df_compare_grouped["time_spent_sec"].sum()
            c_actions = df_compare_grouped["actions"].sum()
            
            c_avg_time = c_time / c_unique if c_unique > 0 else 0
            c_time_action = c_time / c_actions if c_actions > 0 else 0

        # ==========================================
        # 3. LAYOUT VISUALIZZAZIONE
        # ==========================================
        
        st.subheader(f"🌍 Performance Globale ({source_name})")
        
        # --- RIGA 1: KPI PRINCIPALI (Con Delta) ---
        k1, k2, k3, k4, k5 = st.columns(5)
        
        with k1:
            # CORREZIONE: Aggiunto int() per convertire da numpy a python nativo
            delta_val = int(tot_unique - c_unique) if c_unique is not None else None
            st.metric("🖼️ Imm. Univoche", tot_unique, delta=delta_val)
        
        with k2:
            val_min = tot_work/60
            # Questo era già una stringa (f-string), quindi è sicuro
            delta_val = f"{(val_min - (c_time/60)):.1f} m" if c_time is not None else None
            st.metric("⏱️ Tempo Tot", f"{val_min:.1f} m", delta=delta_val, delta_color="inverse")

        with k3:
            # Sicuro (stringa)
            delta_val = f"{(avg_time - c_avg_time):.1f} s" if c_avg_time is not None else None
            st.metric("⚡ Media/Imm", f"{avg_time:.1f} s", delta=delta_val, delta_color="inverse")

        with k4:
            # Sicuro (stringa)
            delta_val = f"{(time_per_action - c_time_action):.2f} s" if c_time_action is not None else None
            st.metric("⏱️ Sec/Azione", f"{time_per_action:.2f} s", delta=delta_val, delta_color="inverse")
            
        with k5:
            # CORREZIONE ERRORE LINEA 660: Aggiunto int() attorno alla sottrazione
            delta_val = int(tot_actions - c_actions) if c_actions is not None else None
            st.metric("🖱️ Azioni Tot", int(tot_actions), delta=delta_val, delta_color="inverse")

        # --- RIGA 2: QUALITÀ PRINCIPALE ---
        st.markdown("") # Spazio
        q1, q2, q3, q4, q5 = st.columns(5)
        q1.metric("📚 Log Totali", tot_logs)
        q2.metric("↩️ Undo Rate", f"{undo_rate:.1f}%")
        q3.metric("📝 OCR Tot", int(df_unique["num_ocr"].sum()))
        q4.metric("✅ OCR Validati", int(df_unique["ocr_validated"].sum()))
        q5.metric("⚠️ OCR Non Validati", int(df_unique["ocr_not_validated"].sum()))

        # ==========================================
        # 4. SEZIONE CONFRONTO (Identica a PDF 1.1)
        # ==========================================
        if c_unique is not None:
            st.markdown("---")
            st.subheader("🆚 Performance Benchmark (File Confronto)")
            
            # Creiamo una riga identica a quella sopra, ma con i dati del secondo file
            ck1, ck2, ck3, ck4, ck5 = st.columns(5)
            
            ck1.metric("🖼️ Imm. Univoche", c_unique, help="Totale immagini uniche nel file di confronto (Globale)")
            ck2.metric("⏱️ Tempo Tot", f"{c_time/60:.1f} m")
            ck3.metric("⚡ Media/Imm", f"{c_avg_time:.1f} s")
            ck4.metric("⏱️ Sec/Azione", f"{c_time_action:.2f} s")
            ck5.metric("🖱️ Azioni Tot", int(c_actions))

        # ==========================================
        # 5. DETTAGLIO PER SESSIONE
        # ==========================================
        st.markdown("---")
        st.subheader("📍 Dettaglio per Sessione (File Principale)")
        
        unique_sessions = sorted(df_unique['session_id'].unique())
        for s_id in unique_sessions:
            df_sess = df_unique[df_unique['session_id'] == s_id]
            folder_name = df_sess['session_folder'].iloc[0] if not df_sess.empty else "Unknown"
            
            s_imgs = len(df_sess)
            s_time = df_sess["time_spent_sec"].sum()
            s_actions = df_sess["actions"].sum()
            s_ocr_ok = df_sess["ocr_validated"].sum()
            
            with st.expander(f"📂 Sessione {s_id} ({s_imgs} immagini) - {folder_name}", expanded=False):
                sc1, sc2, sc3, sc4 = st.columns(4)
                sc1.metric("Immagini", s_imgs)
                sc2.metric("Tempo", f"{s_time/60:.1f} min")
                sc3.metric("Azioni", int(s_actions))
                sc4.metric("OCR Validati", int(s_ocr_ok))
                
    with tab2:
        st.subheader("Analisi Efficienza")
        c1, c2 = st.columns(2)
        with c1:
            if not df_unique.empty:
                fig_sc = px.scatter(
                    df_unique,
                    x="time_spent_sec",
                    y="actions",
                    size="complexity_score",
                    color="undo_rate",
                    color_continuous_scale="RdYlGn_r",
                    title="Tempo vs Azioni",
                    hover_data=["filename"]
                )
                st.plotly_chart(fig_sc, use_container_width=True)
                pdf_figures["scatter"] = fig_sc

        with c2:
            if not df_unique.empty:
                fig_bar = px.bar(
                df_unique.sort_values("time_spent_sec", ascending=False).head(20), 
                x="time_spent_sec",
                y="filename",
                orientation='h',
                title="Top 20 Lente"
            )

            # FORZA COLORE BARRE (PDF SAFE)
            fig_bar.update_traces(marker_color="#0b2c4d")

            # Migliora leggibilità PDF
            fig_bar.update_layout(
                plot_bgcolor="white",
                paper_bgcolor="white",
                font=dict(color="black"),
                xaxis=dict(showgrid=True, gridcolor="#dddddd"),
                yaxis=dict(showgrid=False)
            )

            st.plotly_chart(fig_bar, use_container_width=True)
            pdf_figures["bar_chart"] = fig_bar
            
    with tab3:
        st.subheader("🌍 Timeline Globale")
        if not df_raw.empty:
            df_t = df_raw.copy()
            df_t = df_t.dropna(subset=["timestamp_obj"])
            df_t["end_time"] = df_t["timestamp_obj"] + pd.to_timedelta(df_t["time_spent_sec"], unit="s")

            # Grafico Globale
            fig_tl = px.timeline(df_t, x_start="timestamp_obj", x_end="end_time", 
                              y="filename", color="Session Label",
                              title="Flusso Operativo Completo")
            fig_tl.update_yaxes(autorange="reversed")
            st.plotly_chart(fig_tl, use_container_width=True)
            pdf_figures["timeline"] = fig_tl # Salviamo solo la globale nel PDF per non intasarlo

            # --- SEZIONE TIMELINE PER SESSIONE ---
            st.markdown("---")
            st.subheader("📍 Timeline per Singola Sessione")
            
            unique_sessions_raw = sorted(df_t['session_id'].unique())
            
            for s_id in unique_sessions_raw:
                # Filtra dati per sessione
                df_t_sess = df_t[df_t['session_id'] == s_id]
                folder_name = df_t_sess['session_folder'].iloc[0] if not df_t_sess.empty else ""
                
                with st.expander(f"🕒 Timeline Sessione {s_id} - {folder_name}", expanded=True):
                    if not df_t_sess.empty:
                        fig_s = px.timeline(
                            df_t_sess, 
                            x_start="timestamp_obj", 
                            x_end="end_time", 
                            y="filename", 
                            color="actions", 
                            color_continuous_scale="Viridis",
                            title=f"Sessione {s_id}"
                        )
                        fig_s.update_yaxes(autorange="reversed")
                        st.plotly_chart(fig_s, use_container_width=True)
                        
                        # --- NUOVO: Salviamo il grafico per il PDF ---
                        pdf_figures[f"timeline_sess_{s_id}"] = fig_s 
                    else:
                        st.warning("Nessun dato temporale valido per questa sessione.")

    with tab4:
        st.subheader("👁️ Ispezione Visiva e Ordinamento")

        # 1. Preparazione Dati (CON DEDUPLICAZIONE)
        # Prendiamo df_unique e rimuoviamo eventuali duplicati basati sul NOME FILE.
        # keep='last' mantiene l'ultima sessione registrata per quel file.
        df_view = df_unique.drop_duplicates(subset=['filename'], keep='last').copy()

        # Dati JSON (BB e OCR) - Calcolati solo sulle immagini uniche
        # USIAMO st.session_state.current_folder_path CHE ORA È GESTITO DALLA SIDEBAR
        if st.session_state.current_folder_path and os.path.isdir(st.session_state.current_folder_path):
            df_view[['real_bb', 'real_ocr']] = df_view['filename'].apply(
                lambda x: pd.Series(get_json_stats(x, st.session_state.current_folder_path))
            )
        else:
            df_view['real_bb'] = 0
            df_view['real_ocr'] = 0

        # 2. Ordinamento
        col_sort1, col_sort2, col_sort3 = st.columns([2, 1, 1])
        with col_sort1:
            sort_criteria = st.selectbox(
                "Ordina lista per:",
                options=["Nome File (A-Z)", "Tempo Speso (Decrescente)", "Azioni Totali (Decrescente)", "N. Bounding Box (Decrescente)", "N. OCR (Decrescente)"]
            )
        
        # Applicazione Ordinamento
        if sort_criteria == "Nome File (A-Z)":
            df_view = df_view.sort_values(by="filename", ascending=True)
        elif sort_criteria == "Tempo Speso (Decrescente)":
            df_view = df_view.sort_values(by="time_spent_sec", ascending=False)
        elif sort_criteria == "Azioni Totali (Decrescente)":
            df_view = df_view.sort_values(by="actions", ascending=False)
        elif sort_criteria == "N. Bounding Box (Decrescente)":
            df_view = df_view.sort_values(by="real_bb", ascending=False)
        elif sort_criteria == "N. OCR (Decrescente)":
            df_view = df_view.sort_values(by="real_ocr", ascending=False)

        # --- GESTIONE NAVIGAZIONE ---
        sorted_ids = df_view.index.tolist()

        # Inizializzazione sicura dello stato
        if "viz_selection" not in st.session_state:
            if sorted_ids:
                st.session_state.viz_selection = sorted_ids[0]
        
        # Se l'ID selezionato non è più nella lista (es. cambio ordinamento), resetta
        if st.session_state.viz_selection not in sorted_ids:
             if sorted_ids:
                st.session_state.viz_selection = sorted_ids[0]

        # --- FUNZIONE CALLBACK PER I PULSANTI ---
        def change_image(direction, all_ids):
            try:
                current_id = st.session_state.viz_selection
                if current_id in all_ids:
                    curr_pos = all_ids.index(current_id)
                    # Calcola nuovo indice con loop circolare
                    new_pos = (curr_pos + direction) % len(all_ids)
                    st.session_state.viz_selection = all_ids[new_pos]
                elif all_ids:
                    st.session_state.viz_selection = all_ids[0]
            except:
                pass

        # 3. Layout Visualizzatore
        col_l, col_r = st.columns([1, 2])
        
        with col_l:
            # Qui ora vedrai il numero corretto (es. 100 invece di 203)
            st.info(f"Visualizzando {len(df_view)} immagini uniche")
            
            def format_option(idx):
                row = df_view.loc[idx]
                return f"{row['filename']} | ⏱ {row['time_spent_sec']:.0f}s | 🖱 {row['actions']} | 📦 {row['real_bb']} | 📝 {row['real_ocr']}"

            # Selectbox collegata allo stato
            st.selectbox(
                "Seleziona immagine:",
                options=sorted_ids,
                format_func=format_option,
                key="viz_selection"
            )
            # Recupera l'indice attuale
            sel_idx = st.session_state.viz_selection

        with col_r:
            if sel_idx is not None and sorted_ids:
                
                # --- PULSANTI CON CALLBACK ---
                btn_c1, btn_c2, btn_c3 = st.columns([1, 4, 1])
                
                with btn_c1:
                    st.button("⬅️ Prec", use_container_width=True, on_click=change_image, args=(-1, sorted_ids))
                        
                with btn_c3:
                    st.button("Succ ➡️", use_container_width=True, on_click=change_image, args=(1, sorted_ids))

                # --- CARICAMENTO IMMAGINE ---
                row = df_view.loc[sel_idx]
                file_name = row["filename"]
                
                # Usa il percorso deciso nella Sidebar (path_override)
                img_path = load_image_smart(file_name, row["session_folder"], path_override, use_override)
                
                if img_path:
                    try:
                        img = Image.open(img_path).convert("RGB")
                        json_path = os.path.splitext(img_path)[0] + ".json"
                        img, ocr_data = draw_overlay(img, json_path)
                        
                        st.image(img, use_container_width=True, caption=f"{file_name}")
                        
                        # Statistiche
                        st.info(
                            f"📊 **Dati Globali:** "
                            f"Tempo {row['time_spent_sec']:.1f}s | "
                            f"Azioni {row['actions']} | "
                            f"Undos {row['undos']} | "
                            f"📦 BB {row['real_bb']} | "
                            f"🚗 TARGHE {row['real_ocr']}"
                        )
                        
                        if ocr_data:
                            with st.expander("Dettagli OCR (Contenuto)"):
                                for label, txt in ocr_data:
                                    st.write(f"**{label}:** {txt}")
                                    
                    except Exception as e:
                        st.error(f"Errore visualizzazione: {e}")
                else:
                    if st.session_state.current_folder_path == DEFAULT_FOLDER:
                        st.warning(f"File non trovato nel Cloud: {file_name}")
                    else:
                        st.warning(f"File non trovato in locale. (Ricorda: su Cloud non puoi vedere file di C:)")

# BOTTONE PDF NELLA SIDEBAR
    with st.sidebar:
        st.divider()
        # Verifichiamo che ci siano dati nel file principale
        if 'df_unique' in locals() and not df_unique.empty:
            
            if st.button("🖨️ Genera Report PDF"):
                with st.spinner("Calcolo dati aggregati e generazione PDF..."):
                    try:
                        # 1. AGGREGAZIONE PER FILE UNICO (La tua logica originale: corretta)
                        df_pdf = df_unique.groupby('filename', as_index=False).agg({
                            'time_spent_sec': 'sum',  # Somma tempo totale sessioni
                            'actions': 'sum',         # Somma click
                            'undos': 'sum',
                            'session_folder': 'last', # Ultimo percorso
                            'session_id': 'last'      # Ultimo ID
                        })
                        
                        # 2. LETTURA DATI REALI DAL JSON (La tua logica originale)
                        if st.session_state.get('current_folder_path') and os.path.isdir(st.session_state.current_folder_path):
                            # Recuperiamo i dati dai JSON
                            stats_df = df_pdf['filename'].apply(
                                lambda x: pd.Series(get_json_stats(x, st.session_state.current_folder_path))
                            )
                            df_pdf['real_bb'] = stats_df['real_bb']
                            df_pdf['real_ocr'] = stats_df['real_ocr']
                            
                            # Calcolo Validazione (Booleano)
                            df_pdf['is_validated'] = (df_pdf['real_bb'] > 0) | (df_pdf['real_ocr'] > 0)
                        else:
                            # Default se non trova la cartella
                            df_pdf['real_bb'] = 0
                            df_pdf['real_ocr'] = 0
                            df_pdf['is_validated'] = False

                        # --- MODIFICA FONDAMENTALE 1: CONVERSIONE PER IL PDF ---
                        # Il PDF si aspetta colonne numeriche (0 o 1) per fare le somme, non booleani.
                        df_pdf['ocr_validated'] = df_pdf['is_validated'].astype(int)
                        # Se è validato = 0 nella colonna "non validati", se non è validato = 1
                        df_pdf['ocr_not_validated'] = (~df_pdf['is_validated']).astype(int)

                        # --- MODIFICA FONDAMENTALE 2: RECUPERO DATI CONFRONTO ---
                        # Controlliamo se le variabili di confronto esistono, altrimenti None
                        comp_grouped = df_compare_grouped if 'df_compare_grouped' in locals() else None
                        comp_raw = df_compare_raw if 'df_compare_raw' in locals() else None

                        # 3. GENERAZIONE PDF (Passiamo 5 Argomenti ora!)
                        pdf_data = create_full_pdf(
                            df_pdf,          # Dati aggregati file principale
                            df_unique,       # Dati grezzi (sessioni) file principale
                            pdf_figures,     # Grafici
                            comp_grouped,    # Dati aggregati confronto (o None)
                            comp_raw         # Dati grezzi confronto (o None)
                        )
                        
                        st.download_button("📥 Download Report.pdf", pdf_data, "Report_KPI_Reali.pdf", "application/pdf")
                        st.toast("PDF Generato con successo!", icon="🎉")
                        
                    except Exception as e:
                        st.error(f"Errore generazione PDF: {e}")
                        import traceback
                        st.text(traceback.format_exc())
