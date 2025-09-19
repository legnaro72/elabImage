import os
import cv2
import numpy as np
import streamlit as st
from PIL import Image, ImageDraw
import tempfile
from streamlit_drawable_canvas import st_canvas
import base64
from io import BytesIO

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

def draw_boxes(image, bboxes):
    """Disegna i bounding box sull'immagine"""
    draw = ImageDraw.Draw(image)
    for box in bboxes:
        x1, y1, x2, y2 = box['coords']
        cls = box['class']
        color = COLORS.get(cls, '#FF0000')
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        label = f"{cls}"
        text_bbox = draw.textbbox((x1, y1), label)
        draw.rectangle(text_bbox, fill=color)
        draw.text((x1, y1), label, fill='white')
    return image

def save_annotated_image(image_data, bboxes, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    from io import BytesIO
    img = Image.open(BytesIO(image_data['content']))
    img = draw_boxes(img, bboxes)
    base_name = os.path.splitext(image_data['name'])[0]
    output_path = os.path.join(output_dir, f"{base_name}_marked.jpg")
    img.save(output_path)
    return output_path

def parse_filename_boxes(filename):
    """
    Estrae i bounding box dal nome file in formato:
    ..._class_x1_y1_x2_y2_class_x1_y1_x2_y2.jpg
    """
    name, _ = os.path.splitext(filename)
    parts = name.split("_")
    boxes, i = [], 0
    while i < len(parts):
        if parts[i] in CLASSES:
            cls = parts[i]
            try:
                x1, y1, x2, y2 = map(int, parts[i+1:i+5])
                boxes.append({'class': cls, 'coords': [x1, y1, x2, y2]})
                i += 5
                continue
            except Exception:
                pass
        i += 1
    return boxes

# Interfaccia utente
st.title("🖼️ Annota Immagini")

# Sidebar per i controlli
with st.sidebar:
    st.header("Controlli")
    st.subheader("Seleziona Classe")
    for cls in CLASSES:
        if st.button(cls, key=f"btn_{cls}"):
            st.session_state.current_class = cls

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

    if st.button("💾 Salva"):
        if st.session_state.images and st.session_state.bboxes:
            output_dir = os.path.join(os.path.dirname(st.session_state.images[0]['name']), "annotated") if isinstance(st.session_state.images[0], dict) else "annotated"
            save_annotated_image(
                st.session_state.images[st.session_state.current_image_idx],
                st.session_state.bboxes,
                output_dir
            )
            st.sidebar.success(f"Salvato in: {output_dir}")

    st.subheader("Carica Immagini")
    uploaded_files = st.file_uploader("Carica immagini", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    if uploaded_files:
        st.session_state.images = []
        for uploaded_file in uploaded_files:
            try:
                file_content = uploaded_file.getvalue()
                st.session_state.images.append({
                    'name': uploaded_file.name,
                    'content': file_content
                })
            except Exception as e:
                st.sidebar.error(f"❌ Errore con {uploaded_file.name}: {str(e)}")
        if st.session_state.images:
            st.session_state.current_image_idx = 0
            st.session_state.bboxes = []
            st.rerun()

# Area principale
if st.session_state.images:
    current_image = st.session_state.images[st.session_state.current_image_idx]
    from io import BytesIO
    img = Image.open(BytesIO(current_image['content']))
    if img.mode != 'RGB':
        img = img.convert('RGB')

    st.subheader(f"Immagine {st.session_state.current_image_idx + 1} di {len(st.session_state.images)}")
    st.caption(f"File: {current_image['name']}")

    # Se i bboxes sono vuoti, prova a leggerli dal nome file
    if not st.session_state.bboxes:
        parsed_boxes = parse_filename_boxes(current_image['name'])
        if parsed_boxes:
            st.session_state.bboxes = parsed_boxes

    # === Editor Bounding Box ===
    st.subheader("Editor Bounding Box")
    drawing_mode = st.selectbox("Modalità disegno:", ("rect", "transform"), index=0)
    stroke_color = COLORS.get(st.session_state.current_class, '#FF0000')

    img_with_boxes = img.copy()
    if st.session_state.bboxes:
        img_with_boxes = draw_boxes(img_with_boxes, st.session_state.bboxes)

    # Converti immagine in base64 per compatibilità
    buffered = BytesIO()
    img_with_boxes.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    background_url = f"data:image/png;base64,{img_str}"

    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=2,
        stroke_color=stroke_color,
        background_image=background_url,  # URL base64 invece di PIL.Image
        update_streamlit=True,
        height=img.height,
        width=img.width,
        drawing_mode=drawing_mode,
        key="canvas",
    )

    if canvas_result.json_data is not None:
        new_bboxes = []
        for obj in canvas_result.json_data["objects"]:
            if obj["type"] == "rect":
                x1 = int(obj["left"])
                y1 = int(obj["top"])
                x2 = int(x1 + obj["width"])
                y2 = int(y1 + obj["height"])
                cls = obj.get("class", st.session_state.current_class)
                new_bboxes.append({'coords': [x1, y1, x2, y2], 'class': cls})
        if new_bboxes != st.session_state.bboxes:
            st.session_state.bboxes = new_bboxes

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

# CSS personalizzato
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
