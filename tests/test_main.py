from syntetisk_kart import build_message


def test_build_message() -> None:
    assert build_message() == "Hei fra Syntetisk-kart!"
