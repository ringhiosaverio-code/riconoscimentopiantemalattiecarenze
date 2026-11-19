from pathlib import Path

import pytest
from PIL import Image

from plantcare.data.pipeline import (
    find_corrupt_images,
    find_cross_split_duplicates,
    parse_plantvillage_folder,
    read_manifest,
    scan_ip102,
    scan_plantvillage,
    summarize,
    write_manifest,
)


def _png(path: Path, color=(120, 180, 90), size=(16, 16)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def test_parse_plantvillage_folder():
    crop, name = parse_plantvillage_folder("Tomato___Late_blight")
    assert crop == "Tomato"
    assert name == "Tomato___Late_blight"


def test_parse_plantvillage_rejects_other_folders():
    with pytest.raises(ValueError):
        parse_plantvillage_folder("images")


def test_scan_plantvillage_assigns_all_splits(tmp_path):
    for i in range(10):
        _png(tmp_path / "Tomato___healthy" / f"{i}.png")
    rows = scan_plantvillage(tmp_path, seed=1)
    assert len(rows) == 10
    splits = {r.split for r in rows}
    assert splits == {"train", "val", "test"}
    assert all(r.plant == "Tomato" and r.disease == "Tomato___healthy" for r in rows)


def test_scan_ip102_reads_official_split_files(tmp_path):
    _png(tmp_path / "images" / "a.jpg")
    (tmp_path / "train.txt").write_text("a.jpg 7\n", encoding="utf-8")
    rows = scan_ip102(tmp_path, label_base=0)  # base 0: etichetta 7 -> classe ufficiale 8
    assert len(rows) == 1
    assert rows[0].split == "train"
    assert rows[0].pest == "ip102_008"
    assert rows[0].path == "images/a.jpg"


def test_cross_split_duplicates_are_detected(tmp_path):
    _png(tmp_path / "x" / "one.png", color=(1, 2, 3))
    _png(tmp_path / "x" / "two.png", color=(1, 2, 3))  # stessi byte
    rows = [
        _row("x/one.png", "train"),
        _row("x/two.png", "test"),
    ]
    leaks = find_cross_split_duplicates(tmp_path, rows)
    assert len(leaks) == 1


def test_corrupt_images_are_reported(tmp_path):
    (tmp_path / "bad.jpg").write_bytes(b"non e' un'immagine")
    rows = [_row("bad.jpg", "train")]
    assert find_corrupt_images(tmp_path, rows) == ["bad.jpg"]


def test_manifest_roundtrip_and_summary(tmp_path):
    rows = [_row("a.png", "train", plant="Tomato", disease="Tomato___healthy"), _row("b.png", "val", pest="ip102_001")]
    out = tmp_path / "m.csv"
    write_manifest(rows, out)
    back = read_manifest(out)
    assert len(back) == 2
    s = summarize(rows)
    assert s["train"]["plant"] == 1
    assert s["val"]["pest"] == 1


def _row(path, split, **kw):
    from plantcare.data.pipeline import ManifestRow
    return ManifestRow(path=path, source="test", split=split, **kw)


def test_leaf_identifier_mirrors_official_loader():
    from plantcare.data.pipeline import leaf_identifier
    assert leaf_identifier("rutg._hl 3733.JPG") == "rutg._hl 3733"
    assert leaf_identifier("img_final_masked.jpg") == "img"
    assert leaf_identifier("a___b.png") == "b"


def test_same_leaf_images_stay_in_same_split(tmp_path):
    from plantcare.data.pipeline import scan_plantvillage
    cls = "Tomato___Late_blight"
    names = [f"leafA_{i}.jpg" for i in range(4)] + [f"leafB_{i}.jpg" for i in range(4)] + [f"leafC_{i}.jpg" for i in range(4)]
    for n in names:
        _png(tmp_path / cls / n)
    # Tutte le foto di una stessa foglia hanno lo stesso gruppo
    leaf_map = {}
    for n in names:
        leaf = n.split("_")[0]
        leaf_map[n.replace(".jpg", "").lower()] = [f"{cls}:::{leaf}"]
    rows = scan_plantvillage(tmp_path, seed=3, leaf_map=leaf_map)
    by_leaf = {}
    for r in rows:
        leaf = Path(r.path).name.split("_")[0]
        by_leaf.setdefault(leaf, set()).add(r.split)
    assert all(len(s) == 1 for s in by_leaf.values()), by_leaf


def test_ip102_label_base_is_applied(tmp_path):
    _png(tmp_path / "images" / "a.jpg")
    (tmp_path / "train.txt").write_text("a.jpg 0\n", encoding="utf-8")
    rows0 = scan_ip102(tmp_path, label_base=0)
    assert rows0[0].pest == "ip102_001"
    (tmp_path / "train.txt").write_text("a.jpg 1\n", encoding="utf-8")
    rows1 = scan_ip102(tmp_path, label_base=1)
    assert rows1[0].pest == "ip102_001"


def test_ip102_classes_file_has_102_names():
    from plantcare.data.pipeline import load_ip102_classes
    names = load_ip102_classes(Path(__file__).resolve().parents[1] / "configs" / "ip102_classes.yaml")
    assert len(names) == 102 and names[1] == "rice leaf roller"
