"""Foglie delle colture del Sud viste in condizioni difficili, per il lettore della coltura.

Il lettore della coltura sbaglia con foglie viste dal rovescio, controluce, coperte di insetti, melata o
fumaggine (es. limone scambiato per melo). Per ogni coltura del lettore si scaricano da iNaturalist foto di
osservazioni con licenza CC0, CC BY o CC BY-NC (fino a 3 foto per osservazione, perché spesso una mostra il
rovescio della foglia; al massimo 6 osservazioni per autore), prima "research grade", poi coltivate con
almeno un'identificazione concorde. CLIP (ViT-B/32, zero-shot) ordina le foto per le situazioni difficili;
si tengono le migliori per coltura (--tieni), da verificare a vista con scripts/foglio_contatti.py.

Uso: python scripts/import_inat_colture.py [--per-coltura 450] [--tieni 90]
Uscita: data/external/inat_colture/manifest.json (importers.import_inat_colture).
"""
import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from import_inat_quiz import API, LICENSES, get, taxon_info  # noqa: E402

OUT = ROOT / "data" / "external" / "inat_colture"
IMG = ROOT / "data" / "external" / "images" / "inat_colture"

# classe del lettore della coltura -> taxon di iNaturalist
COLTURE = {
    "actinidia_chinensis": "Actinidia chinensis", "allium_cepa_tropea": "Allium cepa", "allium_sativum": "Allium sativum",
    "annona_cherimola": "Annona cherimola", "brassica_oleracea_italica": "Brassica oleracea", "capsicum_annuum": "Capsicum annuum",
    "citrus_limon": "Citrus limon", "citrus_reticulata": "Citrus reticulata", "citrus_sinensis": 331122,
    "corylus_avellana": "Corylus avellana", "cucumis_sativus": "Cucumis sativus", "cucurbita_pepo": "Cucurbita pepo",
    "cynara_cardunculus": "Cynara cardunculus", "ficus_carica": "Ficus carica", "fragaria_ananassa": "Fragaria ananassa",
    "lactuca_sativa": "Lactuca sativa", "malus_domestica": "Malus domestica", "olea_europaea": "Olea europaea",
    "opuntia_ficus_indica": "Opuntia ficus-indica", "persea_americana": "Persea americana", "prunus_avium": "Prunus avium",
    "prunus_domestica": "Prunus domestica", "prunus_persica": "Prunus persica", "punica_granatum": "Punica granatum",
    "pyrus_communis": "Pyrus communis", "solanum_lycopersicum": "Solanum lycopersicum", "solanum_melongena": "Solanum melongena",
    "solanum_tuberosum": "Solanum tuberosum", "vitis_vinifera": "Vitis vinifera",
}
DIFFICILI = [
    "the underside of a leaf seen from below", "the pale underside of leaves with visible veins",
    "a leaf against the light, backlit by the sun", "a leaf covered with many small insects",
    "a leaf with white waxy insects on the underside", "a leaf with black sooty mold",
    "a sticky shiny leaf with honeydew", "a leaf with scale insects", "a leaf with spider mites and fine webs",
    "a hand holding a leaf turned upside down", "a close-up of a leaf with yellow spots",
]
FACILI = ["a photo of a fruit", "a photo of a flower", "a photo of a whole tree", "a photo of a field of crops",
          "a photo of a vegetable on a table", "a photo of the upper side of a green leaf", "a photo of a tree trunk",
          "a photo of seeds", "a photo of a market stall"]


def osservazioni(taxon_id, n, per_user=6):
    out, users = [], Counter()
    for qual in ({"quality_grade": "research"}, {"quality_grade": "casual", "captive": "true", "identifications": "some_agree"}):
        page = 1
        while len(out) < n and page <= 6:
            params = {"taxon_id": taxon_id, "photo_license": ",".join(LICENSES), "per_page": 200, "page": page,
                      "order_by": "id", "order": "desc", "photos": "true", **qual}
            res = json.loads(get(f"{API}/observations", params))["results"]
            if not res:
                break
            for o in res:
                user = (o.get("user") or {}).get("login", "")
                if users[user] >= per_user:
                    continue
                phs = [p for p in o.get("photos", []) if p.get("license_code") in LICENSES and p.get("url")][:3]
                if not phs:
                    continue
                users[user] += 1
                for ph in phs:
                    out.append({"photo_id": ph["id"], "url": ph["url"].replace("/square.", "/medium."), "user": user,
                                "license": ph["license_code"], "attribution": ph.get("attribution", ""), "osservazione": o["id"]})
                if len(out) >= n:
                    break
            page += 1
        if len(out) >= n:
            break
    return out


def punteggi(paths):
    import open_clip
    import torch
    from PIL import Image
    m, _, pre = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
    tok = open_clip.get_tokenizer("ViT-B-32")
    m.eval()
    with torch.no_grad():
        t = m.encode_text(tok(DIFFICILI + FACILI))
        t = t / t.norm(dim=-1, keepdim=True)
    out = []
    for i in range(0, len(paths), 32):
        ims = []
        for p in paths[i:i + 32]:
            try:
                ims.append(pre(Image.open(p).convert("RGB")))
            except Exception:
                ims.append(None)
        ok = [x for x in ims if x is not None]
        pr = []
        if ok:
            with torch.no_grad():
                f = m.encode_image(torch.stack(ok))
                f = f / f.norm(dim=-1, keepdim=True)
                pr = (100 * f @ t.T).softmax(-1)[:, :len(DIFFICILI)].sum(1).tolist()
        it = iter(pr)
        out += [next(it) if x is not None else 0.0 for x in ims]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-coltura", type=int, default=450)
    ap.add_argument("--tieni", type=int, default=90)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    man_path = OUT / "manifest.json"
    man = json.load(open(man_path, encoding="utf-8")) if man_path.exists() else {}
    for cls, taxon in COLTURE.items():
        if man.get(cls, {}).get("completo"):
            continue
        try:
            # numero = id del taxon di iNaturalist (es. 331122, Citrus × aurantium: su iNaturalist l'arancio dolce
            # è riunito all'arancio amaro, perché il nome Citrus sinensis porta a un ibrido e verrebbe scartato)
            info = {"id": taxon, "name": "Citrus × aurantium"} if isinstance(taxon, int) else taxon_info(taxon)
            if not info:
                print("non trovato:", taxon, flush=True)
                continue
            obs = osservazioni(info["id"], args.per_coltura)
        except Exception as ex:
            print("errore", taxon, ex, flush=True)
            continue

        def fetch(p):
            f = IMG / cls / f"{p['photo_id']}.jpg"
            if not f.exists():
                try:
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_bytes(get(p["url"], pause=0.1))
                except Exception:
                    return None
            return {**p, "path": str(f.relative_to(ROOT / "data"))}
        with ThreadPoolExecutor(4) as pool:
            saved = [x for x in pool.map(fetch, obs) if x]
        sc = punteggi([ROOT / "data" / x["path"] for x in saved])
        for x, s in zip(saved, sc):
            x["difficile"] = round(s, 4)
        saved.sort(key=lambda x: -x["difficile"])
        tenute = saved[:args.tieni]
        for x in saved[args.tieni:]:  # le altre foto non servono: si cancellano per non occupare disco
            try:
                (ROOT / "data" / x["path"]).unlink()
            except OSError:
                pass
        man[cls] = {"taxon": taxon, "taxon_inat": info, "foto": tenute, "completo": True}
        json.dump(man, open(man_path, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"{cls:28s} scaricate {len(saved):4d}, tenute {len(tenute)} (punteggio minimo {tenute[-1]['difficile'] if tenute else '-'})", flush=True)
    print("FATTO", sum(len(v["foto"]) for v in man.values()))


if __name__ == "__main__":
    main()
