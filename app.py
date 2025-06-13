from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
import json
import os
import datetime
import openpyxl
import io
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

app = Flask(__name__)
# Chave secreta para sessões (essencial para login e flash messages)
app.secret_key = os.urandom(24)

# Nomes dos arquivos de dados
ARQUIVO_DADOS = "localidades.json"
ARQUIVO_USUARIOS = "users.json"

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
FIXED_RECIPIENT_EMAIL = os.environ.get('FIXED_RECIPIENT_EMAIL')

# --- Funções Auxiliares de Dados ---

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

# --- Rotas de Autenticação ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        users = carregar_dados(ARQUIVO_USUARIOS)
        
        if username in users and users[username] == password:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            flash('Nome de usuário ou senha inválidos.', 'error')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        users = carregar_dados(ARQUIVO_USUARIOS)

        if username in users:
            flash('Este nome de usuário já existe.', 'error')
        elif password != confirm_password:
            flash('As senhas não coincidem.', 'error')
        else:
            users[username] = password
            salvar_dados(users, ARQUIVO_USUARIOS)
            flash('Cadastro realizado com sucesso! Faça o login.', 'success')
            return redirect(url_for('login'))
            
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

# --- Rota Principal da Aplicação ---

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    data_hoje = datetime.date.today().strftime('%Y-%m-%d')
    return render_template(
        'index.html',
        data_hoje=data_hoje,
        tipos_piso=TIPOS_PISO,
        tipos_medida=TIPOS_MEDIDA,
        tipos_parede=TIPOS_PAREDE
    )

# --- Rotas da API (CRUD e Exportação) ---

@app.route('/salvar', methods=['POST'])
def salvar_unidade():
    if not session.get('logged_in'):
        return jsonify({"status": "error", "message": "Acesso não autorizado"}), 401
    
    data = request.json
    localidade = data.get('localidade')
    unidade = data.get('unidade')

    if not localidade or not unidade:
        return jsonify({"status": "error", "message": "Localidade e Unidade são obrigatórios."}), 400

    localidades = carregar_dados(ARQUIVO_DADOS)
    if localidade not in localidades:
        localidades[localidade] = {}

    vidros_altos = data.get('vidros_altos', 'Não')
    vidros_altos_risco = data.get('vidros_altos_risco', False) if vidros_altos == 'Sim' else False

    localidades[localidade][unidade] = {
        "data": data.get('data'),
        "responsavel": data.get('responsavel'),
        "qtd_func": data.get('qtd_func'),
        "piso": data.get('piso', []),
        "paredes": data.get('paredes', []),
        "vidros_altos": vidros_altos,
        "vidros_altos_risco": vidros_altos_risco,
        "estacionamento": data.get('estacionamento', False),
        "gramado": data.get('gramado', False),
        "curativo": data.get('curativo', False),
        "vacina": data.get('vacina', False),
        "medidas": data.get('medidas', [])
    }
    salvar_dados(localidades, ARQUIVO_DADOS)
    return jsonify({"status": "success", "message": "Unidade salva com sucesso!"})

@app.route('/unidades', methods=['GET'])
def get_unidades():
    if not session.get('logged_in'):
        return jsonify([]), 401
        
    localidades = carregar_dados(ARQUIVO_DADOS)
    lista_unidades = []
    for local, unidades in sorted(localidades.items()):
        for unidade in sorted(unidades.keys()):
            lista_unidades.append(f"{local}|{unidade}")
    return jsonify(lista_unidades)

@app.route('/carregar', methods=['GET'])
def carregar_unidade():
    if not session.get('logged_in'):
        return jsonify({"status": "error", "message": "Acesso não autorizado"}), 401
        
    localidade = request.args.get('localidade')
    unidade = request.args.get('unidade')
    localidades = carregar_dados(ARQUIVO_DADOS)
    
    data = localidades.get(localidade, {}).get(unidade)
    if data:
        return jsonify({"status": "success", "data": data})
    return jsonify({"status": "error", "message": "Unidade não encontrada."}), 404

@app.route('/deletar', methods=['POST'])
def deletar_unidade():
    if not session.get('logged_in'):
        return jsonify({"status": "error", "message": "Acesso não autorizado"}), 401
        
    data = request.json
    localidade = data.get('localidade')
    unidade = data.get('unidade')
    localidades = carregar_dados(ARQUIVO_DADOS)

    if localidade in localidades and unidade in localidades[localidade]:
        del localidades[localidade][unidade]
        if not localidades[localidade]:
            del localidades[localidade]
        salvar_dados(localidades, ARQUIVO_DADOS)
        return jsonify({"status": "success", "message": "Unidade deletada com sucesso."})
    return jsonify({"status": "error", "message": "Unidade não encontrada."}), 404

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
    
    # Aba Detalhes (continua igual)
    ws_detalhe = wb.active
    ws_detalhe.title = "Detalhe"
    
    ws_detalhe.append([
        "Localidade", "Unidade", "Data", "Responsável", "Tipo de Piso", 
        "Vidros Altos", "Vidros Altos - Risco", "Paredes", "Estacionamento", 
        "Gramado", "Sala de Curativo", "Sala de Vacina", "Qtd Funcionários"
    ])
    ws_detalhe.append([
        local, 
        unidade, 
        info.get("data", ""), 
        info.get("responsavel", ""),
        ", ".join(info.get("piso", [])), 
        info.get("vidros_altos", ""),
        "Sim" if info.get("vidros_altos_risco") else "Não",
        ", ".join(info.get("paredes", [])),
        "Sim" if info.get("estacionamento") else "Não",
        "Sim" if info.get("gramado") else "Não",
        "Sim" if info.get("curativo") else "Não",
        "Sim" if info.get("vacina") else "Não",
        info.get("qtd_func", "")
    ])

    # ===== INÍCIO DA NOVA LÓGICA PARA ABAS DE MEDIDAS =====
    
    todas_as_medidas = info.get("medidas", [])
    
    # Define as categorias e os nomes das abas
    categorias = {
        "Vidros": [m for m in todas_as_medidas if m.get("tipo") == "Vidro"],
        "Áreas Externas": [m for m in todas_as_medidas if m.get("tipo") == "Área Externa"],
        "Áreas Internas": [m for m in todas_as_medidas if m.get("tipo") == "Área Interna"],
        "Sanitários e Vestiários": [m for m in todas_as_medidas if m.get("tipo") == "Sanitário-Vestiário"]
    }
    
    header_medidas = ["Tipo", "Altura (m)", "Largura (m)", "Quantidade", "m² Total"]
    
    # Itera sobre cada categoria e cria uma aba se houver dados
    for nome_aba, medidas_da_categoria in categorias.items():
        if not medidas_da_categoria:
            continue # Pula para a próxima categoria se não houver medidas

        # Cria a aba e adiciona o cabeçalho
        ws = wb.create_sheet(title=nome_aba)
        ws.append(header_medidas)
        
        # Adiciona os dados de cada medida na aba
        for medida in medidas_da_categoria:
            altura = medida.get("altura") or 0
            largura = medida.get("largura") or 0
            qtd = medida.get("qtd") or 1
            m2_total = altura * largura * qtd
            ws.append([medida.get("tipo"), altura, largura, qtd, m2_total])

    # ===== FIM DA NOVA LÓGICA =====

    # Salva o arquivo Excel em memória
    excel_buffer = io.BytesIO()
    wb.save(excel_buffer)
    excel_content = excel_buffer.getvalue()
    excel_buffer.close()

    # Verifica as configurações de e-mail
    if not all([EMAIL_USER, EMAIL_PASS, EMAIL_SERVER, FIXED_RECIPIENT_EMAIL]):
        return jsonify({"status": "error", "message": "Configurações de e-mail incompletas no servidor."}), 500

    # Monta e envia o e-mail
	# ... dentro da função exportar_excel_e_enviar_email()
	def sanitizar_nome(nome):
    	return re.sub(r'[^a-zA-Z0-9_-]', '_', nome)

	local_sanitizado = sanitizar_nome(local)
	unidade_sanitizado = sanitizar_nome(unidade)
	nome_arquivo = f"Levantamento_{local_sanitizado}_{unidade_sanitizado}.xlsx"
    # nome_arquivo = f"Levantamento_{local}_{unidade}.xlsx"
    
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = FIXED_RECIPIENT_EMAIL
    msg['Subject'] = f"Levantamento de Medidas: {local} - {unidade}"
    
    body = f"Segue em anexo o levantamento de medidas para a unidade {unidade} na localidade {local}."
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
        return jsonify({"status": "success", "message": "Unidade salva e Excel enviado por e-mail com sucesso!"})
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
        return jsonify({"status": "error", "message": f"Erro ao enviar e-mail: {e}"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)