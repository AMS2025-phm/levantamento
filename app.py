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

ARQUIVO_DADOS = "localidades.json"
TIPOS_PISO = ["Paviflex", "Cerâmica", "Porcelanato", "Granilite", "Cimento Queimado", "Epoxi", "Ardósia", "Outros"]
TIPOS_MEDIDA = ["Vidro", "Sanitário-Vestiário", "Área Interna", "Área Externa"]
TIPOS_PAREDE = ["Alvenaria", "Estuque", "Divisórias"]

EMAIL_USER = os.environ.get('EMAIL_USER')
EMAIL_PASS = os.environ.get('EMAIL_PASS')
EMAIL_SERVER = os.environ.get('EMAIL_SERVER')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
FIXED_RECIPIENT_EMAIL = "comercialservico2025@gmail.com"

def carregar_dados():
    if os.path.exists(ARQUIVO_DADOS):
        with open(ARQUIVO_DADOS, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def salvar_dados(dados):
    with open(ARQUIVO_DADOS, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

def gerar_e_enviar_excel_por_email(local, unidade, info):
    wb = openpyxl.Workbook()
    ws_detalhe = wb.active
    ws_detalhe.title = "Detalhe"
    ws_detalhe.append(["Localidade", "Unidade", "Data", "Responsável", "Tipo de Piso",
                       "Vidros Altos", "Paredes", "Estacionamento", "Gramado",
                       "Sala de Curativo", "Sala de Vacina", "Qtd Funcionários"])
    ws_detalhe.append([
        local, unidade, info.get("data", ""), info.get("responsavel", ""),
        ", ".join(info.get("piso", [])), info.get("vidros_altos", ""),
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
    for sheet_name, sheet_obj in list(abas.items()):
        if sheet_obj.max_row == 1:
            wb.remove(sheet_obj)
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])
    excel_io = io.BytesIO()
    wb.save(excel_io)
    excel_io.seek(0)
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = FIXED_RECIPIENT_EMAIL
    msg['Subject'] = f"Dados da Unidade: {local} - {unidade}"
    msg.attach(MIMEText(f"""
    Prezado(a),

    Segue em anexo a planilha com os dados da unidade {local} - {unidade}.

    Data: {info.get('data', 'Não informada')}
    Responsável: {info.get('responsavel', 'Não informado')}
    """, 'plain', 'utf-8'))
    part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    part.set_payload(excel_io.getvalue())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="{unidade}_{local}.xlsx"')
    msg.attach(part)
    with smtplib.SMTP(EMAIL_SERVER, EMAIL_PORT) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)

@app.route('/')
def index():
    return render_template('index.html',
        tipos_piso=TIPOS_PISO,
        tipos_medida=TIPOS_MEDIDA,
        tipos_parede=TIPOS_PAREDE,
        data_hoje=datetime.date.today().isoformat())

@app.route('/get_localidades_unidades', methods=['GET'])
def get_localidades_unidades():
    localidades = carregar_dados()
    lista = [f"{local} - {unidade}" for local in sorted(localidades) for unidade in sorted(localidades[local])]
    return jsonify(lista)

@app.route('/carregar_unidade', methods=['POST'])
def carregar_unidade():
    data = request.get_json()
    local_unidade = data.get('local_unidade')
    if not local_unidade or " - " not in local_unidade:
        return jsonify({"status": "error", "message": "Formato de unidade inválido."}), 400
    local, unidade = local_unidade.split(" - ", 1)
    localidades = carregar_dados()
    if local in localidades and unidade in localidades[local]:
        info = localidades[local][unidade]
        try:
            gerar_e_enviar_excel_por_email(local, unidade, info)
        except Exception as e:
            print(f"Erro ao enviar e-mail: {e}")
        return jsonify({"status": "success", "data": info}), 200
    else:
        return jsonify({"status": "error", "message": "Unidade não encontrada."}), 404

@app.route('/salvar_unidade', methods=['POST'])
def salvar_unidade():
    # Mesma lógica existente do salvamento (mantido do seu código)
    pass

@app.route('/exportar_excel_e_enviar_email', methods=['POST'])
def exportar_excel_e_enviar_email():
    selected = request.form.get('selected_unit_to_export')
    if not selected or " - " not in selected:
        return jsonify({"status": "error", "message": "Selecione uma unidade válida."}), 400
    local, unidade = selected.split(" - ", 1)
    localidades = carregar_dados()
    if local not in localidades or unidade not in localidades[local]:
        return jsonify({"status": "error", "message": "Unidade não encontrada."}), 404
    try:
        gerar_e_enviar_excel_por_email(local, unidade, localidades[local][unidade])
        return jsonify({"status": "success", "message": "Excel enviado por e-mail com sucesso!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao enviar e-mail: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)
