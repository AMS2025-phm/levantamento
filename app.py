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
FIXED_RECIPIENT_EMAIL = "comercialservico2025@gmail.com" # Destinatário fixo

# Função para carregar dados do arquivo JSON
def carregar_dados():
    if os.path.exists(ARQUIVO_DADOS):
        with open(ARQUIVO_DADOS, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {} # Retorna vazio se o arquivo estiver corrompido/vazio
    return {}

# Função para salvar dados no arquivo JSON
def salvar_dados(dados):
    with open(ARQUIVO_DADOS, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

@app.route('/')
def index():
    data_hoje = datetime.date.today().strftime('%Y-%m-%d')
    return render_template('index.html', data_hoje=data_hoje,
                           tipos_piso=TIPOS_PISO,
                           tipos_medida=TIPOS_MEDIDA,
                           tipos_parede=TIPOS_PAREDE)

@app.route('/salvar_unidade', methods=['POST'])
def salvar_unidade():
    try:
        data = request.json
        localidade = data.get('localidade')
        unidade = data.get('unidade')
        data_cadastro = data.get('data')
        responsavel = data.get('responsavel')
        qtd_func = data.get('qtd_func')

        if not all([localidade, unidade, data_cadastro, responsavel, qtd_func]):
            return jsonify({"status": "error", "message": "Todos os campos da unidade são obrigatórios!"}), 400

        dados = carregar_dados()

        # Garante que a localidade exista
        if localidade not in dados:
            dados[localidade] = {}

        # Adiciona ou atualiza a unidade na localidade
        dados[localidade][unidade] = {
            'data_cadastro': data_cadastro,
            'responsavel': responsavel,
            'qtd_func': qtd_func,
            'medidas': [] # Inicializa lista de medidas
        }

        salvar_dados(dados)

        # Geração do Excel e envio por e-mail
        output = io.BytesIO()
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Dados da Unidade"

        # Cabeçalhos
        sheet.append(["Localidade", "Unidade", "Data de Cadastro", "Responsável", "Quantidade de Funcionários"])

        # Dados da unidade
        sheet.append([localidade, unidade, data_cadastro, responsavel, qtd_func])

        # Se houver medidas, adicioná-las também (opcional, dependendo do que você quer no Excel inicial)
        # Para incluir medidas aqui, você precisaria carregar os dados de 'medidas' da unidade recém-salva
        # E formatar as listas de checkboxes para uma string para a célula do Excel.
        # Exemplo (se for adicionar cabeçalhos para medidas):
        # sheet.append(["Tipo de Medida", "Metragem", "Tipo de Piso", "Tipo de Parede", "Área Coberta", "Área Descoberta", "Observações"])
        # for medida in dados[localidade][unidade]['medidas']:
        #     sheet.append([
        #         ", ".join(medida.get('tipo_medida', [])),
        #         medida.get('metragem'),
        #         ", ".join(medida.get('tipo_piso', [])),
        #         ", ".join(medida.get('tipo_parede', [])),
        #         medida.get('area_externa_coberta'),
        #         medida.get('area_externa_descoberta'),
        #         medida.get('obs')
        #     ])


        workbook.save(output)
        excel_content = output.getvalue()

        # --- Envio de E-mail ---
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = FIXED_RECIPIENT_EMAIL
        msg['Subject'] = f"Dados de Cadastro da Unidade: {unidade}"

        body = f"Olá,\n\nOs dados da unidade '{unidade}' foram cadastrados com sucesso.\n\nAtenciosamente,\nSeu Sistema de Cadastro"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        part.set_payload(excel_content)
        encoders.encode_base64(part)

        nome_arquivo = f'{unidade}.xlsx'
        part.add_header('Content-Disposition', f'attachment; filename=\"{nome_arquivo}\"')
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
            print(f"Erro ao enviar e-mail: {e}")
            return jsonify({"status": "error", "message": f"Erro ao enviar e-mail: {e}"}), 500

    except Exception as e:
        print(f"Erro ao salvar unidade: {e}")
        return jsonify({"status": "error", "message": f"Erro interno ao salvar unidade: {e}"}), 500

@app.route('/carregar_unidades')
def carregar_unidades():
    dados = carregar_dados()
    unidades_salvas = []
    for localidade in dados:
        for unidade in dados[localidade]:
            unidades_salvas.append(unidade)

    return jsonify(unidades_salvas)

@app.route('/get_unidade_data/<unidade_nome>')
def get_unidade_data(unidade_nome):
    dados = carregar_dados()
    for localidade, unidades in dados.items():
        if unidade_nome in unidades:
            return jsonify(unidades[unidade_nome])
    return jsonify({"error": "Unidade não encontrada"}), 404

@app.route('/salvar_medidas', methods=['POST'])
def salvar_medidas():
    try:
        data = request.json
        localidade = data.get('localidade')
        unidade = data.get('unidade')

        # Captura todos os dados de medida
        # Garante que os campos de checkbox sejam sempre listas
        nova_medida = {
            "tipo_medida": data.get('tipo_medida', []), # Agora espera uma lista
            "metragem": data.get('metragem'),
            "tipo_piso": data.get('tipo_piso', []),     # Agora espera uma lista
            "tipo_parede": data.get('tipo_parede', []), # Agora espera uma lista
            "area_externa_coberta": data.get('area_externa_coberta'),
            "area_externa_descoberta": data.get('area_externa_descoberta'),
            "obs": data.get('obs')
        }

        # Validação para campos que antes eram required e agora são arrays
        # É importante que 'tipo_medida' tenha pelo menos uma seleção
        if not all([localidade, unidade, nova_medida['metragem']]) or not nova_medida['tipo_medida']:
            return jsonify({"status": "error", "message": "Campos essenciais da medida (localidade, unidade, tipo de medida e metragem) são obrigatórios!"}), 400

        dados = carregar_dados()

        if localidade in dados and unidade in dados[localidade]:
            dados[localidade][unidade]['medidas'].append(nova_medida)
            salvar_dados(dados)
            return jsonify({"status": "success", "message": "Medida adicionada com sucesso!"}), 200
        else:
            return jsonify({"status": "error", "message": "Localidade ou unidade não encontrada."}), 404
    except Exception as e:
        print(f"Erro ao salvar medida: {e}")
        return jsonify({"status": "error", "message": f"Erro interno ao salvar medida: {e}"}), 500

@app.route('/excluir_medida', methods=['POST'])
def excluir_medida():
    try:
        data = request.json
        localidade = data.get('localidade')
        unidade = data.get('unidade')
        index = data.get('index')

        dados = carregar_dados()

        if localidade in dados and unidade in dados[localidade]:
            if 0 <= index < len(dados[localidade][unidade]['medidas']):
                del dados[localidade][unidade]['medidas'][index]
                salvar_dados(dados)
                return jsonify({"status": "success", "message": "Medida excluída com sucesso!"}), 200
            else:
                return jsonify({"status": "error", "message": "Índice da medida inválido."}), 400
        else:
            return jsonify({"status": "error", "message": "Localidade ou unidade não encontrada."}), 404
    except Exception as e:
        print(f"Erro ao excluir medida: {e}")
        return jsonify({"status": "error", "message": f"Erro interno ao excluir medida: {e}"}), 500

@app.route('/excluir_unidade', methods=['POST'])
def excluir_unidade():
    try:
        data = request.json
        localidade = data.get('localidade')
        unidade = data.get('unidade')

        dados = carregar_dados()

        if localidade in dados and unidade in dados[localidade]:
            del dados[localidade][unidade]
            if not dados[localidade]:
                del dados[localidade]
            salvar_dados(dados)
            return jsonify({"status": "success", "message": "Unidade excluída com sucesso!"}), 200
        else:
            return jsonify({"status": "error", "message": "Localidade ou unidade não encontrada."}), 404
    except Exception as e:
        print(f"Erro ao excluir unidade: {e}")
        return jsonify({"status": "error", "message": f"Erro interno ao excluir unidade: {e}"}), 500

if __name__ == '__main__':
    app.run(debug=True)