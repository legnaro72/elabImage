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

# ==========================================================
# CONFIGURAZIONE PAGINA
# ==========================================================
st.set_page_config(
    page_title="KPI Manager v12 – FINAL PDF",
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
            prefix = "IMAGE_START "
            marker_time = " time="
            filename = "Unknown"
            img_start_time = None

            if marker_time in line:
                idx_time = line.rfind(marker_time)
                if idx_time > len(prefix):
                    filename = line[len(prefix):idx_time].strip()
                try:
                    time_str = line[idx_time + len(marker_time):].strip()
                    time_str = time_str.split(" ")[0]
                    img_start_time = datetime.fromisoformat(time_str)
                except: pass
            else:
                parts = line.split()
                filename = parts[1] if len(parts) > 1 else "Unknown"

            current_image = {
                "session_id": current_session_id,
                "session_folder": session_folder,
                "filename": filename,
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

    df_unique = df.groupby('filename').agg({
        'session_id': 'first',
        'session_folder': 'first',
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
# 3. PDF REPORT GENERATOR (FIXED ENCODING)
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

    def kpi_box(self, label, value, x, y, w=45):
        self.set_xy(x, y)
        self.set_fill_color(255, 255, 255)
        self.set_draw_color(200, 200, 200)
        self.rect(x, y, w, 18, 'DF')
        
        self.set_font('Arial', 'B', 8)
        self.set_text_color(127, 140, 141)
        self.cell(w, 6, self.clean_text(label), 0, 1, 'C')
        
        self.set_font('Arial', 'B', 12)
        self.set_text_color(44, 62, 80)
        self.set_x(x)
        self.cell(w, 8, self.clean_text(value), 0, 0, 'C')

def create_full_pdf(df_unique, df_raw, figures):
    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # --- PAGINA 1: DASHBOARD ---
    pdf.section_header("1. PANORAMICA ESECUTIVA")
    
    tot_work = df_unique["time_spent_sec"].sum()
    tot_actions = df_unique["actions"].sum()
    undo_rate = (df_unique["undos"].sum() / tot_actions * 100) if tot_actions > 0 else 0
    
    y = pdf.get_y()
    pdf.kpi_box("TOT IMG", str(len(df_unique)), 10, y)
    pdf.kpi_box("TEMPO TOT", f"{tot_work/60:.1f} m", 60, y)
    pdf.kpi_box("AZIONI", str(int(tot_actions)), 110, y)
    pdf.kpi_box("UNDO RATE", f"{undo_rate:.1f}%", 160, y)
    
    pdf.set_y(y + 25)
    pdf.set_font('Arial', '', 11)
    txt = (f"Analisi completata su {len(df_unique)} immagini uniche.\n"
           f"Tempo totale di annotazione: {tot_work:.0f} secondi.\n"
           f"OCR Validati: {int(df_unique['ocr_validated'].sum())} su {int(df_unique['num_ocr'].sum())}.")
    pdf.multi_cell(0, 6, pdf.clean_text(txt))
    pdf.ln(10)
    
    # --- SCATTER PLOT ---
    pdf.section_header("2. ANALISI EFFICIENZA")
    if "scatter" in figures:
        try:
            tmp_path = os.path.join(
                tempfile.gettempdir(),
                "kpi_scatter.png"
            )
            figures["scatter"].write_image(
                tmp_path, width=1000, height=500, scale=1.5
            )
            pdf.image(tmp_path, x=10, w=190)
            os.remove(tmp_path)
        except Exception as e:
            pdf.cell(0, 10, f"Err grafico scatter: {str(e)}", 0, 1)


    # --- PAGINA 2: TOP 20 LENTE ---
    pdf.add_page()
    pdf.section_header("3. TOP 20 IMMAGINI PIU LENTE")
    
    if "bar_chart" in pdf_figures:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tf:
                # Altezza maggiore per vedere bene le barre
                figures["bar_chart"].write_image(tf.name, width=900, height=800, scale=1.5) 
                pdf.image(tf.name, x=10, y=pdf.get_y()+5, w=190) 
                os.unlink(tf.name)
        except Exception as e:
            pdf.cell(0, 10, f"Err grafico bar: {str(e)}", 0, 1)
    else:
        pdf.cell(0, 10, "Nessun dato disponibile per il grafico a barre.", 0, 1)

    # --- PAGINA 3: TIMELINE ---
    pdf.add_page()
    pdf.section_header("4. FLUSSO TEMPORALE (Timeline)")
    if "timeline" in figures:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tf:
                figures["timeline"].write_image(tf.name, width=1000, height=500, scale=1.5)
                pdf.image(tf.name, x=10, w=190)
                os.unlink(tf.name)
        except: pass
    
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
    upl_file = st.file_uploader("Carica File KPI", type=["kpi", "txt", "kkk"])
    st.divider()

    # FIX PATH: Aggiornamento automatico con path dal log
    if upl_file and not st.session_state.current_folder_path:
        st.info("📁 Seleziona la cartella che contiene le immagini del KPI caricato")

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
st.title("🧠 KPI Manager v3 – FINAL ") 

pdf_figures = {}

if upl_file:
    # Parsing effettivo
    df_raw, df_unique = enrich_data(parse_kpi_file(upl_file))

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Dashboard",
        "📈 Analisi Efficienza",
        "🕒 Timeline",
        "👁️ Ispezione"
    ])

    with tab1:
        st.subheader("Performance Operativa")
        tot_unique = len(df_unique)
        tot_work = df_unique["time_spent_sec"].sum()
        avg_time = tot_work / tot_unique if tot_unique > 0 else 0
        tot_actions = df_unique["actions"].sum()
        undo_rate = (df_unique["undos"].sum() / tot_actions * 100) if tot_actions > 0 else 0
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🖼️ Immagini", tot_unique)
        c2.metric("⏱️ Tempo Tot", f"{tot_work/60:.1f} min")
        c3.metric("⚡ Media/Imm", f"{avg_time:.1f} s")
        c4.metric("🖱️ Azioni", int(tot_actions))
        st.divider()
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("↩️ Undo Rate", f"{undo_rate:.1f}%")
        k2.metric("📝 OCR Tot", int(df_unique["num_ocr"].sum()))
        k3.metric("✅ Validati", int(df_unique["ocr_validated"].sum()))
        k4.metric("⚠️ Non Validati", int(df_unique["ocr_not_validated"].sum()))
                
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
        st.subheader("Timeline Completa")
        if not df_raw.empty:
            df_t = df_raw.copy()
            df_t = df_t.dropna(subset=["timestamp_obj"])
            df_t["end_time"] = df_t["timestamp_obj"] + pd.to_timedelta(df_t["time_spent_sec"], unit="s")

            fig_tl = px.timeline(df_t, x_start="timestamp_obj", x_end="end_time", 
                              y="filename", color="Session Label",
                              title="Sequenza Operazioni")
            fig_tl.update_yaxes(autorange="reversed")
            st.plotly_chart(fig_tl, use_container_width=True)
            pdf_figures["timeline"] = fig_tl            

    with tab4:
        col_l, col_r = st.columns([1, 2])
        with col_l:
            sel_file = st.selectbox("Seleziona Immagine", df_unique["filename"],
                                    format_func=lambda x: f"{x} ({df_unique[df_unique['filename']==x]['time_spent_sec'].values[0]:.1f}s)")
        with col_r:
            if sel_file:
                row = df_unique[df_unique["filename"] == sel_file].iloc[0]
                img_path = load_image_smart(sel_file, row["session_folder"], path_override, use_override)
                if img_path:
                    try:
                        img = Image.open(img_path).convert("RGB")
                        json_path = os.path.splitext(img_path)[0] + ".json"
                        img, ocr = draw_overlay(img, json_path)
                        st.image(img, use_container_width=True)
                    except: st.error("Errore lettura immagine")
                else: st.error("File non trovato")

    # BOTTONE PDF NELLA SIDEBAR
    with st.sidebar:
        st.divider()
        # Mostra il bottone solo se abbiamo dati
        if not df_unique.empty:
            if st.button("🖨️ Genera Report PDF"):
                with st.spinner("Rendering PDF..."):
                    try:
                        pdf_data = create_full_pdf(df_unique, df_raw, pdf_figures)
                        st.download_button("📥 Download Report.pdf", pdf_data, "Report_KPI_V3.pdf", "application/pdf")
                    except Exception as e:
                        st.error(f"Errore PDF: {e}")
                        st.info("Nota: Assicurati di aver visualizzato i grafici nei Tab prima di stampare.")
