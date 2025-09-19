import os
import cv2
import numpy as np
import streamlit as st
from PIL import Image, ImageDraw
import tempfile
from streamlit_drawable_canvas import st_canvas

# Configurazione della pagina
st.set_page_config(
    page_title="Annota Immagini",
    page_icon="📝",
    layout="wide"
)

# Classi disponibili
CLASSES = ['car', 'van', 'plate', 'bus', 'motorcycle', 'truck', 'person']
COLORS = {
    'car': '#FF0000',
    'van': '#0000FF',
    'plate': '#00FF00',
    'bus': '#FF00FF',
    'motorcycle': '#FFA500',
    'truck': '#00FFFF',
    'person': '#008000'
}

# Inizializza lo stato della sessione
if 'bboxes' not in st.session_state:
    st.session_state.bboxes = []
if 'current_class' not in st.session_state:
    st.session_state.current_class = CLASSES[0]
if 'current_image_idx' not in st.session_state:
    st.session_state.current_image_idx = 0
if 'images' not in st.session_state:
    st.session_state.images = []
if 'temp_dir' not in st.session_state:
    st.session_state.temp_dir = tempfile.TemporaryDirectory()

def load_images(folder):
    """Carica tutte le immagini dalla cartella specificata"""
    valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp')
    images = []
    for f in os.listdir(folder):
        if f.lower().endswith(valid_extensions) and not (f.endswith('_marked.jpg') or f.endswith('_annotated.jpg')):
            images.append(os.path.join(folder, f))
    return images

def draw_boxes(image, bboxes):
    """Disegna i bounding box sull'immagine"""
    draw = ImageDraw.Draw(image)
    for box in bboxes:
        x1, y1, x2, y2 = box['coords']
        cls = box['class']
        color = COLORS.get(cls, '#FF0000')
        
        # Disegna il rettangolo
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        
        # Aggiungi l'etichetta
        label = f"{cls}"
        text_bbox = draw.textbbox((x1, y1), label)
        draw.rectangle(text_bbox, fill=color)
        draw.text((x1, y1), label, fill='white')
    
    return image

def save_annotated_image(image_path, bboxes, output_dir):
    """Salva l'immagine con le annotazioni"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Carica l'immagine originale
    img = Image.open(image_path)
    img = draw_boxes(img, bboxes)
    
    # Crea il nome del file di output
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    output_path = os.path.join(output_dir, f"{base_name}_marked.jpg")
    
    # Salva l'immagine
    img.save(output_path)
    return output_path

# Interfaccia utente
st.title("🖼️ Annota Immagini")

# Sidebar per i controlli
with st.sidebar:
    st.header("Controlli")
    
    # Seleziona la classe
    st.subheader("Seleziona Classe")
    for cls in CLASSES:
        if st.button(cls, key=f"btn_{cls}"):
            st.session_state.current_class = cls
    
    # Pulsanti di navigazione
    st.subheader("Navigazione")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Precedente"):
            if st.session_state.current_image_idx > 0:
                st.session_state.current_image_idx -= 1
                st.session_state.bboxes = []
    with col2:
        if st.button("Prossima →"):
            if st.session_state.images and st.session_state.current_image_idx < len(st.session_state.images) - 1:
                st.session_state.current_image_idx += 1
                st.session_state.bboxes = []
    
    # Pulsante Salva
    if st.button("💾 Salva"):
        if st.session_state.images and st.session_state.bboxes:
            output_dir = os.path.join(os.path.dirname(st.session_state.images[0]), "annotated")
            save_annotated_image(
                st.session_state.images[st.session_state.current_image_idx],
                st.session_state.bboxes,
                output_dir
            )
            st.sidebar.success(f"Salvato in: {output_dir}")
    
    # Seleziona cartella immagini
    st.subheader("Carica Immagini")
    uploaded_files = st.file_uploader("Carica immagini", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    
    if uploaded_files:
        # Salva i file caricati in una cartella temporanea
        temp_dir = st.session_state.temp_dir.name
        for uploaded_file in uploaded_files:
            with open(os.path.join(temp_dir, uploaded_file.name), "wb") as f:
                f.write(uploaded_file.getbuffer())
        
        # Aggiorna la lista delle immagini
        st.session_state.images = [os.path.join(temp_dir, f.name) for f in uploaded_files]
        st.session_state.current_image_idx = 0
        st.session_state.bboxes = []
        st.rerun()

# Area principale per l'immagine
if st.session_state.images:
    current_image_path = st.session_state.images[st.session_state.current_image_idx]
    img = Image.open(current_image_path)
    
    # Mostra l'immagine con i bounding box
    st.subheader(f"Immagine {st.session_state.current_image_idx + 1} di {len(st.session_state.images)}")
    st.caption(f"File: {os.path.basename(current_image_path)}")
    
    # Crea un'immagine con i bounding box
    img_with_boxes = img.copy()
    if st.session_state.bboxes:
        img_with_boxes = draw_boxes(img_with_boxes, st.session_state.bboxes)
    
    # Mostra l'immagine
    st.image(img_with_boxes, use_column_width=True)
    
    # Aggiungi la possibilità di disegnare un nuovo box
    st.subheader("Aggiungi Bounding Box")
    st.write("Seleziona un'area nell'immagine per creare un nuovo box")
    
    # Usa st.image con drawing_mode per il disegno
    drawing_mode = st.selectbox(
        "Modalità disegno:",
        ("freedraw", "line", "rect", "circle", "transform", "point")
    )
    
    # Seleziona il colore in base alla classe corrente
    stroke_color = COLORS.get(st.session_state.current_class, '#FF0000')
    
    # Usa st_canvas per disegnare
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=2,
        stroke_color=stroke_color,
        background_image=img_with_boxes,
        update_streamlit=True,
        height=img.height,
        width=img.width,
        drawing_mode=drawing_mode,
        key="canvas",
    )
    
    # Gestisci il disegno completato
    if canvas_result.json_data is not None:
        objects = canvas_result.json_data["objects"]
        for obj in objects:
            if obj["type"] == "rect":
                x1 = int(obj["left"])
                y1 = int(obj["top"])
                x2 = int(x1 + obj["width"])
                y2 = int(y1 + obj["height"])
                
                # Aggiungi il nuovo box alla lista
                st.session_state.bboxes.append({
                    'coords': [x1, y1, x2, y2],
                    'class': st.session_state.current_class
                })
                st.rerun()
    
    # Mostra i box correnti
    st.subheader("Bounding Box Correnti")
    for i, box in enumerate(st.session_state.bboxes):
        x1, y1, x2, y2 = box['coords']
        cls = box['class']
        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            st.write(f"{cls}: ({x1}, {y1}) - ({x2}, {y2})")
        with col2:
            new_class = st.selectbox(
                f"Classe {i+1}",
                CLASSES,
                index=CLASSES.index(cls),
                key=f"class_{i}"
            )
            if new_class != cls:
                st.session_state.bboxes[i]['class'] = new_class
                st.rerun()
        with col3:
            if st.button("❌", key=f"del_{i}"):
                del st.session_state.bboxes[i]
                st.rerun()
else:
    st.info("Carica delle immagini usando il pannello a sinistra per iniziare.")

# Aggiungi stili CSS personalizzati
st.markdown("""
    <style>
        .stButton>button {
            width: 100%;
            margin: 5px 0;
        }
        .stSelectbox {
            margin: 5px 0;
        }
    </style>
""", unsafe_allow_html=True)
