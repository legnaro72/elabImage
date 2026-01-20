import os
import shutil
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
import math

def organizza_dataset():
    # 1. Configurazione GUI (nasconde la finestra principale)
    root = tk.Tk()
    root.withdraw()

    print("--- Selezione Cartella ---")
    
    # 2. Chiede all'utente di scegliere la cartella
    cartella_input = filedialog.askdirectory(title="Seleziona la cartella contenente immagini e JSON")
    
    if not cartella_input:
        print("Nessuna cartella selezionata. Uscita.")
        return

    path_origine = Path(cartella_input)
    nome_cartella_origine = path_origine.name
    path_padre = path_origine.parent

    # Estensioni immagini supportate
    estensioni_img = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff'}

    # 3. Scansione e accoppiamento file
    files = list(path_origine.iterdir())
    coppie_valide = [] # Lista di tuple (path_immagine, path_json)

    # Trova tutte le immagini e cerca il relativo JSON
    for file in files:
        if file.suffix.lower() in estensioni_img:
            # Costruisce il nome del presunto json
            file_json = file.with_suffix('.json')
            
            # Se esiste il json corrispondente, aggiungiamo alla lista
            if file_json.exists():
                coppie_valide.append((file, file_json))

    totale_coppie = len(coppie_valide)
    print(f"Trovate {totale_coppie} coppie (Immagine + JSON).")

    # CORREZIONE QUI: usato 'totale_coppie' invece di 'total_coppie'
    if totale_coppie == 0:
        print("Nessuna coppia valida trovata. Nessuna operazione eseguita.")
        return

    # 4. Calcolo dei batch e spostamento
    dimensione_batch = 100
    numero_cartelle = math.ceil(totale_coppie / dimensione_batch)

    print(f"Verranno create {numero_cartelle} cartelle.")

    # Ordina i file per nome per mantenere un ordine logico
    coppie_valide.sort(key=lambda x: x[0].name)

    for i in range(numero_cartelle):
        # Definisce il nome della nuova cartella: Originale_1, Originale_2, etc.
        nuova_cartella_nome = f"{nome_cartella_origine}_{i+1}"
        nuova_cartella_path = path_padre / nuova_cartella_nome
        
        # Crea la cartella se non esiste
        nuova_cartella_path.mkdir(exist_ok=True)
        
        # Seleziona le coppie per questo batch
        start_index = i * dimensione_batch
        end_index = start_index + dimensione_batch
        batch = coppie_valide[start_index:end_index]
        
        print(f"Spostamento batch {i+1} ({len(batch)} coppie) in: {nuova_cartella_nome}...")
        
        for img, js in batch:
            shutil.move(str(img), str(nuova_cartella_path / img.name))
            shutil.move(str(js), str(nuova_cartella_path / js.name))

    print("--- Spostamento completato ---")

    # 5. Pulizia Cartella Originale
    # Controlliamo se la cartella è vuota (ignorando file di sistema come .DS_Store o Thumbs.db)
    rimanenti = [f for f in path_origine.iterdir() if f.name not in ['.DS_Store', 'Thumbs.db']]
    
    if not rimanenti:
        print(f"La cartella '{nome_cartella_origine}' è vuota. Cancellazione in corso...")
        try:
            shutil.rmtree(path_origine) # Rimuove la cartella e tutto il contenuto
            print("Cartella originale eliminata con successo.")
        except Exception as e:
            print(f"Errore durante l'eliminazione della cartella: {e}")
    else:
        print(f"ATTENZIONE: La cartella '{nome_cartella_origine}' NON è stata cancellata perché contiene ancora {len(rimanenti)} file (es. file orfani).")

if __name__ == "__main__":
    organizza_dataset()