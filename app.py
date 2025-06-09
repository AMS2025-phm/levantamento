from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/exportar_excel_e_enviar_email', methods=['POST'])
def exportar_excel_e_enviar_email():
    selected_unit_str = request.form.get('selected_unit_to_export')
    print(f"DEBUG 🔍 selected_unit_str recebido: '{selected_unit_str}'")

    parts = (selected_unit_str or "").split(" - ", 1)
    if len(parts) != 2:
        local = parts[0] if parts else "local"
        unidade = parts[1] if len(parts) > 1 else "unidade"
    else:
        local, unidade = parts

    print(f"DEBUG 🔍 partes extraídas: local='{local}', unidade='{unidade}'")

    nome_arquivo = f"{unidade} - {local}.xlsx".replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")

    print(f"DEBUG 🔍 nome do arquivo gerado: {nome_arquivo}")
    return jsonify({"status": "success", "filename": nome_arquivo})

if __name__ == '__main__':
    app.run(debug=True)
