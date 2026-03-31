from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from unittest import mock

from forge.uplink.slack import SlackNotifier


class SlackNotifierTest(unittest.TestCase):
    def test_notify_posts_to_webhook_from_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            payloads: list[tuple[str, dict[str, str]]] = []

            def sender(url: str, payload: dict[str, str]) -> None:
                payloads.append((url, payload))

            with mock.patch.dict("os.environ", {"FORGE_SLACK_WEBHOOK_URL": "https://hooks.slack.test/abc"}):
                notifier = SlackNotifier(repo_root=repo_root, sender=sender)
                sent = notifier.notify("Forge heartbeat")

        self.assertTrue(sent)
        self.assertEqual(payloads, [("https://hooks.slack.test/abc", {"text": "Forge heartbeat"})])

    def test_notify_reads_webhook_from_tools_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            (repo_root / "TOOLS.md").write_text(
                "\n".join(
                    [
                        "# TOOLS.md",
                        "",
                        "## Slack (Uplink)",
                        "Notification target: `forge-alerts` (channel ID: `C123`)",
                        "Webhook URL: `https://hooks.slack.test/from-tools`",
                    ]
                ),
                encoding="utf-8",
            )
            payloads: list[tuple[str, dict[str, str]]] = []

            notifier = SlackNotifier(
                repo_root=repo_root,
                sender=lambda url, payload: payloads.append((url, payload)),
            )
            sent = notifier.notify("Forge failure")

        self.assertTrue(sent)
        self.assertEqual(payloads[0][0], "https://hooks.slack.test/from-tools")
        self.assertEqual(payloads[0][1]["text"], "Forge failure")

    def test_notify_is_noop_without_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            notifier = SlackNotifier(repo_root=repo_root)

            sent = notifier.notify("Forge heartbeat")

        self.assertFalse(sent)
