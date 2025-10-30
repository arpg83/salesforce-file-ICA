import os
import requests
import base64
from uuid import uuid4
from flask import Flask, request, render_template, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename # Para validar y limpiar el nombre del archivo
from jinja2 import Environment, FileSystemLoader
from werkzeug.utils import secure_filename
from flask_restful import Resource, Api
from schemas import ResponseMessageModel, OutputModel
from simple_salesforce import Salesforce
from dotenv import load_dotenv
from uvicorn.middleware.wsgi import WSGIMiddleware

load_dotenv()

username = os.getenv("SALESFORCE_USER_NAME")
password = os.getenv("SALESFORCE_PASSWORD")
security_token = os.getenv("SALESFORCE_SECURITY_TOKEN")
domain = os.getenv("SALESFORCE_DOMAIN")  # "login" o "test"
link_server = os.getenv("LOCAL_SERVER")
instance_url = None

try:
    client = Salesforce(
        username=username,
        password=password,
        security_token=security_token,
        domain=domain
    )
    print("✅ Conectado a Salesforce correctamente")
    print("Instancia:", client.sf_instance)
    instance_url=client.sf_instance
except Exception as e:
    print("❌ Error al conectar con Salesforce:", e)

#logger = logging.getLogger(__name__)
template_env = Environment(loader=FileSystemLoader("templates"))

app = Flask(__name__)
CORS(app)
#CORS(app, resources={r"/api/*": {"origins": "https://browse-file-ica.onrender.com/"}}) 
api = Api(app)
asgi_app = WSGIMiddleware(app)
app.config['UPLOAD_FOLDER'] = './upload_file' # Carpeta donde se guardarán los archivos

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])


@app.route('/download/<filename>')
def download_file(filename):
    # Construye la ruta completa al archivo en el servidor
    directorio_actual = os.getcwd() + "/upload_file"
    ruta_archivo_servidor = os.path.join(directorio_actual, filename)
    try:
        # Forzar la descarga del archivo
        return send_file(ruta_archivo_servidor, as_attachment=True)
    except FileNotFoundError:
        return "Archivo no encontrado", 404


def attach_file(incidente: str, file_url: str):
    # Construimos la query filtrando directamente por el número de incidente
    #soql = f"SELECT Id, CaseNumber, Subject, Status FROM Case WHERE CaseNumber = '{incidente}' LIMIT 1"
    soql = f"SELECT Id, CaseNumber, Subject, Status FROM Case WHERE Ticket_SGC__c = '{incidente}' LIMIT 1"
    
    response=client.query(soql)
    
    message_error = None
    if response["records"]:
        case_id = response["records"][0]["Id"]
        print(f"Subiendo archivo al Case con ID: {case_id}")
        file_name = None
        file_base64 = None

        # Descargar el archivo desde la URL
        file_response = requests.get(file_url)
        if file_response.status_code == 200:
            file_data = file_response.content
            file_base64 = base64.b64encode(file_data).decode("utf-8")
            file_name = os.path.basename(file_url.split("?")[0])  # Nombre del archivo sin query params
        else:
            message_error = f"No se pudo descargar el archivo desde la URL. Código {file_response.status_code}"
            print(message_error)
                
        # 1. Subir el archivo como ContentVersion
        content_version_payload = {
            "Title": file_name,
            "PathOnClient": file_name,
            "VersionData": file_base64,
            'FirstPublishLocationId': case_id
        }

        resultado = client.ContentVersion.create(content_version_payload)

        if resultado['success']:
            print(f"✓ PDF adjuntado exitosamente al caso {case_id}")
            print(f"  ContentVersion ID: {resultado['id']}")
            message_error = "200" # Se instancia con 200 cuado el attach es exitoso
        else:
            print(f"✗ Error al adjuntar PDF: {resultado}")
            message_error = "Error al crear el ContentDocumentLink"
    else:
        message_error = f"No se encontró el incidente {incidente}"
        print(message_error)

    return message_error


@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return 'No hay archivo en la solicitud', 400

    archivos = request.files.getlist('file')
    message_attach = None
    status_code = 200
    for file in archivos:
        if file.filename == '':
            return "No se seleccionó ningún archivo", 400
        
        if file:
            filename = secure_filename(file.filename) # Limpia el nombre del archivo
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath) # Guarda el archivo en la carpeta especificada

            list_filename = filename.split("-")
            ticket_sgc = list_filename[0] + "-" + list_filename[1]
            print(f"Archivo guardado: {filename} / Ticket SGC: {ticket_sgc}")

            message_attach = attach_file(ticket_sgc, link_server + filename)
            print("************")
            print(message_attach)
            print("******")
            if message_attach != "200":
                status_code = 400

            #Se borra el archivo del servidor luego de procesarlo
            os.remove(filepath)

    #return str(status_code)
    if status_code != 200:
        return None
    else: 
        return jsonify({
            'message': 'Archivo subido exitosamente',
            'filename': filename,
            'size': 0,
            'path': filepath,
            'status': status_code
        }), status_code
    



















