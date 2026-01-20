import os
import sys
import json
import re
import cv2
import pygame
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog, Toplevel, StringVar, BooleanVar, OptionMenu, Entry, Button, Label, Checkbutton, Frame, LabelFrame, Scrollbar, Canvas
from PIL import Image, ImageTk, ImageFont, ImageDraw
import copy

# --- REGEX GLOBALI PRE-COMPILATE ---
# RE_OCR_STARTS: Serve per identificare velocemente le classi OCR senza ricompilare ogni volta
RE_LETTA_PLATE_CHECK = re.compile(r"^(.*?)(_\d+)?$", re.IGNORECASE)
RE_LETTA_PLATE_FULL = re.compile(r"^letta_plate(?:_(\d+))?$", re.IGNORECASE)
RE_OCR_STARTS = re.compile(r"^ocr", re.IGNORECASE)  # <--- ECCOLA, QUELLA MANCANTE

DEFAULT_CLASSES = [
    'bicycle', 'bus', 'car', 'motorcycle', 'pickup',
    'truck', 'van', 'plate', 'person',
    'backpack', 'handbag', 'suitcase'
]

CLASS_COLORS = {
    'car': 'red', 'van': 'blue', 'plate': 'green', 'bus': 'magenta',
    'motorcycle': 'orange', 'truck': 'cyan', 'bicycle': 'lime green',
    'person': 'yellow green', 'handbag': 'purple', 'backpack': 'teal',
    'suitcase': 'brown', 'ocr': 'grey', 'pickup': 'lightcoral'
}

PIL_SAFE_COLORS = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "orange": (255, 165, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "white": (255, 255, 255),
    "black": (0, 0, 0),

    # alias custom
    "yellow green": (154, 205, 50),
    "light green": (144, 238, 144),
}


# --- SAVE MODES ---
SAVE_MODE_SAFE = "SAFE"
SAVE_MODE_NO_SAVE = "UNSAFE"
SAVE_MODE_SMART = "SMART"


# Aggiunge il supporto per il ri-campionamento di PIL
try:
    # Per PIL 10.0.0 e successive
    Image.Resampling.LANCZOS 
except AttributeError:
    # Per versioni precedenti
    Image.Resampling.LANCZOS = Image.LANCZOS
except:
     # Fallback per qualsiasi altro errore o versioni molto vecchie
    Image.Resampling.LANCZOS = Image.ANTIALIAS


def resource_path(relative_path):
    """ Ottiene il percorso assoluto delle risorse, funziona per dev e per PyInstaller """
    try:
        # PyInstaller crea una cartella temporanea e memorizza il percorso in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
    



def ask_mode_selection():
    """
    Mostra una finestra iniziale per scegliere la modalità di salvataggio:
    - SAFE: chiede sempre conferma di salvataggio
    - SMART: chiede conferma solo se ci sono modifiche non salvate
    - NO SAVE: non chiede mai conferma di salvataggio
    """
    class ModeSelector:
        def __init__(self, root):
            self.root = root
            self.root.title("Seleziona Modalità")
            self.root.geometry("550x300")
            self.root.resizable(False, False)
            
            # Stile scuro coerente con l'applicazione
            self.bg_color = '#2C3E50'
            self.fg_color = 'white'
            self.button_bg = '#3498DB'
            self.button_active = '#2980B9'
            
            self.root.configure(bg=self.bg_color)
            
            # Frame principale
            self.main_frame = tk.Frame(self.root, bg=self.bg_color, padx=20, pady=20)
            self.main_frame.pack(expand=True, fill='both')
            
            # Etichetta di istruzioni
            tk.Label(
                self.main_frame, 
                text="Seleziona la modalità di salvataggio:",
                bg=self.bg_color, 
                fg=self.fg_color,
                font=('Arial', 12, 'bold')
            ).pack(pady=(0, 20))
            
            # Variabile per i radio button
            self.mode_var = tk.StringVar(value=SAVE_MODE_SMART)  # Default a SMART
            
            # Opzioni con descrizioni
            self.options = [
                (SAVE_MODE_SAFE, "Modalità SICURA: Chiede sempre conferma di salvataggio ad ogni cambio immagine"),
                (SAVE_MODE_SMART, "Modalità INTELLIGENTE: Chiede conferma solo se ci sono modifiche non salvate (consigliato)"),
                (SAVE_MODE_NO_SAVE, "Modalità LETTURA: Non chiede mai conferma di salvataggio")
            ]
            
            # Crea i radio button
            for mode, text in self.options:
                frame = tk.Frame(self.main_frame, bg=self.bg_color)
                frame.pack(anchor='w', pady=5)
                
                rb = tk.Radiobutton(
                    frame, 
                    text=text,
                    variable=self.mode_var,
                    value=mode,
                    bg=self.bg_color,
                    fg=self.fg_color,
                    selectcolor=self.bg_color,
                    activebackground=self.bg_color,
                    activeforeground=self.fg_color,
                    font=('Arial', 10),
                    wraplength=500,
                    justify='left',
                    indicatoron=1
                )
                rb.pack(side='left', anchor='w')
            
            # Frame per il pulsante di conferma
            button_frame = tk.Frame(self.main_frame, bg=self.bg_color)
            button_frame.pack(pady=(20, 0), fill='x')
            
            # Pulsante Conferma più alto
            self.btn_confirm = tk.Button(
                button_frame,
                text="CONFERMA E AVVIA",
                command=self.on_confirm,
                bg=self.button_bg,
                fg=self.fg_color,
                activebackground=self.button_active,
                activeforeground=self.fg_color,
                padx=30,
                pady=10,  # Aumentato il padding verticale
                font=('Arial', 12, 'bold'),
                relief='flat',
                bd=0,
                height=2  # Altezza maggiore
            )
            self.btn_confirm.pack(expand=True, fill='x')
            
            # Centra la finestra
            self.center_window()
            
            # Imposta la modalità di default
            self.selected_mode = SAVE_MODE_SMART
            
        def center_window(self):
            self.root.update_idletasks()
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            x = (self.root.winfo_screenwidth() // 2) - (width // 2)
            y = (self.root.winfo_screenheight() // 4) - (height // 2)
            self.root.geometry(f'{width}x{height}+{x}+{y}')
            
        def on_confirm(self):
            self.selected_mode = self.mode_var.get()
            self.root.destroy()
            
        def get_mode(self):
            return self.selected_mode
    
    root = tk.Tk()
    app = ModeSelector(root)
    root.mainloop()
    
    return app.get_mode()


def ask_class_filter(root, classes, current_filter=None):
 
    dialog = Toplevel(root)
    dialog.title("Imposta Filtro")
    dialog.geometry("350x220")
    dialog.resizable(False, False)
    dialog.grab_set()

    # Classi Extra richieste + quelle standard
    extra_classes = ['Letta_plate', 'scooter', 'hat']
    # Uniamo le liste e rimuoviamo duplicati, ordinando
    full_list = sorted(list(set(classes + extra_classes)))

    # Variabili
    # Se c'è già un filtro attivo, la checkbox parte attiva
    is_active_var = BooleanVar(value=bool(current_filter))
    
    # Se c'è un filtro corrente lo usiamo come default, altrimenti il primo della lista
    default_val = current_filter if current_filter in full_list else full_list[0]
    selected_var = StringVar(value=default_val)
    
    custom_var = StringVar()
    result = {"value": None}

    # --- UI ---
    
    # Checkbox per attivare/disattivare
    check_frame = Frame(dialog)
    check_frame.pack(pady=10)
    chk = Checkbutton(check_frame, text="Attiva Filtro per classe", variable=is_active_var, font=("Arial", 10, "bold"))
    chk.pack()

    # Area selezione (abilitata solo se checkbox è attiva)
    selection_frame = Frame(dialog)
    selection_frame.pack(pady=5)

    Label(selection_frame, text="Classe da filtrare:").pack()
    
    # Dropdown
    opt_menu = OptionMenu(selection_frame, selected_var, *(full_list + ["Altro"]))
    opt_menu.config(width=20)
    opt_menu.pack(pady=5)

    # Entry per "Altro"
    entry_custom = Entry(selection_frame, textvariable=custom_var)
    
    # Logica visualizzazione campo "Altro" e stato abilitato/disabilitato
    def update_state(*args):
        # Abilita/Disabilita controlli in base alla checkbox
        state = 'normal' if is_active_var.get() else 'disabled'
        opt_menu.config(state=state)
        entry_custom.config(state=state)
        
        # Mostra/Nascondi entry "Altro"
        if is_active_var.get() and selected_var.get() == "Altro":
            entry_custom.pack(pady=5)
        else:
            entry_custom.pack_forget()

    # Trigger aggiornamento stato
    is_active_var.trace_add("write", update_state)
    selected_var.trace_add("write", update_state)
    
    # Inizializza stato UI
    update_state()

    def confirm():
        if not is_active_var.get():
            # Filtro disabilitato
            result["value"] = None
        else:
            # Filtro attivo
            if selected_var.get() == "Altro":
                val = custom_var.get().strip()
                if not val:
                    messagebox.showerror("Errore", "Inserisci un nome classe valido", parent=dialog)
                    return
                result["value"] = val
            else:
                result["value"] = selected_var.get()
        dialog.destroy()

    Button(dialog, text="Conferma", command=confirm, bg='#2ECC71', fg='white', font=('Arial', 10, 'bold')).pack(pady=20)

    root.wait_window(dialog)
    return result["value"]



# ====================================================================
# CLASSE PER GESTIRE I TOOLTIP
# ====================================================================

class CreateToolTip(object):
    """
    Crea un ToolTip personalizzato per un dato widget usando Toplevel.
    """
    def __init__(self, widget, text='widget info'):
        self.widget = widget
        self.text = text
        self.widget.bind('<Enter>', self.enter)
        self.widget.bind('<Leave>', self.leave)
        self.widget.bind('<ButtonPress>', self.leave) # Nasconde al click
        self.tw = None

    def enter(self, event=None):
        self.showtip()

    def leave(self, event=None):
        self.hidetip()

    def showtip(self):
        "Mostra il tooltip come finestra Toplevel"
        if self.tw:
            return
        # Calcola la posizione del tooltip (leggermente offset dalla posizione del cursore)
        x = self.widget.winfo_rootx() + self.widget.winfo_width()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        self.tw = tk.Toplevel(self.widget)
        # Rimuove le decorazioni della finestra (borderless, no title bar)
        self.tw.wm_overrideredirect(True) 
        self.tw.wm_geometry(f"+{x}+{y}")
        
        # Colori per il ToolTip
        BG_COLOR = '#FFFFCC' 
        FG_COLOR = 'black'
        
        label = tk.Label(self.tw, text=self.text, justify=tk.LEFT,
                         background=BG_COLOR, foreground=FG_COLOR,
                         relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hidetip(self):
        if self.tw:
            self.tw.destroy()
        self.tw = None

# ====================================================================

class BoundingBoxEditor:

    # ----------------------------------------------------------------------
    # *** NUOVI METODI UNDO: CTRL + z ***
    # ----------------------------------------------------------------------
    
        
    def _get_history(self):
        # Sostituisci self.current_image_path con self.filename
        img_id = self.filename  

        if img_id not in self.history:
            self.history[img_id] = {
                "undo": [],
                "redo": []
            }

        return self.history[img_id]

    def _push_undo_state(self, action="Modifica"):
        

        hist = self._get_history()

        state = {
            "bboxes": copy.deepcopy(self.bboxes),
            "ocr": copy.deepcopy(getattr(self, "loaded_ocr_boxes", [])),
            "current_box": self.current_box,
            "action": action
        }

        hist["undo"].append(state)
        hist["redo"].clear()

        if len(hist["undo"]) > self.max_undo:
            hist["undo"].pop(0)
        
        if not self.is_loading_image:
            self.is_dirty = True


        
    def undo_last_action(self, event=None):
        hist = self._get_history()

        if not hist["undo"]:
            self.status_label.config(text="Nessuna operazione da annullare", fg="orange")
            return

        
        current_state = {
            "bboxes": copy.deepcopy(self.bboxes),
            "ocr": copy.deepcopy(getattr(self, "loaded_ocr_boxes", [])),
            "current_box": self.current_box
        }

        hist["redo"].append(current_state)
        state = hist["undo"].pop()

        self.bboxes = state["bboxes"]
        self.loaded_ocr_boxes = state["ocr"]
        self.current_box = state["current_box"]

        self._draw_bboxes()
        self._update_current_box_info()
        self._update_plate_entry_from_selection()
        
        # ✅ AGGIUNGI QUESTA RIGA
        self._update_filename_color()
        
        # ✅ AGGIUNGI QUESTA RIGA
        self.is_dirty = True

        action = state.get("action", "Modifica")
        self.status_label.config(
            text=f"Undo: {action}",
            fg="yellow"
        )



    def redo_last_action(self, event=None):
        hist = self._get_history()

        if not hist["redo"]:
            self.status_label.config(text="Nessuna operazione da ripristinare", fg="orange")
            return

        
        current_state = {
            "bboxes": copy.deepcopy(self.bboxes),
            "ocr": copy.deepcopy(getattr(self, "loaded_ocr_boxes", [])),
            "current_box": self.current_box
        }

        hist["undo"].append(current_state)
        state = hist["redo"].pop()

        self.bboxes = state["bboxes"]
        self.loaded_ocr_boxes = state["ocr"]
        self.current_box = state["current_box"]

        self._draw_bboxes()
        self._update_current_box_info()
        self._update_plate_entry_from_selection()
        
              
        # ✅ AGGIUNGI QUESTA RIGA
        self._update_filename_color()
        
        # ✅ AGGIUNGI QUESTA RIGA
        self.is_dirty = True

        action = state.get("action", "Modifica")
        self.status_label.config(
            text=f"Redo: {action}",
            fg="lightgreen"
        )
        
    # ----------------------------------------------------------------------
    # *** NUOVI METODI: crea snapshot e controllo se dirty ***
    # ----------------------------------------------------------------------

    def _make_snapshot(self):
        """
        Snapshot CANONICO dello stato persistente.
        Usato SOLO per confronti SMART, non per disegno.
        """
        def norm_box(b):
            # coords sempre normalizzate
            x1, y1, x2, y2 = b.get("coords", [0, 0, 0, 0])
            x_min, x_max = min(x1, x2), max(x1, x2)
            y_min, y_max = min(y1, y2), max(y1, y2)

            return {
                "class": b.get("class"),
                "coords": [int(x_min), int(y_min), int(x_max), int(y_max)]
            }

        def norm_ocr(o):
            return {
                "bbox_id": o.get("bbox_id"),
                "value": list(o.get("value", [])),
                "validated": bool(o.get("validated", False))
            }

        return {
            "bboxes": [norm_box(b) for b in self.bboxes],
            "ocr": sorted(
                [norm_ocr(o) for o in getattr(self, "loaded_ocr_boxes", [])],
                key=lambda x: (x["bbox_id"], x["value"])
            )
        }



    # ----------------------------------------------------------------------
    # *** NUOVI METODI: Clonare BB ***
    # ----------------------------------------------------------------------
    
    def copy_selected_box(self, event=None):
        """Copia i dati del box selezionato negli appunti interni."""
        if self.current_box != -1 and self.current_box < len(self.bboxes):
            # Salviamo una copia del dizionario del box (classe e coordinate)
            
            self.clipboard_box = copy.deepcopy(self.bboxes[self.current_box])
            self.status_label.config(text=f"Box '{self.clipboard_box['class']}' copiato!", fg='yellow')
        else:
            self.status_label.config(text="Seleziona un box per copiarlo!", fg='orange')

    def paste_box(self, event=None):
        """Incolla il box copiato nell'immagine corrente."""
        if self.clipboard_box:
            self._push_undo_state("Incolla box")   # 
            # Creiamo una copia per non influenzare l'originale se lo modifichiamo
            
            new_box = copy.deepcopy(self.clipboard_box)
            
            # Aggiungiamo il box alla lista corrente
            self.bboxes.append(new_box)
            self.current_box = len(self.bboxes) - 1 # Seleziona il nuovo box
            
            self._draw_bboxes()
            self._update_current_box_info()
            self._update_plate_entry_from_selection()
            self.status_label.config(text=f"Box '{new_box['class']}' incollato!", fg='lime')
        else:
            self.status_label.config(text="Nessun box negli appunti!", fg='orange')
    # ----------------------------------------------------------------------
    # *** NUOVI METODI: convertire Plate in Letta_plate ***
    # ----------------------------------------------------------------------
    
    def _set_navigation_lock(self, value: bool):
        """
        Gestisce il blocco della navigazione in modo centralizzato.
        Modifica il cursore per dare feedback visivo all'utente.
        """
        self.is_navigating = value
        
        # Opzionale: Cambia il cursore per mostrare che il programma sta lavorando
        if value:
            self.root.config(cursor="watch") # Clessidra/Orologio
        else:
            self.root.config(cursor="")      # Cursore normale
    
    def _ocr_class_for_plate(self, plate_class):
        """
        Restituisce il nome della classe OCR corrispondente a una classe Letta_plate.
        Esempio: 'Letta_plate' -> 'OCR'
        Restituisce None se non è una classe Letta_plate.
        """
        if not plate_class:
            return None
            
        cls_lower = plate_class.lower()
        
        # Caso base: 'Letta_plate' -> 'OCR'
        if cls_lower == 'letta_plate':
            return 'OCR'
            
        # Caso numerato: 'Letta_plate_N' -> 'OCR_N'
        if cls_lower.startswith('letta_plate'):
            # Usa una sostituzione case-insensitive sicura o semplice replace
            # Dato che i tuoi nomi sono consistenti, replace va bene:
            return plate_class.replace('Letta_plate', 'OCR')
            
        return None
    
    def next_filtered_box(self, event=None):
        # 1. Determina target
        target_class = None
        if self.root._class_filter:
            target_class = self.root._class_filter
        else:
            if self.current_box == -1 or self.current_box >= len(self.bboxes): return
            
            raw = self.bboxes[self.current_box].get("class", "")
            # Usa la regex globale
            m = RE_LETTA_PLATE_CHECK.match(raw)
            target_class = m.group(1) if m else raw

        if not target_class: return

        # 2. Costruisci la Regex per trovare target e varianti (target, target_1, target_2...)
        # re.escape serve per evitare problemi se il nome ha caratteri speciali
        pattern = re.compile(f"^{re.escape(target_class)}(_\\d+)?$", re.IGNORECASE)
        # 3. Trova tutti gli indici che corrispondono
        indices = [
            i for i, b in enumerate(self.bboxes)
            if pattern.match(str(b.get("class", "")))
        ]

        if not indices:
            return

        # 4. Navigazione ciclica
        if self.current_box not in indices:
            # Se siamo finiti su un box che non c'entra, andiamo al primo valido
            self.current_box = indices[0]
        else:
            # Altrimenti andiamo al prossimo
            pos = indices.index(self.current_box)
            self.current_box = indices[(pos + 1) % len(indices)]

        # 5. Aggiorna UI
        self._draw_bboxes()
        self._update_current_box_info()
        self._update_plate_entry_from_selection()
        
        # Feedback visivo
        if not self.root._class_filter:
             self.status_label.config(text=f"Ciclo locale su: {target_class}*", fg='#AAA')

    
    def change_class_filter(self, event=None):
        # Passiamo il filtro attuale per pre-compilare la dialog
        new_filter = ask_class_filter(self.root, self.classes, current_filter=self.root._class_filter)

        # Se new_filter è None, significa che l'utente ha tolto la spunta o non ha cambiato nulla di nullo
        # Verifichiamo se è cambiato rispetto a prima
        if new_filter == self.root._class_filter:
             # Se era None ed è rimasto None, o era "car" ed è rimasto "car", non fare nulla, MA:
             # Se l'utente preme OK confermando lo stesso filtro, va bene ricaricare.
             # L'unico caso di uscita è se annulla (che però qui gestiamo con il return della dialog).
             pass

        self.root._class_filter = new_filter

        # Logica di applicazione
        if self.root._class_filter:
            # Filtro Attivo
            # NUOVO CODICE VELOCE
            if not self.cache_valid: self._rebuild_metadata_cache()
            target = self.root._class_filter.lower()
            self.images = [
                img for img in self._all_images
                if target in self.metadata_cache.get(img, set())
            ]
            msg_text = f"Filtro: {new_filter} (Trovate: {len(self.images)})"
            msg_color = 'cyan'
        else:
            # Filtro Disattivato (Checkbox spenta) -> Ricarica TUTTO
            self.images = list(self._all_images)
            msg_text = "Filtro Disabilitato (Tutte le immagini)"
            msg_color = 'white'

        self.index = 0
        if not self.images:
             messagebox.showinfo("Filtro", f"Nessuna immagine trovata.")
        
        # Tenta di andare alla prima vergine
        virgin_idx = self.find_first_virgin_index()
        if virgin_idx < len(self.images):
             self.index = virgin_idx

        self.load_image()
        self.status_label.config(text=msg_text, fg=msg_color)
    
    def _find_next_letta_and_ocr_names(self):
        """
        Restituisce (letta_name, ocr_name) per il prossimo set.
        Se non esiste nessuna Letta_plate -> ('Letta_plate', 'OCR')
        Altrimenti -> ('Letta_plate_N', 'OCR_N') con N = max esistente + 1
        """
        
        indices = []
        for box in self.bboxes:
            m = RE_LETTA_PLATE_FULL.match(box.get('class', ''))
            if m:
                idx = m.group(1)
                indices.append(int(idx) if idx is not None else 0)
        # anche le OCR caricate (nel caso alcuni sono separati)
        if hasattr(self, 'loaded_ocr_boxes'):
            for o in self.loaded_ocr_boxes:
                cl = o.get('class', '')
                m = RE_LETTA_PLATE_FULL.match(cl.replace('ocr','letta_plate',1)) if cl.lower().startswith('ocr') else None
                # non necessario ma lasciato per robustezza

        next_idx = (max(indices) + 1) if indices else 0
        if next_idx == 0:
            return "Letta_plate", "OCR"
        else:
            return f"Letta_plate_{next_idx}", f"OCR_{next_idx}"


    def _find_ocr_by_letta_class(self, letta_class):
        """
        Dato 'Letta_plate' o 'Letta_plate_N' ritorna l'oggetto OCR corrispondente
        dalla lista self.loaded_ocr_boxes (o None se mancante).
        """
        if not hasattr(self, 'loaded_ocr_boxes'):
            return None
        # mappa: Letta_plate -> OCR, Letta_plate_2 -> OCR_2
        if letta_class.lower() == 'letta_plate':
            target = 'OCR'
        else:
            target = letta_class.replace('Letta_plate', 'OCR')
        for o in self.loaded_ocr_boxes:
            if o.get('class', '').lower() == target.lower():
                return o
        return None


    def _bind_plate_entry_to_ocr(self, ocr_obj):
        """Bind l'entry e la checkbox alla struttura ocr_obj corrente."""
        # prima togli eventuali binding precedenti
        self._unbind_plate_entry()

        # setta i valori della UI con quelli dell'ocr_obj
        val = ""
        if isinstance(ocr_obj.get('value'), list) and ocr_obj.get('value'):
            val = ocr_obj['value'][0]
        self.plate_var.set(val.upper() if val else "")
        self.validate_plate_var.set(bool(ocr_obj.get('validated', False)))

        # abilitazione dei controlli
        self.plate_entry.config(state='normal')
        self.validate_plate_check.config(state='normal')

        # binding: ogni modifica testo aggiorna ocr_obj['value'][0]
        def _on_plate_key(e=None, obj=ocr_obj):
            txt = self.plate_entry.get()
            obj['value'] = [txt]
        # memorizza il binding per poterlo rimuovere dopo
        self._plate_key_binding = self.plate_entry.bind("<KeyRelease>", _on_plate_key)

        # binding checkbox: aggiorna validated nello stesso OCR object
        # -> IMPORTANTISSIMO: 'obj' legato come default arg garantisce che il riferimento rimanga valido
        def _on_validate_toggle(obj=ocr_obj):
            obj['validated'] = bool(self.validate_plate_var.get())

        # assegna il comando in modo robusto e memorizza la funzione per _unbind
        try:
            self.validate_plate_check.config(command=_on_validate_toggle)
            self._validate_cmd = _on_validate_toggle
        except Exception:
            # fallback (compatibilità)
            self._validate_cmd = None


    def _unbind_plate_entry(self):
        """Rimuove binding precedenti sulla plate_entry se presenti."""
        try:
            if hasattr(self, '_plate_key_binding') and self._plate_key_binding:
                try:
                    self.plate_entry.unbind("<KeyRelease>", self._plate_key_binding)
                except Exception:
                    # alcune versioni di tkinter restituiscono None dall'unbind
                    try:
                        self.plate_entry.unbind("<KeyRelease>")
                    except Exception:
                        pass
                self._plate_key_binding = None
        except Exception:
            pass

        # rimuove il command sulla checkbox ripristinandolo a None
        try:
            if hasattr(self, '_validate_cmd') and self._validate_cmd:
                # imposta comando neutro
                try:
                    self.validate_plate_check.config(command=lambda: None)
                except Exception:
                    try:
                        self.validate_plate_check.configure(command=lambda: None)
                    except Exception:
                        pass
                self._validate_cmd = None
        except Exception:
            pass


    def _update_plate_entry_from_selection(self):
        """
        Controlla la box selezionata: se è Letta_plate* -> popola/lega entry con OCR corrispondente.
        Altrimenti disabilita entry e resettala.
        """
        # prima dislega binding precedenti
        try:
            self._unbind_plate_entry()
        except Exception:
            pass

        if self.current_box == -1 or self.current_box >= len(self.bboxes):
            # CHIUDI QUALSIASI STATO OCR ATTIVO
            self._unbind_plate_entry()

            if hasattr(self, 'plate_entry'):
                self.plate_entry.config(state='disabled')
            if hasattr(self, 'validate_plate_check'):
                self.validate_plate_check.config(state='disabled')

            self.plate_var.set("")
            self.validate_plate_var.set(False)

            # RIPRISTINA FOCUS AL CANVAS
            self.canvas.focus_set()
            return

        box = self.bboxes[self.current_box]
        cls = box.get('class', '')
        
        # --- SE È UNA TARGA (Letta_plate) ---
        if str(cls).lower().startswith('letta_plate'):
            # trova OCR corrispondente
            o = self._find_ocr_by_letta_class(cls)
            if o:
                self._bind_plate_entry_to_ocr(o)
            else:
                # non esiste ancora OCR corrispondente: crealo al volo
                ocr_name = self._ocr_class_for_plate(cls)
                if not ocr_name: ocr_name = 'OCR'
                
                if not hasattr(self, 'loaded_ocr_boxes'):
                    self.loaded_ocr_boxes = []
                    
                new_ocr = {"class": ocr_name, "value": [""], "validated": False}
                self.loaded_ocr_boxes.append(new_ocr)
                self._bind_plate_entry_to_ocr(new_ocr)
            
            # --- FIX FOCUS AUTOMATICO QUI ---
            # Se abbiamo appena selezionato una targa, forziamo il focus sulla casella di testo
            # Usiamo after(50) per dare tempo a Tkinter di abilitare il widget
            self.plate_entry.after(50, self.plate_entry.focus_set)
            # --------------------------------

        else:
            # --- SE NON È UNA TARGA (Es. Motorcycle, Car...) ---
            # DISATTIVA OCR COMPLETAMENTE
            self._unbind_plate_entry()

            if hasattr(self, 'plate_entry'):
                self.plate_entry.config(state='disabled')
            if hasattr(self, 'validate_plate_check'):
                self.validate_plate_check.config(state='disabled')

            self.plate_var.set("")
            self.validate_plate_var.set(False)

            # RIPRISTINA FOCUS AL CANVAS
            self.canvas.focus_set()


    def _is_editing_plate_entry(self):
        """
        True SOLO se:
        - esiste un box selezionato
        - il box è una Letta_plate*
        - il focus è sulla entry OCR
        """
        if self.current_box == -1 or self.current_box >= len(self.bboxes):
            return False

        cls = str(self.bboxes[self.current_box].get("class", "")).lower()
        if not cls.startswith("letta_plate"):
            return False

        return self.root.focus_get() == self.plate_entry


    
    def on_press_L(self, event=None):
        """Gestisce la pressione di L: converte in Targa e crea OCR."""
        # Evita attivazione se stai scrivendo
        if self.root.focus_get() == self.plate_entry: return
        if self.current_box == -1: return

        box = self.bboxes[self.current_box]
        # Check difensivo
        if str(box.get("class", "")).lower() != "plate":
            self.status_label.config(text="Devi selezionare un box 'plate'!", fg="orange")
            return

        # USIAMO LA FUNZIONE ESISTENTE (DRY - Don't Repeat Yourself)
        # Se questa funzione non esiste nel tuo v43, copiala dal mio messaggio precedente, 
        # ma nel v43 dovrebbe esserci se è basato sul v42.
        new_letta, new_ocr = self._find_next_letta_and_ocr_names()
        
        # UNDO: snapshot PRIMA di cambiare box e OCR
        self._push_undo_state("Conversione Plate → Letta_plate")
        
        box["class"] = new_letta
        
        # Crea entry OCR vuota
        ocr_obj = {"class": new_ocr, "value": [""], "validated": False}
        self.loaded_ocr_boxes.append(ocr_obj)
        
        self._draw_bboxes()
        self._update_plate_entry_from_selection() # O come si chiama la tua funzione di update sidebar
        self.plate_entry.focus_set()
        
    # ----------------------------------------------------------------------
    # *** NUOVI METODI: GESTIONE AUDIO ***
    # ----------------------------------------------------------------------

    
    def _load_playlist(self):
        """Carica tutti gli MP3 dalla cartella 'playlistAudio'."""
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))

        self.playlist_dir = os.path.join(base_path, "playlistAudio")

        if not os.path.isdir(self.playlist_dir):
            print("Cartella playlistAudio non trovata.")
            self.playlist = []
            return

        self.playlist = [
            os.path.join(self.playlist_dir, f)
            for f in os.listdir(self.playlist_dir)
            if f.lower().endswith(".mp3")
        ]

        self.playlist.sort()

        if not self.playlist:
            print("Nessun file MP3 trovato in playlistAudio.")


    def _start_background_music(self, index=0):
        """Avvia la playlist dalla traccia indicata."""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()

            self._load_playlist()

            if not self.playlist:
                print("Playlist vuota. Nessun audio avviato.")
                return

            self.track_index = index % len(self.playlist)

            pygame.mixer.music.load(self.playlist[self.track_index])
            pygame.mixer.music.play()

            # Callback quando il brano finisce → passa al successivo
            pygame.mixer.music.set_endevent(pygame.USEREVENT + 1)

        except Exception as e:
            print("Errore avvio playlist:", e)


    def _stop_background_music(self):
        try:
            pygame.mixer.music.stop()
        except:
            pass


    def toggle_audio(self):
        """Attiva o disattiva l'audio."""
        if self.audio_enabled.get():
            self._start_background_music(getattr(self, "track_index", 0))
        else:
            self._stop_background_music()


    # --------------------------------------------------------------
    # NAVIGAZIONE PLAYLIST
    # --------------------------------------------------------------

    def play_next_track(self, event=None):
        # --- FIX: Ignora freccia destra se si sta scrivendo nel box ---
        if event and self.root.focus_get() == self.plate_entry:
            return
        # -------------------------------------------------------------
        if not self.playlist:
            return
        self.track_index = (self.track_index + 1) % len(self.playlist)
        pygame.mixer.music.load(self.playlist[self.track_index])
        pygame.mixer.music.play()

    def play_prev_track(self, event=None):
        # --- FIX: Ignora freccia destra se si sta scrivendo nel box ---
        if event and self.root.focus_get() == self.plate_entry:
            return
        # -------------------------------------------------------------
        if not self.playlist:
            return
        self.track_index = (self.track_index - 1) % len(self.playlist)
        pygame.mixer.music.load(self.playlist[self.track_index])
        pygame.mixer.music.play()

    def pause_track(self, event=None):
        pygame.mixer.music.pause()

    def resume_track(self, event=None):
        pygame.mixer.music.unpause()

            
    # ----------------------------------------------------------------------
    
    # --- UTILITY FILE (JSON/FILENAME) ---
    
    def _json_path(self, image_filename):
        base, _ = os.path.splitext(image_filename)
        return os.path.join(self.folder, base + ".json")
        
    

    def _get_current_save_count(self):
        """Restituisce il conteggio dei salvataggi (0 se il JSON non esiste o la chiave manca)."""
        # USA self.filename CHE DEVE ESSERE SETTATO CORRETTAMENTE PRIMA DI CHIAMARE
        json_path = self._json_path(self.filename) 
        if not os.path.exists(json_path):
            return 0
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("save_count", 0) # Ritorna 0 se la chiave non esiste
        except Exception:
            return 0 # In caso di errore di lettura/JSON malformato

    
    def _load_boxes_from_json(self, image_filename):
        json_path = self._json_path(image_filename)
        boxes = []

        # Reimposta le strutture per ogni immagine
        self.loaded_ocr_boxes = []   # LISTA di tutti gli OCR letti per l'immagine corrente
        self.original_ocr_box = None # mantenuta per compatibilità

        # Reimposta le variabili UI (vuote fino a selezione)
        if hasattr(self, 'plate_var') and self.plate_var:
             self.plate_var.set("")
        if hasattr(self, 'validate_plate_var') and self.validate_plate_var:
             self.validate_plate_var.set(False)

        if not os.path.exists(json_path):
            # Nulla da caricare, disabilita entry
            if hasattr(self, 'plate_entry'):
                self.plate_entry.config(state='disabled')
            if hasattr(self, 'validate_plate_check'):
                self.validate_plate_check.config(state='disabled')
            return boxes

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            # ERRORE CRITICO: Il file esiste ma è rotto. Avvisiamo l'utente!
            print(f"CORRUZIONE JSON {json_path}: {e}")
            messagebox.showerror(
                "Errore Dati", 
                f"Il file di annotazione per questa immagine è corrotto!\n\nFile: {os.path.basename(json_path)}\nErrore: {e}\n\nVerranno mostrati 0 box, ma FAI ATTENZIONE a non sovrascrivere se volevi recuperare i dati."
            )
            return [] # O gestisci come preferisci, ma almeno l'utente sa.
        except Exception as e:
            # Altri errori (es. permessi, file non trovato mentre si apriva)
            print(f"Errore lettura JSON {json_path}: {e}")
            return boxes

        # Legge tutte le entry boxes
        for box in data.get("boxes", []):
            cls = str(box.get("class", "") or "")
            
            # 1. Box geometrici (hanno le coordinate)
            if "coords" in box and isinstance(box["coords"], list) and len(box["coords"]) == 4:
                boxes.append({"class": box.get("class"), "coords": box.get("coords")})
            
            # 2. OCR entries (match veloce con Regex Globale)
            #    Sostituisce il vecchio startswith
            elif RE_OCR_STARTS.match(cls):
                o = {
                    "class": box.get("class"),
                    "value": box.get("value", [""]),
                    "validated": bool(box.get("validated", False))
                }
                self.loaded_ocr_boxes.append(o)
            
            # 3. Altre voci (fallback)
            else:
                boxes.append(box)

        # UI reset finale
        if hasattr(self, 'plate_entry'):
            self.plate_entry.config(state='disabled')
        if hasattr(self, 'validate_plate_check'):
            self.validate_plate_check.config(state='disabled')

        return boxes

    def _save_boxes_to_json(self):
        """Salva i bounding box (self.bboxes) nel file JSON associato all'immagine corrente."""
        json_path = self._json_path(self.filename)

        # Inizializza con l'array box
        data = {"boxes": []}

        # 1. Aggiunge i Bounding Box standard (self.bboxes contiene solo box geometrici)
        data["boxes"].extend(self.bboxes)

        # 2. Sincronizza l'OCR corrispondente alla plate selezionata (se presente)
        # Se l'utente ha scritto nella sidebar su una Letta_plate selezionata, assicuriamoci
        # che il corrispondente ocr object in memoria sia aggiornato (o creato).
        try:
            plate_value = self.plate_var.get().strip()
        except Exception:
            plate_value = ""

        try:
            is_validated = bool(self.validate_plate_var.get())
        except Exception:
            is_validated = False

        # Se esiste una box selezionata e questa è una Letta_plate*, trova/crea OCR corrispondente
        if hasattr(self, 'current_box') and self.current_box != -1 and \
           self.current_box < len(self.bboxes):
            sel_box = self.bboxes[self.current_box]
            sel_cls = str(sel_box.get('class', '') or '')
            if sel_cls.lower().startswith('letta_plate'):
                # trova o crea la lista loaded_ocr_boxes se necessario
                if not hasattr(self, 'loaded_ocr_boxes') or self.loaded_ocr_boxes is None:
                    self.loaded_ocr_boxes = []

                # trova OCR esistente
                ocr_obj = self._find_ocr_by_letta_class(sel_cls)
                if ocr_obj is None:
                    # crea un nuovo OCR con nome coerente
                    if sel_cls.lower() == 'letta_plate':
                        ocr_name = 'OCR'
                    else:
                        ocr_name = sel_cls.replace('Letta_plate', 'OCR')
                    ocr_obj = {"class": ocr_name, "value": [plate_value], "validated": is_validated}
                    self.loaded_ocr_boxes.append(ocr_obj)
                else:
                    # aggiorna il value e validated dall'UI (l'entry potrebbe già aver sincronizzato,
                    # ma ridondanza non fa male e garantisce coerenza)
                    ocr_obj['value'] = [plate_value]
                    ocr_obj['validated'] = is_validated

        # 3. Costruisci l'insieme dei nomi OCR richiesti dalle Letta_plate presenti
        required_ocr_names = set()
        for b in self.bboxes:
            cls = str(b.get('class','') or '')
            if cls.lower().startswith('letta_plate'):
                if cls.lower() == 'letta_plate':
                    required_ocr_names.add('OCR')
                else:
                    required_ocr_names.add(cls.replace('Letta_plate', 'OCR'))

        # 4. Aggiungi SOLO gli OCR richiesti (evita di salvare OCR orfani)
        if hasattr(self, 'loaded_ocr_boxes') and self.loaded_ocr_boxes:
            for ocr in self.loaded_ocr_boxes:
                if str(ocr.get('class','')) in required_ocr_names:
                    # assicurati della struttura corretta
                    o = {
                        "class": ocr.get("class", "OCR"),
                        "value": ocr.get("value", [""]),
                        "validated": bool(ocr.get("validated", False))
                    }
                    data["boxes"].append(o)

        # 5. Aggiorna save_count come facevi tu
        try:
            current_save_count = self._get_current_save_count()
        except Exception:
            current_save_count = 0
        data["save_count"] = current_save_count + 1

        # 6. Scrivi su file in modo ATOMICO (Safe Save)
        # Scriviamo prima su un file temporaneo per evitare corruzione in caso di crash
        temp_path = json_path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
                f.flush() # Forza la scrittura su disco
                os.fsync(f.fileno()) # Assicurati che il sistema operativo scriva fisicamente
            
            # Se siamo arrivati qui, il file temp è sano. Sostituiamo l'originale.
            os.replace(temp_path, json_path)
            
            self.cache_valid = False 
            return True
        except Exception as e:
            # Se qualcosa va storto, il file originale è salvo. Cancelliamo il temp se esiste.
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass
            
            messagebox.showerror("Errore di Salvataggio", f"Impossibile salvare il JSON {json_path}: {e}")
            return False


    # ----------------------------------------------------------------------
    # *** METODO CHIAVE: CHIEDI CONFERMA SALVATAGGIO PRIMA DI CAMBIARE ***
    # ----------------------------------------------------------------------


    def _ask_save_confirmation(self):
        """
        SAVE MODES:
        SAFE   → chiedi sempre
        NO     → non chiedere mai
        SMART  → chiedi solo se is_dirty == True
        """

        # --- NO SAVE ---
        if self.save_mode == SAVE_MODE_NO_SAVE:
            return True

        # --- SMART ---
        if self.save_mode == SAVE_MODE_SMART:
            if not self.is_dirty:
                return True
            # se dirty → comportamento SAFE

        # --- SAFE (default) ---
        response = messagebox.askyesnocancel(
            "Salvare le modifiche?",
            f"L'immagine '{self.filename}' è stata modificata.\nVuoi salvarla?"
        )

        if response is None:
            return False

        if response is True:
            self._save_current_image()
            return True

        return True



    def _save_current_image(self, event=None):
        """Salva l'immagine corrente e le sue annotazioni (sovrascrive il JSON)."""
            # Non bloccare se NON c'è una Letta_plate selezionata
        if self._is_editing_plate_entry():
            self.canvas.focus_set()
            # NON return → il salvataggio DEVE avvenire
        if self._save_boxes_to_json():
            # Mostra il nuovo save count nello status bar
            save_count = self._get_current_save_count()
            self.status_label.config(
                text=f"Annotazioni salvate (Salvataggio n.{save_count}) per {self.filename}",
                fg='green'
            )
            
            # ✅ QUESTA RIGA È FONDAMENTALE
            self._saved_snapshot = self._make_snapshot()
            
            self._update_filename_color()  # Aggiorna il colore del nome file a verde
            self._update_current_box_info()  # Aggiorna le info del box
            # --- RESET DIRTY DOPO SALVATAGGIO ---
            self.is_dirty = False
            return True  # Salvataggio riuscito
        else:
            return False  # Errore nel salvataggio


    def _get_display_filename(self, filename, max_len=35):
        """Tronca il nome file se troppo lungo per la visualizzazione, mantenendo l'estensione."""
        if len(filename) > max_len:
            base, ext = os.path.splitext(filename)
            trunc_len = max_len - len(ext) - 3 
            
            if trunc_len <= 0:
                return filename[:max_len-3] + "..."
                
            return base[:trunc_len] + "..." + ext
        return filename
    
    def _get_truncated_filename(self, filename, max_len=30):
        """Tronca un filename troppo lungo per la sidebar (utilizzato dal codice base)."""
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
    
    # ----------------------------------------------------------------------
    # *** NUOVI METODI: HELP E ABOUT ***
    # ----------------------------------------------------------------------

    def show_help(self, event=None):
        """Mostra una finestra con la lista dei comandi."""
        # --- FIX: Ignora se l'utente sta scrivendo nel box ---
        if self.root.focus_get() == self.plate_entry:
            return
        # -----------------------------------------------------
        help_text = (
            "COMANDI MOUSE:\n"
            "• Click SX + Trascina: Crea nuovo Box (se in modalità 'n') o Seleziona multipli\n"
            "• Click SX su Box + Trascina: Sposta Box\n"
            "• Click su maniglie: Ridimensiona Box\n"
            "• Click DX (o Tasto 3) + Trascina: Pan (Sposta immagine)\n"
            "• Rotella Mouse: Zoom In/Out\n"
            "• Doppio Click SX: Zoom 4x sul punto\n\n"
            
            "COMANDI TASTIERA:\n"
            "• A / D: Immagine Precedente / Successiva\n"
            "• N: Modalità Nuovo Box\n"
            "• Canc / Delete: Elimina Box selezionato\n"
            "• Tab / Shift+Tab: Seleziona Box Successivo / Precedente\n"
            "• L: Converte 'Plate' in Box OCR modificabile\n"
            "• Ctrl+S: Salva Annotazioni\n"
            "• Ctrl+F: Cambia Filtro Classe\n"
            "• Ctrl+c: Copia BB selezionato\n"
            "• Ctrl+v: Incolla BB precedentemente copiato su immagine nuova\n"
            "• Ctrl+z/Z: UNDO fino a 50 livelli\n"
            "• Ctrl+y/Y: REDO (ripristino dopo Ctrl+z/Z)\n"
            "• Spazio: Passa al prossimo box della classe filtrata\n"
            "• H: Mostra questa guida\n"
            "• K: Info, Autore e Changelog\n\n"
            
            "AUDIO:\n"
            "• Freccia Su/Giù: Riprendi/Pausa Audio\n"
            "• Freccia Dx/Sx: Traccia Successiva/Precedente"
        )
        
        messagebox.showinfo("Guida Comandi (H)", help_text)

    def show_about(self, event=None):
        """Mostra finestra About con foto autore, versione e changelog esterno (Versione Grande)."""
        # --- FIX: Ignora se l'utente sta scrivendo nel box ---
        if self.root.focus_get() == self.plate_entry:
            return
        # -----------------------------------------------------
        
        top = tk.Toplevel(self.root)
        top.title("About / Info")
        
        # MODIFICA 1: Dimensioni iniziali molto più grandi
        top.geometry("1000x800")
        
        # MODIFICA 2: Sfondo (preso dalle tue costanti)
        top.configure(bg=self.BG_LIGHT)
        
        # MODIFICA 3: Ora è ridimensionabile
        top.resizable(True, True)
        
        # MODIFICA 4: Tenta di aprirla "Massimizzata" (A tutto schermo su Windows)
        try:
            top.state('zoomed')
        except:
            pass # Su Linux/Mac ignora e usa 1000x800

        # --- Intestazione e Foto ---
        header_frame = tk.Frame(top, bg=self.BG_LIGHT)
        header_frame.pack(fill=tk.X, padx=20, pady=20) # Aumentato padding

        # Usa resource_path come da tua indicazione
        photo_path = resource_path("max.jpg")

        try:
            pil_img = Image.open(photo_path)
            pil_img.thumbnail((150, 150)) # Foto leggermente più grande
            tk_photo = ImageTk.PhotoImage(pil_img)
            
            lbl_img = tk.Label(header_frame, image=tk_photo, bg=self.BG_LIGHT)
            lbl_img.image = tk_photo # Mantieni reference
            lbl_img.pack(side=tk.LEFT, padx=(0, 20))
        except Exception:
            # Fallback se non trova la foto
            lbl_placeholder = tk.Label(header_frame, text="[Foto non trovata]", 
                                     bg='gray', fg='white', width=20, height=10)
            lbl_placeholder.pack(side=tk.LEFT, padx=(0, 20))

        # Info Testuali
        info_text_frame = tk.Frame(header_frame, bg=self.BG_LIGHT)
        info_text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(info_text_frame, text="AnnotaImmagini OCR Tool", 
                 font=("Arial", 22, "bold"), # Font aumentato
                 bg=self.BG_LIGHT, fg="white", anchor="w").pack(fill=tk.X)
        
        # Versione
        VERSION = "v6.3" # Ho aggiornato a 6.3 visto il nome del file, se no rimetti 6.0
        tk.Label(info_text_frame, text=f"Versione: {VERSION}", 
                 font=("Arial", 14, "bold"), # Font aumentato
                 bg=self.BG_LIGHT, fg="gold", anchor="w").pack(fill=tk.X)
        
        tk.Label(info_text_frame, text="Autore: Max", 
                 font=("Arial", 14), # Font aumentato
                 bg=self.BG_LIGHT, fg="white", anchor="w").pack(fill=tk.X, pady=(10,0))

        # --- Changelog ---
        tk.Label(top, text="Changelog / Novità:", bg=self.BG_LIGHT, fg="white", 
                 font=("Arial", 14, "bold"), anchor="w").pack(fill=tk.X, padx=20, pady=(20,0))

        txt_frame = tk.Frame(top, bg=self.BG_LIGHT)
        txt_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        scrollbar = tk.Scrollbar(txt_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Text area più grande
        txt_changelog = tk.Text(txt_frame, height=10, width=50, 
                                bg="white", fg="black", font=("Consolas", 11), # Font più leggibile
                                yscrollcommand=scrollbar.set, state="normal")
        txt_changelog.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=txt_changelog.yview)

        # Caricamento changelog con resource_path
        changelog_path = resource_path("changelog.txt")
        
        try:
            if os.path.exists(changelog_path):
                with open(changelog_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    txt_changelog.insert(tk.END, content)
            else:
                txt_changelog.insert(tk.END, "File 'changelog.txt' non trovato.")
        except Exception as e:
            txt_changelog.insert(tk.END, f"Errore lettura changelog: {e}")

        txt_changelog.config(state="disabled") # Sola lettura

        # Pulsante chiudi (più grande)
        tk.Button(top, text="Chiudi", command=top.destroy, 
                  bg=self.BUTTON_ACCENT, fg="white", font=("Arial", 12, "bold"), 
                  pady=10, padx=20).pack(pady=20)
        
    def _on_save_mode_changed(self, *_):
        """Callback cambio modalità salvataggio (safe per init)."""
        self.save_mode = self.save_mode_var.get()

        # status_label potrebbe non esistere ancora durante __init__
        if hasattr(self, "status_label"):
            self.status_label.config(
                text=f"Save mode: {self.save_mode}",
                fg="cyan"
            )


    
    # --- INIZIALIZZAZIONE ---
    
    def __init__(self, root, folder, save_mode, filter_class=None):
        
        self.root = root
        self.folder = folder
        self.clipboard_box = None  # Memoria per il "Copia"
        # ======================================================
        # FILTRO DI CLASSE – STATO PERSISTENTE
        # ======================================================
        if not hasattr(self.root, "_class_filter"):
            self.root._class_filter = filter_class

        # --------------------------------------------------------------------------
        # NUOVA VARIABILE: Controlla la Modalità Safe (conferma salvataggio)
        # Prende il valore iniziale dalla scelta utente all'avvio
        # --- SAVE MODE RADIO VAR ---
        self.save_mode_var = tk.StringVar(value=save_mode)

        # --- SAVE MODE & DIRTY STATE ---
        # Modalità di salvataggio:
        # "safe"  = chiedi sempre
        # "none"  = non chiedere mai
        # "smart" = chiedi solo se modificato
        
        self.save_mode = save_mode   # default = comportamento attuale
        self.is_dirty = False             # immagine appena caricata = pulita
        
        # Snapshot dell'ultimo stato salvato / caricato
        self._saved_snapshot = None

        
        self.is_loading_image = False

        




        # --------------------------------------------------------------------------
        # NUOVA VARIABILE: Controlla l'audio di background
        self.audio_enabled = tk.BooleanVar(root, value=True) # audio attivo di default (ora usa 'root')
        # --------------------------------------------------------------------------
        # Variabili di controllo (OCR)
        self.plate_var = tk.StringVar(root)        
        self.validate_plate_var = tk.BooleanVar(root)  
        self.original_ocr_box = None # PER MODIFICA: Salva il blocco OCR originale al caricamento

        # Variabili GUI
        self.square_img = tk.PhotoImage(width=1, height=1) 
        self.stats_label_var = tk.StringVar(root)
        self.show_all_boxes_var = tk.BooleanVar(value=True) 

        all_images = sorted([
            f for f in os.listdir(folder)
            if f.lower().endswith(('.jpg', '.jpeg', '.png'))
        ])
            
        # lista completa e non filtrata (sorgente unica)
        self._all_images = all_images

        # Inizializza la cache dei metadata PRIMA di applicare qualsiasi filtro
        # (necessario perché image_has_class_fast può essere chiamata subito dopo)
        self.metadata_cache = {}
        self.cache_valid = False

        # ======================================================
        # APPLICAZIONE FILTRO DI CLASSE (PERSISTENTE)
        # ======================================================
        filter_class = self.root._class_filter

        if filter_class:
            self.images = [
                img for img in self._all_images
                if self.image_has_class_fast(img, self.root._class_filter)
            ]
        else:
            self.images = list(self._all_images)




        
        self.bboxes = []
        self.current_box = -1
        
        # Variabili di interazione
        self.dragging = False
        self.resizing = False
        self.resize_handle = None
        self.creating_box = False      
        self.new_box_start = None      
        self.new_box_end = None        
        self.deleting_image = False # Aggiunta per prevenire eventi doppi (CRITICO)
        self.panning = False # Aggiunto per tracciare lo stato del pan
        
        # *** INSERISCI QUI LA NUOVA RIGA CRITICA PER IL BLOCCO DELLA NAVIGAZIONE ***
        self._set_navigation_lock(False)
        
        # Variabili di visualizzazione
        self.scale = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.original_img = None
        
        # ======================================================
        # UNDO / REDO STACK
        # ======================================================
        #self.undo_stack = []
        #self.redo_stack = []
        self.history = {}
        self.max_undo = 50  # limite sicurezza

        
        # Classi disponibili
        # HO MANTENUTO LA STRUTTURA ORIGINALE CON IL NUOVO ORDINE/LOGICA
        self.classes = DEFAULT_CLASSES.copy()

        
        self.current_class = self.classes[0] if self.classes else 'object'
        
        

        
        # --- DEFINIZIONE COLORI (Dark Mode) ---
        self.BG_DARK = '#2C3E50'     
        self.BG_LIGHT = '#34495E'    
        self.FG_WHITE = 'white'
        self.BUTTON_ACCENT = '#3498DB' 
        self.BUTTON_ACCENT_ACTIVE = '#2980B9'
        self.BUTTON_DANGER = '#E74C3C' 
        self.BUTTON_DANGER_ACTIVE = '#C0392B'

        self.root.title("AnnotaImmagini Bounding Box e Targhe Vers 6.0 - Dark Mode")
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
            return
            
        # AGGIUNGI QUESTO:
        self.metadata_cache = {}
        self.cache_valid = False
            
        # *** MODIFICA INIZIO: APERTURA PRIORITARIA ***
        self.index = self.find_first_virgin_index()
        # *** MODIFICA FINE ***
        
        # --------------------------------------------------------------------------
        # NUOVO BLOCCO: AVVIO AUDIO RITARDATO TRAMITE self.toggle_audio
        # Questo risolve il problema di temporizzazione all'avvio dell'applicazione.
        if self.audio_enabled.get():
            self.root.after(100, self.toggle_audio) # Ritarda l'esecuzione di 100ms
        # --------------------------------------------------------------

    
        self.load_image()
        self.root.after(100, self.canvas.focus_set)
        
        messagebox.showinfo(
            "Istruzioni Focus",
            "Benvenuto! Se le scorciatoie da tastiera (Tab, Canc, N) non dovessero funzionare immediatamente all'avvio, ti preghiamo di **cliccare una volta sulla 'Sidebar'** e solo dopo ricliccare sull'immagine da annotare."
        )
        

    # --- WIDGETS E UI ---
    
    def create_widgets(self):
        
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
        self.SIDEBAR_WIDTH = 340 
        control_frame = tk.Frame(main_frame, width=self.SIDEBAR_WIDTH, bg=self.BG_LIGHT) 
        control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
        control_frame.pack_propagate(False) 

        # 1. Status Bar
        status_frame = tk.Frame(self.root, bd=1, relief=tk.SUNKEN, bg=self.BG_DARK)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # Label per lo stato generale (es. salvataggio, pronto) - Lato Sinistro
        self.status_label = tk.Label(status_frame, text="", anchor=tk.W, bg=self.BG_DARK, fg=self.FG_WHITE, font=('Arial', 9))
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Label per l'informazione sul box corrente - Lato Destro (Box Corrente info)
        self.current_box_info_label = tk.Label(status_frame, text="", anchor=tk.E, bg=self.BG_DARK, 
                                               fg='#3498DB', font=('Arial', 12, 'bold'), padx=5)
        self.current_box_info_label.pack(side=tk.RIGHT)
        
        # 2. --- Controlli Immagine (Navigazione) ---
        img_controls = tk.LabelFrame(control_frame, text="Navigazione Immagini", padx=5, pady=5, bg=self.BG_LIGHT, fg=self.FG_WHITE, font=('Arial', 10, 'bold'))
        img_controls.pack(fill=tk.X, pady=5, padx=5)
        
        # Riga con nome immagine + pulsanti (USA GRID)
        img_label_frame = tk.Frame(img_controls, bg=self.BG_LIGHT)
        img_label_frame.pack(fill=tk.X, pady=5)
        
        # --- CONFIGURAZIONE GRIGLIA AGGIORNATA ---
        # Col 0: Pulsante Cartella (fisso)
        # Col 1: Label Nome File (si espande - weight=1)
        # Col 2: Pulsante Help (fisso)
        # Col 3: Pulsante About (fisso)
        img_label_frame.grid_columnconfigure(0, weight=0) 
        img_label_frame.grid_columnconfigure(1, weight=1) 
        img_label_frame.grid_columnconfigure(2, weight=0) 
        img_label_frame.grid_columnconfigure(3, weight=0)

        # 1. Pulsante CARTELLA (Spostato a sinistra e ridimensionato)
        reload_btn = tk.Button(
            img_label_frame,
            text="📁",    # Solo testo emoji
            width=3,      # Larghezza standard caratteri (uguale a ? e i)
            bg=self.BUTTON_ACCENT,
            fg=self.FG_WHITE,
            font=('Arial', 9, 'bold'),
            relief=tk.FLAT,
            activebackground=self.BUTTON_ACCENT_ACTIVE,
            activeforeground=self.FG_WHITE,
            command=self._select_new_folder
        )
        reload_btn.grid(row=0, column=0, padx=(0, 2))
        CreateToolTip(reload_btn, "Apri nuova cartella")

        # 2. LABEL IMMAGINE (Al centro, dopo la cartella)
        # NOTA: il colore FG è inizializzato a FG_WHITE, verrà aggiornato a GIALLO/VERDE
        self.image_label = tk.Label(img_label_frame, text="IMG 0/0: N/A", 
                                    bg=self.BG_LIGHT, fg=self.FG_WHITE, font=('Arial', 10), anchor='w')
        self.image_label.grid(row=0, column=1, sticky='ew', padx=(2, 2)) 

        # 3. Pulsante Help (?) (A destra)
        help_btn = tk.Button(img_label_frame, text="?", command=self.show_help,
                             bg=self.BUTTON_ACCENT, fg=self.FG_WHITE, width=3,
                             relief=tk.FLAT, font=('Arial', 9, 'bold'))
        help_btn.grid(row=0, column=2, padx=1)
        CreateToolTip(help_btn, "Guida Comandi (Premi 'h')")

        # 4. Pulsante About (i) (A destra)
        about_btn = tk.Button(img_label_frame, text="i", command=self.show_about,
                              bg=self.BUTTON_ACCENT, fg=self.FG_WHITE, width=3,
                              relief=tk.FLAT, font=('Arial', 9, 'bold'))
        about_btn.grid(row=0, column=3, padx=1)
        CreateToolTip(about_btn, "About / Changelog (Premi 'k')")

        # --- FINE MODIFICA BARRA SUPERIORE ---

        nav_buttons_frame = tk.Frame(img_controls, bg=self.BG_LIGHT)
        nav_buttons_frame.pack(fill=tk.X)
        
        tk.Button(nav_buttons_frame, text="<<Prec(a)", command=self.prev_image, **button_options).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        tk.Button(nav_buttons_frame, text="Salva(Ctrl+S)", command=self._save_current_image, **button_options).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        # Pulsante per cancellare l'immagine corrente
        delete_img_options = {'bg': self.BUTTON_DANGER, 'fg': self.FG_WHITE, 'relief': tk.FLAT,
                              'activebackground': self.BUTTON_DANGER_ACTIVE, 'activeforeground': self.FG_WHITE,
                              'font': ('Arial', 9, 'bold'), 'pady': 5}
        
        tk.Button(nav_buttons_frame, text="Del", command=self.delete_current_image,
                  **delete_img_options).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        tk.Button(nav_buttons_frame, text="Succ(d)>>", command=self.next_image, **button_options).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
       
        # 3. --- CONTAINER COMPATTATO: Statistiche BB ---
        stats_controls = tk.LabelFrame(control_frame, text="Statistiche Box", padx=5, pady=5, bg=self.BG_LIGHT, fg=self.FG_WHITE, font=('Arial', 10, 'bold'))
        stats_controls.pack(fill=tk.X, pady=5, padx=5)

        # Frame per il Totale BB (in linea)
        total_frame = tk.Frame(stats_controls, bg=self.BG_LIGHT)
        total_frame.pack(fill=tk.X)
        
        # BOLLINO A DESTRA
        self.overlap_status_label = tk.Label(
            total_frame, 
            text="🟢", 
            bg=self.BG_LIGHT, 
            fg='green', 
            font=('Arial', 12)
        )
        self.overlap_status_label.pack(side=tk.RIGHT, padx=(5, 5)) 
        
        tk.Label(total_frame, text="Tot Box:", bg=self.BG_LIGHT, fg=self.FG_WHITE, font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 5))

        self.total_bb_label = tk.Label(total_frame, text="0", bg=self.BG_LIGHT, fg='cyan', font=('Arial', 12, 'bold'))
        self.total_bb_label.pack(side=tk.LEFT, padx=(0,5))

        # Checkbox ALL
        all_check = tk.Checkbutton(
            total_frame,
            text="ALL",
            variable=self.show_all_boxes_var,
            bg=self.BG_LIGHT,
            fg=self.FG_WHITE,
            selectcolor=self.BG_LIGHT,
            font=('Arial', 10, 'bold'),
            command=self._draw_bboxes
        )
        all_check.pack(side=tk.LEFT, padx=(0, 2))
        
        # --- SAVE MODE DROPDOWN ---
        save_mode_menu = tk.OptionMenu(
            total_frame,
            self.save_mode_var,
            SAVE_MODE_SAFE,
            SAVE_MODE_SMART,
            SAVE_MODE_NO_SAVE,
            command=self._on_save_mode_changed
        )

        save_mode_menu.config(
            bg=self.BG_LIGHT,
            fg=self.FG_WHITE,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_WHITE,
            font=('Arial', 9, 'bold'),
            highlightthickness=0
        )

        save_mode_menu["menu"].config(
            bg=self.BG_LIGHT,
            fg=self.FG_WHITE,
            font=('Arial', 9)
        )

        save_mode_menu.pack(side=tk.LEFT, padx=(4, 4))

        
        # Checkbox Audio
        tk.Checkbutton(
            total_frame,
            text="🎶",
            variable=self.audio_enabled, 
            command=self.toggle_audio,   
            bg=self.BG_LIGHT,
            fg=self.FG_WHITE,
            selectcolor=self.BG_LIGHT,
            activebackground=self.BG_LIGHT,
            activeforeground=self.FG_WHITE,
            font=('Arial', 10, 'bold')
        ).pack(side=tk.LEFT, padx=(0, 2))

        # Label per il Dettaglio
        self.class_breakdown_label = tk.Label(stats_controls, text="Nessun box presente", bg=self.BG_LIGHT, fg=self.FG_WHITE, justify=tk.LEFT, anchor=tk.NW, font=('Arial', 9), wraplength=self.SIDEBAR_WIDTH - 20) 
        self.class_breakdown_label.pack(fill=tk.BOTH, expand=True) 
        
        # 4. --- Controlli Bounding Box (CORRETTO: Auto-adattamento) ---
        box_controls = tk.LabelFrame(control_frame, text="Controlli Box", padx=5, pady=5, 
                                     bg=self.BG_LIGHT, fg=self.FG_WHITE, font=('Arial', 10, 'bold'))
        box_controls.pack(fill=tk.X, pady=5, padx=5)

        # Frame unico per la riga dei pulsanti
        button_frame = tk.Frame(box_controls, bg=self.BG_LIGHT)
        button_frame.pack(fill=tk.X, pady=2)

        # --- Dizionario di stile base pulsanti ---
        base_button_options = {
            "bg": "#3498db",          # blu come Nuovo Box
            "fg": self.FG_WHITE,
            "relief": tk.FLAT,
            "activebackground": "#2980b9",
            "activeforeground": self.FG_WHITE,
            "font": ('Arial', 12, 'bold'),
            "pady": 6,   # altezza uniforme
            "padx": 10
        }


        # --- 1. Pulsante Nuovo Box ---
        tk.Button(button_frame, text="Nuovo (n)", command=self.create_new_box_mode,
                  **base_button_options).pack(side=tk.LEFT, padx=(0,2))

        # --- 2. Pulsante Aggiungi Classe ---
        add_class_options = dict(base_button_options)
        add_class_options["bg"] = "#2ecc71"
        add_class_options["activebackground"] = "#27ae60"
        add_class_options["font"] = ('Arial', 12, 'bold')
        
        # ASSEGNO A VARIABILE self.btn_add_class
        self.btn_add_class = tk.Button(button_frame, text=" + ", command=self._add_new_class,
                                       **add_class_options)
        self.btn_add_class.pack(side=tk.LEFT, padx=2)

        # AGGIUNTA TOOLTIP
        if 'CreateToolTip' in globals(): 
            CreateToolTip(self.btn_add_class, "Aggiungi nuova classe personalizzata")

        # --- 3. Pulsante Elimina Box ---
        delete_options = dict(base_button_options)
        delete_options["bg"] = self.BUTTON_DANGER
        delete_options["activebackground"] = self.BUTTON_DANGER_ACTIVE
        delete_options["font"] = ('Arial', 12, 'bold')
        tk.Button(button_frame, text="🗑 (Canc)", command=self.delete_current_box,
                  **delete_options).pack(side=tk.LEFT, padx=2)

        # --- 4. Pulsante Snapshot (emoji grande + flash) ---
        snap_button_options = dict(base_button_options)
        snap_button_options["font"] = ('Arial', 12, 'bold')  # emoji più grande
        snap_button_options["pady"] = 6                     # stessa altezza degli altri

        self.btn_snap = tk.Button(button_frame, text="📷", command=self._snapshot_with_flash,
                                  **snap_button_options)
        self.btn_snap.pack(side=tk.LEFT, padx=(2,0))

        
        if 'CreateToolTip' in globals(): CreateToolTip(self.btn_snap, "Marked Snapshot")
        

        # 5. --- Controlli OCR/Targa ---
        ocr_controls = tk.LabelFrame(control_frame, text="Controllo Targa (OCR)", padx=5, pady=5, bg=self.BG_LIGHT, fg=self.FG_WHITE, font=('Arial', 10, 'bold'))
        ocr_controls.pack(fill=tk.X, pady=5, padx=5)

        plate_line_frame = tk.Frame(ocr_controls, bg=self.BG_LIGHT)
        plate_line_frame.pack(fill=tk.X) 
        
        self.plate_entry = tk.Entry(plate_line_frame, 
                                    textvariable=self.plate_var, 
                                    bg="white", 
                                    fg="black", 
                                    font=("Arial", 12, "bold"), 
                                    state='disabled',
                                    width=10) 
        self.plate_entry.pack(side=tk.LEFT, padx=(0, 5), pady=2) 
        
        self.validate_plate_check = tk.Checkbutton(plate_line_frame, 
                       text="Valida (Salva)",
                       variable=self.validate_plate_var,
                       bg=self.BG_LIGHT, 
                       fg=self.FG_WHITE, 
                       selectcolor=self.BG_LIGHT,
                       font=("Arial", 9), 
                       state='disabled')
        self.validate_plate_check.pack(side=tk.LEFT, pady=2, fill=tk.X, expand=True) 

        # 6. --- Selettore Classi ---
        class_frame = tk.LabelFrame(control_frame, text="Seleziona Classe", padx=5, pady=5, bg=self.BG_LIGHT, fg=self.FG_WHITE, font=('Arial', 10, 'bold'))
        class_frame.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)

        canvas_class = tk.Canvas(class_frame, bg=self.BG_LIGHT, highlightthickness=0)
        canvas_class.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(class_frame, orient="vertical", command=canvas_class.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        canvas_class.configure(yscrollcommand=scrollbar.set)
        
        self.class_button_frame = tk.Frame(canvas_class, bg=self.BG_LIGHT) 
        
        def on_canvas_class_configure(event):
            if event is not None:
                canvas_class.itemconfig(self.scrollable_frame_id, width=event.width)
            else:
                canvas_class.itemconfig(self.scrollable_frame_id, width=canvas_class.winfo_width())

        self.scrollable_frame_id = canvas_class.create_window((0, 0), window=self.class_button_frame, anchor="nw")
        canvas_class.bind('<Configure>', on_canvas_class_configure)
        self.class_button_frame.bind('<Enter>', lambda e: canvas_class.bind_all('<MouseWheel>', self._on_mousewheel))
        self.class_button_frame.bind('<Leave>', lambda e: canvas_class.unbind_all('<MouseWheel>'))
        
        self.root.after_idle(lambda: on_canvas_class_configure(None)) 

        self.update_class_buttons()
        
    def _on_mousewheel(self, event):
        """Gestisce lo scroll con la rotella sulla lista delle classi."""
        if event.delta: # Per Windows/Linux
            self.class_button_frame.master.yview_scroll(int(-1*(event.delta/120)), "units")
        elif event.num == 5: # Rotella verso il basso su X11
            self.class_button_frame.master.yview_scroll(1, "unit")
        elif event.num == 4: # Rotella verso l'alto su X11
            self.class_button_frame.master.yview_scroll(-1, "unit")
        
    # --- NUOVI METODI: Aggiungi Classe con Logica di Ordinamento ---

    def _ask_new_class(self):
        """Mostra una finestra di dialogo personalizzata per l'inserimento della classe e la selezione del tipo."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Nuova Classe")
        dialog.geometry("300x200")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # Variabili
        class_name_var = tk.StringVar()
        is_vehicle_var = tk.BooleanVar(value=False)
        is_luggage_var = tk.BooleanVar(value=False)
        result = {"name": None, "type": None}

        # UI Setup (usando i colori Dark Mode)
        BG_LIGHT = self.BG_LIGHT
        FG_WHITE = self.FG_WHITE

        dialog.configure(bg=BG_LIGHT)

        tk.Label(dialog, text="Nome Nuova Classe:", bg=BG_LIGHT, fg=FG_WHITE, font=('Arial', 10, 'bold')).pack(pady=(10, 2), padx=10, fill=tk.X)
        entry = tk.Entry(dialog, textvariable=class_name_var, bg="white", fg="black", font=("Arial", 11))
        entry.pack(pady=(0, 10), padx=10, fill=tk.X)
        entry.focus_set()

        def on_checkbox_toggle(current_var, other_var):
            """Assicura l'esclusività tra le due checkbox."""
            if current_var.get():
                other_var.set(False)

        # Checkbox Veicolo
        check_vehicle = tk.Checkbutton(dialog, text="Classe Veicolo", variable=is_vehicle_var,
                                       bg=BG_LIGHT, fg=FG_WHITE, selectcolor=BG_LIGHT,
                                       font=("Arial", 9),
                                       command=lambda: on_checkbox_toggle(is_vehicle_var, is_luggage_var))
        check_vehicle.pack(anchor=tk.W, padx=10)

        # Checkbox Bagaglio
        check_luggage = tk.Checkbutton(dialog, text="Classe Bagaglio", variable=is_luggage_var,
                                       bg=BG_LIGHT, fg=FG_WHITE, selectcolor=BG_LIGHT,
                                       font=("Arial", 9),
                                       command=lambda: on_checkbox_toggle(is_luggage_var, is_vehicle_var))
        check_luggage.pack(anchor=tk.W, padx=10)


        # Handlers
        def on_ok():
            name = class_name_var.get().strip().lower()
            is_vehicle = is_vehicle_var.get()
            is_luggage = is_luggage_var.get()

            if not name:
                messagebox.showerror("Errore", "Il nome della classe non può essere vuoto.", parent=dialog)
                return

            if not is_vehicle and not is_luggage:
                messagebox.showerror("Errore", "Devi selezionare 'Classe Veicolo' o 'Classe Bagaglio'.", parent=dialog)
                return
                
            result["name"] = name
            result["type"] = "vehicle" if is_vehicle else "luggage"
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        # Button Frame (utilizza i colori Dark Mode)
        btn_frame = tk.Frame(dialog, bg=BG_LIGHT)
        btn_frame.pack(fill=tk.X, pady=10, padx=10)

        # Pulsante OK (Stile verde/accento)
        tk.Button(btn_frame, text="OK", command=on_ok, 
                  bg='#2ECC71', fg=FG_WHITE, relief=tk.FLAT,
                  activebackground='#27AE60', font=('Arial', 9, 'bold')
                  ).pack(side=tk.RIGHT, padx=5)
        # Pulsante Annulla (Stile neutrale)
        tk.Button(btn_frame, text="Annulla", command=on_cancel, 
                  bg=BG_LIGHT, fg=FG_WHITE, relief=tk.FLAT).pack(side=tk.RIGHT)

        dialog.bind('<Return>', lambda e: on_ok())
        dialog.bind('<Escape>', lambda e: on_cancel())
        
        self.root.wait_window(dialog)
        return result


    def _add_new_class(self):
        """Chiede all'utente una nuova classe, ne determina il tipo (veicolo/bagaglio) e la aggiunge ordinata."""
        
        dialog_result = self._ask_new_class() 
        
        if not dialog_result.get("name"):
            return # Utente ha annullato o nome classe è vuoto

        new_class_name = dialog_result["name"]
        class_type = dialog_result["type"] # 'vehicle' o 'luggage'
        
        SEPARATOR_CLASS = 'person'
        LUGGAGE_FIXED_CLASSES = ['backpack', 'handbag', 'suitcase'] # Classi bagaglio fisse
        
        if new_class_name in self.classes:
            messagebox.showinfo("Informazione", f"La classe '{new_class_name}' esiste già.")
            return

        if new_class_name == SEPARATOR_CLASS or new_class_name in LUGGAGE_FIXED_CLASSES:
             messagebox.showinfo("Informazione", f"La classe '{new_class_name}' è una classe riservata e non può essere aggiunta in questo modo.")
             return
        
        # 1. Trova l'indice del separatore
        try:
            person_index = self.classes.index(SEPARATOR_CLASS)
        except ValueError:
            messagebox.showerror("Errore", "Impossibile trovare il separatore 'person'. La struttura delle classi è compromessa. Aggiunta annullata.")
            return

        # 2. Suddivide i gruppi
        current_vehicle_group = self.classes[:person_index] # Tutte le classi prima di 'person'
        current_luggage_group = self.classes[person_index + 1:] # Tutte le classi dopo di 'person'
        
        
        if class_type == "vehicle":
            # Aggiungi in ordine alfabetico nel gruppo veicoli
            current_vehicle_group.append(new_class_name)
            current_vehicle_group.sort() 
            
            # Ricostruisce la lista
            self.classes = current_vehicle_group + [SEPARATOR_CLASS] + current_luggage_group

        elif class_type == "luggage":
            # Aggiungi in ordine alfabetico nel gruppo bagagli
            current_luggage_group.append(new_class_name)
            current_luggage_group.sort() 
            
            # Ricostruisce la lista
            self.classes = current_vehicle_group + [SEPARATOR_CLASS] + current_luggage_group
        
        # Finalizzazione
        self.update_class_buttons()
        self.set_current_class(new_class_name) # Imposta la nuova classe come corrente
        self.status_label.config(text=f"Nuova classe '{new_class_name}' ({class_type}) aggiunta.", fg='green')


    # --- METODI STATISTICHE E CLASSI ---

    def _calculate_iou(self, boxA_coords, boxB_coords):
        """Calcola l'Intersection over Union (IoU) tra due bounding box."""
        xA = max(boxA_coords[0], boxB_coords[0])
        yA = max(boxA_coords[1], boxB_coords[1])
        xB = min(boxA_coords[2], boxB_coords[2])
        yB = min(boxA_coords[3], boxB_coords[3])

        inter_width = max(0, xB - xA)
        inter_height = max(0, yB - yA)
        inter_Area = inter_width * inter_height

        boxA_Area = (boxA_coords[2] - boxA_coords[0]) * (boxA_coords[3] - boxA_coords[1])
        boxB_Area = (boxB_coords[2] - boxB_coords[0]) * (boxB_coords[3] - boxB_coords[1])

        union_Area = float(boxA_Area + boxB_Area - inter_Area)

        if union_Area <= 0:
            return 0.0

        return inter_Area / union_Area

    def _update_current_box_info(self):
        """
        Aggiorna la label in basso a destra con il numero e la classe del box corrente.
        """
        if self.current_box != -1 and self.current_box < len(self.bboxes):
            # Box selezionato (Formato richiesto)
            box = self.bboxes[self.current_box]
            current = self.current_box + 1
            total = len(self.bboxes)
            # Formato: x/n: Classe
            text = f"{current}/{total}: {box['class'].capitalize()}"
            self.current_box_info_label.config(text=text, fg='gold') 
        else:
            # Nessun box selezionato
            # Questo conteggio include ancora l'OCR per dare un'indicazione completa nel footer
            total_boxes_all = len(self.bboxes) + (1 if self.original_ocr_box else 0) 
            text = f"Box Corrente: Nessuno ({total_boxes_all} totali)"
            # Colore di default (blu/accento) per lo stato non selezionato
            self.current_box_info_label.config(text=text, fg='#3498DB') 

    def _compute_overlaps(self, iou_threshold=0.8):
        """
        Calcola gli indici dei box che partecipano a sovrapposizioni tra classi diverse.
        Restituisce (set_indices, red_flag, orange_flag).
        """
        overlapped = set()
        red_alert = False
        orange_alert = False

        IGNORED_CLASSES = ['ocr']

        n = len(self.bboxes)
        for i in range(n):
            bi = self.bboxes[i]
            if 'coords' not in bi or not isinstance(bi['coords'], list) or len(bi['coords']) != 4:
                continue
            ci = bi.get('class', '').lower()
            if ci in IGNORED_CLASSES:
                continue
            for j in range(i + 1, n):
                bj = self.bboxes[j]
                if 'coords' not in bj or not isinstance(bj['coords'], list) or len(bj['coords']) != 4:
                    continue
                cj = bj.get('class', '').lower()
                if cj in IGNORED_CLASSES:
                    continue

                c1 = bi['coords']
                c2 = bj['coords']

                # Coordinate uguali (esatto)
                if c1 == c2:
                    overlapped.add(i)
                    overlapped.add(j)
                    red_alert = True
                    continue

                iou = self._calculate_iou(c1, c2)
                if iou >= iou_threshold:
                    overlapped.add(i)
                    overlapped.add(j)
                    orange_alert = True

        return overlapped, red_alert, orange_alert


    def _update_box_stats(self):
        """Aggiorna le statistiche dei BB e lo stato di sovrapposizione. Chiama _update_current_box_info."""
        
        # *** MODIFICA PER ESCLUDERE OCR: Conteggio solo dei Bounding Box geometrici (self.bboxes) ***
        total_boxes = len(self.bboxes) 
        self.total_bb_label.config(text=str(total_boxes))

        # Calcola overlap e ottieni set indici
        overlapped_set, red_alert, orange_alert = self._compute_overlaps(iou_threshold=0.8)
        self.overlapped_indices = overlapped_set  # memorizza per il disegno

        if total_boxes > 0:
            class_counts = {}
            for box in self.bboxes:
                cls = box['class']
                # Normalizza le varianti Letta_plate_N in 'Letta_plate' per il conteggio
                if str(cls).lower().startswith('letta_plate'):
                    key = 'Letta_plate'
                else:
                    key = cls
                class_counts[key] = class_counts.get(key, 0) + 1

            
            # Rimosso il blocco che aggiungeva il conteggio del box OCR per soddisfare la richiesta.
            
            # Formattazione compatta: Classe1 (N1), Classe2 (N2), ...
            stats_list = [f"{cls} ({count})" for cls, count in sorted(class_counts.items())]
            
            # Unisce tutto in una stringa compatta (Tkinter si occuperà del wrapping se necessario)
            stats_text = ", ".join(stats_list)

            self.class_breakdown_label.config(text=stats_text.strip(), fg=self.FG_WHITE)
        else: 
            self.class_breakdown_label.config(text="Nessun box presente", fg=self.FG_WHITE)
            

        # Aggiornamento Label Sovrapposizione
        if red_alert:
            self.overlap_status_label.config(text="🔴", fg='red') 
            self.status_label.config(text="⚠ Duplicati: due box di classi diverse hanno le stesse coordinate.", fg='red')
        elif orange_alert:
            self.overlap_status_label.config(text="🟠", fg='orange') 
            self.status_label.config(text="⚠ Sovrapposizione eccessiva (>80%) tra classi diverse.", fg='orange')
        else:
            self.overlap_status_label.config(text="🟢", fg='green') 
            
            if self.status_label.cget('fg') not in ('red', 'orange', 'blue'):
                if total_boxes > 0:
                    self.status_label.config(text="Tutti i box validi.", fg='green')
                else:
                    self.status_label.config(text="Pronto per creare un box. Premi 'n'", fg='white')
        
        self._update_current_box_info() 
        
        
    

    def _update_filename_color(self):
        """Verifica il save_count e aggiorna il colore: Giallo per vergine (0), Verde per salvato (>0)."""
        
        # Verifica solo se self.filename è disponibile
        if not hasattr(self, 'filename'):
             return

        save_count = self._get_current_save_count()
        
        if save_count == 0:
            # GIALLO: Vergine (mai salvato)
            self.image_label.config(fg='gold') 
        else:
            # VERDE: Salvato almeno una volta
            self.image_label.config(fg='lime green') 
            
        # Aggiunge il save_count al testo dell'etichetta (opzionale)
        current_text = self.image_label.cget('text')
        # Rimuove il vecchio conteggio se presente
        current_text = current_text.split(" [S:")[0]
        
        self.image_label.config(text=f"{current_text} [S:{save_count}]")
        

    
    def update_class_buttons(self):
        """Aggiorna i bottoni delle classi in un layout a 2 colonne e ricalcola l'area di scroll."""
        
        CLS_BTN_BG = '#4A6572'
        CLS_BTN_ACTIVE_BG = '#607D8B'
        
        for widget in self.class_button_frame.winfo_children():
            widget.destroy()

        NUM_COLUMNS = 2
        
        for i, cls in enumerate(self.classes):
            # *** MODIFICA: Aggiunge un indicatore visuale per la classe corrente ***
            is_current = (cls == self.current_class)
            btn_bg = 'gold' if is_current else CLS_BTN_BG
            btn_fg = self.BG_DARK if is_current else 'white'
            
            btn = tk.Button(self.class_button_frame, text=cls, 
                            command=lambda c=cls: self.set_current_class(c),
                            bg=btn_bg, fg=btn_fg, relief=tk.FLAT,
                            activebackground=CLS_BTN_ACTIVE_BG, activeforeground='white',
                            font=('Arial', 8, 'bold' if is_current else 'normal')) 
            
            row = i // NUM_COLUMNS
            col = i % NUM_COLUMNS
            
            btn.grid(row=row, column=col, sticky=tk.W + tk.E, padx=1, pady=1)

        self.class_button_frame.grid_columnconfigure(0, weight=1)
        self.class_button_frame.grid_columnconfigure(1, weight=1)
        
        self.class_button_frame.update_idletasks()
        self.class_button_frame.master.config(scrollregion=self.class_button_frame.master.bbox("all"))
        self.class_button_frame.bind('<Configure>', lambda e: self.class_button_frame.master.config(scrollregion=self.class_button_frame.master.bbox("all")))

    def _ocr_class_for_plate(self, plate_class):
        if plate_class.lower() == 'letta_plate':
            return 'OCR'
        if plate_class.lower().startswith('letta_plate'):
            return plate_class.replace('Letta_plate', 'OCR')
        return None

    
    def set_current_class(self, cls):
        self.current_class = cls
        
        self.update_class_buttons() # Aggiorna i bottoni per evidenziare la nuova classe
        
        if self.current_box != -1 and self.current_box < len(self.bboxes):
            old_cls = self.bboxes[self.current_box].get('class','')
            new_cls = cls
            
            # --- INIZIO LOGICA INTELLIGENTE OCR ---
            # Verifica se stiamo modificando un box di tipo Targa
            if str(old_cls).lower().startswith('letta_plate'):
                old_ocr_target = self._ocr_class_for_plate(old_cls)

                # CASO A: Stiamo rinominando da Targa X a Targa Y (es. Letta_plate -> Letta_plate_1)
                # Dobbiamo rinominare anche l'OCR associato per non perderlo
                if str(new_cls).lower().startswith('letta_plate'):
                    new_ocr_target = self._ocr_class_for_plate(new_cls)
                    
                    # Rinomina nei box visibili
                    for box in self.bboxes:
                        if box.get('class') == old_ocr_target:
                            box['class'] = new_ocr_target
                            
                    # Rinomina anche nella memoria OCR separata (se esiste)
                    if hasattr(self, 'loaded_ocr_boxes'):
                        for box in self.loaded_ocr_boxes:
                             if box.get('class') == old_ocr_target:
                                box['class'] = new_ocr_target

                # CASO B: Stiamo cambiando da Targa a NON-Targa (es. Letta_plate -> car)
                # L'OCR non serve più, lo rimuoviamo (la tua logica originale)
                else:
                    # Rimuovi dai box visibili (opzionale, ma consigliato per pulizia visiva immediata)
                    self.bboxes = [b for b in self.bboxes if b.get('class') != old_ocr_target]
                    
                    # Rimuovi dalla memoria OCR separata
                    if hasattr(self, 'loaded_ocr_boxes'):
                        self.loaded_ocr_boxes = [o for o in self.loaded_ocr_boxes if o.get('class','').lower() != old_ocr_target.lower()]
            # --- FINE LOGICA INTELLIGENTE OCR ---

            # ora assegna la nuova classe al box selezionato
            self._push_undo_state(f"Cambio classe → {cls}")   # 
            self.bboxes[self.current_box]['class'] = cls
            self._draw_bboxes()
            self._update_box_stats()
            self.status_label.config(text=f"Classe box {self.current_box+1} impostata su {cls}", fg='blue')
        else:
            self.status_label.config(text=f"Classe predefinita impostata su {cls}. Premi 'n' per un nuovo box.", fg='blue')
        
        self._update_current_box_info()
        
    # --- GESTIONE CACHE E FILTRI (INCOLLA QUESTO BLOCCO) ---
    def _rebuild_metadata_cache(self):
        """Legge tutti i JSON una volta sola per velocizzare i filtri."""
        # Se non ci sono immagini, esci
        if not hasattr(self, '_all_images') or not self._all_images: return

        self.metadata_cache = {}
        # Scorre tutti i file immagine trovati
        for img_name in self._all_images:
            json_path = self._json_path(img_name)
            classes_found = set()
            
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for box in data.get("boxes", []):
                            c = box.get("class", "")
                            if c: classes_found.add(str(c).lower())
                except Exception:
                    pass 
            
            self.metadata_cache[img_name] = classes_found
        
        self.cache_valid = True
        print(f"Cache rigenerata: {len(self.metadata_cache)} file indicizzati.")

    def image_has_class_fast(self, img_name, target_class):
        """Verifica se l'immagine ha la classe usando la memoria RAM (Veloce)."""
        if not self.cache_valid:
            self._rebuild_metadata_cache()
            
        # Se target_class è vuoto, accetta tutto
        if not target_class: return True

        # Controlla nella cache
        file_classes = self.metadata_cache.get(img_name, set())
        return target_class.lower() in file_classes
    # -------------------------------------------------------

    # --- LOGICA IMMAGINE (CARICAMENTO E DISEGNO) ---

    def load_image(self, event=None):
        """Carica l'immagine corrente e le annotazioni JSON."""
        if not self.images:
            return
            
        self.is_loading_image = True
    
        self.filename = self.images[self.index]
        self.image_path = os.path.join(self.folder, self.filename)
        display_filename = self._get_display_filename(self.filename) # Il conteggio [S:X] verrà aggiunto da _update_filename_color

        self.image_label.config(text=f"IMG {self.index + 1}/{len(self.images)}: {display_filename}")
        
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
        # reset stato OCR/selection temporaneo
        self.loaded_ocr_boxes = []
        self._unbind_plate_entry()  # rimuove eventuali binding residui della sidebar
        self.plate_var.set("")
        self.validate_plate_var.set(False)

        self.bboxes = self._load_boxes_from_json(self.filename)
        self.current_box = -1
        self._fit_image_to_canvas()
        self._update_box_stats()
        self._update_filename_color() # Aggiorna il colore in base al JSON
        self.status_label.config(text=f"Immagine caricata: {self.filename}", fg='white')
        self.canvas.focus_set()
        self._update_current_box_info() 
        
        # --- RESET DIRTY STATE (nuova immagine caricata) ---
        self.is_dirty = False
        self.is_loading_image = False

        # ----------------------------------------------------------------------
        # *** NUOVA LINEA: RILASCIO DEL BLOCCO DI NAVIGAZIONE (ULTIMA RIGA) ***
        # ----------------------------------------------------------------------
        self._set_navigation_lock(False)
        self._update_plate_entry_from_selection()


    def _fit_image_to_canvas(self):
        """Calcola il fattore di scala per adattare l'immagine alla tela."""
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

    def draw_box(self, box, selected=False, overlapped=False):
        """Disegna un singolo bounding box con etichetta e maniglie se selezionato.
           Se overlapped==True il bordo è 3x più spesso dello spessore normale."""
        
        # Ignora i box OCR che non hanno coordinate valide
        if box.get('class') == 'OCR' and (len(box.get('coords', [])) < 4 or all(c == 0 for c in box['coords'])):
            return

        x1_img, y1_img, x2_img, y2_img = box['coords']
        x1_img, x2_img = min(x1_img, x2_img), max(x1_img, x2_img)
        y1_img, y2_img = min(y1_img, y2_img), max(y1_img, y2_img)

        x1 = x1_img * self.scale + self.pan_x * self.scale
        y1 = y1_img * self.scale + self.pan_y * self.scale
        x2 = x2_img * self.scale + self.pan_x * self.scale
        y2 = y2_img * self.scale + self.pan_y * self.scale

        color = "yellow" if selected else CLASS_COLORS.get(box['class'].lower(), 'red')


        # Determina lo spessore: se overlapped -> 3x spessore normale (normale=2)
        normal_width = 2
        selected_width = 3
        if overlapped:
            width = normal_width * 3  # 6
        else:
            width = selected_width if selected else normal_width

        # Disegna il Rettangolo
        self.canvas.create_rectangle(x1, y1, x2, y2, 
                                     outline=color, 
                                     width=width, 
                                     tags="bbox")

        text = box.get('class', 'unknown')
        font_size = max(8, int(10 * self.scale))
        font = ('Arial', font_size, 'bold')

        # Posizionamento Etichetta
        text_w = len(text) * font_size * 0.6
        text_h = font_size + 4
        text_x = x1 + 2
        text_y = max(y1 - text_h - 2, 5) 
        
        # Sposta l'etichetta sotto se non c'è spazio sopra
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
            text_x, text_y, text=text, anchor=tk.NW, fill='white', font=font, tags=("label",)
        )
        
        # Maniglie di Ridimensionamento (solo se selezionato)
        if selected:
            s = 6
            for hx, hy in [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]:
                self.canvas.create_oval(hx - s, hy - s, hx + s, hy + s, 
                                        fill=color, outline="white", width=1, tags="handle")

    
    def _draw_bboxes(self):
        """Disegna i bounding box sulla tela, in base allo stato della checkbox ALL.
           Applica bordo spesso solo ai box presenti in self.overlapped_indices."""
        self.canvas.delete("bbox", "label", "handle", "label_bg")
        show_all = self.show_all_boxes_var.get()

        # Assicurati che overlapped_indices sia calcolato
        if not hasattr(self, 'overlapped_indices'):
            self.overlapped_indices, _, _ = self._compute_overlaps()

        if show_all:
            for i, box in enumerate(self.bboxes):
                if i != self.current_box:
                    is_overlapped = (i in self.overlapped_indices)
                    self.draw_box(box, selected=False, overlapped=is_overlapped)
        else:
            if self.current_box == -1 or self.current_box >= len(self.bboxes):
                return

        if self.current_box != -1 and self.current_box < len(self.bboxes):
            is_overlapped = (self.current_box in self.overlapped_indices)
            self.draw_box(self.bboxes[self.current_box], selected=True, overlapped=is_overlapped)

    def create_new_box_mode(self, event=None):  
        """Attiva la modalità di creazione di un nuovo bounding box."""
        
        # --- FIX: Ignora se l'utente sta scrivendo nel box ---
        if self.root.focus_get() == self.plate_entry:
            return
        # -----------------------------------------------------

        if self._is_editing_plate_entry():
            return "break"
            
        if not self.original_img: return
        
        self.current_box = -1
        self.dragging = False
        self.resizing = False
        self.creating_box = True
        self.canvas.config(cursor="cross")
        self.status_label.config(text=f"MODALITÀ CREAZIONE: Trascina per disegnare un box di classe '{self.current_class}'.", fg='gold')
        self._draw_bboxes() # Rimuove la selezione dai box esistenti
        self._update_current_box_info()
        
    def _select_next_box(self, event=None):
        """Seleziona il prossimo bounding box. (Usato dal tasto TAB)"""
        if self._is_editing_plate_entry():
            return "break"

        if not self.bboxes:
            self.current_box = -1
            self._draw_bboxes()
            self.status_label.config(text="Nessun box da selezionare.", fg='orange')
            self._update_current_box_info() 
            return

        self.creating_box = False
        # Se non c'era nessun box selezionato (-1), il prossimo è l'indice 0.
        if self.current_box == -1:
            self.current_box = 0
        else:
            # Cicla tra i box (compreso il ritorno al primo)
            self.current_box = (self.current_box + 1) % len(self.bboxes)

        self._draw_bboxes()
        self.status_label.config(text=f"Selezionato Box {self.current_box + 1}/{len(self.bboxes)}.", fg='blue')
        self._update_current_box_info() 
        self._update_plate_entry_from_selection()


    def _select_prev_box(self, event=None):
        """Seleziona il bounding box precedente. (Usato da SHIFT+TAB)"""
        if self._is_editing_plate_entry():
            return "break"
        if not self.bboxes:
            self.current_box = -1
            self._draw_bboxes()
            self.status_label.config(text="Nessun box da selezionare.", fg='orange')
            self._update_current_box_info() 
            return
            
        self.creating_box = False
        # Se non c'era nessun box selezionato (-1), il precedente è l'ultimo
        if self.current_box == -1:
            self.current_box = len(self.bboxes) - 1
        else:
            # Cicla tra i box (compreso il ritorno all'ultimo)
            self.current_box = (self.current_box - 1) % len(self.bboxes)

        self._draw_bboxes()
        self.status_label.config(text=f"Selezionato Box {self.current_box + 1}/{len(self.bboxes)}.", fg='blue')
        self._update_current_box_info() 
        self._update_plate_entry_from_selection()


    def delete_current_box(self):
        """Elimina il bounding box attualmente selezionato e l'OCR corrispondente se esistente."""
        
        if self._is_editing_plate_entry():
            return "break"
        if self.current_box != -1 and self.current_box < len(self.bboxes):

            # UNDO: salva lo stato PRIMA di qualsiasi modifica
            self._push_undo_state("Eliminazione box")

            # Ottieni la classe in modo sicuro
            class_name = self.bboxes[self.current_box].get('class', '')

            
            # 1. USA IL METODO CENTRALIZZATO
            # Se restituisce qualcosa, significa che 'class_name' è una targa e 'ocr_target' è il suo OCR
            ocr_target = self._ocr_class_for_plate(class_name)

            # 2. SE C'È UN TARGET OCR, PULISCI MEMORIA E UI
            if ocr_target:
                # Rimuovi dalla memoria OCR nascosta
                if hasattr(self, 'loaded_ocr_boxes'):
                    self.loaded_ocr_boxes = [o for o in self.loaded_ocr_boxes if o.get('class','').lower() != ocr_target.lower()]

                # Opzionale: Rimuovi anche dai box VISIBILI se presenti (es. se visualizzi tutto)
                # Nota: Questo previene che rimangano box OCR "orfani" sullo schermo
                self.bboxes = [b for b in self.bboxes if b.get('class') != ocr_target]

                # Reset UI (Disabilita campi input)
                self._unbind_plate_entry()
                self.plate_var.set("")
                self.validate_plate_var.set(False)
                if hasattr(self, 'plate_entry'):
                    self.plate_entry.config(state='disabled')
                if hasattr(self, 'validate_plate_check'):
                    self.validate_plate_check.config(state='disabled')

            # 3. RIMUOVI IL BOX PRINCIPALE
            # Ricalcoliamo l'indice del box corrente per sicurezza (se avessimo rimosso un OCR precedente dalla lista visibile)
            # Ma dato che cancelliamo per indice, dobbiamo essere certi che l'indice sia ancora quello.
            # Se la lista bboxes è cambiata sopra, l'indice self.current_box potrebbe puntare a un box diverso.
            # Per evitare bug complessi, cerchiamo di cancellare l'oggetto specifico se possibile, o gestiamo l'indice.
            
            # Poiché l'OCR solitamente è DOPO o altrove, nel 99% dei casi l'indice è ok.
            # Per sicurezza estrema verifichiamo bounds:
            if self.current_box < len(self.bboxes):
                del self.bboxes[self.current_box]

            # Aggiornamento indice selezione post-cancellazione
            if len(self.bboxes) == 0:
                self.current_box = -1
            elif self.current_box >= len(self.bboxes):
                self.current_box = len(self.bboxes) - 1

            self._draw_bboxes()
            self._update_box_stats()
            self.status_label.config(text=f"Box di classe '{class_name}' eliminato.", fg='red')
        else:
            self.status_label.config(text="Nessun box selezionato da eliminare.", fg='orange')

        self._update_current_box_info()
        # Aggiorna entry/associazione
        self._update_plate_entry_from_selection()
        
    def _snapshot_with_flash(self):
        flash_color = "#ffffff"
        original_bg = self.btn_snap.cget("bg")

        self.btn_snap.config(bg=flash_color)
        self.root.update_idletasks()

        def _restore_and_snap():
            self.btn_snap.config(bg=original_bg)
            self.save_snapshot()

        self.root.after(80, _restore_and_snap)

    
    def save_snapshot(self):
        try:
            print("=== SNAPSHOT START ===")

            # --------------------------------------------------
            # 1. CHECK BASE
            # --------------------------------------------------
            if not hasattr(self, "folder") or not hasattr(self, "filename"):
                print("ERRORE: folder o filename mancanti")
                return

            img_path = os.path.join(self.folder, self.filename)
            print("IMG PATH:", img_path)

            if not os.path.exists(img_path):
                print("ERRORE: immagine non trovata")
                return

            name_only = os.path.splitext(self.filename)[0]
            json_path = os.path.join(self.folder, name_only + ".json")

            # --------------------------------------------------
            # 2. LEGGI JSON (BOX + OCR)
            # --------------------------------------------------
            boxes_for_draw = []
            footer_strings = []

            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for item in data.get("boxes", []):

                    # --- BOX GEOMETRICI ---
                    if "coords" in item and isinstance(item["coords"], list):
                        boxes_for_draw.append(item)

                    # --- OCR ---
                    cls = str(item.get("class", ""))
                    val = item.get("value", [])

                    if cls.startswith("OCR") and isinstance(val, list) and val:
                        label = "TARGA" if cls == "OCR" else "TARGA" + cls.replace("OCR", "")
                        footer_strings.append(f"[{label}]: {val[0]}")

            print("BOX TROVATI:", len(boxes_for_draw))
            print("OCR TROVATI:", footer_strings)

            # --------------------------------------------------
            # 3. CARICA IMMAGINE
            # --------------------------------------------------
            img = Image.open(img_path).convert("RGB")
            draw = ImageDraw.Draw(img)

            # --------------------------------------------------
            # 4. DISEGNO BOUNDING BOX
            # --------------------------------------------------
            for b in boxes_for_draw:
                cls = str(b.get("class", "object"))
                raw_color = CLASS_COLORS.get(cls.lower(), "white")
                color = PIL_SAFE_COLORS.get(raw_color, (255, 255, 255))


                try:
                    x1, y1, x2, y2 = b["coords"]
                except Exception as e:
                    print("BOX MALFORMATO:", b, e)
                    continue

                x1, x2 = min(x1, x2), max(x1, x2)
                y1, y2 = min(y1, y2), max(y1, y2)

                draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
                draw.text((x1 + 4, y1 + 4), cls, fill=color)

            # --------------------------------------------------
            # 5. FOOTER OCR
            # --------------------------------------------------
            footer_text = " - ".join(footer_strings) if footer_strings else "Nessun OCR associato"

            try:
                font = ImageFont.truetype("arial.ttf", 24)
            except:
                font = ImageFont.load_default()

            w, h = img.size
            footer_h = 50

            final_img = Image.new("RGB", (w, h + footer_h), (0, 0, 0))
            final_img.paste(img, (0, 0))

            draw = ImageDraw.Draw(final_img)
            draw.text((20, h + 10), footer_text, fill="white", font=font)

            # --------------------------------------------------
            # 6. SALVATAGGIO
            # --------------------------------------------------
            if getattr(sys, "frozen", False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))

            out_dir = os.path.join(base_dir, "MarkedSnapshot")
            os.makedirs(out_dir, exist_ok=True)

            out_path = os.path.join(out_dir, f"{name_only}_marked.jpg")
            final_img.save(out_path, quality=95)

            print("SALVATO:", out_path)
            messagebox.showinfo("Snapshot", f"Snapshot salvato:\n{out_path}")

        except Exception as e:
            print("ECCEZIONE SNAPSHOT:", e)
            messagebox.showerror("Errore Snapshot", str(e))





    
    def _get_image_coords(self, event):
        """Converte le coordinate del canvas in coordinate originali dell'immagine (0-W, 0-H)."""
        
        # Coordinate del canvas relative all'immagine riscalata e pannata
        x_scaled = event.x - (self.pan_x * self.scale)
        y_scaled = event.y - (self.pan_y * self.scale)
        
        # Coordinate relative all'immagine originale (senza scala)
        if self.scale > 0:
            x_img = x_scaled / self.scale
            y_img = y_scaled / self.scale
        else:
            x_img = x_scaled
            y_img = y_scaled

        # Clamping per restare all'interno dei limiti dell'immagine
        x_img = max(0, min(self.img_width, round(x_img)))
        y_img = max(0, min(self.img_height, round(y_img)))
        
        return x_img, y_img
    
    def _canvas_to_image_coords(self, x, y):
        """Converte una singola coordinata canvas in coordinata immagine."""
        if self.scale > 0:
            x_img = (x - (self.pan_x * self.scale)) / self.scale
            y_img = (y - (self.pan_y * self.scale)) / self.scale
        else:
            x_img = (x - self.pan_x) 
            y_img = (y - self.pan_y)
            
        x_img = max(0, min(self.img_width, round(x_img)))
        y_img = max(0, min(self.img_height, round(y_img)))
        return x_img, y_img


    def _get_handle_info(self, event):
        """Controlla se il mouse è sopra una maniglia di ridimensionamento di un box selezionato."""
        
        if self.current_box == -1: return None
        
        x_canvas, y_canvas = event.x, event.y
        s = 6 # Dimensione delle maniglie
        
        box = self.bboxes[self.current_box]
        x1_img, y1_img, x2_img, y2_img = box['coords']

        # Converte le coordinate dell'immagine in coordinate del canvas
        def to_canvas(x, y):
            x_c = x * self.scale + self.pan_x * self.scale
            y_c = y * self.scale + self.pan_y * self.scale
            return x_c, y_c

        handles = {
            'nw': to_canvas(x1_img, y1_img),
            'ne': to_canvas(x2_img, y1_img),
            'se': to_canvas(x2_img, y2_img),
            'sw': to_canvas(x1_img, y2_img)
        }

        for handle_name, (hx, hy) in handles.items():
            if (hx - s <= x_canvas <= hx + s) and (hy - s <= y_canvas <= hy + s):
                return handle_name
        return None

    def _on_mouse_down(self, event):
        x_img, y_img = self._get_image_coords(event)
        
        if self.creating_box:
            # 1. Inizia a disegnare un nuovo box
            self.new_box_start = (x_img, y_img)
            self.new_box_end = (x_img, y_img) 
            self.current_box = len(self.bboxes) # Selezione del nuovo box fittizio
            self.dragging = True
            return

        # 2. Controlla se sta ridimensionando un box esistente
        handle = self._get_handle_info(event)
        if handle:
            self._push_undo_state("Resize box")   # 
            self.resizing = True
            self.resize_handle = handle
            self.dragging = True # dragging è vero sia per resize che per move
            self.canvas.config(cursor="hand2")
            return
        
        # 3. Controlla se sta spostando un box esistente o selezionando uno nuovo
        self.dragging = False
        self.resizing = False
        self.current_box = -1 
        
        # --- MODIFICA: SELEZIONE BASATA SULL'AREA PIÙ PICCOLA ---
        # Trova il box cliccato dando priorità al box più piccolo (quello più interno)
        clicked_box_index = -1
        min_area = float('inf') # Inizializza con area infinita

        # Conversione da coordinate immagine a coordinate relative del canvas
        x_rel, y_rel = self._get_image_coords(event)

        for i, box in enumerate(self.bboxes):
            # Ignora OCR senza coordinate
            if box.get('class') == 'OCR' and (len(box.get('coords', [])) < 4):
                continue

            x1, y1, x2, y2 = box['coords']
            x1, x2 = min(x1, x2), max(x1, x2)
            y1, y2 = min(y1, y2), max(y1, y2)
            
            # Check se il punto è all'interno del box (coordinate immagine)
            if (x1 <= x_rel <= x2) and (y1 <= y_rel <= y2):
                # Calcola l'area del box corrente
                area = (x2 - x1) * (y2 - y1)
                
                # Se questo box è più piccolo del precedente trovato, diventa il candidato migliore
                if area < min_area:
                    min_area = area
                    clicked_box_index = i
        # --------------------------------------------------------

        if clicked_box_index != -1:
            self._push_undo_state("Move box")   # 
            self.current_box = clicked_box_index
            self.drag_start_x_img, self.drag_start_y_img = x_rel, y_rel
            self.dragging = True
            self.canvas.config(cursor="fleur") # Simbolo di spostamento
        else:
            self.canvas.config(cursor="")
            
        self._draw_bboxes()
        self._update_current_box_info()
        

    def _on_mouse_move(self, event):
        x_img, y_img = self._get_image_coords(event)

        if self.creating_box:
            # Aggiorna l'end point per la creazione
            self.new_box_end = (x_img, y_img)
            
            # Disegna il box di anteprima
            x1, y1 = self.new_box_start
            x2, y2 = self.new_box_end
            
            # Converte in coordinate canvas
            x1_c, y1_c = self._canvas_to_canvas_coords(x1, y1)
            x2_c, y2_c = self._canvas_to_canvas_coords(x2, y2)
            
            self.canvas.delete("preview_box")
            self.canvas.create_rectangle(x1_c, y1_c, x2_c, y2_c, 
                                         outline='red', width=2, dash=(4, 4), tags="preview_box")
            
            self.status_label.config(text=f"Creando Box: Classe '{self.current_class}'. Premi 'n' per annullare.", fg='gold')

        elif self.dragging and self.current_box != -1:
            # 1. Ridimensionamento
            if self.resizing:
                box = self.bboxes[self.current_box]
                
                # I box sono memorizzati come x1, y1, x2, y2 (non necessariamente min/max)
                x1, y1, x2, y2 = box['coords']
                
                if self.resize_handle == 'nw':
                    x1, y1 = x_img, y_img
                elif self.resize_handle == 'ne':
                    x2, y1 = x_img, y_img
                elif self.resize_handle == 'se':
                    x2, y2 = x_img, y_img
                elif self.resize_handle == 'sw':
                    x1, y2 = x_img, y_img

                # Aggiorna le coordinate (mantenendo l'ordine x1, y1, x2, y2 che sarà normalizzato in draw_box)
                box['coords'] = [x1, y1, x2, y2]
            
            # 2. Spostamento
            elif not self.resizing:
                # Calcola la differenza di movimento (coordinate immagine)
                dx = x_img - self.drag_start_x_img
                dy = y_img - self.drag_start_y_img
                
                box = self.bboxes[self.current_box]
                x1, y1, x2, y2 = box['coords']
                
                # Applica il movimento e clamp per restare nell'immagine
                new_x1 = max(0, x1 + dx)
                new_y1 = max(0, y1 + dy)
                new_x2 = min(self.img_width, x2 + dx)
                new_y2 = min(self.img_height, y2 + dy)
                
                # Correggi se il clamping ha ristretto la dimensione (può succedere se si sposta troppo al bordo)
                if new_x2 - new_x1 != x2 - x1:
                    if new_x1 == 0: new_x2 = x2 - x1
                    elif new_x2 == self.img_width: new_x1 = self.img_width - (x2 - x1)

                if new_y2 - new_y1 != y2 - y1:
                    if new_y1 == 0: new_y2 = y2 - y1
                    elif new_y2 == self.img_height: new_y1 = self.img_height - (y2 - y1)
                
                box['coords'] = [new_x1, new_y1, new_x2, new_y2]

                # Aggiorna il punto di start per i movimenti successivi
                self.drag_start_x_img, self.drag_start_y_img = x_img, y_img
                
            self._draw_bboxes()
            self._update_current_box_info() 
        
        # Aggiorna il cursore se non sto trascinando/ridimensionando
        elif self.current_box != -1:
            handle = self._get_handle_info(event)
            if handle:
                self.canvas.config(cursor="sizing") # Cursore generico per ridimensionamento
            else:
                 self.canvas.config(cursor="fleur")
        else:
            self.canvas.config(cursor="")


    def _on_mouse_up(self, event):
        
        # 1. Finalizza la creazione di un box
        if self.creating_box:
            self.creating_box = False
            self.canvas.delete("preview_box")
            self.canvas.config(cursor="")

            if self.new_box_start and self.new_box_end:
                x1, y1 = self.new_box_start
                x2, y2 = self.new_box_end
                
                # Normalizzazione (assicura che x1 < x2 e y1 < y2)
                x_min, x_max = min(x1, x2), max(x1, x2)
                y_min, y_max = min(y1, y2), max(y1, y2)

                # Controllo dimensione minima (es. 5 pixel)
                if x_max - x_min > 5 and y_max - y_min > 5:
                    self._push_undo_state("Creazione box")   # 
                    new_box = {
                        'class': self.current_class,
                        'coords': [x_min, y_min, x_max, y_max]
                    }
                    self.bboxes.append(new_box)
                    self.current_box = len(self.bboxes) - 1 # Seleziona il box appena creato
                    self.status_label.config(text=f"Box di classe '{self.current_class}' creato.", fg='green')
                else:
                    self.current_box = -1
                    self.status_label.config(text="Creazione annullata: box troppo piccolo.", fg='orange')

        # 2. Finalizza lo spostamento/ridimensionamento
        self.dragging = False
        self.resizing = False
        self.resize_handle = None
        self.canvas.config(cursor="")

        self._draw_bboxes()
        self._update_box_stats()
        
        # Dopo ogni operazione sul box, si ricentra la selezione per il prossimo mouse_down
        if self.current_box != -1 and self.current_box < len(self.bboxes):
             x1, y1, x2, y2 = self.bboxes[self.current_box]['coords']
             self.drag_start_x_img = (x1 + x2) / 2 # Centro X del box
             self.drag_start_y_img = (y1 + y2) / 2 # Centro Y del box
        
        self._update_current_box_info() 
        self._update_plate_entry_from_selection()



    # --- GESTIONE IMMAGINE E NAVIGAZIONE ---
    
    def _canvas_to_canvas_coords(self, x_img, y_img):
        """Converte le coordinate immagine in coordinate canvas (con pan e scala)."""
        x_c = x_img * self.scale + self.pan_x * self.scale
        y_c = y_img * self.scale + self.pan_y * self.scale
        return x_c, y_c
        
    def _zoom(self, event):
        """Gestisce lo zoom con la rotella del mouse."""
        zoom_factor = 1.1 if (event.delta > 0 or event.num == 4) else 1/1.1
        
        # Limita lo zoom per evitare scale eccessive
        new_scale = self.scale * zoom_factor
        if 0.1 <= new_scale <= 10.0:
            self.scale = new_scale
            self._update_canvas_image()

    def _pan_start(self, event):
        """Inizia la traslazione (pan) dell'immagine."""
        self.pan_drag_start_x = event.x
        self.pan_drag_start_y = event.y
        self.pan_start_x = self.pan_x
        self.pan_start_y = self.pan_y
        self.panning = True
        self.canvas.config(cursor="fleur")

    def _pan_move(self, event):
        """Aggiorna la traslazione dell'immagine durante il pan."""
        if self.panning:
            # Calcola lo spostamento del mouse in coordinate del canvas
            dx_canvas = event.x - self.pan_drag_start_x
            dy_canvas = event.y - self.pan_drag_start_y
            
            # Lo spostamento del Pan deve essere proporzionale all'inverso della scala
            # (o più semplicemente, lo spostamento in pixel del pan deve compensare
            # lo spostamento del canvas)
            
            self.pan_x = self.pan_start_x + (dx_canvas / self.scale)
            self.pan_y = self.pan_start_y + (dy_canvas / self.scale)
            
            self._update_canvas_image()

    def _pan_end(self, event):
        """Termina la traslazione (pan) dell'immagine."""
        self.panning = False
        self.canvas.config(cursor="")
        
    def _zoom_double_click(self, event):
        """Zoom ×4 centrato sul punto cliccato."""
        if not self.original_img:
            return

        # Coordinate immagine corrispondenti al punto cliccato
        x_img, y_img = self._get_image_coords(event)

        # Imposta lo zoom (4×)
        self.scale *= 4.0

        # Calcolo pan per centrare il punto cliccato
        self.pan_x = -(x_img - (self.canvas.winfo_width() / (2 * self.scale)))
        self.pan_y = -(y_img - (self.canvas.winfo_height() / (2 * self.scale)))

        self._update_canvas_image()
        
    def _reset_zoom(self):
        """Ripristina la visualizzazione fit-to-canvas."""
        self._fit_image_to_canvas()


        
    def setup_bindings(self):
        """Imposta tutti i binding di Tkinter. CORREZIONE: Aggiunto Tab/Shift-Tab"""
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        
        # Binding per Zoom (Rotella del mouse)
        self.canvas.bind("<MouseWheel>", self._zoom) # Windows/Linux
        self.canvas.bind("<Button-4>", self._zoom)   # Linux scroll up
        self.canvas.bind("<Button-5>", self._zoom)   # Linux scroll down

        # Binding per Pan (Click centrale o tasto destro)
        self.canvas.bind("<ButtonPress-3>", self._pan_start)
        self.canvas.bind("<B3-Motion>", self._pan_move)
        self.canvas.bind("<ButtonRelease-3>", self._pan_end)
        
        # Binding da tastiera
        self.root.bind("<Control-s>", self._save_current_image)
        self.root.bind("<Control-S>", self._save_current_image)
        self.root.bind("<a>", self.prev_image)
        self.root.bind("<d>", self.next_image)
        self.root.bind("<Delete>", lambda e: self.delete_current_box())
        self.root.bind("<n>", lambda e: self.create_new_box_mode())
        self.root.bind("<l>", self.on_press_L)
        self.root.bind("<L>", self.on_press_L)   # se vuoi anche la maiuscola
        self.root.bind("<Control-f>", self.change_class_filter)
        self.root.bind("<Control-F>", self.change_class_filter)
        self.root.bind("<space>", self.next_filtered_box)
        self.root.bind("<Control-c>", self.copy_selected_box)
        self.root.bind("<Control-v>", self.paste_box)
        self.root.bind("<Control-z>", self.undo_last_action)
        self.root.bind("<Control-Z>", self.undo_last_action)
        self.root.bind("<Control-y>", self.redo_last_action)
        self.root.bind("<Control-Y>", self.redo_last_action)


        
        # --- NUOVI BINDING HELP/ABOUT ---
        self.root.bind("<h>", self.show_help)
        #self.root.bind("<H>", self.show_help)
        self.root.bind("<k>", self.show_about)
        #self.root.bind("<K>", self.show_about)
        
        # *** CORREZIONE: FUNZIONALITÀ TAB/SHIFT-TAB RIPRISTINATA ***
        self.root.bind("<Tab>", self._select_next_box)
        self.root.bind("<Shift-Tab>", self._select_prev_box)
        
        # Doppio click per zoomare ×4 centrato sul punto
        self.canvas.bind("<Double-1>", self._zoom_double_click)

        # Tasto ESC per ripristinare il fit-to-canvas
        self.root.bind("<Escape>", lambda e: self._reset_zoom())
        
        # --- TASTI FRECCIA PER NAVIGAZIONE AUDIO ---
        self.root.bind("<Right>", self.play_next_track)
        self.root.bind("<Left>", self.play_prev_track)
        self.root.bind("<Down>", self.pause_track)
        self.root.bind("<Up>", self.resume_track)

        
    def delete_current_image(self):
        """Elimina l'immagine corrente e il suo file JSON associato (se esistono) e passa alla successiva."""
        
        
        if not self.filename or self.deleting_image:
            return

        self.deleting_image = True # Blocca l'esecuzione doppia
        
        response = messagebox.askyesno(
            "Conferma Eliminazione",
            f"Sei sicuro di voler eliminare il file immagine '{self.filename}' e il suo file JSON associato (se esiste)? Questa azione è irreversibile."
        )

        if response:
            try:
                # 1. Elimina il JSON
                json_path = self._json_path(self.filename)
                if os.path.exists(json_path):
                    os.remove(json_path)
                    self.status_label.config(text=f"JSON eliminato: {os.path.basename(json_path)}", fg='red')

                # 2. Elimina l'Immagine
                image_path = self.image_path
                os.remove(image_path)
                self.status_label.config(text=f"Immagine eliminata: {self.filename}", fg='red')
                
                # 3. Rimuovi dalla lista e ricarica
                del self.images[self.index]
                
                # Passa all'immagine successiva o alla prima se eravamo all'ultima
                if self.index >= len(self.images) and len(self.images) > 0:
                    self.index = 0
                elif len(self.images) == 0:
                    messagebox.showinfo("Fine", "Tutte le immagini sono state eliminate.")
                    self.root.destroy()
                    return

                self.load_image()
            
            except Exception as e:
                messagebox.showerror("Errore Eliminazione", f"Impossibile eliminare i file: {e}")
        
        self.deleting_image = False # Sblocca
        
    def find_first_virgin_index(self):
        """Trova l'indice della prima immagine che non ha un file JSON o ha save_count == 0."""
        for i, filename in enumerate(self.images):
            json_path = self._json_path(filename)
            if not os.path.exists(json_path):
                return i # JSON non esiste (vergine)
            
            # Se esiste, controlla il save_count
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("save_count", 0) == 0:
                        return i # save_count è zero (vergine)
            except Exception:
                # JSON malformato, consideralo da rifare
                return i
                
        return 0 # Se tutte sono state salvate, ritorna la prima
        
    # ----------------------------------------------------------------------
    # *** NUOVI METODI: LOGICA DI NAVIGAZIONE SCHEDULATA ***
    # ----------------------------------------------------------------------
    
    def _proceed_to_next_image(self):
        """Logica per passare all'immagine successiva."""
        if self.index < len(self.images) - 1:
            self.index += 1
            self.load_image()
        elif self.index == len(self.images) - 1:
             self.status_label.config(text="Ultima immagine raggiunta.", fg='yellow')
             self._set_navigation_lock(False) # Rilascia il lock se non c'è stata navigazione

    def _proceed_to_prev_image(self):
        """Logica per passare all'immagine precedente."""
        if self.index > 0:
            self.index -= 1
            self.load_image()
        elif self.index == 0:
             self.status_label.config(text="Prima immagine raggiunta.", fg='yellow')
             self._set_navigation_lock(False) # Rilascia il lock se non c'è stata navigazione

    def next_image(self, event=None):
        """Passa all'immagine successiva dopo aver chiesto conferma di salvataggio (con scheduling)."""
        # --- FIX BUG FOCUS ---
        # Se stiamo scrivendo nel box OCR (focus sulla Entry) e l'evento è stato scatenato
        # dalla pressione di un tasto (es. 'd' o 'D'), IGNORIAMO il cambio immagine.
        # Lasciamo che sia la Entry a gestire il carattere.
        if self._is_editing_plate_entry() and event and event.keysym.lower() in ['d', 'a', 'right', 'left']:
            return
        # ---------------------

        # 1. BLOCCO (DEBOUNCING)
        if self.is_navigating:
            return 
        
        # OTTIMIZZAZIONE: Se siamo all'ultima immagine, non bloccare nulla, esci e basta.
        if self.index >= len(self.images) - 1:
            return 

        # 2. Imposta il flag (Cursore clessidra ON)
        self._set_navigation_lock(True)

        # Verifica conferma salvataggio
        if not self._ask_save_confirmation():
            # CORREZIONE QUI: Usa il metodo, non la variabile diretta!
            self._set_navigation_lock(False) # Cursore torna normale
            return 

        # 3. SCHEDULA la navigazione
        self.root.after(10, self._proceed_to_next_image)


    def prev_image(self, event=None):
        """Passa all'immagine precedente dopo aver chiesto conferma di salvataggio (con scheduling)."""
        # --- FIX BUG FOCUS ---
        if self._is_editing_plate_entry() and event and event.keysym.lower() in ['a', 'd', 'left', 'right']:
            return
        # ---------------------

        # 1. BLOCCO (DEBOUNCING)
        if self.is_navigating:
            return 
            
        # OTTIMIZZAZIONE: Se siamo alla prima immagine, esci subito.
        if self.index <= 0:
            return 

        # 2. Imposta il flag
        self._set_navigation_lock(True)

        if not self._ask_save_confirmation():
            # CORREZIONE QUI
            self._set_navigation_lock(False) # Rilascia lock e cursore correttamente
            return 
        
        # 3. SCHEDULA la navigazione
        self.root.after(10, self._proceed_to_prev_image)
            
    def _select_new_folder(self):
        """Permette all'utente di selezionare una nuova cartella immagini e ricarica l'interfaccia rispettando il filtro."""
        
        # Controllo salvataggio esistente
        if hasattr(self, 'filename'):
            if not self._ask_save_confirmation():
                return 

        new_folder = filedialog.askdirectory(title="Seleziona una nuova cartella immagini", initialdir=self.folder)
        if new_folder:
            self.folder = new_folder
            
            # 1. Carichiamo SEMPRE la lista completa di tutti i file nella cartella
            self._all_images = sorted([
                f for f in os.listdir(new_folder) 
                if f.lower().endswith(('.jpg', '.jpeg', '.png'))
            ])

            # Invalida la cache dei metadata: la cartella è cambiata,
            # ricostruiremo la cache quando serve (image_has_class_fast la rigenera).
            self.cache_valid = False
            self.metadata_cache = {}
            
            # 2. Applichiamo il filtro corrente (se esiste) alla nuova cartella
            if self.root._class_filter:
                self.images = [
                    img for img in self._all_images
                    if self.image_has_class_fast(img, self.root._class_filter)
                ]
            else:
                self.images = list(self._all_images)

            if not self.images:
                msg = f"Nessuna immagine trovata nella cartella."
                if self.root._class_filter:
                    msg = f"Nessuna immagine con classe '{self.root._class_filter}' trovata nella nuova cartella."
                messagebox.showinfo("Nessuna Immagine", msg)
                # Pulisci la visualizzazione
                self.canvas.delete("all")
                return
            
            # 3. Posizionamento e caricamento
            self.index = self.find_first_virgin_index()
            self.load_image()
            self.status_label.config(text=f"Nuova cartella caricata: {new_folder}", fg='green')


def main():
    # 1. Chiede all'utente la modalità di lavoro
    is_annotation_mode = ask_mode_selection()

    # 2. Crea la finestra principale
    root = tk.Tk()
    root.withdraw()  # nasconde finestra principale

    # classi NOTE (uguali a quelle del BoundingBoxEditor)
    classes = [
        'bicycle', 'bus', 'car', 'motorcycle', 'pickup',
        'truck', 'van', 'plate', 'person',
        'backpack', 'handbag', 'suitcase'
    ]

    # 1. CHIEDI FILTRO
    filter_class = ask_class_filter(root, classes)

    # 2. CHIEDI CARTELLA (Modificato per loop se vuota)
    while True:
        folder_path = filedialog.askdirectory(
            title="Seleziona la cartella delle immagini",
            parent=root
        )

        if not folder_path:
            root.destroy()
            return

        # Verifica se ci sono immagini valide nella cartella
        estensioni_valide = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')
        immagini = [f for f in os.listdir(folder_path) if f.lower().endswith(estensioni_valide)]
        
        if immagini:
            break # Trovate immagini, procedi
        else:
            messagebox.showwarning(
                "Cartella Vuota", 
                "La cartella selezionata non contiene immagini supportate.\nPer favore, selezionane una diversa."
            )

    root.deiconify()  # mostra finestra principale

    # 3. PASSA IL FILTRO ALL'EDITOR
    app = BoundingBoxEditor(root, folder_path, is_annotation_mode, filter_class)

    root.mainloop()



if __name__ == "__main__":

    main()