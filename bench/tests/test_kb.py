from bench.kb import chunk_markdown, fuse
from bench.tokens import TokenEstimator

LENGTHS = TokenEstimator({"en": 1.0, "fr": 1.0, "ar": 1.0}, per_message=0)


def words(count: int) -> str:
    return " ".join(["word"] * count)  # 5 * count - 1 characters


def test_each_chunk_starts_with_the_title_and_its_heading_path() -> None:
    markdown = f"# Plans\n\n## Changing plans\n\n{words(80)}\n\n## Cancelling\n\n{words(80)}\n"

    chunks = chunk_markdown(
        markdown, document="doc.md", language="en", estimator=LENGTHS, max_tokens=500
    )

    assert [chunk.text.split("\n\n")[0] for chunk in chunks] == [
        "Plans > Changing plans",
        "Plans > Cancelling",
    ]


def test_small_sections_share_a_chunk_under_their_common_heading() -> None:
    markdown = (
        f"# Plans\n\n## Prices\n\n{words(20)}\n\n## Changes\n\n{words(20)}\n\n"
        f"### Mid-month\n\n{words(20)}\n"
    )

    [chunk] = chunk_markdown(
        markdown, document="doc.md", language="en", estimator=LENGTHS, max_tokens=500
    )

    assert chunk.text.startswith("Plans\n\nPrices\n\n")
    assert "\n\nChanges\n\n" in chunk.text
    assert "\n\nMid-month\n\n" in chunk.text


def test_a_long_section_splits_between_paragraphs_with_a_sentence_of_overlap() -> None:
    paragraphs = [f"{words(30)}. P{n} ends here." for n in range(6)]  # 164 characters each
    markdown = "# Doc\n\n## Long\n\n" + "\n\n".join(paragraphs) + "\n"

    chunks = chunk_markdown(
        markdown, document="doc.md", language="en", estimator=LENGTHS, max_tokens=500
    )

    assert [len(chunk.text) <= 500 for chunk in chunks] == [True, True, True]
    # Each chunk after the first opens with the last sentence of the one before it.
    assert [chunk.text.split("\n\n")[1] for chunk in chunks[1:]] == [
        "P1 ends here.",
        "P3 ends here.",
    ]


def test_a_paragraph_longer_than_a_chunk_splits_between_sentences() -> None:
    paragraph = " ".join(f"Sentence {n} has a few words in it." for n in range(30))

    chunks = chunk_markdown(
        f"# Doc\n\n{paragraph}\n", document="doc.md", language="en", estimator=LENGTHS
    )

    assert len(chunks) == 3
    assert all(len(chunk.text) <= 500 for chunk in chunks)


def test_rank_fusion_favours_what_both_searches_found() -> None:
    # k = 60: chunk 1 scores 1/61 + 1/62, chunk 3 scores 1/63 + 1/61, chunk 2 only 1/62.
    assert fuse([[1, 2, 3], [3, 1]]) == [1, 3, 2]


def test_rank_fusion_keeps_the_top_twenty() -> None:
    assert fuse([list(range(30))]) == list(range(20))


def test_a_heading_after_a_skipped_level_is_the_sibling_of_its_own_level() -> None:
    """Web pages skip levels: Service-Public.fr's tabs are level-5 headings under the title."""
    markdown = (
        f"# Card\n\n##### In France\n\n{words(80)}\n\n###### Where to call\n\n{words(80)}\n\n"
        f"##### Abroad\n\n{words(80)}\n\n## Help\n\n{words(80)}\n"
    )

    chunks = chunk_markdown(
        markdown, document="doc.md", language="en", estimator=LENGTHS, max_tokens=500
    )

    assert [chunk.heading_path for chunk in chunks] == [
        ("In France",),
        ("In France", "Where to call"),
        ("Abroad",),
        ("Help",),
    ]


def test_a_chunk_names_its_document_and_every_section_it_holds() -> None:
    markdown = (
        f"# Plans\n\n## Prices\n\n{words(20)}\n\n## Changes\n\n{words(20)}\n\n"
        f"### Mid-month\n\n{words(20)}\n"
    )

    [chunk] = chunk_markdown(
        markdown, document="en-plans.md", language="en", estimator=LENGTHS, max_tokens=500
    )

    assert chunk.document == "en-plans.md"
    assert chunk.sections == (("Prices",), ("Changes",), ("Changes", "Mid-month"))
