from gfs_core.text import normalize_name


def test_normalize_strips_accents_and_suffixes():
    assert (
        normalize_name("Vinícius José Paixão de Oliveira Júnior")
        == "vinicius jose paixao de oliveira"
    )
    assert normalize_name("Sergiño Dest") == "sergino dest"
    assert normalize_name("Junior Firpo") == "junior firpo"
    assert normalize_name("O'Neil") == "o neil"
    assert normalize_name(None) == ""


def test_api_football_reserve_filter_skips_women_and_youth_sides():
    from data_pipeline.ingestion.api_football.teams import RESERVE_RE

    for name in (
        "Leicester City LFC",
        "Leicester City FC W",
        "Leicester City U23",
        "Arsenal Ladies",
    ):
        assert RESERVE_RE.search(normalize_name(name)), name
    for name in ("Leicester", "Leicester City", "Wolves"):
        assert not RESERVE_RE.search(normalize_name(name)), name
