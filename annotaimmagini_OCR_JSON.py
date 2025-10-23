import os
import cv2
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
from PIL import Image, ImageTk, ImageFont, ImageDraw
import sys

# Aggiunge il supporto per il ri-campionamento di PIL
try:
    # Per PIL 10.0.0 e successive
    Image.Resampling.LANCZOS 
except AttributeError:
    # Per versioni precedenti
    Image.Resampling.LANCZOS = Image.LANCZOS




    
class BoundingBoxEditor:
    import json  # Importa il modulo json
    
    def _json_path(self, image_filename):
        base, _ = os.path.splitext(image_filename)
        return os.path.join(self.folder, base + ".json")

    
    def _load_boxes_from_json(self, image_filename):
        json = self.json
        json_path = self._json_path(image_filename)
        boxes = []
        ocr_found = False
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for box in data.get("boxes", []):
                    if "coords" in box and isinstance(box["coords"], list) and len(box["coords"]) == 4:
                        boxes.append({"class": box["class"], "coords": box["coords"]})
                    elif box.get("class") == "OCR":
                        ocr_found = True
                        value = box.get("value", [""])
                        if isinstance(value, list) and value:
                            self.plate_var.set(value[0].upper())
                        else:
                            self.plate_var.set("")
            except Exception as e:
                print(f"Errore lettura JSON {json_path}: {e}")
        # Gestione editabilità OCR
        if hasattr(self, 'plate_entry'):
            state = 'normal' if ocr_found else 'disabled'
            self.plate_entry.config(state=state)
        if hasattr(self, 'validate_plate_check'):
            state = 'normal' if ocr_found else 'disabled'
            self.validate_plate_check.config(state=state)
        return boxes

    def _save_boxes_to_json(self):
        json_path = self._json_path(self.filename)
        try:
            data = {"boxes": []}
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "boxes" not in data:
                    data["boxes"] = []
            # aggiorna box (no OCR)
            new_boxes = [ {"class": b["class"], "coords": b["coords"]} for b in self.bboxes ]
            # conserva OCR
            ocr_boxes = [b for b in data["boxes"] if b.get("class") == "OCR"]
            data["boxes"] = ocr_boxes + new_boxes

            # Aggiorna OCR se confermato
            ocr_val = self.plate_var.get().strip().upper()
            confirmed = bool(self.validate_plate_var.get()) if hasattr(self, 'validate_plate_var') else False
            existing_ocr = next((b for b in data["boxes"] if b.get("class") == "OCR"), None)

            if existing_ocr:
                if confirmed and ocr_val:
                    existing_ocr["value"] = [ocr_val]
                    self.validate_plate_var.set(False)
            elif ocr_val:
                data["boxes"].append({"class": "OCR", "value": [ocr_val]})

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Errore salvataggio JSON {json_path}: {e}")


    def _save_boxes_to_json(self):
        json_path = self._json_path(self.filename)
        try:
            data = {"boxes": []}
            for b in self.bboxes:
                data["boxes"].append({"class": b["class"], "coords": b["coords"]})
            # aggiunge OCR se presente nel campo plate_var
            ocr_val = self.plate_var.get().strip().upper()
            if ocr_val:
                data["boxes"].append({"class": "OCR", "value": [ocr_val]})
            with open(json_path, "w", encoding="utf-8") as f:
                self.json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Errore salvataggio JSON {json_path}: {e}")


    def _extract_plate_from_filename(self, filename):
        name, _ = os.path.splitext(filename)
        parts = name.split("_")
        for i, part in enumerate(parts):
            if part == "ocr" and i + 1 < len(parts):
                return parts[i + 1]
        return ""
        
    def __init__(self, root, folder):
        # === Inizializzazione variabili OCR ===
        self.plate_var = None
        self.validate_plate_var = None
        # === Inizializzazione variabili OCR ===
        # Modifica per inizializzare correttamente le variabili di controllo (OCR)
        self.plate_var = tk.StringVar(root)        # <-- CORREZIONE 1
        self.validate_plate_var = tk.BooleanVar(root)  # <-- CORREZIONE 2
        self.root = root
        self.folder = folder
        # VECCHIO: self.images = [f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.png'))]
        # NUOVO: Filtra solo i file immagine. AGGIUNTO '.jpeg' (anche se il file è .JPEG)
        self.images = [f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        
        self.index = 0
        self.bboxes = []
        # current_box deve essere un intero (-1 per non selezionato)
        self.current_box = -1
        self.dragging = False
        self.resizing = False
        self.resize_handle = None
        self.scale = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.original_img = None
        self.creating_box = False      
        self.new_box_start = None      
        self.new_box_end = None        
        
        # Classi disponibili
        self.classes = ['bicycle', 'bus', 'car', 'motorcycle', 'pickup', 'truck', 'van',  'plate', 'person', 'backpack', 'handbag', 'suitcase']
        
        # Classe predefinita (default)
        self.current_class = self.classes[0] if self.classes else 'object'
        
        # --- DEFINIZIONE COLORI (Dark Mode, rese globali per i metodi) ---
        self.BG_DARK = '#2C3E50'     
        self.BG_LIGHT = '#34495E'    
        self.FG_WHITE = 'white'
        self.BUTTON_ACCENT = '#3498DB' 
        self.BUTTON_ACCENT_ACTIVE = '#2980B9'
        self.BUTTON_DANGER = '#E74C3C' 
        self.BUTTON_DANGER_ACTIVE = '#C0392B'

        self.root.title("Editor Bounding Box - Dark Mode")
        # Tentativo di massimizzare la finestra su Windows
        try:
             self.root.state('zoomed')
        except tk.TclError:
             self.root.geometry("1200x800") 
        
        # --- Configurazione Interfaccia ---
        self.create_widgets()
        self.setup_bindings()

        if not self.images:
            messagebox.showinfo("Nessuna Immagine", "Nessuna immagine trovata nella cartella specificata.")
            self.root.destroy()

            
        # CORREZIONE FOCUS
        self.root.after(100, self.canvas.focus_set)
        
        messagebox.showinfo(
            "Istruzioni Focus",
            "Benvenuto! Se le scorciatoie da tastiera (Tab, Canc, N) non dovessero funzionare immediatamente all'avvio, ti preghiamo di **cliccare una volta sul pulsante 'Aggiungi Classe'** o semplicemente **fare un click a vuoto sul riquadro nero** dell'immagine."
        )


    def create_widgets(self):
        
        # Opzioni base per i pulsanti (stile Flat)
        button_options = {'bg': self.BUTTON_ACCENT, 'fg': self.FG_WHITE, 'relief': tk.FLAT, 
                          'activebackground': self.BUTTON_ACCENT_ACTIVE, 'activeforeground': self.FG_WHITE, 
                          'font': ('Arial', 9, 'bold'), 'pady': 5}
        
        # Frame principale
        main_frame = tk.Frame(self.root, bg=self.BG_DARK)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Canvas per l'immagine
        self.canvas = tk.Canvas(main_frame, bg='black', highlightthickness=0) 
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Sidebar (controlli) - LARGHEZZA 300px
        self.SIDEBAR_WIDTH = 300 
        control_frame = tk.Frame(main_frame, width=self.SIDEBAR_WIDTH, bg=self.BG_LIGHT) 
        control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
        control_frame.pack_propagate(False) 

        # Status Bar
        self.status_label = tk.Label(self.root, text="", bd=1, relief=tk.SUNKEN, anchor=tk.W, bg=self.BG_DARK, fg=self.FG_WHITE, font=('Arial', 9))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 1. --- Controlli Immagine (Navigazione) ---
        img_controls = tk.LabelFrame(control_frame, text="Navigazione Immagini", padx=5, pady=5, bg=self.BG_LIGHT, fg=self.FG_WHITE, font=('Arial', 10, 'bold'))
        img_controls.pack(fill=tk.X, pady=5, padx=5)
        
        # --- Riga con nome immagine + pulsante per cambiare cartella ---
        img_label_frame = tk.Frame(img_controls, bg=self.BG_LIGHT)
        img_label_frame.pack(fill=tk.X, pady=5)

        self.image_label = tk.Label(img_label_frame, text="IMG 0/0: N/A", bg=self.BG_LIGHT, fg='gold', font=('Arial', 10))
        self.image_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 🔘 Pulsante evocativo per ricaricare una nuova cartella immagini
        reload_btn = tk.Button(
            img_label_frame,
            text="📁",  # piccola icona a forma di cartella
            bg='#FF8C00',  # ⬅️ CAMBIATO: Colore arancione (DarkOrange)
            fg=self.FG_WHITE,
            font=('Arial', 10, 'bold'),
            relief=tk.FLAT,
            activebackground='#CC7000', # ⬅️ CAMBIATO: Arancione scuro per lo stato attivo
            activeforeground=self.FG_WHITE,
            command=self._select_new_folder,  # nuovo metodo
            width=5  # ⬅️ AGGIUNTO: Forza una larghezza minima (lo rende più o meno quadrato)
        )
        reload_btn.pack(side=tk.RIGHT, padx=3)

        
        nav_buttons_frame = tk.Frame(img_controls, bg=self.BG_LIGHT)
        nav_buttons_frame.pack(fill=tk.X)
        
        tk.Button(nav_buttons_frame, text="<<Prec(a)", command=self.prev_image, **button_options).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        tk.Button(nav_buttons_frame, text="Salva(Ctrl+S)", command=self._save_current_image, **button_options).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        # 🔴 Nuovo pulsante per cancellare l'immagine corrente
        delete_img_options = {'bg': self.BUTTON_DANGER, 'fg': self.FG_WHITE, 'relief': tk.FLAT,
                              'activebackground': self.BUTTON_DANGER_ACTIVE, 'activeforeground': self.FG_WHITE,
                              'font': ('Arial', 9, 'bold'), 'pady': 5}
        tk.Button(nav_buttons_frame, text="Del", command=self.delete_current_image,
                  **delete_img_options).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        tk.Button(nav_buttons_frame, text="Succ(d)>>", command=self.next_image, **button_options).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)


        # 2. --- CONTAINER COMPATTATO: Statistiche BB ---
        stats_controls = tk.LabelFrame(control_frame, text="Statistiche Box", padx=5, pady=5, bg=self.BG_LIGHT, fg=self.FG_WHITE, font=('Arial', 10, 'bold'))
        stats_controls.pack(fill=tk.X, pady=5, padx=5)

        # Frame per il Totale BB (in linea)
        total_frame = tk.Frame(stats_controls, bg=self.BG_LIGHT)
        total_frame.pack(fill=tk.X)
        
        tk.Label(total_frame, text="Totale BBox:", bg=self.BG_LIGHT, fg=self.FG_WHITE, font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 5))
        self.total_bb_label = tk.Label(total_frame, text="0", bg=self.BG_LIGHT, fg='cyan', font=('Arial', 12, 'bold'))
        self.total_bb_label.pack(side=tk.LEFT)

        # Label per il Dettaglio
        self.class_breakdown_label = tk.Label(stats_controls, text="Nessun box presente", bg=self.BG_LIGHT, fg=self.FG_WHITE, justify=tk.LEFT, anchor=tk.NW, font=('Arial', 9)) # Font più piccolo
        self.class_breakdown_label.pack(fill=tk.BOTH, expand=True) 
        
        # 3. --- Controlli Bounding Box ---
        box_controls = tk.LabelFrame(control_frame, text="Controlli Box", padx=5, pady=5, bg=self.BG_LIGHT, fg=self.FG_WHITE, font=('Arial', 10, 'bold'))
        box_controls.pack(fill=tk.X, pady=5, padx=5)

        # Frame per i pulsanti principali (Nuovo e Cancella sulla stessa riga)
        button_frame = tk.Frame(box_controls, bg=self.BG_LIGHT)
        button_frame.pack(fill=tk.X, pady=2)

        tk.Button(button_frame, text="Nuovo Box (n)", command=self.create_new_box_mode, **button_options).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))

        # Pulsante Elimina con stile di pericolo (rosso)
        delete_options = {'bg': self.BUTTON_DANGER, 'fg': self.FG_WHITE, 'relief': tk.FLAT,
                          'activebackground': self.BUTTON_DANGER_ACTIVE, 'activeforeground': self.FG_WHITE,
                          'font': ('Arial', 10, 'bold'), 'pady': 5}
        tk.Button(button_frame, text="Elimina Box (Canc)", command=self.delete_current_box, **delete_options).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        # Etichetta Classe Corrente
        tk.Label(box_controls, text="Classe Corrente:", bg=self.BG_LIGHT, fg=self.FG_WHITE).pack(fill=tk.X, pady=(5, 0))
        self.current_class_label = tk.Label(box_controls, text=self.current_class, bg='gold', fg=self.BG_DARK, relief=tk.SUNKEN, font=('Arial', 12, 'bold'))
        self.current_class_label.pack(fill=tk.X)
        
        # 4. --- Controlli OCR/Targa (Aggiunto) ---
        ocr_controls = tk.LabelFrame(control_frame, text="Controllo Targa (OCR)", padx=5, pady=5, bg=self.BG_LIGHT, fg=self.FG_WHITE, font=('Arial', 10, 'bold'))
        ocr_controls.pack(fill=tk.X, pady=5, padx=5)

        # Campo di input collegato a self.plate_var
        self.plate_entry = tk.Entry(ocr_controls, textvariable=self.plate_var, bg="white", fg="black", font=("Arial", 12, "bold"))
        self.plate_entry.pack(fill=tk.X, pady=2)
        
        # Checkbox collegato a self.validate_plate_var (usato nella logica di salvataggio)
        self.validate_plate_check = tk.Checkbutton(ocr_controls, text="Conferma Nuova Targa (Salva)", variable=self.validate_plate_var,
                       bg=self.BG_LIGHT, fg=self.FG_WHITE, selectcolor=self.BG_LIGHT,
                       font=("Arial", 9))
        self.validate_plate_check.pack(fill=tk.X)

        # 4bis. --- Selettore Classi (CON GRIGLIA 2 COLONNE) ---
        class_frame = tk.LabelFrame(control_frame, text="Seleziona Classe", padx=5, pady=5, bg=self.BG_LIGHT, fg=self.FG_WHITE, font=('Arial', 10, 'bold'))
        class_frame.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)

        canvas_class = tk.Canvas(class_frame, bg=self.BG_LIGHT, highlightthickness=0)
        canvas_class.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(class_frame, orient="vertical", command=canvas_class.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        canvas_class.configure(yscrollcommand=scrollbar.set)
        
        self.class_button_frame = tk.Frame(canvas_class, bg=self.BG_LIGHT) 
        
        # Caricamento iniziale dell'immagine dopo la creazione completa della GUI
        if self.images:
            self.load_image()

        
        def on_canvas_class_configure(event):
            # Mantiene il frame interno largo quanto il canvas
            # Nota: event potrebbe essere None se chiamato manualmente
            if event is not None:
                canvas_class.itemconfig(self.scrollable_frame_id, width=event.width)
            else:
                # Usa la larghezza attuale del canvas se event è None (chiamata forzata)
                canvas_class.itemconfig(self.scrollable_frame_id, width=canvas_class.winfo_width())


        self.scrollable_frame_id = canvas_class.create_window((0, 0), window=self.class_button_frame, anchor="nw")
        canvas_class.bind('<Configure>', on_canvas_class_configure)
        
        # AGGIUNTA CHIAVE: Forza l'esecuzione della configurazione all'avvio
        # Usa after_idle per garantire che la finestra sia già disegnata
        self.root.after_idle(lambda: on_canvas_class_configure(None)) 

        self.update_class_buttons()  


    # --- NUOVO METODO STATISTICHE ---
    def _update_box_stats(self):
        """Calcola e aggiorna le statistiche dei BB nella sidebar."""
        
        total_boxes = len(self.bboxes)
        self.total_bb_label.config(text=str(total_boxes))
        
        if total_boxes == 0:
            self.class_breakdown_label.config(text="Nessun box presente", fg=self.FG_WHITE)
            return

        class_counts = {}
        for box in self.bboxes:
            cls = box['class']
            class_counts[cls] = class_counts.get(cls, 0) + 1
            
        stats_text = ""
        # Stampa le classi ordinate (più compatte)
        for cls, count in sorted(class_counts.items(), key=lambda item: (item[0], -item[1])):
            stats_text += f"• {cls}: {count}  " # Doppio spazio per separare
            
        # Rimuove l'ultimo doppio spazio e punto elenco se necessario
        self.class_breakdown_label.config(text=stats_text.strip(), fg=self.FG_WHITE)
        
    def _get_truncated_filename(self, filename, max_len=30):
        """Tronca un filename troppo lungo per la sidebar."""
        if len(filename) <= max_len:
            return filename
        
        name, ext = os.path.splitext(filename)
        ext_len = len(ext)
        
        available_len = max_len - ext_len - 3 
        
        if available_len <= 5: 
            return filename[:max_len] + '...'

        start_len = available_len // 2
        end_len = available_len - start_len
        
        truncated_name = name[:start_len] + "..." + name[len(name) - end_len:]
        
        return truncated_name + ext

    # --- CORREZIONE: LOGICA DI SCROLLBAR IN update_class_buttons (Layout GRIGLIA) ---
    def update_class_buttons(self):
        """Aggiorna i bottoni delle classi in un layout a 2 colonne e ricalcola l'area di scroll."""
        
        CLS_BTN_BG = '#4A6572'
        CLS_BTN_ACTIVE_BG = '#607D8B'
        
        # 1. Distrugge i vecchi bottoni
        for widget in self.class_button_frame.winfo_children():
            widget.destroy()

        # 2. Crea i nuovi bottoni usando GRID per un layout a 2 colonne
        NUM_COLUMNS = 2
        
        for i, cls in enumerate(self.classes):
            btn = tk.Button(self.class_button_frame, text=cls, 
                            command=lambda c=cls: self.set_current_class(c),
                            bg=CLS_BTN_BG, fg='white', relief=tk.FLAT,
                            activebackground=CLS_BTN_ACTIVE_BG, activeforeground='white',
                            font=('Arial', 8)) 
            
            # Posizionamento a griglia (due colonne)
            row = i // NUM_COLUMNS
            col = i % NUM_COLUMNS
            
            # Spaziatura minima (padx/pady=1)
            btn.grid(row=row, column=col, sticky=tk.W + tk.E, padx=1, pady=1)

        # Rendi entrambe le colonne espandibili per distribuire la larghezza
        # QUESTE SONO LE RIGHE CRUCIALI PER L'ESPANSIONE
        self.class_button_frame.grid_columnconfigure(0, weight=1)
        self.class_button_frame.grid_columnconfigure(1, weight=1)


        # 3. Aggiorna la scrollregion DOPO aver creato i bottoni
        self.class_button_frame.update_idletasks()
        
        # Ricalcola la scrollregion basandosi sul bbox del frame interno
        self.class_button_frame.master.config(scrollregion=self.class_button_frame.master.bbox("all"))

        # 4. Binding per aggiornare la scrollregion se il frame interno cambia dimensione
        self.class_button_frame.bind('<Configure>', 
             lambda e: self.class_button_frame.master.config(scrollregion=self.class_button_frame.master.bbox("all")))

    def set_current_class(self, cls):
        self.current_class = cls
        self.current_class_label.config(text=self.current_class)
        if self.current_box != -1:
            self.bboxes[self.current_box]['class'] = cls
            self._draw_bboxes()
            self._update_box_stats() # Aggiorna statistiche
            self.status_label.config(text=f"Classe box {self.current_box+1} impostata su {cls}", fg='blue')
        else:
            self.status_label.config(text=f"Classe predefinita impostata su {cls}", fg='blue')
            
    def add_new_class(self):
        new_class = simpledialog.askstring("Aggiungi Classe", "Inserisci il nome della nuova classe:", parent=self.root)
        if new_class and new_class not in self.classes:
            self.classes.append(new_class)
            self.update_class_buttons()
            self.status_label.config(text=f"Classe '{new_class}' aggiunta", fg='green')
        elif new_class:
             self.status_label.config(text=f"Classe '{new_class}' è già presente", fg='orange')


    # --- LOGICA DI PARSING E SALVATAGGIO ---

    def parse_filename_boxes(self, filename):
        """Estrae i bounding box dal nome del file (formato cls_x1_y1_x2_y2)."""
        
        ALL_CLASSES = set([
            'car', 'motorcycle', 'truck', 'bus', 'bicycle', 'plate', 'van', 
            'person', 'handbag', 'backpack', 'suitcase'
        ] + self.classes)
        
        name, _ = os.path.splitext(filename)
        parts = name.split("_")
        boxes, i = [], 0
        
        while i < len(parts):
            cls = parts[i]
            # Controllo più robusto per accettare classi già esistenti
            if cls in ALL_CLASSES or cls in self.classes: 
                try:
                    coords_str = parts[i+1:i+5]
                    if len(coords_str) == 4 and all(p.isdigit() for p in coords_str):
                        x1, y1, x2, y2 = map(int, coords_str) 
                        boxes.append({'class': cls, 'coords': [x1, y1, x2, y2]})
                        i += 5
                        continue
                except ValueError:
                    pass
                except IndexError:
                    pass 
            i += 1
        return boxes

    def boxes_to_filename(self):
        """Genera la parte del nome del file per i bounding box (non scalati)."""
        parts = []
        for b in self.bboxes:
            x1, y1, x2, y2 = b['coords']
            # Normalizza le coordinate (min/max)
            x1, x2 = min(x1, x2), max(x1, x2)
            y1, y2 = min(y1, y2), max(y1, y2)
            
            parts.append(f"{b['class']}_{x1}_{y1}_{x2}_{y2}")
        return "_".join(parts)

    def load_image(self):
        """Carica l'immagine corrente e le annotazioni esistenti dal nome del file."""
        if not self.images:
            return
            
        self.filename = self.images[self.index]
        self.image_path = os.path.join(self.folder, self.filename)
        
        truncated_name = self._get_truncated_filename(self.filename)
        self.image_label.config(text=f"IMG {self.index + 1}/{len(self.images)}: {truncated_name}")

        try:
            img_cv2 = cv2.imread(self.image_path)
            if img_cv2 is None:
                 raise FileNotFoundError("Immagine non valida o non trovata")
            
            img_rgb = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB)
            self.original_img = Image.fromarray(img_rgb)
            self.img_width, self.img_height = self.original_img.size
            
        except Exception as e:
            messagebox.showerror("Errore di Caricamento", f"Errore caricando l'immagine {self.filename}: {e}")
            return

        self.canvas.delete("all")
        
        self.bboxes = self._load_boxes_from_json(self.filename)
        self.current_box = -1 
        
        self._fit_image_to_canvas() 
        
        self._update_box_stats() # Aggiorna statistiche
        
        self.status_label.config(text=f"Immagine caricata: {self.filename}", fg='white')
        
        self.canvas.focus_set()


    def _fit_image_to_canvas(self):
        """Calcola il fattore di scala per adattare l'immagine alla tela e la allinea in alto a sinistra (0,0)."""
        
        self.canvas.update_idletasks() 
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        
        if canvas_w <= 1 or canvas_h <= 1 or self.original_img is None:
            self.scale = 1.0
            self.pan_x = 0
            self.pan_y = 0
        else:
            scale_w = canvas_w / self.img_width
            scale_h = canvas_h / self.img_height
            
            self.scale = min(scale_w, scale_h) 
            
            self.pan_x = 0
            self.pan_y = 0
            
        self._update_canvas_image() 


    def _update_canvas_image(self):
        """Aggiorna l'immagine sulla tela in base a scale e pan."""
        if self.original_img is None:
            return

        new_w = int(self.img_width * self.scale)
        new_h = int(self.img_height * self.scale)

        resized_img = self.original_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        
        final_img = Image.new('RGB', (canvas_w, canvas_h), color = 'black')
        
        insert_x = int(self.pan_x * self.scale)
        insert_y = int(self.pan_y * self.scale)

        final_img.paste(resized_img, (insert_x, insert_y))

        self.tk_img = ImageTk.PhotoImage(final_img)
        self.canvas.delete("img_display")
        self.canvas.create_image(0, 0, image=self.tk_img, anchor=tk.NW, tags="img_display")
        
        self._draw_bboxes()

    # --- LOGICA DI DISEGNO ---

    def draw_box(self, box, selected=False):
        """Disegna un singolo bounding box con etichetta e maniglie se selezionato."""
        
        # 1. Recupera e Scala le Coordinate (aggiunge anche il pan)
        x1_img, y1_img, x2_img, y2_img = box['coords']
        x1_img, x2_img = min(x1_img, x2_img), max(x1_img, x2_img)
        y1_img, y2_img = min(y1_img, y2_img), max(y1_img, y2_img)
        
        x1 = x1_img * self.scale + self.pan_x * self.scale
        y1 = y1_img * self.scale + self.pan_y * self.scale
        x2 = x2_img * self.scale + self.pan_x * self.scale
        y2 = y2_img * self.scale + self.pan_y * self.scale

        # 2. Mappa dei Colori Completa e Aggiornata (CORRETTA)
        colors = {
            'car': 'red', 
            'van': 'blue', 
            'plate': 'green', 
            'bus': 'magenta', 
            'motorcycle': 'orange', 
            'truck': 'cyan',
            'bicycle': 'lime green', 
            'person': 'yellow green', 
            'handbag': 'purple', 
            'backpack': 'teal', 
            'suitcase': 'brown'
        }
        
        color = "yellow" if selected else colors.get(box['class'], 'red')
        
        # 3. Disegna il Rettangolo del Bounding Box
        self.canvas.create_rectangle(x1, y1, x2, y2, 
                                     outline=color, 
                                     width=3 if selected else 2, 
                                     tags="bbox")
        
        text = box.get('class', 'unknown')
        font_size = max(8, int(10 * self.scale))
        font = ('Arial', font_size, 'bold')

        # 4. Disegno Etichetta Principale
        text_w = len(text) * font_size * 0.6
        text_h = font_size + 4
        
        text_x = x1 + 2
        text_y = max(y1 - text_h - 2, 5) 
        
        if y1 < 20 or text_y < 5:
             text_y = y1 + 5 

        # Rettangolo di sfondo per l'etichetta
        self.canvas.create_rectangle(
            text_x - 2, text_y - 2,
            text_x + text_w + 5, text_y + text_h + 2,
            fill=color, outline='black', width=1, tags=("label_bg",)
        )
        
        # Testo dell'etichetta
        self.canvas.create_text(
            text_x, text_y,
            text=text,
            anchor=tk.NW,
            fill='white',
            font=font,
            tags=("label",)
        )

        # 5. Maniglie di Ridimensionamento (solo se selezionato)
        if selected:
            s = 6 
            # Angoli: Top-Left, Top-Right, Bottom-Right, Bottom-Left
            for hx, hy in [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]:
                self.canvas.create_oval(hx - s, hy - s, hx + s, hy + s,
                                        fill=color, outline="white", width=1, tags="handle")
            
            # Etichetta di stato 'grossa' in basso a destra
            canvas_w, canvas_h = self.canvas.winfo_width(), self.canvas.winfo_height()
            font_big = ('Arial', max(14, int(16 * self.scale)), 'bold')
            self.canvas.create_text(canvas_w - 20, canvas_h - 20, text=text, 
                                    anchor=tk.SE, fill='yellow', font=font_big, 
                                    tags=("extra_label",))

    def _draw_bboxes(self):
        """Cicla su tutti i BB e li disegna sulla tela chiamando draw_box."""
        
        self.canvas.delete("bbox", "label", "label_bg", "extra_label", "extra_label_bg", "handle", "temp_box")
        
        for i, b in enumerate(self.bboxes):
            self.draw_box(b, selected=(i == self.current_box))
            
    # --- GESTIONE INTERAZIONE (Input) ---
    
    def setup_bindings(self):
        # Bindings sulla finestra principale (root)
        self.root.bind('a', self.prev_image)
        self.root.bind('d', self.next_image)
        
        # Binding Tab, Delete, BackSpace, e 'n' sul root
        self.root.bind('<Tab>', self._on_tab_press) 
        self.root.bind('<Delete>', self.delete_current_box)
        self.root.bind('<BackSpace>', self.delete_current_box)
        self.root.bind('n', self.create_new_box_mode)
        
        # Binding Tab, Delete, BackSpace, e 'n' anche sul Canvas (per focus)
        self.canvas.bind('<Tab>', self._on_tab_press) 
        self.canvas.bind('<Delete>', self.delete_current_box)
        self.canvas.bind('<BackSpace>', self.delete_current_box)
        self.canvas.bind('n', self.create_new_box_mode)
        
        self.root.bind('<Control-s>', self._save_current_image)
        
        # --- AGGIUNTO: scorciatoia per cancellare immagine corrente (Ctrl+Canc) ---
        self.root.bind('<Control-Delete>', self.delete_current_image)
        # Assicuriamoci che anche il canvas riceva la stessa scorciatoia quando ha il focus:
        self.canvas.bind('<Control-Delete>', self.delete_current_image)
        
        # Mouse bindings
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        
        self.canvas.bind("<MouseWheel>", self.on_scroll)
        self.canvas.bind("<Button-3>", self.on_pan_start)
        self.canvas.bind("<B3-Motion>", self.on_pan_drag)

        self.root.bind("<Configure>", self.on_resize)
    
    def on_resize(self, event):
        if event.widget == self.root:
            if self.original_img is not None and self.canvas.winfo_width() > 1:
                self._fit_image_to_canvas()
            
        elif event.widget == self.canvas and self.original_img is not None:
             self._update_canvas_image()


    def screen_to_image(self, x, y):
        """Converte le coordinate del canvas (scalate e pan) a coordinate dell'immagine originale (non scalate)."""
        if self.scale == 0: return x, y
        
        img_x = (x - self.pan_x * self.scale) / self.scale
        img_y = (y - self.pan_y * self.scale) / self.scale
        
        img_x = max(0, min(img_x, self.img_width))
        img_y = max(0, min(img_y, self.img_height))
        
        return int(img_x), int(img_y)

    def on_click(self, event):
        x, y = event.x, event.y

        self.resizing = True if event.state & 0x1 else False
        
        self.current_box = -1 
        self._draw_bboxes() 

        # 1. Se stiamo creando un box (modalità attiva)
        if self.creating_box:
            self.new_box_start = self.screen_to_image(x, y)
            self.new_box_end = self.new_box_start
            self.dragging = True
            return

        # 2. Verifica se si è cliccato su una maniglia (solo se Shift è premuto)
        if self.resizing:
            for i in range(len(self.bboxes) - 1, -1, -1):
                box = self.bboxes[i]
                x1_img, y1_img, x2_img, y2_img = box['coords']
                x1_img, x2_img = min(x1_img, x2_img), max(x1_img, x2_img)
                y1_img, y2_img = min(y1_img, y2_img), max(y1_img, y2_img)
                
                x1_s = x1_img * self.scale + self.pan_x * self.scale
                y1_s = y1_img * self.scale + self.pan_y * self.scale
                x2_s = x2_img * self.scale + self.pan_x * self.scale
                y2_s = y2_img * self.scale + self.pan_y * self.scale

                s = 10 
                handles = {
                    'tl': (x1_s, y1_s), 'tr': (x2_s, y1_s), 'br': (x2_s, y2_s), 'bl': (x1_s, y2_s)
                }
                
                for handle, (hx, hy) in handles.items():
                    if hx - s < x < hx + s and hy - s < y < hy + s:
                        self.current_box = i 
                        self.resize_handle = handle
                        self.dragging = True 
                        self.status_label.config(text=f"Ridimensionamento Box {i+1} in corso ({handle})", fg='purple')
                        self._draw_bboxes()
                        return 

        # 3. Verifica se si è cliccato all'interno di un box esistente
        selected_box_index = -1
        for i in range(len(self.bboxes) - 1, -1, -1):
            box = self.bboxes[i]
            x1_img, y1_img, x2_img, y2_img = box['coords']
            x1_img, x2_img = min(x1_img, x2_img), max(x1_img, x2_img)
            y1_img, y2_img = min(y1_img, y2_img), max(y1_img, y2_img)
            
            x1_s = x1_img * self.scale + self.pan_x * self.scale
            y1_s = y1_img * self.scale + self.pan_y * self.scale
            x2_s = x2_img * self.scale + self.pan_x * self.scale
            y2_s = y2_img * self.scale + self.pan_y * self.scale
            
            if min(x1_s, x2_s) < x < max(x1_s, x2_s) and min(y1_s, y2_s) < y < max(y1_s, y2_s):
                selected_box_index = i
                break

        if selected_box_index != -1:
            self.current_box = selected_box_index

            # 🔹 Aggiorna la “Classe Corrente” nella sidebar (NUOVO)
            if 0 <= self.current_box < len(self.bboxes):
                self.current_class = self.bboxes[self.current_box]['class']
                if hasattr(self, 'current_class_label'):
                    self.current_class_label.config(text=self.current_class)

            if not self.resizing and not self.resize_handle:
                 self.dragging = True 
                 self.drag_offset_x = x - min(x1_s, x2_s)
                 self.drag_offset_y = y - min(y1_s, y2_s)
                 self.status_label.config(text=f"Box {self.current_box+1} selezionato - Trascinamento", fg='blue')
            elif self.resizing and not self.resize_handle:
                 self.status_label.config(text=f"Box {self.current_box+1} selezionato. Clicca e trascina un angolo (SHIFT + Click) per ridimensionare.", fg='blue')
            
            self._draw_bboxes()
        else:
            if not self.resizing:
                self.current_box = -1
                self.creating_box = True
                self.new_box_start = self.screen_to_image(x, y)
                self.new_box_end = self.new_box_start
                self.dragging = True
                self.status_label.config(text="Modalità 'Nuovo Box' attiva. Clicca e trascina per disegnare.", fg='green')

        x, y = event.x, event.y

        self.resizing = True if event.state & 0x1 else False
        
        self.current_box = -1 
        self._draw_bboxes() 

        # 1. Se stiamo creando un box (modalità attiva)
        if self.creating_box:
            self.new_box_start = self.screen_to_image(x, y)
            self.new_box_end = self.new_box_start
            self.dragging = True
            return

        # 2. Verifica se si è cliccato su una maniglia (solo se Shift è premuto)
        if self.resizing:
            for i in range(len(self.bboxes) - 1, -1, -1):
                box = self.bboxes[i]
                x1_img, y1_img, x2_img, y2_img = box['coords']
                x1_img, x2_img = min(x1_img, x2_img), max(x1_img, x2_img)
                y1_img, y2_img = min(y1_img, y2_img), max(y1_img, y2_img)
                
                x1_s = x1_img * self.scale + self.pan_x * self.scale
                y1_s = y1_img * self.scale + self.pan_y * self.scale
                x2_s = x2_img * self.scale + self.pan_x * self.scale
                y2_s = y2_img * self.scale + self.pan_y * self.scale

                s = 10 
                handles = {
                    'tl': (x1_s, y1_s), 'tr': (x2_s, y1_s), 'br': (x2_s, y2_s), 'bl': (x1_s, y2_s)
                }
                
                for handle, (hx, hy) in handles.items():
                    if hx - s < x < hx + s and hy - s < y < hy + s:
                        self.current_box = i 
                        self.resize_handle = handle
                        self.dragging = True 
                        self.status_label.config(text=f"Ridimensionamento Box {i+1} in corso ({handle})", fg='purple')
                        self._draw_bboxes()
                        return 


        # 3. Verifica se si è cliccato all'interno di un box esistente
        selected_box_index = -1
        for i in range(len(self.bboxes) - 1, -1, -1):
            box = self.bboxes[i]
            x1_img, y1_img, x2_img, y2_img = box['coords']
            x1_img, x2_img = min(x1_img, x2_img), max(x1_img, x2_img)
            y1_img, y2_img = min(y1_img, y2_img), max(y1_img, y2_img)
            
            x1_s = x1_img * self.scale + self.pan_x * self.scale
            y1_s = y1_img * self.scale + self.pan_y * self.scale
            x2_s = x2_img * self.scale + self.pan_x * self.scale
            y2_s = y2_img * self.scale + self.pan_y * self.scale
            
            if min(x1_s, x2_s) < x < max(x1_s, x2_s) and min(y1_s, y2_s) < y < max(y1_s, y2_s):
                selected_box_index = i
                break

        if selected_box_index != -1:
            self.current_box = selected_box_index
            
            if not self.resizing and not self.resize_handle:
                 self.dragging = True 
                 self.drag_offset_x = x - min(x1_s, x2_s)
                 self.drag_offset_y = y - min(y1_s, y2_s)
                 self.status_label.config(text=f"Box {self.current_box+1} selezionato - Trascinamento", fg='blue')
            elif self.resizing and not self.resize_handle:
                 self.status_label.config(text=f"Box {self.current_box+1} selezionato. Clicca e trascina un angolo (SHIFT + Click) per ridimensionare.", fg='blue')
            
            self._draw_bboxes()
        else:
            if not self.resizing:
                self.current_box = -1
                self.creating_box = True
                self.new_box_start = self.screen_to_image(x, y)
                self.new_box_end = self.new_box_start
                self.dragging = True
                self.status_label.config(text="Modalità 'Nuovo Box' attiva. Clicca e trascina per disegnare.", fg='green')


    def create_new_box_mode(self, event=None):
        self.current_box = -1
        self.creating_box = True
        self.status_label.config(text="Modalità 'Nuovo Box' attiva. Clicca e trascina per disegnare.", fg='green')
        self._draw_bboxes()


    def on_drag(self, event):
        if not self.dragging:
            return

        x, y = event.x, event.y
        x_img, y_img = self.screen_to_image(x, y)

        i = self.current_box
        
        if self.creating_box:
            self.new_box_end = (x_img, y_img)
            
            x1_s, y1_s = [c * self.scale for c in self.new_box_start]
            x2_s, y2_s = [c * self.scale for c in self.new_box_end]
            
            x1_s = x1_s + self.pan_x * self.scale
            y1_s = y1_s + self.pan_y * self.scale
            x2_s = x2_s + self.pan_x * self.scale
            y2_s = y2_s + self.pan_y * self.scale

            self.canvas.delete("temp_box")
            self.canvas.create_rectangle(min(x1_s, x2_s), min(y1_s, y2_s), max(x1_s, x2_s), max(y1_s, y2_s), 
                                         outline='white', width=2, tags="temp_box", dash=(4, 4))
            return

        
        if i != -1:
            box = self.bboxes[i]
            x1, y1, x2, y2 = box['coords']
            
            if self.resize_handle:
                x1_img_min, x2_img_max = min(x1, x2), max(x1, x2)
                y1_img_min, y2_img_max = min(y1, y2), max(y1, y2)
                
                if 'l' in self.resize_handle: 
                    if x1_img_min == x1: x1 = x_img
                    else: x2 = x_img
                if 'r' in self.resize_handle: 
                    if x2_img_max == x2: x2 = x_img
                    else: x1 = x_img

                if 't' in self.resize_handle:
                    if y1_img_min == y1: y1 = y_img
                    else: y2 = y_img
                if 'b' in self.resize_handle: 
                    if y2_img_max == y2: y2 = y_img
                    else: y1 = y_img
                
                if abs(x1 - x2) > 5 and abs(y1 - y2) > 5:
                    box['coords'] = [x1, y1, x2, y2]
                    self._draw_bboxes()
            else:
                min_x_s = min(x1, x2) * self.scale + self.pan_x * self.scale
                min_y_s = min(y1, y2) * self.scale + self.pan_y * self.scale
                
                new_min_x_s = x - self.drag_offset_x
                new_min_y_s = y - self.drag_offset_y
                
                dx_s = new_min_x_s - min_x_s
                dy_s = new_min_y_s - min_y_s
                
                dx_img = int(dx_s / self.scale)
                dy_img = int(dy_s / self.scale)
                
                x1 += dx_img
                y1 += dy_img
                x2 += dx_img
                y2 += dy_img
                
                width = abs(x1 - x2)
                height = abs(y1 - y2)
                
                x_min_new = max(0, min(x1, x2))
                y_min_new = max(0, min(y1, y2))
                
                x_max_new = min(self.img_width, max(x1, x2))
                y_max_new = min(self.img_height, max(y1, y2))
                
                if x_max_new - x_min_new < width:
                     if x1 < x2: x1, x2 = x_min_new, x_max_new
                     else: x2, x1 = x_min_new, x_max_new
                
                if y_max_new - y_min_new < height:
                    if y1 < y2: y1, y2 = y_min_new, y_max_new
                    else: y2, y1 = y_min_new, y_max_new
                
                box['coords'] = [x1, y1, x2, y2]
                self._draw_bboxes()


    def on_release(self, event):
        self.dragging = False
        self.resizing = False
        self.resize_handle = None

        self.canvas.delete("temp_box")
        
        if self.creating_box:
            self.creating_box = False
            
            if not self.new_box_start or not self.new_box_end: return
            x1, y1 = self.new_box_start
            x2, y2 = self.new_box_end
            
            if abs(x1 - x2) < 5 or abs(y1 - y2) < 5: 
                self.status_label.config(text="Box troppo piccolo, ignorato.", fg='orange')
                return

            new_box_coords = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
            
            new_box = {'class': self.current_class, 'coords': new_box_coords}
            self.bboxes.append(new_box)
            self.current_box = len(self.bboxes) - 1
            self.status_label.config(text=f"Nuovo box '{self.current_class}' creato.", fg='green')
            self._draw_bboxes()
            self._update_box_stats()
            self.new_box_start, self.new_box_end = None, None
            
        elif self.current_box != -1:
             self.status_label.config(text=f"Box {self.current_box+1} aggiornato.", fg='blue')
             self._draw_bboxes()
             self._update_box_stats()


    def on_scroll(self, event):
        zoom_factor = 1.1 if event.delta > 0 else 1/1.1
        
        px, py = event.x, event.y 

        new_scale = self.scale * zoom_factor
        
        if new_scale > 10.0: new_scale = 10.0
        if new_scale < 0.1: new_scale = 0.1
        
        img_x_before = (px / self.scale) - self.pan_x
        img_y_before = (py / self.scale) - self.pan_y
        
        self.pan_x = (px / new_scale) - img_x_before
        self.pan_y = (py / new_scale) - img_y_before
        
        self.scale = new_scale
        
        self.status_label.config(text=f"Zoom: {self.scale:.2f}x", fg='gray')
        self._update_canvas_image()


    def on_pan_start(self, event):
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        self.original_pan_x = self.pan_x
        self.original_pan_y = self.pan_y
        self.canvas.config(cursor="fleur")

    def on_pan_drag(self, event):
        if self.scale == 0: return

        dx = event.x - self.pan_start_x
        dy = event.y - self.pan_start_y

        self.pan_x = self.original_pan_x + dx / self.scale
        self.pan_y = self.original_pan_y + dy / self.scale
        
        self.canvas.config(cursor="fleur")

        self._update_canvas_image()
        
    # --- GESTIONE BOX ---

    def _on_tab_press(self, event):
        if not self.bboxes:
            self.current_box = -1
            self.status_label.config(text="Nessun box da selezionare.", fg='orange')
            return 'break'
            
        next_index = (self.current_box + 1) % len(self.bboxes)
        
        self.current_box = next_index
        if 0 <= self.current_box < len(self.bboxes):
            self.current_class = self.bboxes[self.current_box]['class']
            self.current_class_label.config(text=self.current_class)
        self._draw_bboxes()
        self.status_label.config(text=f"Box selezionato: {self.current_box + 1}/{len(self.bboxes)}", fg='blue')
        
        return 'break'


    def delete_current_box(self, event=None):
        if self.current_box != -1 and self.current_box < len(self.bboxes):
            box_to_delete = self.bboxes.pop(self.current_box)
            
            if self.bboxes:
                if self.current_box >= len(self.bboxes):
                    self.current_box = len(self.bboxes) - 1
            else:
                 self.current_box = -1 
                 
            self._draw_bboxes()
            self._update_box_stats() 
            self.status_label.config(text=f"Box '{box_to_delete['class']}' eliminato.", fg='red')
        else:
            self.status_label.config(text="Nessun box selezionato da eliminare.", fg='orange')
            
        # >> AGGIUNGI QUESTA RIGA: interrompe la propagazione dell'evento al widget radice (root)
        return 'break'
        
    # --- CANC IMMAGINE ---      
    
    def delete_current_image(self, event=None):
        """Cancella l'immagine corrente senza salvarla o annotarla."""
        if not self.images:
            self.status_label.config(text="Nessuna immagine da cancellare.", fg='orange')
            return

        current_path = os.path.join(self.folder, self.filename)
        try:
            if os.path.exists(current_path):
                os.remove(current_path)
                self.status_label.config(text=f"Immagine '{self.filename}' eliminata.", fg='red')
            else:
                self.status_label.config(text=f"File non trovato: {self.filename}", fg='orange')

            # Rimuovi dal vettore immagini e aggiorna vista
            del self.images[self.index]

            if not self.images:
                messagebox.showinfo("Fine", "Tutte le immagini sono state cancellate.")
                self.root.destroy()
                return

            # Se cancelliamo l'ultima, torna indietro
            if self.index >= len(self.images):
                self.index = len(self.images) - 1

            self.load_image()
        except Exception as e:
            messagebox.showerror("Errore", f"Errore durante la cancellazione: {e}")


    # --- NAVIGAZIONE E SALVATAGGIO ---

    def _save_current_image(self, event=None):
        self._save_boxes_to_json()
        return
        """
        Salva aggiornando solo i nomi dei file (senza creare immagini annotate).

        Regole:
        - Aggiorna il nome dell'immagine originale in base ai BB correnti.
        - Se esiste la stessa immagine nella cartella 'annotated/', rinomina anche quella.
        - Nessuna immagine con BB disegnati viene salvata.
        - Gestione speciale per la targa OCR:
            * Se la checkbox 'validate_plate_var' è flaggata -> aggiorna il segmento ocr_<valore>
              con il valore attuale di self.plate_var (trasformato in maiuscolo).
            * Altrimenti lascia il segmento ocr_ così com'è nel nome originale.
        """
        if self.original_img is None:
            self.status_label.config(text="Nessuna immagine caricata da salvare.", fg='red')
            return

        try:
            base_name, ext = os.path.splitext(self.filename)
            parts = base_name.split("_")

            ALL_CLASSES = set(self.classes + [
                'car', 'motorcycle', 'truck', 'bus', 'bicycle', 'plate', 'van',
                'person', 'handbag', 'backpack', 'suitcase'
            ])

            preserved_before = []
            found_boxes = []
            ocr_segment = []

            i = 0
            while i < len(parts):
                p = parts[i]

                # Mantieni ocr_<valore> in fondo (memorizzalo)
                if p.lower() == 'ocr' and i + 1 < len(parts):
                    ocr_segment = ['ocr', parts[i + 1]]
                    i += 2
                    continue

                # Letta_plate_x_y_x2_y2
                if p == 'Letta' and i + 5 < len(parts) and parts[i+1] == 'plate' and all(t.isdigit() for t in parts[i+2:i+6]):
                    coords = list(map(int, parts[i+2:i+6]))
                    found_boxes.append(('Letta_plate', coords))
                    i += 6
                    continue

                # class_x_y_x2_y2
                if p in ALL_CLASSES or p in self.classes:
                    coords = None
                    try:
                        coords_str = parts[i+1:i+5]
                        if len(coords_str) == 4 and all(t.isdigit() for t in coords_str):
                            x1, y1, x2, y2 = map(int, coords_str)
                            coords = [x1, y1, x2, y2]
                            found_boxes.append((p, coords))
                            i += 5
                            continue
                    except (ValueError, IndexError):
                        pass

                    if coords is None:
                        i += 1
                        continue
                i += 1

            # --- Analizza i BB correnti ---
            current_boxes = []
            for b in self.bboxes:
                x1, y1, x2, y2 = map(int, b['coords'])
                cls = b['class']
                current_boxes.append({'class': cls, 'coords': [x1, y1, x2, y2]})

            # --- Inizializza sempre plate_validated per evitare UnboundLocalError ---
            plate_validated = False
            try:
                if getattr(self, 'validate_plate_var', None) is not None:
                    plate_validated = bool(self.validate_plate_var.get())
            except Exception:
                plate_validated = False

            # --- Trova eventuale Letta_plate precedente (centro) ---
            prev_letta_coords = None
            for k, coords in found_boxes:
                if k == 'Letta_plate':
                    prev_letta_coords = coords
                    break

            selected_letta_index = None
            if prev_letta_coords:
                px = (prev_letta_coords[0] + prev_letta_coords[2]) / 2.0
                py = (prev_letta_coords[1] + prev_letta_coords[3]) / 2.0
                min_dist = None
                for idx, cb in enumerate(current_boxes):
                    if cb['class'] != 'plate':
                        continue
                    x1, y1, x2, y2 = cb['coords']
                    cx = (x1 + x2) / 2.0
                    cy = (y1 + y2) / 2.0
                    dist = (cx - px)**2 + (cy - py)**2
                    if min_dist is None or dist < min_dist:
                        min_dist = dist
                        selected_letta_index = idx
            else:
                # Se non c'era una Letta_plate precedente, e la checkbox è flaggata,
                # scegli la prima plate presente per marcare come Letta_plate.
                if plate_validated:
                    for idx, cb in enumerate(current_boxes):
                        if cb['class'] == 'plate':
                            selected_letta_index = idx
                            break

            # --- Se la checkbox è flaggata sostituisco / aggiorno il valore OCR ---
            if plate_validated:
                try:
                    new_ocr_value = self.plate_var.get().strip().upper()
                    if new_ocr_value:
                        # Aggiorna o crea il segmento ocr_
                        ocr_segment = ['ocr', new_ocr_value]
                except Exception:
                    # In caso di problemi con la GUI, non bloccare il salvataggio
                    pass

            # --- Costruisci il nuovo nome con i BB attuali ---
            new_segments = []
            for idx, cb in enumerate(current_boxes):
                x1, y1, x2, y2 = map(int, cb['coords'])
                cls = cb['class']
                if cls == 'plate' and idx == selected_letta_index:
                    new_segments.append(f"Letta_plate_{x1}_{y1}_{x2}_{y2}")
                else:
                    new_segments.append(f"{cls}_{x1}_{y1}_{x2}_{y2}")

            recomposed_parts = preserved_before + new_segments

            # Aggiungi il segmento OCR (aggiornato o originale) se presente
            if ocr_segment:
                recomposed_parts.extend(ocr_segment)

            # Filtra eventuali elementi vuoti e ricostruisci il nome
            recomposed_parts = [p for p in recomposed_parts if p != ""]
            final_new_name = "_".join(recomposed_parts) + ext
            final_new_name = final_new_name.strip("_")

            # --- Aggiorna file originale (rinomina) ---
            old_path = os.path.join(self.folder, self.filename)
            new_path = os.path.join(self.folder, final_new_name)
            if final_new_name != self.filename and os.path.exists(old_path):
                os.rename(old_path, new_path)
                self.filename = final_new_name
                self.images[self.index] = final_new_name

            # --- Crea copia annotata nella cartella 'annotated/' ---
            annotated_folder = os.path.join(self.folder, "annotated")
            os.makedirs(annotated_folder, exist_ok=True)
            annotated_path = os.path.join(annotated_folder, final_new_name)

            source_path = new_path if os.path.exists(new_path) else old_path
            img_cv2 = cv2.imread(source_path)
            if img_cv2 is not None:
                annotated_img = img_cv2.copy()
                for b in self.bboxes:
                    x1, y1, x2, y2 = map(int, b['coords'])
                    cls = b['class']
                    label = f"Letta_{cls}" if cls == "plate" else cls
                    color = (0, 0, 255)
                    cv2.rectangle(annotated_img, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(annotated_img, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
                cv2.imwrite(annotated_path, annotated_img)
                print(f"Copia annotata creata: {annotated_path}")
            else:
                print(f"Errore: impossibile leggere l'immagine da {source_path}")

            # --- Aggiorna GUI e ricarica immagine ---
            self.status_label.config(text=f"Nome aggiornato: {final_new_name} e copia annotata creata in 'annotated/'.", fg='green')
            self.load_image()

        except Exception as e:
            print("Errore durante il salvataggio:", e)
            self.status_label.config(text=f"Errore salvataggio: {e}", fg='red')

        """
        Salva aggiornando solo i nomi dei file (senza creare immagini annotate).

        Regole:
        - Aggiorna il nome dell'immagine originale in base ai BB correnti.
        - Se esiste la stessa immagine nella cartella 'annotated/', rinomina anche quella.
        - Nessuna immagine con BB disegnati viene salvata.
        - Gestione speciale per la targa OCR:
            * BB di classe 'plate' → Letta_plate se è la targa OCR.
            * Se Letta_plate viene eliminato → rimosso dal nome.
        """
        if self.original_img is None:
            self.status_label.config(text="Nessuna immagine caricata da salvare.", fg='red')
            return

        try:
            import re

            base_name, ext = os.path.splitext(self.filename)
            parts = base_name.split("_")

            ALL_CLASSES = set(self.classes + [
                'car', 'motorcycle', 'truck', 'bus', 'bicycle', 'plate', 'van',
                'person', 'handbag', 'backpack', 'suitcase'
            ])

            preserved_before = []
            found_boxes = []
            ocr_segment = []

            i = 0
            while i < len(parts):
                p = parts[i]

                # Mantieni ocr_<valore> in fondo
                if p.lower() == 'ocr' and i + 1 < len(parts):
                    ocr_segment = ['ocr', parts[i + 1]]
                    i += 2
                    continue

                # Letta_plate_x_y_x2_y2
                if p == 'Letta' and i + 5 < len(parts) and parts[i+1] == 'plate' and all(t.isdigit() for t in parts[i+2:i+6]):
                    coords = list(map(int, parts[i+2:i+6]))
                    found_boxes.append(('Letta_plate', coords))
                    i += 6
                    continue

                # class_x_y_x2_y2
                if p in ALL_CLASSES or p in self.classes: 
                    coords = None  # Inizializza coords
                    try:
                        coords_str = parts[i+1:i+5]
                        if len(coords_str) == 4 and all(t.isdigit() for t in coords_str):
                            x1, y1, x2, y2 = map(int, coords_str) 
                            coords = [x1, y1, x2, y2]
                            found_boxes.append((p, coords))
                            i += 5
                            continue
                    except (ValueError, IndexError):
                        pass
                    
                    # Se coords è ancora None, salta questo elemento
                    if coords is None:
                        i += 1
                        continue
                i += 1

            # --- Analizza i BB correnti ---
            current_boxes = []
            for b in self.bboxes:
                x1, y1, x2, y2 = map(int, b['coords'])
                cls = b['class']
                current_boxes.append({'class': cls, 'coords': [x1, y1, x2, y2]})

            plate_validated = False  # ✅ Inizializzazione preventiva per evitare UnboundLocalError

            prev_letta_coords = None
            for k, coords in found_boxes:
                if k == 'Letta_plate':
                    prev_letta_coords = coords
                    break

            # --- Identifica la Letta_plate corrente ---
            selected_letta_index = None
            if prev_letta_coords:
                px = (prev_letta_coords[0] + prev_letta_coords[2]) / 2.0
                py = (prev_letta_coords[1] + prev_letta_coords[3]) / 2.0
                min_dist = None
                for idx, cb in enumerate(current_boxes):
                    if cb['class'] != 'plate':
                        continue
                    x1, y1, x2, y2 = cb['coords']
                    cx = (x1 + x2) / 2.0
                    cy = (y1 + y2) / 2.0
                    dist = (cx - px)**2 + (cy - py)**2
                    if min_dist is None or dist < min_dist:
                        min_dist = dist
                        selected_letta_index = idx
            else:
                try:
                    plate_validated = getattr(self, 'validate_plate_var', None)
                    if plate_validated is not None:
                        plate_validated = plate_validated.get()
                except Exception:
                    plate_validated = False

                if plate_validated:
                    for idx, cb in enumerate(current_boxes):
                        if cb['class'] == 'plate':
                            selected_letta_index = idx
                            break

            # --- Gestione speciale per targhe OCR validate ---
            if plate_validated:
                try:
                    new_ocr_value = self.plate_var.get().strip().upper()
                    if new_ocr_value:
                        # Aggiorna il segmento OCR esistente o creane uno nuovo
                        if ocr_segment:
                            # Sostituisci il valore OCR esistente
                            ocr_segment = ['ocr', new_ocr_value]
                        else:
                            # Crea un nuovo segmento OCR
                            ocr_segment = ['ocr', new_ocr_value]
                except Exception:
                    pass  # Ignora errori nell'accesso al campo di input

            # --- Costruisci il nuovo nome ---
            new_segments = []
            for idx, cb in enumerate(current_boxes):
                x1, y1, x2, y2 = map(int, cb['coords'])
                cls = cb['class']
                if cls == 'plate' and idx == selected_letta_index:
                    new_segments.append(f"Letta_plate_{x1}_{y1}_{x2}_{y2}")
                else:
                    new_segments.append(f"{cls}_{x1}_{y1}_{x2}_{y2}")

            recomposed_parts = preserved_before + new_segments
            if ocr_segment:
                recomposed_parts.extend(ocr_segment)

            recomposed_parts = [p for p in recomposed_parts if p != ""]
            final_new_name = "_".join(recomposed_parts) + ext
            final_new_name = final_new_name.strip("_")

            # --- Aggiorna file originale ---
            old_path = os.path.join(self.folder, self.filename)
            new_path = os.path.join(self.folder, final_new_name)
            if final_new_name != self.filename and os.path.exists(old_path):
                os.rename(old_path, new_path)
                self.filename = final_new_name
                self.images[self.index] = final_new_name

            # --- Crea copia annotata nella cartella 'annotated/' ---
            annotated_folder = os.path.join(self.folder, "annotated")
            os.makedirs(annotated_folder, exist_ok=True)
            annotated_path = os.path.join(annotated_folder, final_new_name)

            # Determina quale percorso usare per leggere l'immagine
            source_path = new_path if os.path.exists(new_path) else old_path

            img_cv2 = cv2.imread(source_path)
            if img_cv2 is not None:
                annotated_img = img_cv2.copy()
                for b in self.bboxes:
                    x1, y1, x2, y2 = map(int, b['coords'])
                    cls = b['class']
                    label = f"Letta_{cls}" if cls == "plate" else cls
                    color = (0, 0, 255)
                    cv2.rectangle(annotated_img, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(annotated_img, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
                cv2.imwrite(annotated_path, annotated_img)
                print(f"Copia annotata creata: {annotated_path}")
            else:
                print(f"Errore: impossibile leggere l'immagine da {source_path}")

            # --- Aggiorna GUI ---
            self.status_label.config(text=f"Nome aggiornato: {final_new_name} e copia annotata creata in 'annotated/'.", fg='green')
            self.load_image()

        except Exception as e:
            print("Errore durante il salvataggio:", e)
            self.status_label.config(text=f"Errore salvataggio: {e}", fg='red')

    def prev_image(self, event=None): 
        if self.index > 0:
            self.index -= 1
            self.current_box = -1
            self.load_image()
        else:
            self.status_label.config(text="Prima immagine", fg='orange')
            
    def next_image(self, event=None): 
        if self.index < len(self.images) - 1:
            self.index += 1
            self.current_box = -1
            self.load_image()
        else:
            self.status_label.config(text="Ultima immagine", fg='orange')
            
    def _select_new_folder(self):
        """Permette all'utente di selezionare una nuova cartella immagini e ricarica l'interfaccia."""
        new_folder = filedialog.askdirectory(title="Seleziona una nuova cartella immagini")
        if new_folder:
            self.folder = new_folder
            self.images = [f for f in os.listdir(new_folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            if not self.images:
                messagebox.showinfo("Nessuna Immagine", "Nessuna immagine trovata nella nuova cartella selezionata.")
                return
            self.index = 0
            self.load_image()
            self.status_label.config(text=f"Nuova cartella caricata: {new_folder}", fg='green')


def main():
    root = tk.Tk()
    
    root.configure(bg='#2C3E50')
    
    folder_path = filedialog.askdirectory(title="Seleziona la cartella contenente le immagini")
    
    if folder_path:
        app = BoundingBoxEditor(root, folder_path)
        root.mainloop()

if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        pass 
        
    main()