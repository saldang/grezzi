from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket
from fastapi.responses import HTMLResponse, FileResponse
from fastapi_socketio import SocketManager
from typing import List
import os
import subprocess
from pathlib import Path
from threading import Thread
import asyncio
from jinja2 import Environment, FileSystemLoader
import logging


# Creazione dell'applicazione FastAPI
app = FastAPI()
sio = SocketManager(app=app)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Definizione della cartella per gli upload
UPLOAD_FOLDER = "daPulire"
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)

OUTPUT_FOLDER = "puliti"
Path(OUTPUT_FOLDER).mkdir(exist_ok=True)

OUTPUT_CSV_FOLDER = "output_csv"
Path(OUTPUT_CSV_FOLDER).mkdir(exist_ok=True)

OUTPUT_RAW_FOLDER = "output_raw_csv"
Path(OUTPUT_RAW_FOLDER).mkdir(exist_ok=True)
env = Environment(loader=FileSystemLoader("templates"))


# Lista di connessioni WebSocket attive
active_connections = set()


async def notify_clients():
    """Invia un messaggio a tutti i client connessi per ricaricare la pagina"""
    for websocket in active_connections:
        try:
            await websocket.send_json({"event": "task_completed"})
        except:
            pass  # Ignora eventuali errori


def execute_script_in_background():
    """Esegue lo script e notifica i client WebSocket al termine"""
    try:
        script_path = os.path.join(os.getcwd(), "clean.py")
        if os.path.exists(script_path):
            subprocess.run(["python", script_path])  # Esegui lo script
        asyncio.run(notify_clients())  # Notifica i client WebSocket
    except Exception as e:
        print(f"Errore nell'esecuzione dello script: {str(e)}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Gestisce le connessioni WebSocket"""
    await websocket.accept()
    active_connections.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # Mantiene la connessione aperta
    except:
        pass
    finally:
        active_connections.remove(websocket)


@app.get("/", response_class=HTMLResponse)
async def get_root():
    template = env.get_template("index.html")
    return template.render()


@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    try:

        for file in files:
            file_path = os.path.join(UPLOAD_FOLDER, file.filename)
            logging.info(f"Saving file to {file_path}")

            with open(file_path, "wb") as f:
                while chunk := await file.read(1024 * 1024):
                    f.write(chunk)
            logging.info(f"File {file.filename} saved successfully")

        # Avvia lo script in background
        Thread(target=execute_script_in_background, daemon=True).start()
        # Redirect alla pagina che mostra l'elenco dei file
        logging.info("Redirecting to /list_files")
        return {"status": "processing", "redirect": "/list_files"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Errore durante il caricamento: {str(e)}"
        )
    finally:
        for file in files:
            await file.close()


@app.get("/list_files", response_class=HTMLResponse)
async def list_files():
    try:
        files = [
            f
            for f in os.listdir(OUTPUT_FOLDER)
            if os.path.isfile(os.path.join(OUTPUT_FOLDER, f))
        ]
        if not files:
            template = env.get_template("list_files.html")
            return template.render(files=None)

        template = env.get_template("list_files.html")
        return template.render(files=files)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Errore durante la lettura dei file: {str(e)}"
        )


@app.get("/download/{filename}", response_class=FileResponse)
async def download_file(filename: str):
    file_path = os.path.join(OUTPUT_FOLDER, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File non trovato")

    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/clear_puliti")
async def clear_puliti():
    try:
        for filename in os.listdir(OUTPUT_FOLDER):
            file_path = os.path.join(OUTPUT_FOLDER, filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)
        logging.info("Output folder cleared successfully")
        return {"status": "success", "message": "Output folder cleared successfully"}
    except Exception as e:
        logging.error(f"Error clearing output folder: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante la pulizia della cartella: {str(e)}",
        )


@app.post("/clear_output")
async def clear_output():
    try:
        for filename in os.listdir(OUTPUT_CSV_FOLDER):
            file_path = os.path.join(OUTPUT_CSV_FOLDER, filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)
        for filename in os.listdir(OUTPUT_RAW_FOLDER):
            file_path = os.path.join(OUTPUT_RAW_FOLDER, filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)
        logging.info("Output folder cleared successfully")
        return {"status": "success", "message": "Output folder cleared successfully"}
    except Exception as e:
        logging.error(f"Error clearing output folder: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante la pulizia della cartella: {str(e)}",
        )
