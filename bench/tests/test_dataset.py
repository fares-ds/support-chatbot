from datetime import date
from pathlib import Path

import pytest

from bench.data import Provenance, load_dataset

KB = {
    "fr-recharges.md": (
        "# Recharges\n\nAcme Pay recharge les trois opérateurs.\n\n"
        "## Recharge échouée\n\nLe montant revient au portefeuille sous 24 heures.\n\n"
        "### Signaler\n\nSignalez-la dans l'application.\n"
    ),
    "ar-recharges.md": "# الشحن\n\n## فشل الشحن\n\nيعود المبلغ إلى المحفظة خلال 24 ساعة.\n",
}
ANSWERABLE = """
[[turns]]
id = "fr-failed"
language = "fr"
message = "Ma recharge n'est pas arrivée."
category = "on_topic"
expect = "answer"
facts = ["The amount returns to the wallet within 24 hours"]
sources = ["{source}"]
"""
EXAMPLES = """
yes = ["oui"]

[examples]
on_topic = ["Comment payer une facture ?"]
off_topic = ["Écris un poème"]
human_request = ["Je veux parler à quelqu'un"]
smalltalk = ["Bonjour"]
"""
SOURCES = """
license = "Vendor-owned"
origin = "Written for the benchmark"

[[documents]]
file = "ar-recharges.md"
origin = "https://example.com/ar/recharges"
retrieved = 2026-10-07
"""


def dataset(
    tmp_path: Path,
    *,
    turns: str = ANSWERABLE.format(source="fr-recharges.md#Recharge échouée"),
    sources: str = SOURCES,
    examples: str = EXAMPLES,
    description: str = "A wallet for top-ups and bills.",
) -> Path:
    directory = tmp_path / "acme-pay"
    (directory / "kb").mkdir(parents=True)
    for name, markdown in KB.items():
        (directory / "kb" / name).write_text(markdown, encoding="utf-8")
    business = f'[business]\nname = "Acme Pay"\ndescription = "{description}"\n'
    (directory / "turns.toml").write_text(business + turns, encoding="utf-8")
    (directory / "sources.toml").write_text(sources, encoding="utf-8")
    (directory / "examples.toml").write_text(examples, encoding="utf-8")
    return directory


def test_each_document_takes_its_provenance_from_the_sources_file(
    tmp_path: Path,
) -> None:
    loaded = load_dataset(dataset(tmp_path))

    assert loaded.name == "acme-pay"
    assert [document.name for document in loaded.documents] == [
        "ar-recharges.md",
        "fr-recharges.md",
    ]
    assert loaded.provenance == {
        "ar-recharges.md": Provenance(
            "https://example.com/ar/recharges", "Vendor-owned", "", date(2026, 10, 7)
        ),
        "fr-recharges.md": Provenance("Written for the benchmark", "Vendor-owned", "", None),
    }


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"sources": 'license = "Vendor-owned"\n'}, "recharges.md has no origin"),
        ({"sources": 'origin = "Written for the benchmark"\n'}, "recharges.md has no license"),
        (
            {"sources": SOURCES + '\n[[documents]]\nfile = "en-fees.md"\norigin = "x"\n'},
            "en-fees.md.*not in kb",
        ),
        ({"turns": ANSWERABLE.format(source="fr-frais.md")}, "fr-failed.*fr-frais.md"),
        (
            {"turns": ANSWERABLE.format(source="fr-recharges.md#Signaler")},
            "fr-failed.*Signaler",
        ),
        (
            {"turns": ANSWERABLE.format(source="fr-recharges.md#Recharge échouée > Rembourser")},
            "fr-failed.*Rembourser",
        ),
        (
            {"examples": EXAMPLES.replace("Écris un poème", "ma recharge n'est pas  arrivée.")},
            "fr-failed.*example",
        ),
        ({"description": "x" * 501}, "500 characters"),
    ],
)
def test_a_dataset_that_disagrees_with_itself_is_refused(
    tmp_path: Path, change: dict[str, str], error: str
) -> None:
    directory = dataset(tmp_path, **change)

    with pytest.raises(ValueError, match=error):
        load_dataset(directory)


@pytest.mark.parametrize(
    "source",
    [
        "fr-recharges.md",
        "fr-recharges.md#Recharge échouée > Signaler",
        "ar-recharges.md#فشل الشحن | fr-recharges.md#Recharge échouée",
    ],
)
def test_a_source_may_name_a_whole_document_a_nested_section_or_copies(
    tmp_path: Path, source: str
) -> None:
    loaded = load_dataset(dataset(tmp_path, turns=ANSWERABLE.format(source=source)))

    assert len(loaded.samples[0].sources) == 1
