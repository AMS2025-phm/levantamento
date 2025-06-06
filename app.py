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
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587)) # Padrão 587, converte para int

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

@app.route('/')
def index():
    """Renderiza a página principal com o formulário e a lista de unidades."""
    # A lista de localidades_unidades será carregada via JS agora
    data_hoje = datetime.date.today().isoformat() # Data atual para preencher o campo de data

    return render_template(
        'index.html',
        tipos_piso=TIPOS_PISO,
        tipos_medida=TIPOS_MEDIDA,
        tipos_parede=TIPOS_PAREDE,
        data_hoje=data_hoje,
        # lista_localidades_unidades não é mais passada aqui, será carregada via AJAX
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
    """Salva os dados de uma unidade submetidos via formulário."""
    localidade = request.form['localidade'].strip()
    unidade = request.form['unidade'].strip()

    if not localidade or not unidade:
        return jsonify({"status": "error", "message": "Localidade e Unidade são campos obrigatórios."}), 400

    data = request.form.get('data', '')
    responsavel = request.form.get('responsavel', '')
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

    # Verifica se os checkboxes "Outras Informações" foram marcados
    estacionamento = 'estacionamento' in request.form
    gramado = 'gramado' in request.form
    curativo = 'curativo' in request.form
    vacina = 'vacina' in request.form

    medidas_json_str = request.form.get('medidas_json', '[]')
    try:
        medidas = json.loads(medidas_json_str)
    except json.JSONDecodeError:
        medidas = [] # Retorna lista vazia se houver erro no JSON

    localidades = carregar_dados()
    if localidade not in localidades:
        localidades[localidade] = {}
    
    localidades[localidade][unidade] = {
        "data": data,
        "responsavel": responsavel,
        "qtd_func": qtd_func,
        "piso": piso_selecionado,
        "vidros_altos": vidros_altos,
        "paredes": paredes_selecionadas,
        "estacionamento": estacionamento,
        "gramado": gramado,
        "curativo": curativo,
        "vacina": vacina,
        "medidas": medidas
    }
    salvar_dados(localidades)
    return jsonify({"status": "success", "message": "Unidade salva com sucesso!"})

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

@app.route('/exportar_excel_e_enviar_email', methods=['POST'])
def exportar_excel_e_enviar_email():
    """Gera uma planilha Excel com os dados de uma unidade e a envia por e-mail."""
    selected_unit_str = request.form.get('selected_unit_to_export')
    recipient_email = FIXED_RECIPIENT_EMAIL

    if not selected_unit_str or " - " not in selected_unit_str:
        return jsonify({"status": "error", "message": "Selecione uma unidade válida para exportar."}), 400
    
    local, unidade = selected_unit_str.split(" - ", 1)
    localidades = carregar_dados()

    if local not in localidades or unidade not in localidades[local]:
        return jsonify({"status": "error", "message": "Unidade não encontrada para exportação."}), 404

    info = localidades[local][unidade]

    wb = openpyxl.Workbook()
    
    ws_detalhe = wb.active
    ws_detalhe.title = "Detalhe" 

    ws_detalhe.append(["Localidade", "Unidade", "Data", "Responsável", "Tipo de Piso", 
                       "Vidros Altos", "Paredes", "Estacionamento", "Gramado", 
                       "Sala de Curativo", "Sala de Vacina", "Qtd Funcionários"])
    
    ws_detalhe.append([
        local, 
        unidade, 
        info.get("data", ""), 
        info.get("responsavel", ""),
        ", ".join(info.get("piso", [])), 
        info.get("vidros_altos", ""),
        ", ".join(info.get("paredes", [])),
        "Sim" if info.get("estacionamento") else "Não",
        "Sim" if info.get("gramado") else "Não",
        "Sim" if info.get("curativo") else "Não",
        "Sim" if info.get("vacina") else "Não",
        info.get("qtd_func", "")
    ])

    abas = {
        "Vidro": wb.create_sheet("Vidros"),
        "Área Interna": wb.create_sheet("Área Interna"),
        "Sanitário-Vestiário": wb.create_sheet("Sanitário-Vestiário"),
        "Área Externa": wb.create_sheet("Área Externa")
    }
    for ws in abas.values():
        ws.append(["Localidade", "Unidade", "Comprimento (m)", "Largura (m)", "Área (m²)"])

    for medida in info.get("medidas", []):
        if isinstance(medida, list) and len(medida) == 4:
            tipo, comp, larg, area = medida
            if tipo in abas:
                abas[tipo].append([local, unidade, comp, larg, round(area, 2)])
        else:
            print(f"Aviso: Formato de medida inesperado: {medida}")


    for sheet_name, sheet_obj in list(abas.items()):
        if sheet_obj.max_row == 1:
            wb.remove(sheet_obj)
            
    if "Sheet" in wb.sheetnames:
        default_sheet = wb["Sheet"]
        if default_sheet.max_row == 0 or (default_sheet.max_row == 1 and all(cell.value is None for cell in default_sheet[1])):
            wb.remove(default_sheet)

    if "Detalhe" in wb.sheetnames:
        wb.active = wb["Detalhe"]

    excel_file_in_memory = io.BytesIO()
    wb.save(excel_file_in_memory)
    excel_file_in_memory.seek(0)

    # Adicionando log para verificar o tamanho do arquivo Excel gerado
    excel_content = excel_file_in_memory.getvalue()
    print(f"Tamanho do arquivo Excel gerado: {len(excel_content)} bytes")
    if len(excel_content) == 0:
        print("Aviso: O arquivo Excel gerado está vazio.")
        # Retorne um erro ou tome uma ação apropriada se o arquivo estiver vazio
        return jsonify({"status": "error", "message": "O arquivo Excel gerado está vazio. Verifique os dados da unidade."}), 500

    # Adicionando logs para depurar o nome do arquivo
    print(f"DEBUG: Localidade recebida: '{local}'")
    print(f"DEBUG: Unidade recebida: '{unidade}'")

    # CORREÇÃO: Nome do arquivo Excel agora prioriza a unidade
    nome_arquivo = f"{unidade}_{local}.xlsx".replace(" ", "_").replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")
    
    print(f"DEBUG: Nome do arquivo gerado: '{nome_arquivo}'")

    if not EMAIL_USER or not EMAIL_PASS or not EMAIL_SERVER:
        print("Erro: Variáveis de ambiente de e-mail (EMAIL_USER, EMAIL_PASS, EMAIL_SERVER) não configuradas.")
        return jsonify({"status": "error", "message": "Configurações de e-mail incompletas no servidor. Verifique EMAIL_USER, EMAIL_PASS, EMAIL_SERVER no Render."}), 500

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = recipient_email
    msg['Subject'] = f"Dados de Cadastro da Unidade: {local} - {unidade}"

    body = f"""
    Prezado(a),

    Segue em anexo a planilha Excel com os dados de cadastro da unidade {local} - {unidade}.

    Data: {info.get('data', 'Não informada')}
    Responsável: {info.get('responsavel', 'Não informado')}

    Atenciosamente,
    Seu Sistema de Cadastro
    """
    
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet') # MIME Type específico para .xlsx
    part.set_payload(excel_content) # Usar o conteúdo lido e verificado
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="{nome_arquivo}"')
    msg.attach(part)

    try:
        with smtplib.SMTP(EMAIL_SERVER, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        
        return jsonify({"status": "success", "message": "Unidade salva e Excel enviado por e-mail com sucesso!"}), 200

    except smtplib.SMTPAuthenticationError as e:
        print(f"Erro de autenticação SMTP: {e}")
        return jsonify({"status": "error", "message": f"Erro de autenticação ao enviar e-mail. Verifique EMAIL_USER e EMAIL_PASS (senha de aplicativo)."}), 500
    except smtplib.SMTPConnectError as e:
        print(f"Erro de conexão SMTP: {e}")
        return jsonify({"status": "error", "message": f"Erro de conexão ao servidor de e-mail. Verifique EMAIL_SERVER e EMAIL_PORT."}), 500
    except Exception as e:
        print(f"Erro inesperado ao enviar e-mail: {e}")
        return jsonify({"status": "error", "message": f"Erro ao enviar Excel por e-mail: {str(e)}. Verifique as configurações de e-mail e permissões."}), 500

if __name__ == '__main__':
    app.run(debug=True)
