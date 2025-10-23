import os
import re
import json
from tkinter import Tk, filedialog
from datetime import datetime

def scegli_cartella():
    """Apre una finestra di dialogo per selezionare la directory contenente i file."""
    root = Tk()
    root.withdraw()
    cartella = filedialog.askdirectory(title="Seleziona la cartella contenente i file JSON da aggiornare")
    return cartella

def estrai_dati(nome_file_base):
    """
    Estrae targa (dall'indice 2) e coordinate (dal blocco X###Y###W###H###) dal nome base del file (senza estensione).
    Formato: [IP]_[data]_[TARGA]_[Normal/Letta_plate]_X###Y###W###H###...
    Restituisce (targa, x1, y_max, x2, y_min) oppure None se non valido.
    """
    try:
        # 1. Estrai la targa (indice 2)
        parts = nome_file_base.split('_')
        # Il nome del file deve avere almeno tre parti
        if len(parts) < 3:
            return None 
        targa = parts[2]
        
        # 2. Estrai le coordinate X###Y###W###H###
        # Utilizza la regex per trovare le 4 cifre numeriche
        coord_match = re.search(r"X(\d+)Y(\d+)W(\d+)H(\d+)", nome_file_base)
        
        if coord_match:
            # X: x1 (bordo sinistro), Y: y1 (bordo superiore = y_min), W: width, H: height
            x1, y1_min, w, h = map(int, coord_match.groups()) # Rinomina la variabile Y in y1_min
            
            # Calcola le coordinate del bounding box nel formato richiesto: [x1, y_max, x2, y_min]
            
            # x2 = x_destra
            x2 = x1 + w 
            
            # y_max = y_inferiore (y_min + height)
            y_max = y1_min + h # Modifica: y_max = y_min + h
            
            # y_min = y_superiore (il valore Y estratto)
            y_min = y1_min # Modifica: y_min è il valore Y estratto (y1_min)
            
            # L'output è: targa, x1, y_max, x2, y_min (ordine per 'coords' nel JSON)
            return targa, x1, y_max, x2, y_min
        
        return None 

    except Exception:
        return None

def update_metadata_json(cartella):
    """
    Itera solo sui file JSON, estrae i dati dal loro nome e aggiorna il loro contenuto.
    """
    log_path = os.path.join(cartella, "log_update_targhe_json.txt")
    
    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"LOG AGGIORNAMENTO JSON METADATI TARGA - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"Cartella analizzata: {cartella}\n\n")

        processed_count = 0
        total_json_found = 0
        
        for nome in os.listdir(cartella):
            
            # --- NUOVA STRATEGIA: Lavora solo sui file JSON ---
            if not nome.lower().endswith('.json'):
                continue
                
            percorso_json = os.path.join(cartella, nome)
            if not os.path.isfile(percorso_json):
                continue

            base, _ = os.path.splitext(nome) # base è il nome file senza .json
            
            total_json_found += 1
            log.write(f"  Analizzo file JSON: {nome}\n") 
            
            # 1. Estrazione dati dal NOME JSON (base)
            dati = estrai_dati(base)

            if not dati:
                msg = f"⚠️  File JSON saltato (nome file non parsabile): {nome}"
                log.write(msg + "\n")
                continue

            # L'ordine è: targa, x1, y_max, x2, y_min
            targa, x1, y_max, x2, y_min = dati
            
            # 2. Lettura JSON esistente
            dati_json = {}
            msg_read = ""
            try:
                with open(percorso_json, "r", encoding="utf-8") as f:
                    dati_json = json.load(f)
                msg_read = f"   (JSON esistente letto)"
            except Exception as e:
                msg = f"❌  Errore lettura/corruzione JSON per {nome}: {str(e)}. Uso struttura base."
                log.write(msg + "\n")
                dati_json = {}
            
            # 3. Assicura che 'boxes' sia una lista e pulisci i vecchi dati targa/OCR
            if 'boxes' not in dati_json or not isinstance(dati_json['boxes'], list):
                dati_json['boxes'] = []
            
            # Rimuovi i precedenti box di targa/OCR se presenti
            dati_json['boxes'] = [
                box for box in dati_json['boxes'] 
                if box.get('class') not in ('Letta_plate', 'OCR')
            ]
            
            # 4. Preparazione dei nuovi metadati nel formato e ordine richiesto
            new_plate_box = {
                "class": "Letta_plate",
                "coords": [x1, y_max, x2, y_min] # Rispetta l'ordine [x1, y_max, x2, y_min]
            }
            
            new_ocr_value = {
                "class": "OCR",
                "value": [targa] # Formato richiesto [TARGA]
            }
            
            # 5. Aggiunta dei nuovi dati alla lista 'boxes'
            dati_json['boxes'].append(new_plate_box)
            dati_json['boxes'].append(new_ocr_value)
            
            # 6. Salvataggio JSON aggiornato
            try:
                with open(percorso_json, "w", encoding="utf-8") as f:
                    json.dump(dati_json, f, indent=4)
                
                msg = f"✅  Metadati targa/OCR ({targa}) integrati in: {nome}. {msg_read}"
                print(msg)
                log.write(msg + "\n")
                processed_count += 1

            except Exception as e:
                msg = f"❌  Errore nel salvataggio del JSON aggiornato per {nome}: {str(e)}"
                print(msg)
                log.write(msg + "\n")


        print(f"\nOperazione completata.")
        print(f"File JSON totali trovati: {total_json_found}. File JSON aggiornati con successo: {processed_count}")
        print(f"Log salvato in: {log_path}")
        log.write(f"\nOperazione completata. File JSON totali trovati: {total_json_found}. File JSON aggiornati con successo: {processed_count}\n")

if __name__ == "__main__":
    cartella = scegli_cartella()
    if cartella:
        update_metadata_json(cartella)
    else:
        print("Nessuna cartella selezionata. Operazione annullata.")