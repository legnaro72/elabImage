import os
import tkinter as tk
from tkinter import filedialog
from collections import Counter
import csv
import json

# --- CLASSI YOLO da cercare nei metadati JSON ---
YOLO_CLASSES = [
    "car", "motorcycle", "truck", "bus", "van", "pickup", # Aggiunti 'van' e 'pickup'
    "plate", "Letta_plate", "backpack", "handbag", "suitcase"
]


def scegli_cartella():
    """ Apre una finestra di dialogo per selezionare la cartella da analizzare. """
    root = tk.Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title="Seleziona la cartella da analizzare")
    return folder

def conta_occorrenze_json(cartella_base, classi_yolo):
    """
    Scansiona la cartella base alla ricerca di file JSON, legge le classi di annotazione
    usando la struttura 'boxes'/'class' e conta le occorrenze.
    """
    contatore = Counter()
    json_letti = 0
    # Prepara un set di classi target in lowercase per il confronto
    classi_valide = {c.lower() for c in classi_yolo} 

    for root, _, files in os.walk(cartella_base):
        for file in files:
            if file.lower().endswith(".json"):
                json_path = os.path.join(root, file)
                json_letti += 1

                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # 1. ESTRAZIONE CORRETTA: La lista di annotazioni è sotto la chiave 'boxes'
                    boxes = data.get("boxes", []) 

                    if not boxes:
                        # Non ci sono annotazioni 'boxes' in questo file, passiamo al prossimo.
                        continue

                    # 2. Iterazione e Conteggio
                    for annotation in boxes:
                        # ESTRAZIONE CORRETTA: La classe è sotto la chiave 'class'
                        classe = annotation.get("class") 
                        
                        if classe:
                            classe_lower = classe.lower().strip() # Aggiunto .strip() per sicurezza

                            # 3. Confronto con le classi YOLO target
                            if classe_lower in classi_valide:
                                contatore[classe_lower] += 1
                            # NOTE: Le classi come "OCR" non verranno contate perché non sono in YOLO_CLASSES

                except json.JSONDecodeError:
                    print(f"ATTENZIONE: Salto il file '{file}'. Errore di decodifica JSON.")
                except Exception as e:
                    print(f"ATTENZIONE: Errore generico nella lettura di '{file}': {e}")


    print(f"\nAnalisi completata. File JSON esaminati: {json_letti}")
    return contatore

def salva_csv(conteggi, output_path):
    """ Salva i risultati del conteggio in un file CSV. """
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["classe", "conteggio"])
        # Ordiniamo per chiave (classe) per un output CSV stabile
        for classe in sorted(conteggi.keys()): 
            writer.writerow([classe, conteggi[classe]])

def main():
    cartella = scegli_cartella()
    if not cartella:
        print("Nessuna cartella selezionata. Uscita.")
        return

    risultati = conta_occorrenze_json(cartella, YOLO_CLASSES)

    print("\n--- RISULTATI CONTEGGIO CLASSI YOLO ---")
    
    conteggio_totale_visibile = 0
    for classe in YOLO_CLASSES:
        cnt = risultati.get(classe.lower(), 0)
        print(f"{classe:15s}: {cnt}")
        conteggio_totale_visibile += cnt

    totale_effettivo = sum(risultati.values())
    
    print(f"\nTotale annotazioni rilevate per le classi target: {conteggio_totale_visibile}")
    if totale_effettivo != conteggio_totale_visibile:
        print(f"(Le classi non target, come 'OCR', sono state ignorate dal conteggio finale)")


    salva = input("\nVuoi salvare i risultati in CSV? (s/n): ").strip().lower()
    if salva == "s":
        out = os.path.join(cartella, "conteggio_classi_yolo_json_corretto.csv")
        # Passiamo solo i risultati che sono stati effettivamente contati
        salva_csv(risultati, out) 
        print(f"Salvato: {out}")

if __name__ == "__main__":
    main()