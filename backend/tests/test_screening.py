from backend.app.screening import best_name_match, normalize_name, similarity_score


def test_name_normalization_handles_punctuation_suffixes_and_scripts():
    assert normalize_name("Example Trading, L.L.C.") == "example trading"
    assert normalize_name("Éxample Trading Limited") == "example trading"
    assert normalize_name("示例贸易有限公司") == "示例贸易"


def test_best_name_match_distinguishes_exact_and_fuzzy():
    matched, score, match_type = best_name_match(
        "Example Trading LLC", ["Other Entity", "Example Trading Limited"]
    )
    assert matched == "Example Trading Limited"
    assert score == 100.0
    assert match_type == "exact"

    matched, score, match_type = best_name_match(
        "Fictional Orian Logistics", ["Fictional Orion Logistics Group"]
    )
    assert matched == "Fictional Orion Logistics Group"
    assert 85 <= score < 100
    assert match_type == "fuzzy"


def test_similarity_rejects_unrelated_names():
    assert similarity_score(normalize_name("Northwind Tools"), normalize_name("Blue Ocean Foods")) < 50
