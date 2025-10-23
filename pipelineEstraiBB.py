# pipelineEstraiBB.py - VERSIONE DEFINITIVA SENZA SALVATAGGIO IMMAGINI MARKED

import os
import sys
import traceback

# Importa le funzioni dagli script, assumendo che siano nello stesso percorso
try:
    from estraibindingbox import process_images_in_folder 
    from postanalisiMotoCompleto import process_images_recursively_moto, show_stats_dialog
    from postanalisiAltroCompleto import process_images_recursively_altro
except ImportError as e:
    print(f"Errore di importazione: Assicurati che 'estraibindingbox.py', 'postanalisiMotoCompleto.py' e 'postanalisiAltroCompleto.py' siano nella stessa directory.")
    print(f"Dettagli: {e}")
    sys.exit(1)


def run_full_pipeline():
    """
    Esegue la pipeline completa (NON salva immagini annotate).
    """
    
    # --- FASE 1: Rilevamento Veicoli/Oggetti e Smistamento ---
    print("--- FASE 1: Rilevamento Veicoli/Oggetti e Smistamento ---")
    
    try:
        # Chiamata senza il parametro save_marked_images
        main_folder, vehicle_folders = process_images_in_folder()
    except Exception as e:
        print(f"Errore durante la Fase 1: {e}")
        traceback.print_exc()
        return
    
    if not main_folder:
        print("Pipeline interrotta: Nessuna cartella selezionata o errore nella Fase 1.")
        return

    # --- Creazione Cartella Post-Analisi Principale ---
    target_post_analysis_root = os.path.join(main_folder, "post_analisi")
    os.makedirs(target_post_analysis_root, exist_ok=True)
    print(f"\nCreata cartella radice post-analisi: {target_post_analysis_root}")

    stats_moto = None
    stats_altro_final = {'total_images': 0, 'processed_images': 0, 'merged_boxes': 0, 'output_folder': target_post_analysis_root}

    # --- FASE 2: Post-Analisi Moto (con fusione BB) ---
    print("\n--- FASE 2: Post-Analisi Moto (con fusione BB) ---")
    moto_folder = vehicle_folders.get('motorcycle') 
    
    if moto_folder and os.path.exists(moto_folder):
        try:
            print(f"Elaborazione: Moto")
            stats_moto = process_images_recursively_moto(
                source_folder=moto_folder, 
                target_post_folder=target_post_analysis_root, 
                class_name='Moto', 
                # Rimosso: save_marked_images
                iou_thresh=0.12, 
                center_factor=0.25
            )
            # Aggiorna le statistiche totali per la fase 2
            stats_altro_final['total_images'] += stats_moto['total_images']
            stats_altro_final['processed_images'] += stats_moto['processed_images']
            stats_altro_final['merged_boxes'] += stats_moto['merged_boxes']
        except Exception as e:
            print(f"Errore durante la Fase 2 (Moto): {e}")
            traceback.print_exc()
            stats_moto = None
    else:
        print("Cartella 'Moto' non trovata o vuota. Saltata elaborazione post-analisi Moto.")


    # --- FASE 3: Post-Analisi Altri Veicoli/Oggetti (senza fusione BB) ---
    print("\n--- FASE 3: Post-Analisi Altri Veicoli/Oggetti (senza fusione BB) ---")
    
    other_classes_to_process = {k: v for k, v in vehicle_folders.items() if k not in ['motorcycle', 'no_vehicles']}
    
    for class_key, source_folder in other_classes_to_process.items():
        class_name_for_output = os.path.basename(source_folder)
        
        if source_folder and os.path.exists(source_folder):
            try:
                print(f"Elaborazione: {class_name_for_output}")
                stats_current = process_images_recursively_altro(
                    source_folder=source_folder,
                    target_post_folder=target_post_analysis_root,
                    class_name=class_name_for_output,
                    # Rimosso: save_marked_images
                    iou_thresh=0.12, 
                    center_factor=0.25
                )
                
                # Aggiorna le statistiche totali per la fase 3
                stats_altro_final['total_images'] += stats_current['total_images']
                stats_altro_final['processed_images'] += stats_current['processed_images']
                
            except Exception as e:
                print(f"Errore durante la Fase 3 ({class_name_for_output}): {e}")
                traceback.print_exc()
        else:
            print(f"Cartella '{class_key}' non trovata o vuota. Saltata elaborazione.")
            
            
    print("\n--- Pipeline Completata ---\n")
    
    # --- Statistiche Finali ---
    total_images_all = stats_altro_final['total_images']
    total_processed_all = stats_altro_final['processed_images']
    total_merged_boxes = stats_altro_final['merged_boxes']

    if total_images_all > 0:
        final_stats = {
            'total_images': total_images_all,
            'processed_images': total_processed_all,
            'merged_boxes': total_merged_boxes,
            'output_folder': target_post_analysis_root 
        }
        
        print(f"Riassunto Generale:")
        print(f"Immagini totali scansionate: {final_stats['total_images']}")
        print(f"Immagini processate (con BB validi): {final_stats['processed_images']}")
        print(f"BB di moto fusi: {final_stats['merged_boxes']}")
        print(f"Output salvato in: {final_stats['output_folder']}")
        
        if 'show_stats_dialog' in globals():
            show_stats_dialog(final_stats)
    else:
        print("Nessuna immagine elaborata in nessuna delle fasi.")

if __name__ == "__main__":
    run_full_pipeline()