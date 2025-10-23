# estraibindingbox-bag.py - VERSIONE DEFINITIVA CON METADATI IN FILE .JSON

import os
import shutil
import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageDraw, ImageOps 
from ultralytics import YOLO
import json # NUOVO

# Mappa le classi rilevate da YOLO alle cartelle di destinazione.
VEHICLE_CLASS_MAP = {
    'motorcycle': 'Moto',
    'bus': 'Bus',
    'truck': 'Truck',
    'bicycle': 'Bicycle',
    'backpack': 'Bag',
    'handbag': 'Bag',
    'suitcase': 'Bag',
    'car': 'Car', 
    'person': 'Bag', 
}

# ----------------------------
# Gestione Metadati (Sidecar .json)
# ----------------------------

def save_metadata(image_path, boxes, plate_box=None):
    """Salva i BB e le informazioni sulla targa in un file .json affiancato."""
    metadata_path = os.path.splitext(image_path)[0] + '.json'
    
    # Assicura che le coordinate siano tipi nativi JSON (list/int)
    serializable_boxes = []
    for box in boxes:
        serializable_boxes.append({
            'class': box['class'],
            'coords': [int(c) for c in box['coords']]
        })
        
    data = {'boxes': serializable_boxes}
    if plate_box:
        # Assicura che la targa sia serializzabile
        plate_box['coords'] = [int(c) for c in plate_box['coords']]
        data['plate'] = plate_box

    # Scrivi il file json nella stessa cartella dell'immagine originale
    with open(metadata_path, 'w') as f:
        json.dump(data, f, indent=4)
        
    return metadata_path


def process_images_in_folder():
    """
    Analizza, salva i BB in file .json affiancati e smista le immagini.
    Mantiene il nome file originale.
    """
    root = tk.Tk()
    root.withdraw()

    main_folder_path = filedialog.askdirectory(title="Seleziona la cartella principale con le immagini")
    
    if not main_folder_path:
        print("Nessuna cartella selezionata. Uscita.")
        return None, {}

    try:
        model = YOLO('yolov8n.pt') 
    except Exception as e:
        print(f"Errore nel caricamento del modello YOLO: {e}")
        return main_folder_path, {}

    vehicle_folders = {}
    for class_folder_name in set(VEHICLE_CLASS_MAP.values()):
        folder_path = os.path.join(main_folder_path, class_folder_name)
        os.makedirs(folder_path, exist_ok=True)
        vehicle_folders[class_folder_name.lower()] = folder_path

    no_vehicles_folder = os.path.join(main_folder_path, 'no_vehicles')
    os.makedirs(no_vehicles_folder, exist_ok=True)
    vehicle_folders['no_vehicles'] = no_vehicles_folder
    
    total_images = 0
    processed_images = 0

    print(f"Inizio analisi nella cartella: {main_folder_path}")

    for subdir, dirs, files in os.walk(main_folder_path):
        if any(subdir.endswith(d) for d in vehicle_folders.values()):
            continue
            
        for filename in files:
            if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                total_images += 1
                original_image_path = os.path.join(subdir, filename)
                
                try:
                    image = Image.open(original_image_path)
                    image = ImageOps.exif_transpose(image)
                    
                    results = model(image, verbose=False)
                    boxes = []
                    
                    for result in results:
                        for box in result.boxes:
                            class_id = int(box.cls[0].item())
                            class_name = model.names[class_id]
                            
                            if class_name in VEHICLE_CLASS_MAP:
                                x1, y1, x2, y2 = [int(x.item()) for x in box.xyxy[0]]
                                boxes.append({'class': class_name, 'coords': (x1, y1, x2, y2)})
                    
                    if not boxes:
                        # Non ci sono BB, copia l'immagine in no_vehicles e basta
                        shutil.copy2(original_image_path, os.path.join(no_vehicles_folder, filename))
                        print(f"    Immagine copiata in 'no_vehicles': {filename}")
                        continue
                        
                    processed_images += 1
                    
                    # NUOVO: Salva i metadati in un file .json temporaneo
                    temp_metadata_path = save_metadata(original_image_path, boxes) 
                    
                    # Determinazione della cartella di destinazione (usando il nome originale)
                    target_folder = None
                    detected_classes = [b['class'] for b in boxes]
                    
                    for yolo_class, target_name in VEHICLE_CLASS_MAP.items():
                        if yolo_class in detected_classes:
                            target_folder = vehicle_folders[target_name.lower()]
                            break
                            
                    if not target_folder:
                        target_folder = no_vehicles_folder
                        
                    # Mantieni il nome file originale
                    dest_image_path = os.path.join(target_folder, filename)
                    dest_metadata_path = os.path.splitext(dest_image_path)[0] + '.json'
                    
                    # Copia sia l'immagine che il file .json affiancato
                    shutil.copy2(original_image_path, dest_image_path)
                    shutil.copy2(temp_metadata_path, dest_metadata_path)
                    
                    # Rimuovi il file .json temporaneo
                    os.remove(temp_metadata_path)

                    print(f"    Immagine elaborata (BB in .json): {filename}")

                except Exception as e:
                    print(f"    Errore durante l'elaborazione di {original_image_path}: {e}")
                    # Assicurati di pulire il file json temporaneo in caso di errore
                    temp_json_path = os.path.splitext(original_image_path)[0] + '.json'
                    if os.path.exists(temp_json_path):
                        os.remove(temp_json_path)

    print(f"\nElaborazione completata. Totale immagini scansionate: {total_images}. Immagini processate: {processed_images}.")
    return main_folder_path, vehicle_folders

if __name__ == "__main__":
    main_folder_path, vehicle_folders = process_images_in_folder()
    
    if main_folder_path:
        print("\nCartelle create per la post-analisi:")
        for name, path in vehicle_folders.items():
            print(f"- {name.capitalize()}: {path}")