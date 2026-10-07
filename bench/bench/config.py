"""A model configuration: one TOML file per configuration to benchmark, in configs/."""

import tomllib
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, model_validator

from bench.classify import ON_TOPIC_MARGIN
from bench.prompts import Budgets


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Classifier(_Section):
    mode: Literal["model", "embedding"]
    """A small model through DSPy, or the embedding check on tei-embed (AI-8)."""
    model: str | None = None
    """A LiteLLM model. Models on Ollama start with ollama_chat/."""
    api_base: str | None = None
    """Where the model is served. Ollama models default to the stack's Ollama."""
    reasoning_effort: str | None = None
    margin: float = ON_TOPIC_MARGIN
    """The embedding check's on_topic bias."""

    @model_validator(mode="after")
    def _a_model_mode_names_its_model(self) -> Self:
        if self.mode == "model" and not self.model:
            raise ValueError("classifier.mode = 'model' needs classifier.model")
        return self


class Answer(_Section):
    model: str
    api_base: str | None = None
    reasoning_effort: str | None = None
    temperature: float = Field(default=0.3, ge=0, le=0.3)
    """Gate 3 allows at most 0.3."""


class Run(_Section):
    concurrency: list[PositiveInt] = [1]
    turns: PositiveInt = 20
    """Turns per concurrency level. p95 means little below about 20."""
    warmup: NonNegativeInt = 2
    """Turns before the first level, left out of the results: they load the models."""


class Data(_Section):
    dataset: Path = Path("data/acme-pay")
    """One business's directory in data/, relative to the bench directory."""


class Stack(_Section):
    project: str = "support-chatbot"
    """The Compose project whose containers are measured, and whose api container tells the
    harness where Ollama is and the Postgres password."""
    extra_containers: list[str] = []
    """Containers outside the project to measure too, such as an Ollama that runs on its own."""


class Config(_Section):
    name: str
    description: str = ""
    classifier: Classifier
    answer: Answer
    budgets: Budgets = Field(default_factory=Budgets)
    run: Run = Field(default_factory=Run)
    data: Data = Field(default_factory=Data)
    stack: Stack = Field(default_factory=Stack)

    def with_dataset(self, dataset: Path) -> Self:
        return self.model_copy(update={"data": Data(dataset=dataset)})


def load_config(path: Path) -> Config:
    return Config.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
