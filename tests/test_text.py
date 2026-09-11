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
