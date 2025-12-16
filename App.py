from flask import Flask, request, jsonify
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app)

# =========================
# DATA LADEN
# =========================
with open("keuzeboom.json", encoding="utf-8") as f:
    KEUZEBOOM = json.load(f)

with open("Prijstabellen coatingsystemen.json", encoding="utf-8") as f:
    PRIJZEN = json.load(f)

# Index voor snelle lookup
NODE_INDEX = {node["id"]: node for node in KEUZEBOOM}

# =========================
# HULPFUNCTIES
# =========================
def expand_node(node):
    """
    Breidt next: ["A","B"] uit naar volledige nodes
    BEHOUDT bestaande structuur
    """
    expanded = dict(node)
    expanded_next = []

    for nid in node.get("next", []):
        next_node = NODE_INDEX.get(nid)
        if next_node:
            expanded_next.append(dict(next_node))

    expanded["next"] = expanded_next
    return expanded


def get_staffel_index(oppervlakte, staffels):
    for i, s in enumerate(staffels):
        if "+" in s:
            return i
        onder, boven = s.split("-")
        if float(onder) <= oppervlakte <= float(boven):
            return i
    return len(staffels) - 1


# =========================
# API: START
# =========================
@app.route("/api/start", methods=["GET"])
def start():
    # gebruik eerste node als start (zoals eerder)
    start_node = KEUZEBOOM[0]
    return jsonify(expand_node(start_node))


# =========================
# API: NEXT
# =========================
@app.route("/api/next", methods=["POST"])
def next_node():
    data = request.json
    node_id = data.get("node_id")
    choice = data.get("choice")

    if node_id not in NODE_INDEX:
        return jsonify({"error": "Node niet gevonden"}), 400

    node = NODE_INDEX[node_id]
    next_ids = node.get("next", [])

    if choice is None or choice >= len(next_ids):
        return jsonify({"error": "Ongeldige keuze"}), 400

    next_id = next_ids[choice]
    next_node = NODE_INDEX.get(next_id)

    if not next_node:
        return jsonify({"error": "Volgende node niet gevonden"}), 404

    return jsonify(expand_node(next_node))


# =========================
# API: PRIJSBEREKENING
# =========================
@app.route("/api/calculate", methods=["POST"])
def calculate():
    data = request.json
    systeem = data.get("system")
    oppervlakte = data.get("oppervlakte")
    ruimtes = data.get("ruimtes")

    if systeem not in PRIJZEN:
        return jsonify({"error": "Onbekend systeem"}), 400

    prijsdata = PRIJZEN[systeem]
    staffels = prijsdata["staffel"]
    prijzen = prijsdata["prijzen"]

    staffel_index = get_staffel_index(oppervlakte, staffels)
    ruimte_key = "3" if ruimtes >= 3 else str(ruimtes)

    prijs_pm2 = prijzen[ruimte_key][staffel_index]
    totaal = round(prijs_pm2 * oppervlakte, 2)

    return jsonify({
        "systeem": systeem,
        "oppervlakte": oppervlakte,
        "ruimtes": ruimtes,
        "staffel": staffels[staffel_index],
        "prijs_per_m2": prijs_pm2,
        "basisprijs": totaal
    })


# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)
