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
    rows = scan_ip102(tmp_path)
    assert len(rows) == 1
    assert rows[0].split == "train"
    assert rows[0].pest == "ip102_007"
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
