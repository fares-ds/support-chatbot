from pathlib import Path

from bench.config import load_config


def test_a_configuration_names_its_dataset_and_a_run_can_swap_it(tmp_path: Path) -> None:
    path = tmp_path / "dev.toml"
    path.write_text(
        'name = "dev"\n[classifier]\nmode = "embedding"\n[answer]\nmodel = "ollama_chat/m"\n',
        encoding="utf-8",
    )
    config = load_config(path)

    swapped = config.with_dataset(Path("data/gov-uk"))

    assert config.data.dataset == Path("data/acme-pay")
    # The results' header holds the configuration as run, so it names the dataset.
    assert swapped.model_dump(mode="json")["data"] == {"dataset": "data/gov-uk"}
