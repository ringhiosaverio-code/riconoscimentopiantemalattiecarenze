import pytest

from plantcare.taxonomy import (
    DEFAULT_TAXONOMY_PATH,
    Taxonomy,
    TaxonomyError,
    load_taxonomy,
    validate,
)


def test_default_taxonomy_loads_and_is_consistent():
    tax = load_taxonomy(DEFAULT_TAXONOMY_PATH)
    assert tax.plants
    assert tax.diseases
    assert tax.insects


def test_every_pathogen_type_used_is_declared():
    tax = load_taxonomy()
    used = {d["pathogen_type"] for d in tax.diseases.values()}
    assert used <= set(tax.pathogen_types)


def test_insect_roles_cover_agronomic_categories():
    tax = load_taxonomy()
    assert tax.insects_by_role("phytophagous")
    assert tax.insects_by_role("entomophagous")


def test_class_ids_are_sorted_and_stable():
    tax = load_taxonomy()
    ids = tax.class_ids("plants")
    assert ids == sorted(ids)


def test_duplicate_id_is_rejected(tmp_path):
    bad = tmp_path / "t.yaml"
    bad.write_text(
        "plants:\n  - {id: a, common: A}\n  - {id: a, common: B}\n", encoding="utf-8"
    )
    with pytest.raises(TaxonomyError, match="duplicato"):
        load_taxonomy(bad)


def test_unknown_host_is_rejected():
    tax = Taxonomy(
        version="t",
        plants={"tomato": {"id": "tomato"}},
        pathogen_types={"fungal": {"id": "fungal"}},
        diseases={
            "x": {"id": "x", "pathogen_type": "fungal", "agent": "F", "hosts": ["ghost"]}
        },
        insects={},
        macro_nutrients={},
        micro_nutrients={},
    )
    with pytest.raises(TaxonomyError, match="ospite sconosciuto"):
        validate(tax)


def test_invalid_insect_role_is_rejected():
    tax = Taxonomy(
        version="t",
        plants={},
        pathogen_types={},
        diseases={},
        insects={"bug": {"id": "bug", "role": "boh"}},
        macro_nutrients={},
        micro_nutrients={},
    )
    with pytest.raises(TaxonomyError, match="ruolo non valido"):
        validate(tax)
