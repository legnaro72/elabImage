# postanalisiAltroCompleto.py - VERSIONE DEFINITIVA CON METADATI IN FILE .JSON

import os
import re
import shutil
import logging
import traceback
from datetime import datetime
from tkinter import Tk, filedialog, messagebox
from PIL import Image, ImageDraw
import tkinter as tk
from tkinter import ttk
import math
import json # Importato per la gestione del JSON

# ----------------------------
# Logging Setup
# ----------------------------
def setup_logging(folder):
    """Configura il logging su file e console."""
    log_file = os.path.join(folder, "log_altro.txt")
    
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='a'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("postanalisialtro")

# ----------------------------
# Metadati Sidecar .json
# ----------------------------

def read_metadata_from_json(filepath):
    """Legge BB e targa da un file .json affiancato."""
    base, ext = os.path.splitext(filepath)
    metadata_path = base + '.json'
    
    if not os.path.exists(metadata_path):
        return base, [], None, ext # Non ha metadati

    try:
        with open(metadata_path, 'r') as f:
            data = json.load(f)
            
        parsed_boxes = []
        for box in data.get('boxes', []):
            box['coords'] = [int(c) for c in box['coords']] 
            parsed_boxes.append(box)
            
        plate_box = data.get('plate')
        if plate_box:
            plate_box['coords'] = [int(c) for c in plate_box['coords']]
            
        return os.path.basename(base), parsed_boxes, plate_box, ext
        
    except Exception:
        return os.path.basename(base), [], None, ext

# ----------------------------
# UI Helper functions (OMESSE PER BREVITÀ - MANTENUTE NELLA VERSIONE ORIGINALE)
# ----------------------------
def choose_input_folder():
    root = Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title="Seleziona la cartella da analizzare")
    return folder

def show_stats_dialog(stats_data):
    """
    Visualizza una finestra di dialogo con le statistiche finali.
    Accetta un singolo dizionario di statistiche o una lista di dizionari.
    """
    
    # --- Passo 1: Normalizzazione dell'Input (FIX per il TypeError) ---
    # Se riceve un singolo dizionario (vecchio formato), lo avvolge in una lista.
    if isinstance(stats_data, dict):
        stats_list = [stats_data]
    elif isinstance(stats_data, list):
        stats_list = stats_data
    else:
        # Evita crash se l'input è inaspettato (es. None)
        return 

    root = tk.Tk()
    root.title("Statistiche Elaborazione Post-Analisi")
    
    main_frame = ttk.Frame(root, padding="10")
    main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    
    ttk.Label(main_frame, text="Risultati Post-Analisi (Fusioni)", font=("Arial", 14, "bold")).grid(row=0, column=0, columnspan=2, pady=10)
    
    row_offset = 1
    
    # --- Passo 2: Iterazione e Visualizzazione Separata ---
    for stats in stats_list:
        # Assicura che l'elemento sia un dizionario valido prima di accedervi
        if not isinstance(stats, dict):
            continue 
            
        # Determina il nome della classe per il titolo del riquadro
        class_name = os.path.basename(stats.get('output_folder', 'Sconosciuta'))

        # Crea un riquadro separato (LabelFrame) per le statistiche di questa classe
        frame = ttk.LabelFrame(main_frame, text=f"Statistiche: {class_name}", padding="10")
        frame.grid(row=row_offset, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        merged_count = stats.get('merged_boxes', 0)
        
        row_idx = 0
        ttk.Label(frame, text="Cartella di Output:").grid(row=row_idx, column=0, sticky=tk.W)
        ttk.Label(frame, text=class_name).grid(row=row_idx, column=1, sticky=tk.W)
        
        row_idx += 1
        ttk.Label(frame, text="Immagini totali scansionate:").grid(row=row_idx, column=0, sticky=tk.W)
        ttk.Label(frame, text=stats['total_images']).grid(row=row_idx, column=1, sticky=tk.W)
        
        row_idx += 1
        ttk.Label(frame, text="Immagini processate (con BB):").grid(row=row_idx, column=0, sticky=tk.W)
        ttk.Label(frame, text=stats['processed_images']).grid(row=row_idx, column=1, sticky=tk.W)
        
        row_idx += 1
        # Mostra i BB fusi solo se merged_boxes è maggiore di 0 (rilevante per Moto/Bicycle)
        if merged_count > 0 or class_name in ['Moto', 'Bicycle']: 
            ttk.Label(frame, text="BB fusi:").grid(row=row_idx, column=0, sticky=tk.W)
            ttk.Label(frame, text=merged_count).grid(row=row_idx, column=1, sticky=tk.W)
        
        row_offset += 1 # Prepara la riga per il prossimo LabelFrame
    
    # Bottone OK alla fine
    ttk.Button(main_frame, text="OK", command=root.destroy).grid(row=row_offset + 1, column=0, columnspan=2, pady=10)
    root.mainloop()


# ----------------------------
# Main processing function
# ----------------------------
def process_images_recursively_altro(source_folder, target_post_folder, class_name, iou_thresh=0.12, center_factor=0.25):
    """Copia le immagini e i loro file .json affiancati nella cartella di output (senza fusione)."""
    logger = setup_logging(source_folder)
    logger.info(f"--- Inizio Post-Analisi per {class_name} (metadati in .json) ---")
    
    dest_folder = os.path.join(target_post_folder, class_name)
    if not os.path.exists(dest_folder):
        os.makedirs(dest_folder)
        logger.info("Creata cartella di output: %s", dest_folder)
        
    stats = {'total_images': 0, 'processed_images': 0, 'merged_boxes': 0, 'output_folder': dest_folder} 

    for subdir, dirs, files in os.walk(source_folder):
        if subdir == dest_folder:
            continue
            
        for fname in files:
            full_in_path = os.path.join(subdir, fname)
            
            if not fname.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue

            # Assicurati di non processare due volte il JSON
            if fname.lower().endswith('.json'):
                continue

            stats['total_images'] += 1
            
            try:
                # Legge i metadati per verificare se il file è da processare
                base_name_clean, parsed_boxes, plate_box, ext = read_metadata_from_json(full_in_path)
                
                # Se non ha BB, non lo contiamo come processato in post-analisi (dovrebbe essere in no_vehicles)
                if not parsed_boxes:
                    logger.debug(f"File saltato (nessun BB valido nel .json): {fname}")
                    continue

                stats['processed_images'] += 1
                
                # Mantieni il nome file originale
                new_name = fname
                out_clean_path = os.path.join(dest_folder, new_name)
                
                # 1. Copia l'immagine
                try:
                    shutil.copy2(full_in_path, out_clean_path)
                except Exception as e:
                    logger.error(f"Errore nel salvataggio dell'immagine {out_clean_path}: {str(e)}")
                    continue
                
                # 2. Copia il file .json affiancato
                in_json_path = os.path.splitext(full_in_path)[0] + '.json'
                out_json_path = os.path.splitext(out_clean_path)[0] + '.json'
                
                if os.path.exists(in_json_path):
                    shutil.copy2(in_json_path, out_json_path)
                    logger.info("Salvata copia (Immagine e JSON): %s", new_name)
                else:
                    # Questo caso non dovrebbe succedere se la FASE 1 ha funzionato correttamente
                    logger.warning("Immagine %s trovata senza il file .json corrispondente.", fname)

            except Exception as e:
                logger.error(f"Errore imprevisto durante l'elaborazione di {fname}: {str(e)}")
                logger.error(traceback.format_exc())
                continue

    logger.info("Completato. Tot immagini: %d, processate: %d", stats['total_images'], stats['processed_images'])
    return stats

# ----------------------------
# Main (per esecuzione stand-alone)
# ----------------------------
# ----------------------------
# Main (per esecuzione stand-alone)
# ----------------------------
if __name__ == "__main__":
    folder = choose_input_folder()
    if not folder:
        raise SystemExit("Nessuna cartella selezionata")
        
    post_analysis_root = os.path.join(folder, 'post_analisi_test')
    
    # MODIFICA: La lista contiene SOLO le classi che NON richiedono la fusione
    # (Bicycle viene processata da 'postanalisiMotoCompleto.py').
    folders_to_process = ['Car'] 
    
    all_stats = []

    for class_name in folders_to_process:
        source_folder = os.path.join(folder, class_name)
        
        if os.path.exists(source_folder):
            try:
                print(f"Inizio elaborazione per {class_name}...")
                stats = process_images_recursively_altro(
                    source_folder=source_folder, 
                    target_post_folder=post_analysis_root, 
                    class_name=class_name, # Sarà 'Car'
                    iou_thresh=0.12, 
                    center_factor=0.25
                )
                all_stats.append(stats)
            except Exception as e:
                messagebox.showerror("Errore di Elaborazione", f"Si è verificato un errore critico per {class_name}: {str(e)}")
                logging.getLogger("postanalisialtro").error(f"Errore critico nel main per {class_name}: {str(e)}")
        else:
            print(f"ATTENZIONE: La cartella {source_folder} non esiste. Saltata.")

    if all_stats:
        show_stats_dialog(all_stats[-1]) 
    else:
        messagebox.showinfo("Avviso", "Nessuna cartella valida trovata per l'elaborazione.")