"""Interfaccia web: pagina per caricare una foto e endpoint JSON /predict.

Avvio:
    PLANTCARE_CKPT=models/baseline/model.pt plantcare serve
Poi aprire http://127.0.0.1:8000
"""

from __future__ import annotations

import io
import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from PIL import Image, UnidentifiedImageError

from plantcare.predict import Predictor

MAX_BYTES = 10 * 1024 * 1024

PAGE = """<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PlantCare</title>
<style>
:root{--bg:#f6f7f4;--fg:#1d2420;--card:#fff;--accent:#2f6b3b;--muted:#5d6b62;--warn:#8a5a00;--warnbg:#fff4dc}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#121613;--fg:#e6ece7;--card:#1c231e;--accent:#7fc08f;--muted:#9aa89e;--warn:#f0c674;--warnbg:#332a14}}
:root[data-theme="dark"]{--bg:#121613;--fg:#e6ece7;--card:#1c231e;--accent:#7fc08f;--muted:#9aa89e;--warn:#f0c674;--warnbg:#332a14}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:720px;margin:0 auto;padding:16px}
h1{font-size:1.6rem;color:var(--accent);margin:8px 0}
.card{background:var(--card);border-radius:12px;padding:16px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}
input[type=file]{width:100%}
button{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:10px 18px;font-size:1rem;cursor:pointer}
.muted{color:var(--muted);font-size:.9rem}
.warn{background:var(--warnbg);color:var(--warn);border-radius:8px;padding:8px 12px;margin:6px 0}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:6px 4px;border-bottom:1px solid #8883}
img{max-width:100%;border-radius:10px}
</style></head>
<body><main>
<h1>PlantCare</h1>
<p class="muted">Carica una foto ravvicinata di foglia, frutto o insetto. Il risultato è un supporto, non una diagnosi.</p>
<div class="card">
<form id="f"><input type="file" name="file" accept="image/*" required>
<p><button type="submit">Analizza</button></p></form>
<div id="preview"></div>
</div>
<div id="out"></div>
<script>
const f=document.getElementById('f'),out=document.getElementById('out'),pv=document.getElementById('preview');
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
f.file.addEventListener('change',()=>{const file=f.file.files[0];if(file){pv.innerHTML='<img alt="anteprima" src="'+URL.createObjectURL(file)+'">';}});
f.addEventListener('submit',async e=>{e.preventDefault();out.textContent='Analisi in corso...';
const fd=new FormData(f);
try{const r=await fetch('/predict',{method:'POST',body:fd});const j=await r.json();
if(!r.ok){out.innerHTML='<div class="card warn">'+esc(j.detail||'Errore')+'</div>';return;}
let h='<div class="card">';
for(const [head,v] of Object.entries(j.heads)){
 h+='<h3>'+esc(head)+': '+esc(v.answer)+'</h3><table>';
 for(const c of v.candidates){h+='<tr><td>'+esc(c.label)+'</td><td>'+(c.probability*100).toFixed(1)+'%</td></tr>';}
 h+='</table>';}
for(const w of j.warnings){h+='<div class="warn">'+esc(w)+'</div>';}
h+='<p class="muted">'+esc(j.disclaimer)+'</p></div>';
out.innerHTML=h;}catch(err){out.innerHTML='<div class="card warn">Errore di rete.</div>';}
});
</script></main></body></html>"""


def create_app(checkpoint: str | Path | None = None, abstain_threshold: float = 0.5) -> FastAPI:
    ckpt = checkpoint or os.environ.get("PLANTCARE_CKPT")
    app = FastAPI(title="PlantCare", version="0.2.0")
    state: dict[str, Predictor] = {}
    if ckpt:
        state["predictor"] = Predictor(ckpt, abstain_threshold=abstain_threshold)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGE

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "model_loaded": "predictor" in state}

    @app.post("/predict")
    async def predict(file: UploadFile = File(...)) -> dict:
        if "predictor" not in state:
            raise HTTPException(status_code=503, detail="Modello non caricato: impostare PLANTCARE_CKPT")
        data = await file.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="File troppo grande (max 10 MB)")
        try:
            img = Image.open(io.BytesIO(data))
            img.verify()
            img = Image.open(io.BytesIO(data))
        except (UnidentifiedImageError, OSError):
            raise HTTPException(status_code=400, detail="File non riconosciuto come immagine")
        return state["predictor"].predict(img)

    return app
