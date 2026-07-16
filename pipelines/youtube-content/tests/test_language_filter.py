"""语言检测模块测试。"""
from trending_aggregator.scouts.language_filter import detect_language, is_target_language


def test_detect_indonesian():
    assert detect_language("Makanan enak banget nih") == "id"
    assert detect_language("Aku suka nonton film ini") == "id"
    assert detect_language("Film ini sangat bagus") == "id"


def test_detect_thai():
    assert detect_language("หนังเรื่องนี้สนุกมาก") == "th"
    assert detect_language("ฉันรักหนังเรื่องนี้") == "th"


def test_detect_english():
    assert detect_language("This movie is amazing") == "en"
    assert detect_language("I love watching kdramas") == "en"
    assert detect_language("Best kdrama recommendation") == "en"
    assert detect_language("Netflix new series 2025") == "en"


def test_unsupported_language():
    assert detect_language("Ce film est magnifique") is None
    assert detect_language("この映画が大好き") is None


def test_empty_text():
    assert detect_language("") is None


def test_is_target():
    assert is_target_language("I love this film")
    assert not is_target_language("Ce film est magnifique")
