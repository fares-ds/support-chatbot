from bench.tokens import TokenEstimator, calibration_texts


def test_calibration_turns_measured_tokens_into_characters_per_token() -> None:
    estimator = TokenEstimator.calibrated(
        {"en": (4000, 1000), "fr": (3500, 1000), "ar": (2000, 1000)}
    )

    assert estimator.tokens("x" * 400, "en") == 100


def test_darija_follows_the_ratio_of_its_script() -> None:
    estimator = TokenEstimator({"en": 4.0, "fr": 5.0, "ar": 2.0})

    latin = estimator.tokens("wach nqder nbeddel", "darija")  # 18 characters, French ratio
    arabic = estimator.tokens("واش نقدر نبدل", "darija")  # 13 characters, Arabic ratio

    assert (latin, arabic) == (4, 7)


def test_truncating_keeps_whole_words_from_the_start() -> None:
    estimator = TokenEstimator({"en": 4.0, "fr": 4.0, "ar": 4.0})

    assert estimator.truncate("one two three four", 3, "en") == "one two"


def test_truncating_can_keep_the_end_instead() -> None:
    estimator = TokenEstimator({"en": 4.0, "fr": 4.0, "ar": 4.0})

    assert estimator.truncate("one two three four", 3, "en", keep="end") == "three four"


def test_calibration_text_draws_on_every_text_of_its_script() -> None:
    texts = [("a" * 1000, "en"), ("b" * 1000, "en"), ("c" * 1000, "fr"), ("واو " * 100, "ar")]

    calibration = calibration_texts(texts, size=600, piece=300)

    assert sorted(set(calibration["en"]) - {" "}) == ["a", "b"]
    assert len(calibration["en"]) <= 600
