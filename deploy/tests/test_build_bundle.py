import hashlib
import sys
import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_bundle import build, missing_from_template, pin, unpinned_images  # noqa: E402

COMPOSE = """services:
  api:
    image: ghcr.io/fares-ds/support-chatbot-backend:${SC_VERSION:?SC_VERSION is not set}
  caddy:
    image: ghcr.io/fares-ds/support-chatbot-caddy:${SC_VERSION:?SC_VERSION is not set}
  postgres:
    image: pgvector/pgvector:0.8.7-pg18-trixie
"""


class PinTest(unittest.TestCase):
    def test_our_images_are_pinned_to_the_release(self) -> None:
        pinned = pin(COMPOSE, "1.4.0")

        self.assertIn("image: ghcr.io/fares-ds/support-chatbot-backend:1.4.0\n", pinned)
        self.assertIn("image: ghcr.io/fares-ds/support-chatbot-caddy:1.4.0\n", pinned)
        self.assertNotIn("SC_VERSION", pinned)



class UnpinnedImagesTest(unittest.TestCase):
    def test_fixed_tags_pass(self) -> None:
        compose = pin(COMPOSE, "1.4.0") + (
            "  tei:\n    image: ghcr.io/huggingface/text-embeddings-inference:"
            "${SC_TEI_TAG:-cpu-1.9.4}\n"
            "  valkey:\n    image: valkey/valkey@sha256:" + "a" * 64 + "\n"
        )

        self.assertEqual(unpinned_images(compose, "1.4.0"), [])

    def test_a_moving_or_missing_tag_is_refused(self) -> None:
        for image in [
            "valkey/valkey",
            "ollama/ollama:latest",
            "caddy:alpine",
            "ghcr.io/huggingface/text-embeddings-inference:${SC_TEI_TAG}",
            "ghcr.io/huggingface/text-embeddings-inference:${SC_TEI_TAG:-latest}",
            "ghcr.io/fares-ds/support-chatbot-backend:1.3.9",
            "ghcr.io/fares-ds/support-chatbot-backend:${SC_VERSION:?SC_VERSION is not set}",
        ]:
            with self.subTest(image=image):
                compose = f"services:\n  one:\n    image: {image}\n"
                self.assertEqual(len(unpinned_images(compose, "1.4.0")), 1)



class TemplateTest(unittest.TestCase):
    def test_the_template_covers_every_setting_the_compose_file_reads(self) -> None:
        compose = (
            "    image: x:${SC_VERSION:?not set}\n"
            "    environment:\n"
            "      SC_DOMAIN: ${SC_DOMAIN:?not set}\n"
            "      SC_OLLAMA_URL: ${SC_OLLAMA_URL:-http://ollama:11434}\n"
            "      SC_TEI_TAG: ${SC_TEI_TAG:-cpu-1.9.4}\n"
        )
        template = "SC_DOMAIN=\n# SC_OLLAMA_URL=http://ollama:11434\n"

        self.assertEqual(missing_from_template(compose, template), ["SC_TEI_TAG"])



def deploy_directory(root: Path, compose: str = COMPOSE) -> Path:
    deploy = root / "deploy"
    deploy.mkdir()
    (deploy / "compose.yaml").write_text(compose)
    (deploy / "Caddyfile").write_text("{$SC_DOMAIN} {\n}\n")
    (deploy / "env.template").write_text("SC_DOMAIN=\n")
    (deploy / "README.md").write_text("# The install bundle\n")
    (deploy / "compose.dev.yaml").write_text("services: {}\n")
    return deploy


class BuildTest(unittest.TestCase):
    def test_a_bundle_holds_the_pinned_compose_file_and_its_companions(self) -> None:
        with TemporaryDirectory() as tmp:
            archive = build("1.4.0", deploy_directory(Path(tmp)), Path(tmp) / "dist")

            with tarfile.open(archive) as tar:
                names = sorted(tar.getnames())
                compose = tar.extractfile("support-chatbot-1.4.0/compose.yaml").read().decode()
            checksum = archive.with_name(archive.name + ".sha256").read_text()
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()

        self.assertEqual(archive.name, "support-chatbot-1.4.0.tar.gz")
        self.assertEqual(
            names,
            [
                "support-chatbot-1.4.0",
                "support-chatbot-1.4.0/Caddyfile",
                "support-chatbot-1.4.0/README.md",
                "support-chatbot-1.4.0/compose.yaml",
                "support-chatbot-1.4.0/env.template",
            ],
        )
        self.assertIn("support-chatbot-backend:1.4.0", compose)
        self.assertEqual(checksum, f"{digest}  support-chatbot-1.4.0.tar.gz\n")

    def test_a_version_reads_major_minor_patch(self) -> None:
        with TemporaryDirectory() as tmp:
            deploy = deploy_directory(Path(tmp))
            for version in ["v1.4.0", "1.4", "1.4.0-rc1"]:
                with self.subTest(version=version), self.assertRaises(ValueError):
                    build(version, deploy, Path(tmp) / "dist")

    def test_an_unpinned_image_or_an_unlisted_setting_is_refused(self) -> None:
        for extra in [
            "  valkey:\n    image: valkey/valkey:latest\n",
            "    environment:\n      SC_LOG_LEVEL: ${SC_LOG_LEVEL:-INFO}\n",
        ]:
            with self.subTest(extra=extra), TemporaryDirectory() as tmp:
                deploy = deploy_directory(Path(tmp), COMPOSE + extra)
                with self.assertRaises(ValueError):
                    build("1.4.0", deploy, Path(tmp) / "dist")


if __name__ == "__main__":
    unittest.main()
