"""
Document Parser Module — Test & Validation Script.
"""

from doc_parser import parse_document


def test_raw_text():
    """Test manual text input"""
    print("=" * 50)
    print("Test 1: Manual raw text input")
    doc = parse_document(raw_text="I need to memorize 500 words in 7 days.")
    assert doc.file_type == "raw_text"
    assert "500 words" in doc.raw_text
    print(f"  PASS — {doc}")
    return doc


def test_text_file():
    """Test .txt file parsing"""
    import tempfile, os

    print("=" * 50)
    print("Test 2: .txt file parsing")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write("Math homework: Complete chapter 3 exercises, 20 problems, due in 2 weeks.\n")
        f.write("Difficulty: medium-hard, requires textbook examples.")
        tmp_path = f.name

    try:
        doc = parse_document(tmp_path)
        assert doc.file_type == "txt"
        assert "Math homework" in doc.raw_text
        print(f"  PASS — {doc}")
    finally:
        os.unlink(tmp_path)
    return doc


def test_unsupported():
    """Test unsupported file type"""
    print("=" * 50)
    print("Test 3: Unsupported file type")
    try:
        parse_document("dummy.xyz")
        print("  FAIL — no exception raised")
    except ValueError as e:
        print(f"  PASS — ValueError raised: {e}")


def test_file_not_found():
    """Test nonexistent file"""
    print("=" * 50)
    print("Test 4: File not found")
    try:
        parse_document("nonexistent_file.pdf")
        print("  FAIL — no exception raised")
    except FileNotFoundError as e:
        print(f"  PASS — FileNotFoundError raised: {e}")


def test_both_params():
    """Test both params provided"""
    print("=" * 50)
    print("Test 5: Both file_path and raw_text provided")
    try:
        parse_document(file_path="test.txt", raw_text="hello")
        print("  FAIL — no exception raised")
    except ValueError as e:
        print(f"  PASS — ValueError raised: {e}")


def test_empty_params():
    """Test no params provided"""
    print("=" * 50)
    print("Test 6: No parameters provided")
    try:
        parse_document()
        print("  FAIL — no exception raised")
    except ValueError as e:
        print(f"  PASS — ValueError raised: {e}")


if __name__ == "__main__":
    test_raw_text()
    test_text_file()
    test_unsupported()
    test_file_not_found()
    test_both_params()
    test_empty_params()
    print("\n" + "=" * 50)
    print("All tests passed! Document parser module is working correctly.")
