from bench.prompts import (
    AnswerPrompt,
    Budgets,
    Business,
    ClassifyPrompt,
    Message,
    Source,
    answer_prompt,
    classify_prompt,
)
from bench.tokens import TokenEstimator

# One token per character and no cost per message, so a test's token counts are lengths.
LENGTHS = TokenEstimator({"en": 1.0, "fr": 1.0, "ar": 1.0}, per_message=0)
BUSINESS = Business(
    name="Acme Mobile", description="A fictional phone company: plans, bills, SIMs."
)


def test_the_answer_prompt_keeps_the_prd_order() -> None:
    prompt = answer_prompt(
        business=BUSINESS,
        sources=[Source(title="Plans", text="The Pro plan costs 20 euros a month.", language="en")],
        history=[Message("customer", "Hello"), Message("ai", "Hello! How can I help?")],
        message="How much is Pro?",
        language="en",
        filler=[],
        budgets=Budgets(),
        estimator=LENGTHS,
        fixed_tokens=0,
    )

    system = prompt.messages[0]["content"]
    assert system.index("NO_ANSWER") < system.index("Acme Mobile") < system.index("20 euros")
    assert [message["role"] for message in prompt.messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert "How much is Pro?" in prompt.messages[-1]["content"]


def build_answer(
    *,
    sources: list[Source] | None = None,
    history: list[Message] | None = None,
    message: str = "How much is Pro?",
    filler: list[Message] | None = None,
    budgets: Budgets | None = None,
    fixed_tokens: int = 0,
) -> AnswerPrompt:
    return answer_prompt(
        business=BUSINESS,
        sources=sources or [],
        history=history or [],
        message=message,
        language="en",
        filler=filler or [],
        budgets=budgets or Budgets(),
        estimator=LENGTHS,
        fixed_tokens=fixed_tokens,
    )


def sources(count: int, words: int) -> list[Source]:
    return [Source(title=f"Doc {n}", text="word " * words, language="en") for n in range(count)]


def test_the_sources_stop_at_their_budget() -> None:
    prompt = build_answer(sources=sources(7, words=160))  # 800 tokens each

    kept = [len(source.text) for source in prompt.sources]

    assert len(kept) == 4  # three whole, and the fourth cut to what is left of 2,500
    assert 2490 <= sum(kept) <= 2500


def test_the_sources_stop_at_five() -> None:
    prompt = build_answer(sources=sources(9, words=20))

    assert len(prompt.sources) == 5


def alternating(count: int, words: int) -> list[Message]:
    return [Message("customer" if n % 2 == 0 else "ai", "word " * words) for n in range(count)]


def history_tokens(prompt: AnswerPrompt) -> int:
    """The history as the prompt carries it: every message between the system's and the last."""
    return sum(len(message["content"]) for message in prompt.messages[1:-1])


def test_filler_fills_the_history_to_its_cap() -> None:
    prompt = build_answer(filler=alternating(20, words=56))

    assert 1490 <= history_tokens(prompt) <= 1500


def prompt_tokens(prompt: AnswerPrompt, fixed_tokens: int) -> int:
    """`fixed_tokens` plus whatever the prompt carries beyond an empty one."""
    skeleton = build_answer(message="")
    return fixed_tokens + characters(prompt) - characters(skeleton)


def characters(prompt: AnswerPrompt) -> int:
    return sum(len(message["content"]) for message in prompt.messages)


def test_a_lower_budget_shrinks_the_history_first_then_the_sources() -> None:
    budgets = Budgets(answer_in=1500, sources=1500, answer_history=600)

    prompt = build_answer(
        sources=sources(3, words=160),
        filler=alternating(20, words=56),
        budgets=budgets,
        fixed_tokens=400,
    )

    assert history_tokens(prompt) == 0
    assert 1490 <= prompt_tokens(prompt, fixed_tokens=400) <= 1500


def test_without_fill_the_history_is_the_conversations_own() -> None:
    own = [Message("customer", "Hello"), Message("ai", "Hello! How can I help?")]

    prompt = build_answer(
        history=own, filler=alternating(20, words=56), budgets=Budgets(fill=False)
    )

    assert prompt.history == own


def test_a_long_history_keeps_its_newest_messages() -> None:
    own = [*alternating(9, words=100), Message("ai", "The newest reply.")]

    prompt = build_answer(history=own, budgets=Budgets(fill=False))

    assert prompt.history[-1] == own[-1]
    assert len(prompt.history) < len(own)
    assert history_tokens(prompt) <= 1500


def build_classify(
    *, filler: list[Message], budgets: Budgets | None = None, fixed_tokens: int = 350
) -> ClassifyPrompt:
    return classify_prompt(
        business=BUSINESS,
        history=[],
        message="How much is Pro?",
        language="en",
        filler=filler,
        budgets=budgets or Budgets(),
        estimator=LENGTHS,
        fixed_tokens=fixed_tokens,
    )


def test_the_classify_history_fills_its_cap() -> None:
    prompt = build_classify(filler=alternating(20, words=56))

    # Short of the cap by at most a label and the 10 tokens below which a message is left out.
    assert 600 - 25 <= len(prompt.inputs["history"]) <= 600


def test_a_lower_classify_budget_shrinks_the_history() -> None:
    # 700 in: 350 fixed and 16 for the message leave 334 for the history.
    prompt = build_classify(filler=alternating(20, words=56), budgets=Budgets(classify_in=700))

    assert 334 - 25 <= len(prompt.inputs["history"]) <= 334


def test_the_classify_history_keeps_three_exchanges_at_most() -> None:
    prompt = build_classify(filler=alternating(20, words=1))

    assert len(prompt.history) == 6
