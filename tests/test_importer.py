from bulk_music_downloader.importer import parse_file


def test_txt_import(tmp_path):
    p = tmp_path / "songs.txt"
    p.write_text(
        "Song One | Artist One\n"
        "Song Two - Artist Two\n",
        encoding="utf-8",
    )

    assert parse_file(str(p)) == [
        ("Song One", "Artist One"),
        ("Song Two", "Artist Two"),
    ]


def test_csv_import(tmp_path):
    p = tmp_path / "songs.csv"
    p.write_text(
        "title,artist\n"
        "Song,Artist\n",
        encoding="utf-8",
    )

    assert parse_file(str(p)) == [("Song", "Artist")]


def test_tab_separated_txt_import(tmp_path):
    p = tmp_path / "songs.txt"
    p.write_text(
        "Song One\tArtist One\n"
        "Song Two\tArtist Two\n",
        encoding="utf-8",
    )

    assert parse_file(str(p)) == [
        ("Song One", "Artist One"),
        ("Song Two", "Artist Two"),
    ]
