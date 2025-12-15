from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json

app = FastAPI()

# CORS (frontend mag backend aanroepen)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =======================
# JSON LADEN
# =======================
with open("keuzeboom.json", "r", encoding="utf-8") as f:
    KEUZEBoom = json.load(f)

# =======================
# HULPFUNCTIES
# =======================
def find_node(node_id: str):
    for node in KEUZEBoom:
        if node.get("id") == node_id:
            return node
    return None

# =======================
# START
# =======================
@app.get("/api/start")
def start():
    start_node = KEUZEBoom[0]
    return start_node

# =======================
# NEXT
# =======================
class NextRequest(BaseModel):
    node_id: str
    choice: int

@app.post("/api/next")
def next_node(req: NextRequest):
    current_node = find_node(req.node_id)

    if not current_node:
        raise HTTPException(status_code=400, detail="Huidige node niet gevonden")

    if "next" not in current_node:
        raise HTTPException(status_code=400, detail="Node heeft geen vervolg")

    if req.choice >= len(current_node["next"]):
        raise HTTPException(status_code=400, detail="Ongeldige keuze-index")

    # 🔑 DIT IS DE BELANGRIJKSTE REGEL
    next_node_id = current_node["next"][req.choice]

    next_node = find_node(next_node_id)

    if not next_node:
        raise HTTPException(status_code=400, detail="Volgende node niet gevonden")

    return next_node
