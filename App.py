import json
import re
from flask import Flask, request, jsonify
from flask_cors import CORS

# -------------------------------------------------------
# INITIALISATIE
# -------------------------------------------------------
app = Flask(__name__)
CORS(app)

KEUZEBESTAND = "keuzeboom.json"
PRIJSBESTAND = "Prijstabellen coatingsystemen.json"

# Boom & prijzen laden
with open(KEUZEBESTAND, "r", encoding="utf-8") as f:
    boom = json.load(f)

with open(PRIJSBESTAND, "r", encoding="utf-8") as f:
    pdata = json.load(f)

prijzen = pdata.get("Blad1", pdata)


# -------------------------------------------------------
# HELPERS
# -------------------------------------------------------
def clean_answer(txt):
    return re.sub(r"^(Antw:|Sys:|Xtr:)\s*", "", txt).strip()

def find_node(node_id):
    if node_id == "END":
        return {"id": "END", "type": "end", "text": "Einde", "next": []}
    return next((n for n in boom if n["id"] == node_id), None)

def staffel_index(staffels, opp):
    if opp < 30:
        return 0
    for i, s in enumerate(staffels):
        clean = s.replace("+", "")
        parts = clean.split("-")
        try:
            low = float(parts[0])
            high = float(parts[1]) if len(parts) > 1 else 999999
        except:
            continue
        if low <= opp <= high:
            return i
    return len(staffels) - 1

def bereken_prijs(systeem, opp, ruimtes):
    sd = prijzen.get(systeem)
    if not sd:
        return None

    staffels = sd["staffel"]
    prijzen_m2 = sd["prijzen"][str(ruimtes)]

    idx = staffel_index(staffels, opp)
    pm2 = prijzen_m2[idx]
    totaal = pm2 * opp

    return {
        "systeem": systeem,
        "oppervlakte": opp,
        "ruimtes": ruimtes,
        "prijs_m2": pm2,
        "basis": round(totaal, 2),
        "staffel": staffels[idx],
    }


# -------------------------------------------------------
# API ROUTES
# -------------------------------------------------------

@app.route("/api/start", methods=["GET"])
def start():
    """Startvraag (BFC) ophalen."""
    node = find_node("BFC")
    answers = [clean_answer(find_node(n)["text"]) for n in node["next"]]

    return jsonify({
        "node_id": "BFC",
        "type": node["type"],
        "text": node["text"],
        "answers": answers,
        "next": node["next"]
    })


@app.route("/api/next", methods=["POST"])
def next_step():
    """Ontvangt node_id + keuze, geeft volgende node terug."""
    data = request.json
    node_id = data.get("node_id")
    choice = data.get("choice")

    current = find_node(node_id)
    next_id = current["next"][choice]
    node = find_node(next_id)

    response = {
        "node_id": next_id,
        "type": node["type"],
        "text": node["text"],
        "answers": [],
        "next": node["next"]
    }

    if node["type"] == "vraag":
        response["answers"] = [
            clean_answer(find_node(n)["text"]) for n in node["next"]
        ]

    if node["type"] == "antwoord":
        response["answer"] = clean_answer(node["text"])

    if node["type"] == "systeem":
        response["system"] = clean_answer(node["text"])

    if node["type"] == "afw":
        response["systems"] = []
        for sid in node["next"]:
            s_node = find_node(sid)
            response["systems"].append({
                "id": sid,
                "name": clean_answer(s_node["text"])
            })

    return jsonify(response)


@app.route("/api/price", methods=["POST"])
def price():
    """Prijsberekening voor gekozen systeem."""
    data = request.json
    systeem = data["system"]
    opp = float(data["oppervlakte"])
    ruimtes = int(data["ruimtes"])

    pr = bereken_prijs(systeem, opp, ruimtes)
    return jsonify(pr)


# -------------------------------------------------------
# START SERVER
# -------------------------------------------------------
@app.route("/")
def index():
    return "Keuzegids API draait ✔"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
