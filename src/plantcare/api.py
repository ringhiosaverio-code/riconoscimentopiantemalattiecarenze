"""Interfaccia web e API di PlantCare.

Avvio locale:
    PLANTCARE_CKPT=models/baseline/model.pt PLANTCARE_FEEDBACK_DIR=feedback plantcare serve
Poi aprire http://127.0.0.1:8000 (documentazione API su /docs).

Variabili d'ambiente:
    PLANTCARE_CKPT          checkpoint del modello (senza, la pagina funziona ma /predict risponde 503)
    PLANTCARE_FEEDBACK_DIR  cartella per le conferme/correzioni degli agronomi (senza, il feedback è disattivato)
"""

from __future__ import annotations

import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from plantcare.kb import KnowledgeBase
from plantcare.labelmap import DEFAULT_MAP_PATH, load_label_map
from plantcare.predict import Predictor
from plantcare.taxonomy import DEFAULT_TAXONOMY_PATH, load_taxonomy

ROOT_CONFIG = Path(__file__).resolve().parents[2] / "configs"
KNOWLEDGE_PATH = ROOT_CONFIG / "knowledge_base.yaml"
SOURCES_PATH = ROOT_CONFIG / "sources.yaml"


def load_yaml(path: Path) -> dict:
    import yaml
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}

MAX_BYTES = 10 * 1024 * 1024
MAX_COMMENT = 500

PAGE = """<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PlantCare</title>
<style>
:root{--bg:#f6f7f4;--fg:#1d2420;--card:#fff;--accent:#2f6b3b;--muted:#4f5d54;--warn:#7a4f00;--warnbg:#fff4dc;--line:#0002;--bar:#2f6b3b33}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#121613;--fg:#e6ece7;--card:#1c231e;--accent:#7fc08f;--muted:#a9b6ad;--warn:#f0c674;--warnbg:#332a14;--line:#fff2;--bar:#7fc08f33}}
:root[data-theme="dark"]{--bg:#121613;--fg:#e6ece7;--card:#1c231e;--accent:#7fc08f;--muted:#a9b6ad;--warn:#f0c674;--warnbg:#332a14;--line:#fff2;--bar:#7fc08f33}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,sans-serif}
main{max-width:760px;margin:0 auto;padding:16px}
h1{font-size:1.7rem;color:var(--accent);margin:8px 0 4px}
h2{font-size:1.1rem;margin:0 0 6px}
h3{margin:4px 0}
.card{background:var(--card);border-radius:12px;padding:16px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.muted{color:var(--muted);font-size:.92rem}
button{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:11px 18px;font-size:1rem;cursor:pointer;min-height:44px}
button.secondary{background:transparent;color:var(--accent);border:1px solid var(--accent)}
button:disabled{opacity:.5}
input[type=file]{width:100%;font-size:1rem;padding:8px 0}
textarea,select{width:100%;font:inherit;padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--fg)}
.warn{background:var(--warnbg);color:var(--warn);border-radius:8px;padding:10px 12px;margin:8px 0}
.lab{border-left:4px solid var(--warn);padding-left:10px}
video,img.preview{width:100%;max-height:360px;object-fit:cover;border-radius:10px;background:#000;display:block;margin-top:8px}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.reader{border-top:1px solid var(--line);padding-top:10px;margin-top:10px}
.cand{display:grid;grid-template-columns:1fr 64px;gap:6px;align-items:center;margin:4px 0}
.bar{position:relative;background:var(--line);border-radius:6px;height:22px;overflow:hidden}
.bar span{position:absolute;inset:0 auto 0 0;background:var(--bar)}
.bar em{position:relative;padding:0 6px;font-style:normal;font-size:.88rem;line-height:22px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block}
.p{text-align:right;font-variant-numeric:tabular-nums}
ul.guide{padding-left:20px;margin:6px 0}
footer{margin:24px 0;font-size:.85rem;color:var(--muted)}
a{color:var(--accent)}
</style></head>
<body><main>
<h1>PlantCare</h1>
<p class="muted">Lettori ottici per coltura, malattia, insetti e acari, carenze. Ogni lettore dà una probabilità calibrata. Supporto alla decisione per tecnici e agricoltori: non sostituisce la diagnosi di un tecnico abilitato.</p>

<section class="card">
<h2>Lettore ottico</h2>
<p><label for="organ"><strong>Quale parte della pianta è colpita?</strong></label><br>
<select id="organ" name="organ"><option value="">Non indicato</option></select></p>
<video id="video" autoplay playsinline muted hidden></video>
<canvas id="canvas" hidden></canvas>
<div class="row">
<button type="button" id="cam-start">Avvia fotocamera</button>
<button type="button" id="cam-shot" disabled>Scatta e analizza</button>
<button type="button" class="secondary" id="cam-stop" disabled>Spegni</button>
</div>
<p class="muted" id="cam-status"></p>
<details><summary>Oppure carica una foto</summary>
<form id="f"><input id="file" type="file" name="file" accept="image/*" capture="environment">
<div id="preview"></div>
<p><button type="submit">Analizza la foto</button></p></form>
</details>
</section>

<section class="card">
<h2>Come fotografare</h2>
<ul class="guide">
<li>Inquadra da vicino la parte colpita, con luce naturale e senza flash.</li>
<li>Tieni a fuoco la lesione, al centro dell'immagine.</li>
<li>Per gli insetti: dall'alto e di profilo, con un riferimento di scala.</li>
</ul>
</section>

<div id="out" aria-live="polite"></div>

<section class="card" id="feedback-box" hidden>
<h2>Il risultato è corretto?</h2>
<p class="muted">La tua risposta serve a migliorare il sistema. La foto non viene salvata. Nel commento non inserire dati personali (nomi, indirizzi, contatti).</p>
<div class="row">
<button type="button" id="ok">Sì, è corretto</button>
<button type="button" class="secondary" id="ko">No, è sbagliato</button>
</div>
<div id="fb-form" hidden>
<p><label>Che cosa era (se lo sai)?<br><textarea id="fb-comment" rows="3" maxlength="500" placeholder="Es. carenza di ferro, non virosi"></textarea></label></p>
<p><button type="button" id="send">Invia</button></p>
</div>
<p id="fb-status" class="muted"></p>
</section>

<footer>
<p>Stato dei lettori: <a href="/api/readers">/api/readers</a> · Documentazione API: <a href="/docs">/docs</a> · Schede malattie: <a href="/api/diseases">/api/diseases</a></p>
<p>La probabilità di ogni lettore è calibrata sul set di validazione; l'affidabilità indicata è misurata sul set di test. Sotto soglia il lettore risponde "non determinabile". Per virus, viroidi, batteri e nematodi serve sempre la conferma di laboratorio.</p>
</footer>
</main>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=x=>(x==null?'n.d.':(x*100).toFixed(1)+'%');
let last=null,stream=null;
fetch('/api/organs').then(r=>r.json()).then(list=>{const sel=$('organ');for(const o of list){const op=document.createElement('option');op.value=o.id;op.textContent=o.label;sel.appendChild(op);}}).catch(()=>{});
$('file').addEventListener('change',()=>{const f=$('file').files[0];$('preview').innerHTML=f?'<img class="preview" alt="Anteprima della foto caricata" src="'+URL.createObjectURL(f)+'">':'';});

$('cam-start').addEventListener('click',async()=>{
 try{stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:960}},audio:false});
 const v=$('video');v.srcObject=stream;v.hidden=false;$('cam-shot').disabled=false;$('cam-stop').disabled=false;$('cam-status').textContent='Fotocamera attiva: inquadra la parte colpita e premi "Scatta e analizza".';}
 catch(e){$('cam-status').textContent='Fotocamera non disponibile (permesso negato o pagina non in HTTPS). Usa "carica una foto".';}
});
$('cam-stop').addEventListener('click',()=>{if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;}$('video').hidden=true;$('cam-shot').disabled=true;$('cam-stop').disabled=true;$('cam-status').textContent='';});
$('cam-shot').addEventListener('click',()=>{
 const v=$('video'),c=$('canvas');c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d').drawImage(v,0,0);
 c.toBlob(b=>{const fd=new FormData();fd.append('file',b,'scatto.jpg');analyze(fd);},'image/jpeg',0.92);
});
$('f').addEventListener('submit',e=>{e.preventDefault();if(!$('file').files[0])return;const fd=new FormData();fd.append('file',$('file').files[0]);analyze(fd);});

function renderReader(head,h,status){
 let s='<div class="reader"><h3>'+esc(h.reader)+': '+esc(h.answer)+'</h3>';
 for(const c of h.candidates){s+='<div class="cand"><div class="bar"><span style="width:'+(c.probability*100).toFixed(1)+'%"></span><em>'+esc(c.name)+'</em></div><div class="p">'+pct(c.probability)+'</div></div>';}
 if(h.card&&h.card.agent){s+='<p class="muted">Agente: <em>'+esc(h.card.agent)+'</em></p>';}
 if(status&&status.trained){s+='<p class="muted">Affidabilità del lettore sul test: accuratezza '+pct(status.test_accuracy)+', errore di calibrazione '+pct(status.calibration_error)+'</p>';}
 return s+'</div>';
}
function renderReferto(r){
 if(!r||(!r.disease&&!r.plant&&!r.pest))return '';
 let s='<div class="reader"><h3>Referto</h3>';
 if(r.plant)s+='<p><strong>Coltura:</strong> '+esc(r.plant)+'</p>';
 if(r.disease)s+='<p><strong>Malattia:</strong> '+esc(r.disease)+(r.agent?' (<em>'+esc(r.agent)+'</em>)':'')+'</p>';
 if(r.cause)s+='<p><strong>Causa:</strong> '+esc(r.cause)+'</p>';
 if(r.caused_by&&r.caused_by.length)s+='<p><strong>Provocata da:</strong> '+esc(r.caused_by.join(', '))+'</p>';
 if(r.pest)s+='<p><strong>Insetto o acaro:</strong> '+esc(r.pest)+'</p>';
 if(r.management&&r.management.length){s+='<p><strong>Misure ('+esc(r.management_status)+'):</strong></p><ul>';for(const m of r.management)s+='<li>'+esc(m)+'</li>';s+='</ul>';}
 if(r.sources&&r.sources.length){s+='<p class="muted">Fonti: '+r.sources.map(x=>'<a href="'+esc(x.url)+'" target="_blank" rel="noopener">'+esc(x.title)+'</a>').join(' · ')+'</p>';}
 return s+'</div>';
}
async function analyze(fd){
 fd.append('organ',$('organ').value);
 $('out').innerHTML='<div class="card">Analisi in corso…</div>';$('feedback-box').hidden=true;
 try{const r=await fetch('/predict',{method:'POST',body:fd});const j=await r.json();
 if(!r.ok){$('out').innerHTML='<div class="card warn">'+esc(j.detail||'Errore')+'</div>';return;}
 last=j;let h='<section class="card"><h2>Risultato dei lettori</h2>';
 for(const [name,v] of Object.entries(j.heads)){h+=renderReader(name,v,(j.readers||{})[name]);}
 for(const [name,st] of Object.entries(j.readers||{})){if(!st.trained)h+='<div class="reader"><h3>'+esc(st.label)+'</h3><p class="muted">'+esc(st.note)+'</p></div>';}
 h+=renderReferto(j.referto);
 for(const w of j.warnings){h+='<div class="warn'+(w.includes('laboratorio')?' lab':'')+'">'+esc(w)+'</div>';}
 h+='<p class="muted">'+esc(j.disclaimer)+'</p><p class="muted">Modello: '+esc(j.model_version)+' · soglia '+esc(j.abstain_threshold)+'</p></section>';
 $('out').innerHTML=h;$('feedback-box').hidden=false;$('fb-form').hidden=true;$('fb-status').textContent='';
 }catch(err){$('out').innerHTML='<div class="card warn">Errore di rete. Riprova.</div>';}
}
$('ok').addEventListener('click',()=>sendFb('agree'));
$('ko').addEventListener('click',()=>{$('fb-form').hidden=false;});
$('send').addEventListener('click',()=>sendFb('disagree'));
async function sendFb(verdict){
 if(!last)return;
 const body={verdict,model_version:last.model_version,predicted:Object.fromEntries(Object.entries(last.heads).map(([k,v])=>[k,v.answer])),comment:$('fb-comment').value||null};
 try{const r=await fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 $('fb-status').textContent=r.ok?'Grazie, risposta registrata.':(r.status===503?'Il feedback non è attivo su questo server.':'Non è stato possibile registrare la risposta.');}
 catch(e){$('fb-status').textContent='Errore di rete.';}
}
</script></body></html>"""


class FeedbackIn(BaseModel):
    verdict: Literal["agree", "disagree"]
    model_version: str = Field(max_length=200)
    predicted: dict[str, str] = Field(default_factory=dict)
    comment: str | None = Field(default=None, max_length=MAX_COMMENT)
    role: Literal["agronomo", "tecnico", "agricoltore", "altro"] | None = None


def create_app(checkpoint: str | Path | None = None, abstain_threshold: float = 0.5) -> FastAPI:
    ckpt = checkpoint or os.environ.get("PLANTCARE_CKPT")
    feedback_dir = os.environ.get("PLANTCARE_FEEDBACK_DIR")

    tax = load_taxonomy(DEFAULT_TAXONOMY_PATH)
    kb = KnowledgeBase(tax, knowledge=load_yaml(KNOWLEDGE_PATH), sources=load_yaml(SOURCES_PATH))
    label_map = load_label_map(DEFAULT_MAP_PATH, taxonomy=tax)

    app = FastAPI(
        title="PlantCare",
        version="0.3.0",
        description="Riconoscimento visivo di colture, malattie e insetti. Supporto alla decisione, non diagnosi.",
    )
    state: dict[str, Predictor] = {}
    if ckpt:
        state["predictor"] = Predictor(ckpt, abstain_threshold=abstain_threshold, kb=kb, label_map=label_map)

    # ---------------- pagine e stato ----------------
    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGE

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "model_loaded": "predictor" in state,
            "model_version": state["predictor"].version if "predictor" in state else None,
            "taxonomy_version": tax.version,
            "feedback_enabled": bool(feedback_dir),
        }

    # ---------------- predizione ----------------
    @app.post("/predict")
    async def predict(file: UploadFile = File(...), organ: str | None = Form(None)) -> dict:
        if organ and organ not in tax.plant_organs:
            raise HTTPException(status_code=400, detail=f"Organo sconosciuto: {organ}")
        if "predictor" not in state:
            raise HTTPException(status_code=503, detail="Modello non caricato: impostare PLANTCARE_CKPT.")
        data = await file.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="File troppo grande (massimo 10 MB).")
        try:
            img = Image.open(io.BytesIO(data))
            img.verify()
            img = Image.open(io.BytesIO(data))
        except (UnidentifiedImageError, OSError):
            raise HTTPException(status_code=400, detail="Il file non è un'immagine riconosciuta.")
        return state["predictor"].predict(img, organ=organ or None)

    # ---------------- schede per agronomi ----------------
    @app.get("/api/plants")
    def plants(priority: int | None = None) -> list[dict]:
        return kb.list_plants(priority=priority)

    @app.get("/api/readers")
    def readers() -> dict:
        if "predictor" not in state:
            return {"model_loaded": False, "readers": {}}
        return {"model_loaded": True, "model_version": state["predictor"].version,
                "training_sources": state["predictor"].training_sources,
                "readers": state["predictor"].readers_status()}

    @app.get("/api/organs")
    def organs() -> list[dict]:
        return kb.list_organs()

    @app.get("/api/diseases")
    def diseases(plant: str | None = None, organ: str | None = None) -> list[dict]:
        return kb.list_diseases(plant_id=plant, organ=organ)

    @app.get("/api/diseases/{disease_id}")
    def disease(disease_id: str, organ: str | None = None) -> dict:
        card = kb.disease_card(disease_id, organ=organ)
        if card is None:
            raise HTTPException(status_code=404, detail="Malattia non trovata")
        return card

    @app.get("/api/insects")
    def insects(plant: str | None = None, role: str | None = None) -> list[dict]:
        return kb.list_insects(plant_id=plant, role=role)

    @app.get("/api/sources")
    def sources() -> list[dict]:
        return list(kb.sources.values())

    @app.get("/api/insects/{insect_id}")
    def insect(insect_id: str) -> dict:
        card = kb.insect_card(insect_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Insetto non trovato")
        return card

    @app.get("/api/nutrients")
    def nutrients() -> dict:
        return kb.list_nutrients()

    # ---------------- feedback degli agronomi ----------------
    @app.post("/api/feedback", status_code=201)
    def feedback(item: FeedbackIn) -> dict:
        if not feedback_dir:
            raise HTTPException(status_code=503, detail="Feedback non attivo su questo server.")
        folder = Path(feedback_dir)
        folder.mkdir(parents=True, exist_ok=True)
        record = {
            "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **item.model_dump(),
        }
        with open(folder / "feedback.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"status": "registrato"}

    return app
