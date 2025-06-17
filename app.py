from flask import Flask, render_template, request, jsonify
import json
import os
import datetime
import openpyxl
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import re
import unicodedata
from flask_cors import CORS # Importar CORS

app = Flask(__name__)
# Habilitar CORS para todas as rotas (importante para comunicação entre domínios)
# Durante o desenvolvimento, '*' permite qualquer origem.
# Para produção, você pode querer restringir a 'capacitor://localhost'
# ou a URL do seu app publicado, se houver um domínio web para ele.
CORS(app) 

# Nome do arquivo onde os dados são armazenados
ARQUIVO_DADOS = "localidades.json"

# Listas de opções para os campos do formulário
TIPOS_PISO = [
    "Paviflex", "Cerâmica", "Porcelanato", "Granilite",
    "Cimento Queimado", "Epoxi", "Ardósia", "Outros"
]
TIPOS_MEDIDA = ["Vidro", "Sanitário-Vestiário", "Área Interna", "Área Externa"]
TIPOS_PAREDE = ["Alvenaria", "Estuque", "Divisórias"]

# --- Configurações de E-mail (Lidas de variáveis de ambiente do Render) ---
EMAIL_USER = os.environ.get('EMAIL_USER')
EMAIL_PASS = os.environ.get('EMAIL_PASS')
EMAIL_SERVER = os.environ.get('EMAIL_SERVER')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587)) # Default para 587 se não setado

# --- Funções de Carregamento/Salvamento de Dados ---
def carregar_dados():
    if not os.path.exists(ARQUIVO_DADOS):
        return {}
    with open(ARQUIVO_DADOS, 'r', encoding='utf-8') as f:
        return json.load(f)

def salvar_dados(dados):
    with open(ARQUIVO_DADOS, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

# --- Funções de Geração de Excel e Envio de E-mail ---
def remover_acentos(texto):
    return unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8')

def gerar_excel(dados_unidade, localidade_nome, unidade_nome):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Medidas {unidade_nome}"

    # Cabeçalho da tabela
    headers = ["Localidade", "Unidade", "Data Medição", "Responsável", "Medida (m²)", "Tipo de Medida", "Tipo de Piso", "Tipo de Parede", "Observações"]
    ws.append(headers)

    for i, medida in enumerate(dados_unidade['medidas']):
        row = [
            localidade_nome,
            unidade_nome,
            dados_unidade['data_medicao'],
            dados_unidade['responsavel'],
            medida['medida_m2'],
            medida['tipo_medida'],
            medida['tipo_piso'],
            medida['tipo_parede'],
            medida['observacoes']
        ]
        ws.append(row)

    # Ajustar largura das colunas
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter # Get the column name
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column].width = adjusted_width

    excel_file = io.BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)
    return excel_file

def enviar_email(destinatario, assunto, corpo, anexo_excel=None, nome_arquivo_excel=None):
    if not EMAIL_USER or not EMAIL_PASS or not EMAIL_SERVER:
        print("Erro: Variáveis de ambiente de e-mail não configuradas.")
        return False, "Configurações de e-mail incompletas no servidor."

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = destinatario
    msg['Subject'] = assunto

    msg.attach(MIMEText(corpo, 'plain'))

    if anexo_excel and nome_arquivo_excel:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(anexo_excel.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{nome_arquivo_excel}"')
        msg.attach(part)

    try:
        with smtplib.SMTP(EMAIL_SERVER, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        return True, "E-mail enviado com sucesso!"
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
        return False, f"Erro ao enviar e-mail: {str(e)}"

# --- Rotas da API ---

@app.route('/')
def home():
    # Esta rota não será mais usada diretamente por um aplicativo móvel
    # que usa Capacitor para servir o frontend.
    # O Capacitor servirá o index.html diretamente.
    return "Backend do Levantamento de Medidas está online!"

@app.route('/salvar_unidade', methods=['POST'])
def salvar_unidade():
    data = request.get_json()
    localidade = data.get('localidade')
    unidade = data.get('unidade')
    data_medicao = data.get('data_medicao')
    responsavel = data.get('responsavel')
    email_destino = data.get('email_destino')
    medidas = data.get('medidas')

    if not all([localidade, unidade, data_medicao, responsavel, medidas]):
        return jsonify({"status": "error", "message": "Dados incompletos."}), 400

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email_destino):
        return jsonify({"status": "error", "message": "Formato de e-mail inválido."}), 400

    dados = carregar_dados()
    if localidade not in dados:
        dados[localidade] = {}
    dados[localidade][unidade] = {
        "data_medicao": data_medicao,
        "responsavel": responsavel,
        "email_destino": email_destino,
        "medidas": medidas
    }
    salvar_dados(dados)

    try:
        # Gerar Excel
        excel_data = gerar_excel(dados[localidade][unidade], localidade, unidade)
        nome_arquivo = f"Levantamento_Medidas_{remover_acentos(localidade)}_{remover_acentos(unidade)}_{data_medicao}.xlsx"

        # Enviar e-mail
        assunto = f"Levantamento de Medidas - {localidade} - {unidade}"
        corpo_email = (f"Prezado(a),\n\n"
                       f"Segue em anexo o levantamento de medidas para a unidade '{unidade}' "
                       f"na localidade '{localidade}', realizado em {data_medicao} pelo(a) {responsavel}.\n\n"
                       f"Atenciosamente,\nSua Equipe")

        email_sucesso, email_message = enviar_email(email_destino, assunto, corpo_email, excel_data, nome_arquivo)

        if email_sucesso:
            return jsonify({"status": "success", "message": "Unidade salva com sucesso e e-mail enviado!", "email_status": email_message}), 200
        else:
            return jsonify({"status": "warning", "message": "Unidade salva, mas houve um problema ao enviar o e-mail.", "email_status": email_message}), 200

    except Exception as e:
        print(f"Erro ao gerar Excel/enviar e-mail: {e}")
        return jsonify({"status": "error", "message": f"Unidade salva, mas houve um erro ao gerar o Excel ou enviar o e-mail: {str(e)}."}), 500

@app.route('/carregar_unidade', methods=['POST'])
def carregar_unidade():
    """Carrega os dados de uma unidade específica para edição."""
    data = request.get_json()
    local_unidade = data.get('local_unidade')
    
    if not local_unidade or " - " not in local_unidade:
        return jsonify({"status": "error", "message": "Formato de unidade inválido."}), 400

    local, unidade = local_unidade.split(" - ", 1)
    localidades = carregar_dados()

    if local in localidades and unidade in localidades[local]:
        return jsonify({"status": "success", "data": localidades[local][unidade]}), 200
    else:
        return jsonify({"status": "error", "message": "Unidade não encontrada."}), 404

@app.route('/get_localidades_unidades', methods=['GET'])
def get_localidades_unidades():
    """Retorna a lista de localidades e unidades para o dropdown em JSON."""
    localidades = carregar_dados()
    lista_localidades_unidades = []
    for local, unidades in localidades.items():
        for unidade in unidades.keys():
            lista_localidades_unidades.append(f"{local} - {unidade}")
    
    # Ordena a lista alfabeticamente
    lista_localidades_unidades.sort()
    
    return jsonify(lista_localidades_unidades), 200

# Adicione uma rota simples para verificar o status da rede (opcional, mas útil)
@app.route('/healthcheck', methods=['HEAD', 'GET'])
def healthcheck():
    return '', 200

if __name__ == '__main__':
    # Quando rodando localmente, configure as variáveis de ambiente manualmente
    # Ex:
    # os.environ['EMAIL_USER'] = 'seu_email@dominio.com'
    # os.environ['EMAIL_PASS'] = 'sua_senha_app'
    # os.environ['EMAIL_SERVER'] = 'smtp.dominio.com'
    # os.environ['EMAIL_PORT'] = '587'
    app.run(debug=True, host='0.0.0.0', port=5000)