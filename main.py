from datetime import datetime
from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, Form, status
from fastapi import Request, Depends
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi_socketio import SocketManager
from typing import List
import os
from pathlib import Path
from threading import Thread
import asyncio
from jinja2 import Environment, FileSystemLoader
import logging
from .db import get_bases, get_all_tables, create_table
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from passlib.hash import bcrypt
from sqlalchemy.orm import Session
from fastapi import Cookie
from typing import Optional
from dotenv import load_dotenv


# Creazione dell'applicazione FastAPI
app = FastAPI()
sio = SocketManager(app=app)

# Configure logging
logger = logging.getLogger(__name__)

logging.basicConfig(filename="clean.log", level=logging.INFO)
load_dotenv()

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

templates = Jinja2Templates(directory="templates")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/dbname")

# Configure database connection
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# Define User model
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)


# Create tables at bootstrap
Base.metadata.create_all(bind=engine)


# Utility function to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Funzione per creare un utente
def create_user():
    users = os.environ["CLEAN_USERS"]
    created: bool = bool(os.environ.get("USERS_CREATED", "False").lower())
    if created:
        logger.info("Utenti già creati.")
        return
    logger.info("Creazione degli utenti...")
    if users:
        users = users.split("|")
        for user in users:
            username, password = user.split(":")
            db = SessionLocal()
            if db.query(User).filter_by(username=username).first():
                logger.warning("Utente già esistente.")
            else:
                hashed = bcrypt.hash(password)
                user = User(username=username, password_hash=hashed)
                db.add(user)
                db.commit()
                logger.info("Utente creato.")
            db.close()
        created = True
        os.environ["USERS_CREATED"] = "True"
        logger.info("Utenti creati con successo.")


def get_current_user(
    session: Optional[str] = Cookie(None), db: Session = Depends(get_db)
):
    if session is None:
        logger.warning("Session cookie is missing.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    user = db.query(User).filter(User.username == session).first()
    if user is None:
        logger.warning("Invalid session cookie.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


# Lista di connessioni WebSocket attive
active_connections = set()


class TableCreateRequest(BaseModel):
    base_id: str
    table_name: str


async def notify_clients():
    """Invia un messaggio a tutti i client connessi per ricaricare la pagina"""
    for websocket in active_connections:
        try:
            logger.info("Notifying a client about task completion.")
            await websocket.send_json({"event": "task_completed"})
        except Exception as e:
            logger.error(f"Errore durante l'invio del messaggio: {str(e)}")


def execute_script_in_background(table_id, filename):
    """Esegue la funzione di pulizia e notifica i client WebSocket al termine"""
    try:
        logger.info(f"Starting cleaning process for file: {filename}, table_id: {table_id}")
        from .clean import clean_data  # importa la funzione da un modulo Python

        clean_data(table_id, filename)  # esegui la funzione direttamente
        asyncio.run(notify_clients())  # Notifica i client WebSocket
    except Exception as e:
        logger.error(f"Errore nell'esecuzione della funzione di pulizia: {str(e)}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Gestisce le connessioni WebSocket"""
    await websocket.accept()
    active_connections.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # Mantiene la connessione aperta
    except Exception as e:
        logger.error(f"Errore nella connessione WebSocket: {str(e)}")
    finally:
        active_connections.remove(websocket)


# Route root: legge direttamente il cookie 'session', verifica utente, redirect se non valido
@app.get("/", response_class=HTMLResponse)
async def get_root(request: Request, session: Optional[str] = Cookie(None)):

    db = SessionLocal()
    try:
        if session is None:
            return RedirectResponse(url="/login", status_code=302)
        user = db.query(User).filter(User.username == session).first()
        if user is None:
            return RedirectResponse(url="/login", status_code=302)
        template = env.get_template("index.html")
        return template.render()
    finally:
        db.close()


# Login page GET
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    logger.info("Rendering login page")
    create_user()  # Crea l'utente se non esiste
    return templates.TemplateResponse("login.html", {"request": request})


# Login POST
@app.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: SessionLocal = Depends(get_db),
):
    logger.info(f"Login attempt for user: {username}")
    user = db.query(User).filter(User.username == username).first()
    if user and bcrypt.verify(password, user.password_hash):
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie("session", username, httponly=True)
        return response
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Credenziali non valide"}
    )


@app.post("/upload")
async def upload_files(table_id: str = Form(...), files: List[UploadFile] = File(...)):
    logger.info(f"Uploading files for table_id: {table_id}")
    try:

        Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
        for file in files:
            if file.filename is not None:
                file_path = os.path.join(
                    UPLOAD_FOLDER,
                    file.filename,
                )
                logger.info(f"Saving file to {file_path}")

            with open(file_path, "wb") as f:
                while chunk := await file.read(1024 * 1024):
                    f.write(chunk)
            logger.info(f"File {file.filename} saved successfully")

            # Avvia lo script in background
            Thread(
                target=execute_script_in_background,
                daemon=True,
                args=(table_id, file.filename),
            ).start()
        # Redirect alla pagina che mostra l'elenco dei file
        logger.info("Redirecting to /list_files")
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
    logger.info("Listing files in output folder")
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
        logger.error(f"Errore durante la lettura dei file: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Errore durante la lettura dei file: {str(e)}"
        )


@app.get("/download/{filename}", response_class=FileResponse)
async def download_file(filename: str):
    logger.info(f"Downloading file: {filename}")
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
    logger.info("Clearing output folder")
    try:
        for filename in os.listdir(OUTPUT_FOLDER):
            file_path = os.path.join(OUTPUT_FOLDER, filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)
        logger.info("Output folder cleared successfully")
        return {"status": "success", "message": "Output folder cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing output folder: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante la pulizia della cartella: {str(e)}",
        )


@app.post("/clear_output")
async def clear_output():
    logger.info("Clearing output CSV folders")
    try:
        for filename in os.listdir(OUTPUT_CSV_FOLDER):
            file_path = os.path.join(OUTPUT_CSV_FOLDER, filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)
        for filename in os.listdir(OUTPUT_RAW_FOLDER):
            file_path = os.path.join(OUTPUT_RAW_FOLDER, filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)
        logger.info("Output folder cleared successfully")
        return {"status": "success", "message": "Output folder cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing output folder: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante la pulizia della cartella: {str(e)}",
        )


@app.get("/tables/{base_id}")
def get_tables(base_id: str):
    """Recupera tutte le tabelle da NocoDB."""
    logger.info(f"Retrieving tables for base_id: {base_id}")
    tables = get_all_tables(base_id)
    if tables:
        return tables
    else:
        raise HTTPException(status_code=404, detail="Nessuna tabella trovata")


@app.get("/bases")
def get_nc_bases():
    """Recupera tutte le basi da NocoDB."""
    logger.info("Retrieving bases")
    bases = get_bases()
    if bases:
        return bases
    else:
        raise HTTPException(status_code=404, detail="Nessuna base trovata")


@app.post("/create_table")
def nc_create_table(table_create_request: TableCreateRequest):
    """Crea una nuova tabella in NocoDB."""
    logger.info(f"Creating table {table_create_request.table_name} in base {table_create_request.base_id}")
    create_table(table_create_request.base_id, table_create_request.table_name)
    return {"success": True, "message": "Tabella creata con successo"}


# Logout route
@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response
