from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json

app = FastAPI()

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# DATA LADEN
# =========================
with open("keuzeboom.json", encoding="utf-8") as f:
    KEUZEBOOM = json.load(f)

with open("Prijstabellen coatingsystemen.json", encoding="utf-8") as f:
    PRIJZEN = json.load(f)

# =========================
# BESLISBOOM HELPERS
# =========================
def find_node(node_id: str):
    for node in KEUZEBOOM:
        if node.get("id") == node_id:
            return node
    return None


def normalize_node(node):
    """
    Zorgt dat frontend altijd dezelfde structuur krijgt
    """
    return {
        "id": node.get("id"),
        "type": node.get("type"),
        "text": node.get("text"),
        "answers": node.get("answers", []),
        "next": node.get("next", []),
        "system": node.get("system"),
    }

# =========================
# API: START
# =========================
@app.get("/api/start")
def start():
    if not KEUZEBOOM:
        raise HTTPException(500, "Keuzeboom is leeg")
    return normalize_node(KEUZEBOOM[0])

# =========================
# API: NEXT
# =========================
class NextRequest(BaseModel):
    node_id: str
    choice: int

@app.post("/api/next")
def next_node(req: NextRequest):
    current = find_node(req.node_id)
    if not current:
        raise HTTPException(404, "Node niet gevonden")

    try:
        next_id = current["next"][req.choice]
    except Exception:
        raise HTTPException(400, "Ongeldige keuze")

    next_node = find_node(next_id)
    if not next_node:
        raise HTTPException(404, "Volgende node niet gevonden")

    return normalize_node(next_node)

# =========================
# PRIJSBEREKENING HELPERS
# =========================
def staffel_index(oppervlakte: float, staffels: list[str]) -> int:
    """
    Bepaalt de staffel-index op basis van staffel-strings zoals:
    "30-50", "50-70", "300+"
    """
    for i, s in enumerate(staffels):
        if "+" in s:
            return i

        onder, boven = s.split("-")
        if float(onder) <= oppervlakte <= float(boven):
            return i

    return len(staffels) - 1


# =========================
# API: CALCULATE
# =========================
class CalculateRequest(BaseModel):
    system: str
    oppervlakte: float
    ruimtes: int

@app.post("/api/calculate")
def calculate(req: CalculateRequest):
    systeem = req.system

    if systeem not in PRIJZEN:
        raise HTTPException(400, "Onbekend systeem")

    data = PRIJZEN[systeem]

    staffels = data["staffel"]
    prijzen = data["prijzen"]

    staffel_i = staffel_index(req.oppervlakte, staffels)

    # Ruimtes: 1, 2 of 3+
    ruimtes_key = "3" if req.ruimtes >= 3 else str(req.ruimtes)

    try:
        prijs_pm2 = prijzen[ruimtes_key][staffel_i]
    except Exception:
        raise HTTPException(400, "Prijs niet gevonden voor deze combinatie")

    basisprijs = prijs_pm2 * req.oppervlakte

    return {
        "systeem": systeem,
        "oppervlakte": req.oppervlakte,
        "ruimtes": req.ruimtes,
        "staffel": staffels[staffel_i],
        "prijs_per_m2": prijs_pm2,
        "basisprijs": round(basisprijs, 2),
    }
