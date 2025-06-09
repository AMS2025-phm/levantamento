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

from flask import Flask, render_template, request, jsonify # Import Flask and other necessary modules

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

# --- Função para gerar o arquivo Excel completo com múltiplas abas ---
def generate_full_excel(all_data):
    workbook = openpyxl.Workbook()

    # --- Aba 1: Detalhes da Unidade ---
    # Remove a aba padrão criada ('Sheet') se ela existir
    if 'Sheet' in workbook.sheetnames:
        workbook.remove(workbook['Sheet'])

    sheet_unidade = workbook.create_sheet("Detalhes da Unidade", 0) # Cria na primeira posição
    sheet_unidade.append(["Localidade", "Unidade", "Data de Cadastro", "Responsável", "Quantidade de Funcionários", "Tipo de Piso da Unidade", "Tipo de Parede da Unidade"])

    # --- Abas de Medidas ---
    sheets_medidas = {
        "Vidro": workbook.create_sheet("Medidas dos Vidros"),
        "Área Interna": workbook.create_sheet("Medidas das Áreas Internas"),
        "Sanitário-Vestiário": workbook.create_sheet("Medidas dos Sanitários"),
        "Área Externa": workbook.create_sheet("Medidas das Áreas Externas")
    }

    # Definir cabeçalhos para as abas de medidas
    # Vidro tem Largura e Altura
    sheets_medidas["Vidro"].append(["Localidade", "Unidade", "Tipo de Medida", "Metragem (m²)", "Largura (m)", "Altura (m)", "Observações"])
    # Outras medidas têm Área Coberta/Descoberta
    sheets_medidas["Área Interna"].append(["Localidade", "Unidade", "Tipo de Medida", "Metragem (m²)", "Observações"])
    sheets_medidas["Sanitário-Vestiário"].append(["Localidade", "Unidade", "Tipo de Medida", "Metragem (m²)", "Observações"])
    sheets_medidas["Área Externa"].append(["Localidade", "Unidade", "Tipo de Medida", "Metragem (m²)", "Área Externa Coberta (m²)", "Área Externa Descoberta (m²)", "Observações"])


    for localidade_nome, unidades in all_data.items():
        for unidade_nome, unidade_data in unidades.items():
            # Adicionar detalhes da unidade na primeira aba
            sheet_unidade.append([
                localidade_nome,
                unidade_nome,
                unidade_data.get('data_cadastro', ''),
                unidade_data.get('responsavel', ''),
                unidade_data.get('qtd_func', ''),
                ", ".join(unidade_data.get('tipo_piso', [])),
                ", ".join(unidade_data.get('tipo_parede', []))
            ])

            # Adicionar medidas nas abas correspondentes
            for medida in unidade_data.get('medidas', []):
                tipo_medida_list = medida.get('tipo_medida', [])
                metragem = medida.get('metragem', '')
                obs = medida.get('obs', '')

                # Para Vidro
                if "Vidro" in tipo_medida_list:
                    largura = medida.get('largura', '')
                    altura = medida.get('altura', '')
                    sheets_medidas["Vidro"].append([
                        localidade_nome,
                        unidade_nome,
                        ", ".join(tipo_medida_list), # Pode ter outros tipos junto
                        metragem,
                        largura,
                        altura,
                        obs
                    ])

                # Para Área Interna
                if "Área Interna" in tipo_medida_list:
                    sheets_medidas["Área Interna"].append([
                        localidade_nome,
                        unidade_nome,
                        ", ".join(tipo_medida_list),
                        metragem,
                        obs
                    ])

                # Para Sanitário-Vestiário
                if "Sanitário-Vestiário" in tipo_medida_list:
                    sheets_medidas["Sanitário-Vestiário"].append([
                        localidade_nome,
                        unidade_nome,
                        ", ".join(tipo_medida_list),
                        metragem,
                        obs
                    ])

                # Para Área Externa
                if "Área Externa" in tipo_medida_list:
                    area_coberta = medida.get('area_externa_coberta', '')
                    area_descoberta = medida.get('area_externa_descoberta', '')
                    sheets_medidas["Área Externa"].append([
                        localidade_nome,
                        unidade_nome,
                        ", ".join(tipo_medida_list),
                        metragem,
                        area_coberta,
                        area_descoberta,
                        obs
                    ])

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0) # Rewind the buffer to the beginning
    return output.getvalue()


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
        tipo_piso_unidade = data.get('tipo_piso_unidade', [])
        tipo_parede_unidade = data.get('tipo_parede_unidade', [])


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
            'tipo_piso': tipo_piso_unidade,
            'tipo_parede': tipo_parede_unidade,
            'medidas': [] # Inicializa lista de medidas
        }

        salvar_dados(dados)

        # Geração do Excel completo com todas as abas
        all_data = carregar_dados() # Recarrega todos os dados para o Excel
        excel_content = generate_full_excel(all_data)

        # --- Envio de E-mail ---
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = FIXED_RECIPIENT_EMAIL
        # Assunto e nome do arquivo personalizados para a ação de salvar unidade
        msg['Subject'] = f"Unidade {unidade} Cadastrada/Atualizada - Relatório Completo"

        body = f"Olá,\n\nA unidade '{unidade}' foi cadastrada/atualizada. Segue o relatório completo em anexo.\n\nAtenciosamente,\nSeu Sistema de Cadastro"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        part.set_payload(excel_content)
        encoders.encode_base64(part)

        nome_arquivo = f'Dados_Unidade_{unidade}.xlsx' # Nome do arquivo personalizado
        part.add_header('Content-Disposition', f'attachment; filename=\"{nome_arquivo}\"')
        msg.attach(part)

        try:
            with smtplib.SMTP(EMAIL_SERVER, EMAIL_PORT) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASS)
                server.send_message(msg)

            return jsonify({"status": "success", "message": "Unidade salva e relatório completo enviado por e-mail com sucesso!"}), 200

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
            unidade_data = unidades[unidade_nome]
            unidade_data['tipo_piso'] = unidade_data.get('tipo_piso', [])
            unidade_data['tipo_parede'] = unidade_data.get('tipo_parede', [])
            # Adiciona a localidade ao dicionário de dados da unidade para o frontend
            unidade_data['localidade'] = localidade # Necessário para o displayLocalidade
            return jsonify(unidade_data)
    return jsonify({"error": "Unidade não encontrada"}), 404

@app.route('/salvar_medidas', methods=['POST'])
def salvar_medidas():
    try:
        data = request.json
        localidade = data.get('localidade')
        unidade = data.get('unidade')

        nova_medida = {
            "tipo_medida": data.get('tipo_medida', []),
            "metragem": data.get('metragem'),
            "area_externa_coberta": data.get('area_externa_coberta'),
            "area_externa_descoberta": data.get('area_externa_descoberta'),
            "obs": data.get('obs'),
            "largura": data.get('largura'),
            "altura": data.get('altura')
        }

        if not all([localidade, unidade, nova_medida['metragem']]) or not nova_medida['tipo_medida']:
            return jsonify({"status": "error", "message": "Campos essenciais da medida (localidade, unidade, tipo de medida e metragem) são obrigatórios!"}), 400

        dados = carregar_dados()

        if localidade in dados and unidade in dados[localidade]:
            # Limpeza de campos antigos, se existirem em dados legados
            if 'tipo_piso' in nova_medida: del nova_medida['tipo_piso']
            if 'tipo_parede' in nova_medida: del nova_medida['tipo_parede']

            dados[localidade][unidade]['medidas'].append(nova_medida)
            salvar_dados(dados)

            # Após salvar a medida, re-gerar e enviar o Excel completo
            all_data = carregar_dados()
            excel_content = generate_full_excel(all_data)

            msg = MIMEMultipart()
            msg['From'] = EMAIL_USER
            msg['To'] = FIXED_RECIPIENT_EMAIL
            # Assunto e nome do arquivo personalizados para a ação de adicionar medida
            msg['Subject'] = f"Medida Adicionada na Unidade {unidade} - Relatório Completo"

            body = f"Olá,\n\nUma nova medida foi adicionada à unidade '{unidade}'. Segue o relatório completo atualizado em anexo.\n\nAtenciosamente,\nSeu Sistema de Cadastro"
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            part.set_payload(excel_content)
            encoders.encode_base64(part)

            nome_arquivo = f'Dados_Unidade_{unidade}.xlsx' # Nome do arquivo personalizado
            part.add_header('Content-Disposition', f'attachment; filename=\"{nome_arquivo}\"')
            msg.attach(part)

            try:
                with smtplib.SMTP(EMAIL_SERVER, EMAIL_PORT) as server:
                    server.starttls()
                    server.login(EMAIL_USER, EMAIL_PASS)
                    server.send_message(msg)
                return jsonify({"status": "success", "message": "Medida adicionada e relatório completo enviado por e-mail com sucesso!"}), 200
            except Exception as e:
                print(f"Erro ao enviar e-mail após salvar medida: {e}")
                return jsonify({"status": "error", "message": f"Medida adicionada, mas houve erro ao enviar e-mail: {e}"}), 500

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

                # Após excluir a medida, re-gerar e enviar o Excel completo
                all_data = carregar_dados()
                excel_content = generate_full_excel(all_data)

                msg = MIMEMultipart()
                msg['From'] = EMAIL_USER
                msg['To'] = FIXED_RECIPIENT_EMAIL
                # Assunto e nome do arquivo personalizados para a ação de excluir medida
                msg['Subject'] = f"Medida Excluída da Unidade {unidade} - Relatório Completo"

                body = f"Olá,\n\nUma medida foi excluída da unidade '{unidade}'. Segue o relatório completo atualizado em anexo.\n\nAtenciosamente,\nSeu Sistema de Cadastro"
                msg.attach(MIMEText(body, 'plain', 'utf-8'))

                part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                part.set_payload(excel_content)
                encoders.encode_base64(part)

                nome_arquivo = f'Dados_Unidade_{unidade}.xlsx' # Nome do arquivo personalizado
                part.add_header('Content-Disposition', f'attachment; filename=\"{nome_arquivo}\"')
                msg.attach(part)

                try:
                    with smtplib.SMTP(EMAIL_SERVER, EMAIL_PORT) as server:
                        server.starttls()
                        server.login(EMAIL_USER, EMAIL_PASS)
                        server.send_message(msg)
                    return jsonify({"status": "success", "message": "Medida excluída e relatório completo enviado por e-mail com sucesso!"}), 200
                except Exception as e:
                    print(f"Erro ao enviar e-mail após excluir medida: {e}")
                    return jsonify({"status": "error", "message": f"Medida excluída, mas houve erro ao enviar e-mail: {e}"}), 500

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
        unidade = data.get('unidade') # Pega o nome da unidade antes de excluí-la

        dados = carregar_dados()

        if localidade in dados and unidade in dados[localidade]:
            del dados[localidade][unidade]
            if not dados[localidade]:
                del dados[localidade]
            salvar_dados(dados)

            # Após excluir a unidade, re-gerar e enviar o Excel completo
            all_data = carregar_dados()
            excel_content = generate_full_excel(all_data)

            msg = MIMEMultipart()
            msg['From'] = EMAIL_USER
            msg['To'] = FIXED_RECIPIENT_EMAIL
            # Assunto e nome do arquivo personalizados para a ação de excluir unidade
            msg['Subject'] = f"Unidade {unidade} Excluída - Relatório Completo Atualizado"

            body = f"Olá,\n\nA unidade '{unidade}' foi excluída. Segue o relatório completo atualizado em anexo.\n\nAtenciosamente,\nSeu Sistema de Cadastro"
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            part.set_payload(excel_content)
            encoders.encode_base64(part)

            # Nome do arquivo após exclusão: genérico com data
            nome_arquivo = f'Relatorio_Completo_Apos_Exclusao_{datetime.date.today().strftime("%Y%m%d")}.xlsx'
            part.add_header('Content-Disposition', f'attachment; filename=\"{nome_arquivo}\"')
            msg.attach(part)

            try:
                with smtplib.SMTP(EMAIL_SERVER, EMAIL_PORT) as server:
                    server.starttls()
                    server.login(EMAIL_USER, EMAIL_PASS)
                    server.send_message(msg)
                return jsonify({"status": "success", "message": "Unidade excluída e relatório completo enviado por e-mail com sucesso!"}), 200
            except Exception as e:
                print(f"Erro ao enviar e-mail após excluir unidade: {e}")
                return jsonify({"status": "error", "message": f"Unidade excluída, mas houve erro ao enviar e-mail: {e}"}), 500

        else:
            return jsonify({"status": "error", "message": "Localidade ou unidade não encontrada."}), 404
    except Exception as e:
        print(f"Erro ao excluir unidade: {e}")
        return jsonify({"status": "error", "message": f"Erro interno ao excluir unidade: {e}"}), 500

if __name__ == '__main__':
    app.run(debug=True)