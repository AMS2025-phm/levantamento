from flask import Flask, render_template, request, jsonify
import os
app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/exportar_excel_e_enviar_email', methods=['POST'])
def exportar_excel_e_enviar_email():
    selected_unit_str = request.form.get('selected_unit_to_export')
    parts = selected_unit_str.split(" - ", 1)
    if len(parts) != 2:
        return jsonify({"status": "error", "message": "Formato inválido de unidade selecionada."}), 400
    local, unidade = parts
    nome_arquivo = f"{unidade} - {local}.xlsx".replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace("|", "_")
    return jsonify({"status": "success", "filename": nome_arquivo})

if __name__ == '__main__':
    app.run(debug=True)
