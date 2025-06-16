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

app = Flask(__name__)

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
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))

# Endereço de e-mail fixo para o destinatário
FIXED_RECIPIENT_EMAIL = "comercialservico2025@gmail.com"

def carregar_dados():
    """Carrega os dados existentes do arquivo JSON."""
    if os.path.exists(ARQUIVO_DADOS):
        with open(ARQUIVO_DADOS, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def salvar_dados(dados):
    """Salva os dados no arquivo JSON."""
    with open(ARQUIVO_DADOS, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

def generate_excel_and_send_email(localidade, unidade, info, email_copia):
    """
    Gera uma planilha Excel com os dados de uma unidade e a envia por e-mail.
    Recebe localidade, unidade, o dicionário de informações da unidade e um e-mail para cópia.
    """
    wb = openpyxl.Workbook()
    
    ws_detalhe = wb.active
    ws_detalhe.title = "Detalhe" 

    # --- Seção para as informações principais na vertical ---
    ws_detalhe.append(["Campo", "Valor"])
    ws_detalhe.append(["Localidade", localidade])
    ws_detalhe.append(["Unidade", unidade])
    ws_detalhe.append(["Data", info.get("data", "")])
    ws_detalhe.append(["Responsável", info.get("responsavel", "")])
    ws_detalhe.append(["E-mail do Inspetor", info.get("email_copia", "")]) # Adiciona o e-mail do inspetor na planilha
    ws_detalhe.append(["Tipo de Piso", ", ".join(info.get("piso", []))])
    ws_detalhe.append(["Vidros Altos", info.get("vidros_altos", "")])
    
    vidros_perigo_status = info.get("vidros_perigo", "Não")
    texto_vidros_risco = "Necessita equipamento adicional/ representa perigo" if vidros_perigo_status == "Sim" else "Não"
    ws_detalhe.append(["Vidros com Risco", texto_vidros_risco])

    ws_detalhe.append(["Paredes", ", ".join(info.get("paredes", []))])
    ws_detalhe.append(["Estacionamento", "Sim" if info.get("estacionamento") else "Não"])
    ws_detalhe.append(["Gramado", "Sim" if info.get("gramado") else "Não"])
    ws_detalhe.append(["Sala de Curativo", "Sim" if info.get("curativo") else "Não"])
    ws_detalhe.append(["Sala de Vacina", "Sim" if info.get("vacina") else "Não"])
    ws_detalhe.append(["Qtd Funcionários", info.get("qtd_func", "")])
    
    outra_area_valor = info.get("outra_area", "")
    if outra_area_valor:
        ws_detalhe.append(["Outra Área", outra_area_valor])

    ws_detalhe.append([]) 
    ws_detalhe.append([])

    abas = {
        "Vidro": {"sheet": wb.create_sheet("Vidros"), "total_area": 0.0},
        "Área Interna": {"sheet": wb.create_sheet("Área Interna"), "total_area": 0.0},
        "Sanitário-Vestiário": {"sheet": wb.create_sheet("Sanitário-Vestiário"), "total_area": 0.0},
        "Área Externa": {"sheet": wb.create_sheet("Área Externa"), "total_area": 0.0}
    }

    CABECALHO_MEDIDAS = ["Comprimento (m)", "Largura (m)", "Área (m²)"]
    for tipo_aba in abas.keys():
        abas[tipo_aba]["sheet"].append(CABECALHO_MEDIDAS)

    for medida in info.get("medidas", []):
        if isinstance(medida, list) and len(medida) == 4:
            tipo, comp, larg, area = medida
            if tipo in abas:
                abas[tipo]["sheet"].append([comp, larg, round(area, 2)]) 
                abas[tipo]["total_area"] += area
        else:
            print(f"Aviso: Formato de medida inesperado: {medida}")

    ws_detalhe.append(["Resumo de Áreas (m²)"])
    ws_detalhe.append(["Total Vidros (m²)", round(abas["Vidro"]["total_area"], 2)])
    ws_detalhe.append(["Total Área Interna (m²)", round(abas["Área Interna"]["total_area"], 2)])
    ws_detalhe.append(["Total Sanitário-Vestiário (m²)", round(abas["Sanitário-Vestiário"]["total_area"], 2)])
    ws_detalhe.append(["Total Área Externa (m²)", round(abas["Área Externa"]["total_area"], 2)])

    for sheet_name, sheet_data in list(abas.items()):
        if sheet_data["sheet"].max_row == 1 or (sheet_data["sheet"].max_row == 0 and sheet_data["sheet"].max_column == 0):
            wb.remove(sheet_data["sheet"])
            
    if "Sheet" in wb.sheetnames:
        default_sheet = wb["Sheet"]
        if default_sheet.max_row == 0 or (default_sheet.max_row == 1 and all(cell.value is None for cell in default_sheet[1])):
            wb.remove(default_sheet)

    if "Detalhe" in wb.sheetnames:
        wb.active = wb["Detalhe"]

    excel_file_in_memory = io.BytesIO()
    wb.save(excel_file_in_memory)
    excel_file_in_memory.seek(0)

    excel_content = excel_file_in_memory.getvalue()
    if len(excel_content) == 0:
        print("Aviso: O arquivo Excel gerado está vazio.")
        raise Exception("O arquivo Excel gerado está vazio. Verifique os dados da unidade.")

    base_nome = f"{unidade}_{localidade}"
    
    normalized_name = unicodedata.normalize('NFKD', base_nome)
    ascii_name = normalized_name.encode('ascii', 'ignore').decode('utf-8')
    nome_arquivo_limpo = re.sub(r'[^a-zA-Z0-9_]', '_', ascii_name)
    nome_arquivo_limpo = re.sub(r'_+', '_', nome_arquivo_limpo)
    nome_arquivo = f"{nome_arquivo_limpo.strip('_')}.xlsx"

    if not EMAIL_USER or not EMAIL_PASS or not EMAIL_SERVER:
        raise Exception("Configurações de e-mail incompletas no servidor.")

    recipients = [FIXED_RECIPIENT_EMAIL]
    if email_copia and "@" in email_copia:
        recipients.append(email_copia)

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = ", ".join(recipients)
    msg['Subject'] = f"Levantamento das Medidas da Unidade: {localidade} - {unidade}"

    body = f"""
    Prezado(a),

    Segue em anexo a planilha Excel com os dados do Levantamento realizado na unidade {localidade} - {unidade}.

    Data: {info.get('data', 'Não informada')}
    Responsável: {info.get('responsavel', 'Não informado')}
    """
    if outra_area_valor:
        body += f"\nOutra Área: {outra_area_valor}"
    body += """

    Atenciosamente,
    Equipe de levantamento de campo
    """
    
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    part.set_payload(excel_content)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="{nome_arquivo}"')
    msg.attach(part)

    try:
        with smtplib.SMTP(EMAIL_SERVER, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        return True
    except smtplib.SMTPAuthenticationError as e:
        raise Exception(f"Erro de autenticação ao enviar e-mail: {e}.")
    except smtplib.SMTPConnectError as e:
        raise Exception(f"Erro de conexão ao servidor de e-mail: {e}.")
    except Exception as e:
        raise Exception(f"Erro inesperado ao enviar e-mail: {e}.")

@app.route('/')
def index():
    """Renderiza a página principal com o formulário."""
    data_hoje = datetime.date.today().isoformat()
    return render_template(
        'index.html',
        tipos_piso=TIPOS_PISO,
        tipos_medida=TIPOS_MEDIDA,
        tipos_parede=TIPOS_PAREDE,
        data_hoje=data_hoje,
    )

@app.route('/get_localidades_unidades', methods=['GET'])
def get_localidades_unidades():
    """Retorna a lista de localidades e unidades para o dropdown em JSON."""
    localidades = carregar_dados()
    lista_localidades_unidades = []
    for local, unidades in sorted(localidades.items()):
        for unidade_nome in sorted(unidades.keys()):
            lista_localidades_unidades.append(f"{local} - {unidade_nome}")
    return jsonify(lista_localidades_unidades)

@app.route('/salvar_unidade', methods=['POST'])
def salvar_unidade():
    """Salva os dados de uma unidade submetidos via formulário, gera Excel e envia por e-mail."""
    localidade = request.form['localidade'].strip()
    unidade = request.form['unidade'].strip()

    if not localidade or not unidade:
        return jsonify({"status": "error", "message": "Localidade e Unidade são campos obrigatórios."}), 400

    data = request.form.get('data', '')
    responsavel = request.form.get('responsavel', '')
    email_copia = request.form.get('email_copia', '').strip()
    qtd_func = request.form.get('qtd_func', '')

    piso_selecionado = []
    for tipo_piso in TIPOS_PISO:
        if request.form.get(f'piso_{tipo_piso}'):
            piso_selecionado.append(tipo_piso)

    vidros_altos = request.form.get('vidros_altos', 'Não')

    paredes_selecionadas = []
    for tipo_parede in TIPOS_PAREDE:
        if request.form.get(f'parede_{tipo_parede}'):
            paredes_selecionadas.append(tipo_parede)

    estacionamento = 'estacionamento' in request.form
    gramado = 'gramado' in request.form
    curativo = 'curativo' in request.form
    vacina = 'vacina' in request.form
    outra_area = request.form.get('outra_area', '').strip() 

    medidas_json_str = request.form.get('medidas_json', '[]')
    try:
        medidas = json.loads(medidas_json_str)
    except json.JSONDecodeError:
        medidas = []

    unit_data = {
        "data": data,
        "responsavel": responsavel,
        "email_copia": email_copia,
        "qtd_func": qtd_func,
        "piso": piso_selecionado,
        "vidros_altos": vidros_altos,
        "vidros_perigo": request.form.get("vidros_perigo", "Não"),
        "paredes": paredes_selecionadas,
        "estacionamento": estacionamento,
        "gramado": gramado,
        "curativo": curativo,
        "vacina": vacina,
        "medidas": medidas,
        "outra_area": outra_area
    }

    localidades = carregar_dados()
    if localidade not in localidades:
        localidades[localidade] = {}
    
    localidades[localidade][unidade] = unit_data
    salvar_dados(localidades)

    # Inicializa a mensagem de sucesso
    success_message = "Unidade salva e Excel enviado por e-mail com sucesso!"

    # Verifica se o e-mail de cópia está em branco e adiciona a mensagem de aviso
    if not email_copia:
        success_message += " O campo 'Seu E-mail para Cópia' estava em branco, então o e-mail foi enviado apenas para o destinatário principal."

    try:
        generate_excel_and_send_email(localidade, unidade, unit_data, email_copia)
        return jsonify({"status": "success", "message": success_message})
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

if __name__ == '__main__':
    app.run(debug=True)