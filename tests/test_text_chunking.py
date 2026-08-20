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
