"""Contributi dall'app: importazione, duplicati, etichette e split di campo."""

import base64
import io
import json

from PIL import Image

from plantcare.data import importers as im


def _photo():
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (90, 140, 60)).save(buf, format="JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _payload(items):
    return {"schema": "plantcare-contributi/1", "items": items}


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(im, "DATA", tmp_path)
    monkeypatch.setattr(im, "IMG", tmp_path / "external" / "images")
    monkeypatch.setattr(im, "CONTRIB_CSV", tmp_path / "processed" / "contributi.csv")


def test_import_contributions_and_skip_duplicates(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    items = [
        {"id": "a1", "date": "2026-11-20", "photo": _photo(), "province": "Reggio Calabria", "organ": "leaf",
         "diagnosis_source": "lab", "correct": {"plant": "olea_europaea", "disease": "olive_peacock_spot", "deficiency": ""}},
        {"id": "a2", "photo": _photo(), "correct": {"plant": "citrus_limon", "disease": "altro:non_in_elenco", "deficiency": ""},
         "note": "macchie non in elenco"},
        {"id": "a3", "photo": _photo(), "correct": {"plant": "", "disease": "", "deficiency": ""}},  # nessuna etichetta
        {"id": "a4", "photo": "non-una-foto", "correct": {"plant": "olea_europaea"}},
    ]
    f = tmp_path / "c.json"
    f.write_text(json.dumps(_payload(items)), encoding="utf-8")
    new, skipped, warnings = im.import_contributions([f])
    assert new == 2 and skipped == 0 and len(warnings) == 2
    rows = im.contribution_rows()
    by_path = {r.path.split("/")[-1]: r for r in rows}
    assert by_path["a1.jpg"].disease == "olive_peacock_spot" and by_path["a1.jpg"].source == "contributi"
    assert by_path["a2.jpg"].disease == ""  # "non in elenco" non diventa un'etichetta
    assert (tmp_path / "external" / "images" / "contributi" / "a1.jpg").exists()
    # reimportare lo stesso file non duplica
    new2, skipped2, _ = im.import_contributions([f])
    assert new2 == 0 and skipped2 == 2


def test_wrong_schema_is_rejected(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    f = tmp_path / "x.json"
    f.write_text(json.dumps({"schema": "altro", "items": []}), encoding="utf-8")
    new, _, warnings = im.import_contributions([f])
    assert new == 0 and "schema" in warnings[0]


def test_contribution_split_is_stable_and_reserves_a_field_test_set():
    splits = [im._contrib_split(f"id{i}") for i in range(2000)]
    assert splits == [im._contrib_split(f"id{i}") for i in range(2000)]
    share_test = splits.count("test") / len(splits)
    assert 0.25 < share_test < 0.35
