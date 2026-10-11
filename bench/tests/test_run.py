from bench.run import classification_prefix, embedding_prefixes


def test_each_embedding_family_gets_the_prefixes_it_was_trained_with() -> None:
    assert embedding_prefixes("intfloat/multilingual-e5-small") == ("query: ", "passage: ")
    query, document = embedding_prefixes("Qwen/Qwen3-Embedding-0.6B")
    assert query.startswith("Instruct: ") and query.endswith("\nQuery:")  # as its model card has it
    assert document == ""
    assert embedding_prefixes("BAAI/bge-m3") == ("", "")


def test_the_embedding_check_classifies_with_its_own_instruction_not_the_search_one() -> None:
    search, _ = embedding_prefixes("Qwen/Qwen3-Embedding-0.6B")

    classify = classification_prefix("Qwen/Qwen3-Embedding-0.6B")

    assert classify.startswith("Instruct: ") and classify != search
    assert classification_prefix("intfloat/multilingual-e5-small") == "query: "
    assert classification_prefix("BAAI/bge-m3") == ""
