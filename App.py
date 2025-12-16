from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# =========================
# GLOBAL STATE (simpel, bewust)
# =========================
STATE = {
    "system": None
}

# =========================
# DATA LADEN
# =========================
with open(os.path.join(BASE_DIR, "keuzeboom.json"), encoding="utf-8") as f:
    KEUZEBOOM = json.load(f)

with open(os.path.join(BASE_DIR, "Prijstabellen coatingsystemen.json"), encoding="utf-8") as f:
    PRIJS_DATA = json.load(f)

# =========================
# HULPFUNCTIES
# =========================
def get_node(node_id):
    return KEUZEBOOM.get(node_id)


def expand_node(node):
    """
    Vervangt next-id’s door volledige nodes
    """
    expanded = dict(node)
    expanded_next = []

    for nid in node.get("next", []):
        n = get_node(nid)
        if n:
            expanded_next.append({
                "id": n["id"],
                "type": n["type"],
                "text": n.get("text", "")
            })

    expanded["next"] = expanded_next
    return expanded


# =========================
# API ENDPOINTS
# =========================

@app.route("/api/start", methods=["GET"])
def start():
    STATE["system"] = None
    start_node = get_node("BFC")  # start-node id
    return jsonify(expand_node(start_node))


@app.route("/api/next", methods=["POST"])
def next_node():
    data = request.json
    node_id = data.get("node_id")
    choice_index = data.get("choice")

    if node_id is None or choice_index is None:
        return jsonify({"error": "node_id en choice verplicht"}), 400

    node = get_node(node_id)
    if not node:
        return jsonify({"error": "node niet gevonden"}), 404

    try:
        next_id = node["next"][choice_index]
    except (IndexError, KeyError):
        return jsonify({"error": "ongeldige keuze"}), 400

    next_node = get_node(next_id)
    if not next_node:
        return jsonify({"error": "volgende node niet gevonden"}), 404

    # =========================
    # SYSTEEM GEKOZEN → PRIJSFASE
    # =========================
    if next_node.get("type") == "systeem":
        STATE["system"] = next_node.get("text")

        response = expand_node(next_node)
        response["price_ready"] = True  # 🔑 EXPLICIET SIGNAAL
        response["system"] = STATE["system"]
        return jsonify(response)

    # Normale vraag / antwoord
    return jsonify(expand_node(next_node))


@app.route("/api/price", methods=["POST"])
def calculate_price():
    data = request.json

    m2 = data.get("m2")
    ruimtes = str(data.get("ruimtes"))

    system = STATE.get("system")
    if not system:
        return jsonify({"error": "geen systeem gekozen"}), 400

    if not m2 or not ruimtes:
        return jsonify({"error": "m2 en ruimtes verplicht"}), 400

    system_key = system.replace("Sys: ", "").strip()

    prijsinfo = PRIJS_DATA.get(system_key)
    if not prijsinfo:
        return jsonify({"error": "prijssysteem niet gevonden"}), 404

    try:
        m2 = float(m2)
    except ValueError:
        return jsonify({"error": "ongeldige m2"}), 400

    staffel_prijs = None
    for staffel in prijsinfo["staffels"]:
        if staffel["min"] <= m2 <= staffel["max"]:
            staffel_prijs = staffel["prijs"]
            break

    if staffel_prijs is None:
        return jsonify({"error": "geen staffel gevonden"}), 400

    ruimte_toeslag = prijsinfo["ruimtes"].get(ruimtes, 0)

    totaal = (staffel_prijs * m2) + ruimte_toeslag

    return jsonify({
        "systeem": system_key,
        "m2": m2,
        "ruimtes": ruimtes,
        "prijs_per_m2": staffel_prijs,
        "ruimte_toeslag": ruimte_toeslag,
        "totaalprijs": round(totaal, 2)
    })


# =========================
# HEALTHCHECK
# =========================
@app.route("/")
def health():
    return "Keuzegids backend OK"
