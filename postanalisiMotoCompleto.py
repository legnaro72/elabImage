# postanalisiMotoCompleto.py - VERSIONE DEFINITIVA CON METADATI IN FILE .JSON

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
    log_file = os.path.join(folder, "log_moto.txt")
    
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
    return logging.getLogger("postanalisimotp")

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
            
        # Nota: in questo scenario, 'base' è il nome del file senza estensione e senza BB
        return os.path.basename(base), parsed_boxes, plate_box, ext
        
    except Exception:
        return os.path.basename(base), [], None, ext

def save_updated_metadata_json(dest_path_base, boxes, plate_box=None):
    """Salva i BB aggiornati in un nuovo file .json affiancato nella cartella di destinazione."""
    metadata_path = dest_path_base + '.json'
    
    serializable_boxes = []
    for box in boxes:
        serializable_boxes.append({
            'class': box['class'],
            'coords': [int(c) for c in box['coords']]
        })
        
    data = {'boxes': serializable_boxes}
    if plate_box:
        # La targa dovrebbe essere già serializzabile
        data['plate'] = plate_box

    with open(metadata_path, 'w') as f:
        json.dump(data, f, indent=4)
        
    return metadata_path

# ----------------------------
# IOU and merging functions (OMESSE PER BREVITÀ - MANTENUTE NELLA VERSIONE ORIGINALE)
# ----------------------------

def calculate_iou(boxA, boxB):
    # Logica omessa...
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)

    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

    iou = interArea / float(boxAArea + boxBArea - interArea)
    return iou

def get_center(box):
    """Calcola il centro di un box [x1, y1, x2, y2]."""
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)

def is_center_close(boxA, boxB, max_distance_factor):
    """Verifica se i centri sono vicini."""
    centerA = get_center(boxA)
    centerB = get_center(boxB)
    
    dist_sq = (centerA[0] - centerB[0])**2 + (centerA[1] - centerB[1])**2
    
    diagA = math.sqrt((boxA[2] - boxA[0])**2 + (boxA[3] - boxA[1])**2)
    diagB = math.sqrt((boxB[2] - boxB[0])**2 + (boxB[3] - boxB[1])**2)
    max_diag = min(diagA, diagB)
    
    max_dist_sq = (max_diag * max_distance_factor)**2
    
    return dist_sq < max_dist_sq

def merge_boxes(boxes, iou_thresh, center_factor):
    """Fonde i bounding box per le classi specificate che si sovrappongono o sono vicini."""
    if not boxes:
        return [], 0
    
    CLASSES_TO_MERGE = ['motorcycle', 'bicycle'] # Nuove classi
    
    final_boxes = []
    merged_count = 0

    # 1. Isola e raggruppa gli altri box che non necessitano fusione
    other_boxes = [box for box in boxes if box['class'] not in CLASSES_TO_MERGE]
    
    # 2. Processa la fusione per ogni classe specificata
    for target_class in CLASSES_TO_MERGE:
        
        # Estrai solo i box della classe corrente
        current_class_boxes = [box for box in boxes if box['class'] == target_class]
        current_class_coords = [box['coords'] for box in current_class_boxes]
        
        if not current_class_coords:
            continue
            
        num_coords = len(current_class_coords)
        groups = {i: [i] for i in range(num_coords)}
        
        # Algoritmo di clustering (come prima)
        for i in range(num_coords):
            for j in range(i + 1, num_coords):
                boxA = current_class_coords[i]
                boxB = current_class_coords[j]
                
                iou = calculate_iou(boxA, boxB)
                center_close = is_center_close(boxA, boxB, center_factor)
                
                if iou > iou_thresh or center_close:
                    group_i = next(k for k, v in groups.items() if i in v)
                    group_j = next(k for k, v in groups.items() if j in v)

                    if group_i != group_j:
                        if len(groups[group_i]) < len(groups[group_j]):
                            groups[group_j].extend(groups.pop(group_i))
                        else:
                            groups[group_i].extend(groups.pop(group_j))

        # Crea i box finali fusi per questa classe
        for group in groups.values():
            if len(group) > 1:
                merged_count += len(group) - 1
            
            x1_min = min(current_class_coords[i][0] for i in group)
            y1_min = min(current_class_coords[i][1] for i in group)
            x2_max = max(current_class_coords[i][2] for i in group)
            y2_max = max(current_class_coords[i][3] for i in group)
            
            # *** PUNTO CRITICO MODIFICATO ***: Usa la classe originale (target_class)
            final_boxes.append({'class': target_class, 'coords': [x1_min, y1_min, x2_max, y2_max]})

    # 3. Combina i box fusi con gli altri box non toccati
    final_boxes += other_boxes
    
    return final_boxes, merged_count

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
def process_images_recursively_moto(source_folder, target_post_folder, class_name, iou_thresh=0.12, center_factor=0.25):
    """Esegue la fusione BB per le moto (usando e aggiornando il file .json affiancato)."""
    logger = setup_logging(source_folder)
    logger.info(f"--- Inizio Post-Analisi per {class_name} (con fusione, metadati in .json) ---")
    
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
                # Legge i metadati dal file .json affiancato
                base_name_clean, parsed_boxes, plate_box, ext = read_metadata_from_json(full_in_path)
                
                if not parsed_boxes:
                    logger.debug(f"File saltato (nessun BB valido nel .json): {fname}")
                    continue

                stats['processed_images'] += 1
                
                # Fonde i box delle moto
                merged_boxes, merged_count = merge_boxes(parsed_boxes, iou_thresh, center_factor)
                stats['merged_boxes'] += merged_count

                # Prepara i BB finali (moto fuse + altri oggetti + targa) per il nuovo .json
                final_boxes_for_metadata = merged_boxes[:]
                if plate_box:
                    final_boxes_for_metadata.append(plate_box)
                
                # Mantieni il nome file originale
                new_name = fname
                out_clean_path = os.path.join(dest_folder, new_name)
                out_clean_base = os.path.splitext(out_clean_path)[0]

                # 1. Copia l'immagine originale
                try:
                    shutil.copy2(full_in_path, out_clean_path)
                except Exception as e:
                    logger.error(f"Errore nel salvataggio dell'immagine {out_clean_path}: {str(e)}")
                    continue
                
                # 2. Salva il file .json con i metadati aggiornati
                save_updated_metadata_json(out_clean_base, final_boxes_for_metadata, plate_box)
                
                logger.info("Salvata copia (Immagine e JSON aggiornato): %s (fusi: %d)", new_name, merged_count)


            except Exception as e:
                logger.error(f"Errore imprevisto durante l'elaborazione di {fname}: {str(e)}")
                logger.error(traceback.format_exc())
                continue

    logger.info("Completato. Tot immagini: %d, fusioni: %d", stats['total_images'], stats['merged_boxes'])
    return stats

# ----------------------------
# Main (per esecuzione stand-alone)
# ----------------------------
# Nel blocco if __name__ == "__main__":
# Nel file postanalisiMotoCompleto.py

# ----------------------------
# Main (per esecuzione stand-alone)
# ----------------------------
if __name__ == "__main__":
    folder = choose_input_folder()
    if not folder:
        raise SystemExit("Nessuna cartella selezionata")
    
    post_analysis_root = os.path.join(folder, 'post_analisi_test')
    
    # Lista delle cartelle da processare con fusione
    folders_to_process = ['Moto', 'Bicycle']
    
    # Lista per raccogliere le statistiche di ogni esecuzione
    all_stats = [] 

    for class_name in folders_to_process:
        source_folder = os.path.join(folder, class_name)
        
        if os.path.exists(source_folder):
            try:
                stats = process_images_recursively_moto(
                    source_folder=source_folder, 
                    target_post_folder=post_analysis_root, 
                    class_name=class_name, # Passa 'Moto' o 'Bicycle'
                    iou_thresh=0.12, 
                    center_factor=0.25
                )
                # Aggiungi le statistiche del singolo run alla lista
                all_stats.append(stats) 
            except Exception as e:
                messagebox.showerror("Errore di Elaborazione", f"Si è verificato un errore critico per {class_name}: {str(e)}")
                logging.getLogger("postanalisimotp").error(f"Errore critico nel main per {class_name}: {str(e)}")
        else:
            messagebox.showinfo("Avviso", f"La cartella {source_folder} non esiste, saltata.")

    # Chiama la funzione di dialogo con la lista completa
    if all_stats:
        show_stats_dialog(all_stats)