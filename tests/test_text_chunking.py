import pytest

from app.text_chunking import chunk_text


def test_sentence_aware_chunking_preserves_order():
    text = "First sentence. Second sentence! Third sentence?"
    chunks = chunk_text(text, target=18, maximum=26)
    assert " ".join(chunks) == text
    assert all(len(chunk) <= 26 for chunk in chunks)


def test_hard_maximum_and_long_word():
    chunks = chunk_text("alpha " + "x" * 91 + " omega", target=10, maximum=20)
    assert all(len(chunk) <= 20 for chunk in chunks)
    assert "".join(chunks).replace(" ", "") == ("alpha " + "x" * 91 + " omega").replace(" ", "")


def test_blank_input_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        chunk_text("\n  \t")


def test_paragraph_breaks_are_handled():
    chunks = chunk_text("One paragraph.\n\nSecond paragraph.", target=100, maximum=120)
    assert chunks == ["One paragraph. Second paragraph."]


def test_long_comma_separated_text_does_not_overwrite_a_short_piece():
    text = "one, abcdefghij, ending words for overflow."
    chunks = chunk_text(text, target=10, maximum=20)
    assert " ".join(chunks) == text


def test_long_text_preserves_all_words_with_different_segment_limits():
    text = ("One short clause, then a longer clause with several words, and a final phrase. " * 50).strip()
    for maximum in (20, 60, 70, 163, 200, 350):
        chunks = chunk_text(text, target=max(1, maximum // 2), maximum=maximum)
        assert " ".join(chunks) == text
        assert all(len(chunk) <= maximum for chunk in chunks)
