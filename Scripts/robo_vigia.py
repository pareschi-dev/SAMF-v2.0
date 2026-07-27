import os
import sys
import time
import subprocess
import shutil

BASE_PATH = r"C:\Users\nerivaldo.junior\OneDrive - Ministério da Gestão e da Inovação dos Serv. Pub\SAMF"
INPUT_DIR = os.path.join(BASE_PATH, "Faturas_entrada")
PROCESSED_DIR = os.path.join(BASE_PATH, "Processados")
SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processar_fatura.py")

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

print("Robo Vigia SAMF iniciado.")
print(f"Monitorando: {INPUT_DIR}")
print(f"Processados: {PROCESSED_DIR}")
print("Pressione Ctrl+C para encerrar.")

while True:
    try:
        pdf_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith('.pdf')]
        if pdf_files:
            for pdf_name in sorted(pdf_files):
                pdf_path = os.path.join(INPUT_DIR, pdf_name)
                if not os.path.isfile(pdf_path):
                    continue

                print(f"Encontrado PDF: {pdf_name}")
                result = subprocess.run(
                    [sys.executable, SCRIPT_PATH, BASE_PATH, pdf_path],
                    capture_output=True,
                    text=True
                )
                print(f"Processamento: {pdf_name} -> returncode {result.returncode}")
                if result.stdout:
                    print(result.stdout.strip())
                if result.stderr:
                    print(result.stderr.strip())

                dest_name = pdf_name
                dest_path = os.path.join(PROCESSED_DIR, dest_name)
                counter = 1
                while os.path.exists(dest_path):
                    name, ext = os.path.splitext(pdf_name)
                    dest_name = f"{name}_{counter}{ext}"
                    dest_path = os.path.join(PROCESSED_DIR, dest_name)
                    counter += 1

                try:
                    shutil.move(pdf_path, dest_path)
                    print(f"Movido para Processados: {dest_name}")
                except Exception as move_err:
                    print(f"Erro ao mover {pdf_name}: {move_err}")
        else:
            print("Nenhum novo PDF encontrado.")
    except KeyboardInterrupt:
        print("Robo Vigia interrompido pelo usuário.")
        break
    except Exception as e:
        print(f"Erro no robo vigia: {e}")

    time.sleep(10)
