from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
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

app = Flask(__name__)
app.secret_key = os.urandom(24)

ARQUIVO_DADOS = "localidades.json"
ARQUIVO_USUARIOS = "users.json"

TIPOS_PISO = [
    "Paviflex", "Cerâmica", "Porcelanato", "Granilite",
    "Cimento Queimado", "Epoxi", "Ardósia", "Outros"
]
TIPOS_MEDIDA = ["Vidro", "Sanitário-Vestiário", "Área Interna", "Área Externa"]
TIPOS_PAREDE = ["Alvenaria", "Estuque", "Divisórias"]

EMAIL_USER = os.environ.get('EMAIL_USER')
EMAIL_PASS = os.environ.get('EMAIL_PASS')
EMAIL_SERVER = os.environ.get('EMAIL_SERVER')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
FIXED_RECIPIENT_EMAIL = os.environ.get('FIXED_RECIPIENT_EMAIL')

def carregar_dados(arquivo):
    if not os.path.exists(arquivo):
        with open(arquivo, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        return {}
    try:
        with open(arquivo, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def salvar_dados(dados, arquivo):
    with open(arquivo, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

@app.route('/exportar', methods=['POST'])
def exportar_excel_e_enviar_email():
    if not session.get('logged_in'):
        return jsonify({"status": "error", "message": "Acesso não autorizado"}), 401
        
    info = request.json
    local = info.get("localidade")
    unidade = info.get("unidade")

    if not local or not unidade:
        return jsonify({"status": "error", "message": "Localidade e Unidade são necessários."}), 400

    wb = openpyxl.Workbook()
    ws_detalhe = wb.active
    ws_detalhe.title = "Detalhe"
    ws_detalhe.append([
        "Localidade", "Unidade", "Data", "Responsável", "Tipo de Piso", 
        "Vidros Altos", "Vidros Altos - Risco", "Paredes", "Estacionamento", 
        "Gramado", "Sala de Curativo", "Sala de Vacina", "Qtd Funcionários"
    ])
    ws_detalhe.append([
        local, unidade, info.get("data", ""), info.get("responsavel", ""),
        ", ".join(info.get("piso", [])), info.get("vidros_altos", ""),
        "Sim" if info.get("vidros_altos_risco") else "Não",
        ", ".join(info.get("paredes", [])),
        "Sim" if info.get("estacionamento") else "Não",
        "Sim" if info.get("gramado") else "Não",
        "Sim" if info.get("curativo") else "Não",
        "Sim" if info.get("vacina") else "Não",
        info.get("qtd_func", "")
    ])

    todas_as_medidas = info.get("medidas", [])
    categorias = {
        "Vidros": [m for m in todas_as_medidas if m.get("tipo") == "Vidro"],
        "Áreas Externas": [m for m in todas_as_medidas if m.get("tipo") == "Área Externa"],
        "Áreas Internas": [m for m in todas_as_medidas if m.get("tipo") == "Área Interna"],
        "Sanitários e Vestiários": [m for m in todas_as_medidas if m.get("tipo") == "Sanitário-Vestiário"]
    }

    header_medidas = ["Tipo", "Altura (m)", "Largura (m)", "Quantidade", "m² Total"]
    for nome_aba, medidas_da_categoria in categorias.items():
        if not medidas_da_categoria:
            continue
        ws = wb.create_sheet(title=nome_aba)
        ws.append(header_medidas)
        for medida in medidas_da_categoria:
            altura = medida.get("altura") or 0
            largura = medida.get("largura") or 0
            qtd = medida.get("qtd") or 1
            m2_total = altura * largura * qtd
            ws.append([medida.get("tipo"), altura, largura, qtd, m2_total])

    excel_buffer = io.BytesIO()
    wb.save(excel_buffer)
    excel_content = excel_buffer.getvalue()
    excel_buffer.close()

    def sanitizar_nome(nome):
        return re.sub(r'[^a-zA-Z0-9_-]', '_', nome)

    local_sanitizado = sanitizar_nome(local)
    unidade_sanitizado = sanitizar_nome(unidade)
    nome_arquivo = f"Levantamento_{local_sanitizado}_{unidade_sanitizado}.xlsx"

    if not all([EMAIL_USER, EMAIL_PASS, EMAIL_SERVER, FIXED_RECIPIENT_EMAIL]):
        return jsonify({"status": "error", "message": "Configurações de e-mail incompletas no servidor."}), 500

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = FIXED_RECIPIENT_EMAIL
    msg['Subject'] = f"Levantamento de Medidas: {local} - {unidade}"
    msg.attach(MIMEText(f"Segue em anexo o levantamento de medidas para a unidade {unidade} na localidade {local}.", 'plain', 'utf-8'))

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
        return jsonify({"status": "success", "message": "Unidade salva e Excel enviado por e-mail com sucesso!"})
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
        return jsonify({"status": "error", "message": f"Erro ao enviar e-mail: {e}"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
