from ampero2.catalog import Catalog


def test_lookup_model_code_and_params():
    c = Catalog.load()
    m = c.find("DYN", "Limiter")
    assert m.code == 0x23 and m.index == 18
    amp = c.find("AMP", "Marshell 45")
    assert amp.code == 0x0700002A and amp.index == 43 and [p.name for p in amp.params][:2] == ["Volume", "Presence"]


def test_lookup_is_case_insensitive_and_reports_unknown():
    import pytest
    c = Catalog.load()
    assert c.find("amp", "marshell 45").name == "Marshell 45"
    with pytest.raises(KeyError):
        c.find("AMP", "Nope")


def test_categories_and_by_code():
    c = Catalog.load()
    assert [x.name for x in c.categories][:3] == ["DYN", "FREQ", "WAH"]
    assert c.by_code(0x07000000).name == "Tweed Chap"
