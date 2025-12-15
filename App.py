from flask import Flask, jsonify, request
from flask_cors import CORS
import json
import os

app = Flask(__name__)
CORS(app)

# -------------------------------------------------------
# LADEN VAN DE KEUZEBOM
# -------------------------------------------------------

KEUZEBESTAND = os.path.join(os.path.dirname(__file__), "keuzeboom.json")

with open(KEUZEBESTAND, "r", encoding="utf-8") as f:
    TREE = json.load(f)

def find_node(node_id):
    """Zoekt een node op basis van ID."""
    for n in TREE:
        if n.get("id") == node_id:
            return n
    return None


# -------------------------------------------------------
# HULPFUNCTIE VOOR HET FORMATEREN VAN OPTIES
# -------------------------------------------------------

def extract_answer_text(node):
    if not node:
        return ""
    txt = node.get("text", "")
    return txt.replace("Antw:", "").strip()


def compute_options(node):
    """Geeft de juiste antwoordopties terug op basis van het nodetype."""
    if node["type"] == "vraag":
        return [extract_answer_text(find_node(n)) for n in node.get("next", [])]
    return []


# -------------------------------------------------------
# API: STARTPUNT
# -------------------------------------------------------

@app.route("/api/start", methods=["GET"])
def api_start():
    start_id = "BFC"  # vaste startnode
    node = find_node(start_id)

    if not node:
        return jsonify({"error": "Startnode ontbreekt"}), 500

    return jsonify({
        "id": node["id"],
        "type": node["type"],
        "text": node["text"],
        "options": compute_options(node),
        "next": node.get("next", [])
    })


# -------------------------------------------------------
# API: NEXT NODE (volgende vraag / systeem / antwoord)
# -------------------------------------------------------

@app.route("/api/next", methods=["POST"])
def api_next():
    data = request.json
    next_id = data.get("next_id")

    if not next_id:
        return jsonify({"error": "next_id ontbreekt"}), 400

    node = find_node(next_id)
    if not node:
        return jsonify({"error": f"Node '{next_id}' niet gevonden"}), 400

    return jsonify({
        "id": node["id"],
        "type": node["type"],
        "text": node["text"],
        "options": compute_options(node),
        "next": node.get("next", [])
    })


# -------------------------------------------------------
# LOCAL RUN (wordt genegeerd op Render)
# -------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
