from collections.abc import Mapping, Sequence

from bench.classify import Embed, EmbeddingCheck

EXAMPLES = {
    "on_topic": ["How much is the Pro plan?"],
    "off_topic": ["Write me a poem"],
    "human_request": ["Can I talk to a person?"],
    "smalltalk": ["Hi"],
}
YES = ["yes", "oui", "واه"]


def embedder(vectors: Mapping[str, Sequence[float]]) -> Embed:
    async def embed(texts: Sequence[str]) -> list[list[float]]:
        return [list(vectors[text]) for text in texts]

    return embed


AXES = {
    "How much is the Pro plan?": [1.0, 0.0],
    "Write me a poem": [0.0, 1.0],
    "Can I talk to a person?": [-1.0, 0.0],
    "Hi": [0.0, -1.0],
}


async def check(messages: Mapping[str, Sequence[float]]) -> EmbeddingCheck:
    """A check over the four examples above, which also knows the vectors of `messages`."""
    return await EmbeddingCheck.build(EXAMPLES, yes=YES, embed=embedder({**AXES, **messages}))


async def test_the_nearest_example_decides_the_category() -> None:
    classifier = await check({"Combien coûte le forfait Pro ?": [0.9, 0.1]})

    result = await classifier.classify(
        "Combien coûte le forfait Pro ?",
        previous_message=None,
        offered_person=False,
        interface_language="fr",
    )

    assert result.category == "on_topic"


async def classify(
    classifier: EmbeddingCheck,
    message: str,
    *,
    previous_message: str | None = None,
    offered_person: bool = False,
) -> str:
    result = await classifier.classify(
        message,
        previous_message=previous_message,
        offered_person=offered_person,
        interface_language="fr",
    )
    return result.category


async def test_a_close_call_between_on_topic_and_off_topic_goes_on_topic() -> None:
    # Cosine 0.69 to the on-topic example and 0.72 to the off-topic one: within the margin.
    classifier = await check({"Is a poem about my plan possible?": [0.69, 0.72]})

    assert await classify(classifier, "Is a poem about my plan possible?") == "on_topic"


async def test_a_clear_off_topic_message_stays_off_topic() -> None:
    classifier = await check({"Tell me a joke": [0.2, 0.98]})

    assert await classify(classifier, "Tell me a joke") == "off_topic"


async def test_a_short_yes_right_after_an_offer_of_a_person_asks_for_one() -> None:
    classifier = await check({"Oui !": [0.1, -0.9], "Yes please": [0.1, -0.9]})

    categories = [
        await classify(classifier, "Oui !", offered_person=True),
        await classify(classifier, "Yes please", offered_person=True),
        await classify(classifier, "Oui !", offered_person=False),
    ]

    assert categories == ["human_request", "human_request", "smalltalk"]


async def test_the_search_query_adds_the_previous_message() -> None:
    classifier = await check({"Does it include SSO?": [0.8, 0.2]})

    result = await classifier.classify(
        "Does it include SSO?",
        previous_message="How much is the Pro plan?",
        offered_person=False,
        interface_language="en",
    )

    assert result.search_query == "How much is the Pro plan?\nDoes it include SSO?"


async def test_canned_replies_use_the_widgets_language() -> None:
    classifier = await check({"salam": [0.0, -1.0]})

    result = await classifier.classify(
        "salam", previous_message=None, offered_person=False, interface_language="ar"
    )

    assert result.language == "ar"


async def test_many_example_phrases_are_embedded_in_batches_tei_accepts() -> None:
    """TEI refuses a request with more texts than its client batch limit, 32 by default."""
    examples = {
        category: [f"{category} {n}" for n in range(13)]
        for category in ("on_topic", "off_topic", "human_request", "smalltalk")
    }
    sizes: list[int] = []

    async def embed(texts: Sequence[str]) -> list[list[float]]:
        sizes.append(len(texts))
        if len(texts) > 32:
            raise ValueError("422: batch size > max_client_batch_size")
        return [[1.0, float(n)] for n in range(len(texts))]

    await EmbeddingCheck.build(examples, yes=YES, embed=embed)

    assert sum(sizes) == 52
    assert max(sizes) <= 32
