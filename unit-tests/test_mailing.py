import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from cbio_claw import mailing


class MailingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        env = patch.dict(os.environ, {"HERMES_HOME": str(self.data)})
        env.start()
        self.addCleanup(env.stop)
        self.settings = {"forwarder_bot_ids": ["BEMAIL"]}
        self.write_policy()
        base = ModuleType("gateway.platforms.base")
        base.MessageEvent = lambda **kwargs: SimpleNamespace(**kwargs)
        base.resolve_channel_skills = lambda extra, channel: extra.get("skills")
        base.resolve_channel_prompt = lambda extra, channel: None
        modules = patch.dict(sys.modules, {"gateway.platforms.base": base})
        modules.start()
        self.addCleanup(modules.stop)
        self.client = SimpleNamespace(chat_postMessage=AsyncMock(return_value={"ok": True, "ts": "100.2"}))
        self.adapter = SimpleNamespace(
            _bot_user_id="USELF", _team_bot_user_ids={}, _channel_team={},
            _slack_allowed_channels=lambda: {"CSUPPORT"},
            _message_handler=AsyncMock(return_value="💡 *Suggested response:*\nUse the Datasets page."),
            config=SimpleNamespace(extra={}),
            build_source=lambda **kwargs: SimpleNamespace(**kwargs),
            _get_client=lambda channel: self.client,
            format_message=lambda text: text,
        )
        self.event = {"channel": "CSUPPORT", "team": "TTEST", "ts": "100.1", "bot_id": "BEMAIL", "subtype": "bot_message", "attachments": [{"title": "Data download question", "text": "How do I download this study? " + "body " * 200}]}

    def write_policy(self, enabled=True):
        (self.data / "cbio-claw.json").write_text(json.dumps({"mailing_list": {"enabled": enabled, "channels": {"CSUPPORT": self.settings}}}))

    async def dispatch(self, event):
        consumed = await mailing.handle_event(self.adapter, event)
        await asyncio.gather(*list(getattr(self.adapter, "_cbio_mailing_tasks", set())))
        return consumed

    def states(self):
        return mailing.Ledger(self.data / "cbio-claw-mailing.sqlite3").rows()

    async def test_forwarded_email_generates_and_posts_suggested_reply_in_thread(self):
        self.assertTrue(await self.dispatch( self.event))
        message = self.adapter._message_handler.call_args.args[0]
        self.assertIn(self.event["attachments"][0]["text"].strip(), message.text)
        self.assertTrue(message.internal)
        self.assertEqual(message.source.user_id, "BEMAIL")
        self.assertEqual(message.auto_skill, ["cbioportal-answer-support", "cbioportal-support"])
        kwargs = self.client.chat_postMessage.call_args.kwargs
        self.assertEqual(kwargs["channel"], "CSUPPORT")
        self.assertEqual(kwargs["thread_ts"], "100.1")
        self.assertIn("Suggested response", kwargs["text"])
        self.assertEqual(self.states()[0][1], "sent")

    async def test_duplicate_events_and_restart_do_not_repost(self):
        await asyncio.gather(self.dispatch(self.event), self.dispatch(self.event))
        await self.dispatch( dict(self.event))
        self.client.chat_postMessage.assert_awaited_once()
        self.adapter._message_handler.assert_awaited_once()

    async def test_non_actionable_email_does_not_post(self):
        self.adapter._message_handler.return_value = "NO_REPLY"
        await self.dispatch( self.event)
        self.client.chat_postMessage.assert_not_awaited()
        self.assertEqual(self.states()[0][1], "skipped")

    async def test_own_other_bot_edits_and_thread_replies_do_not_trigger(self):
        for update in ({"user": "USELF"}, {"bot_id": "BOTHER"}, {"subtype": "message_changed"}, {"thread_ts": "90.0"}):
            await self.dispatch( {**self.event, **update})
        self.adapter._message_handler.assert_not_awaited()
        self.client.chat_postMessage.assert_not_awaited()

    async def test_human_and_unconfigured_channel_use_normal_hermes_route(self):
        self.assertFalse(await self.dispatch( {"channel": "CSUPPORT", "user": "UHUMAN", "text": "hello"}))
        self.assertFalse(await self.dispatch( {**self.event, "channel": "COTHER"}))
        self.adapter._message_handler.assert_not_awaited()

    async def test_disabled_or_invalid_config_makes_no_calls(self):
        self.write_policy(False)
        self.assertTrue(await self.dispatch( self.event))
        (self.data / "cbio-claw.json").write_text("invalid")
        with self.assertLogs("cbio_claw.mailing", "ERROR"):
            self.assertFalse(await self.dispatch( self.event))
        self.client.chat_postMessage.assert_not_awaited()

    async def test_kill_switch_during_generation_prevents_delivery(self):
        async def generate(message):
            self.write_policy(False)
            return "💡 *Suggested response:*\nA suggestion"
        self.adapter._message_handler.side_effect = generate
        await self.dispatch( self.event)
        self.client.chat_postMessage.assert_not_awaited()
        self.assertEqual(self.states()[0][1], "disabled")

    async def test_dispatch_returns_while_generation_is_pending(self):
        released = asyncio.Event()
        async def generate(message):
            await released.wait()
            return "💡 *Suggested response:*\nA suggestion"
        self.adapter._message_handler.side_effect = generate
        self.assertTrue(await asyncio.wait_for(mailing.handle_event(self.adapter, self.event), timeout=0.2))
        self.client.chat_postMessage.assert_not_awaited()
        self.assertTrue(self.adapter._cbio_mailing_tasks)
        released.set()
        await asyncio.gather(*list(self.adapter._cbio_mailing_tasks))
        self.client.chat_postMessage.assert_awaited_once()

    async def test_env_off_switch_blocks_configured_bots_but_not_humans(self):
        with patch.dict(os.environ, {"CBIO_MAILING_REPLIES": "off"}):
            self.assertTrue(await self.dispatch(self.event))
            self.assertFalse(await self.dispatch({"channel": "CSUPPORT", "user": "UHUMAN"}))
        self.adapter._message_handler.assert_not_awaited()

    async def test_generation_failure_is_logged_and_can_be_reset_locally(self):
        self.adapter._message_handler.side_effect = RuntimeError("model unavailable")
        with self.assertLogs("cbio_claw.mailing", "ERROR"):
            await self.dispatch( self.event)
        self.assertEqual(self.states()[0][1], "failed")
        self.client.chat_postMessage.assert_not_awaited()
        mailing.Ledger(self.data / "cbio-claw-mailing.sqlite3").retry_failed("TTEST:CSUPPORT:100.1")
        self.assertEqual(self.states(), [])

    async def test_generator_error_text_is_not_posted_as_a_suggestion(self):
        self.adapter._message_handler.return_value = "Error: model provider unavailable"
        with self.assertLogs("cbio_claw.mailing", "ERROR"):
            await self.dispatch(self.event)
        self.client.chat_postMessage.assert_not_awaited()
        self.assertEqual(self.states()[0][1], "failed")

    async def test_ambiguous_delivery_is_not_blindly_retried(self):
        self.client.chat_postMessage.side_effect = TimeoutError("response lost")
        with self.assertLogs("cbio_claw.mailing", "ERROR"):
            await self.dispatch( self.event)
        await self.dispatch( self.event)
        self.client.chat_postMessage.assert_awaited_once()
        self.assertEqual(self.states()[0][1], "uncertain")
        with self.assertRaises(ValueError):
            mailing.Ledger(self.data / "cbio-claw-mailing.sqlite3").retry_failed("TTEST:CSUPPORT:100.1")

    async def test_allowed_channel_policy_remains_enforced(self):
        self.adapter._slack_allowed_channels = lambda: {"COTHER"}
        with self.assertLogs("cbio_claw.mailing", "WARNING"):
            await self.dispatch( self.event)
        self.client.chat_postMessage.assert_not_awaited()

    async def test_display_overrides_are_scoped_to_drafting_context(self):
        config = {"display": {"platforms": {"slack": {"streaming": True}}}, "agent": {"disabled_toolsets": ["browser"]}}
        namespace = {"_load_gateway_config": lambda: config}
        mailing.install_gateway(namespace)
        self.assertIs(namespace["_load_gateway_config"](), config)
        token = mailing._drafting.set(True)
        try:
            overridden = namespace["_load_gateway_config"]()
            self.assertFalse(overridden["display"]["platforms"]["slack"]["streaming"])
            self.assertFalse(overridden["display"]["platforms"]["slack"]["interim_assistant_messages"])
            self.assertIn("messaging", overridden["agent"]["disabled_toolsets"])
            self.assertIn("browser", overridden["agent"]["disabled_toolsets"])
        finally:
            mailing._drafting.reset(token)
        self.assertTrue(config["display"]["platforms"]["slack"]["streaming"])
