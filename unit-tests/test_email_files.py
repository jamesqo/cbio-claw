import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from cbio_claw.email_files import MAX_BYTES, email_body, file_text


class EmailFileTests(unittest.IsolatedAsyncioTestCase):
    async def read(self, response, **metadata):
        file = {"mimetype": "text/html", "size": 1000, "url_private_download": "https://files.slack.com/files-pri/T-F/question.html", **metadata}
        client = SimpleNamespace(token="xoxb-fake", files_info=AsyncMock(return_value={"ok": True, "file": file}))
        adapter = SimpleNamespace(_get_client=lambda channel: client)
        real_client = httpx.AsyncClient
        requests = []
        def transport(request):
            requests.append(request)
            return response(request)
        with patch("httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs)):
            result = await file_text(adapter, {"channel": "CTEST", "files": [{"id": "FEMAIL"}]})
        client.files_info.assert_awaited_once_with(file="FEMAIL")
        return result, requests

    async def test_html_email_is_downloaded_with_channel_token(self):
        result, requests = await self.read(lambda request: httpx.Response(200, headers={"content-type": "text/html"}, text="<head><style>hidden</style></head><p>How do I export <b>MET</b> alterations?</p><script>ignore</script><a href='https://example.org/study'>study</a>"))
        self.assertIn("How do I export MET alterations?", result)
        self.assertIn("https://example.org/study", result)
        self.assertNotIn("hidden", result)
        self.assertNotIn("ignore", result)
        self.assertEqual(requests[0].headers["authorization"], "Bearer xoxb-fake")
        self.assertEqual(len(requests), 1)  # Embedded links are never fetched.

    async def test_envelope_prefers_complete_plain_body(self):
        plain = "Question " + "full body " * 200
        raw = json.dumps({"subject": "Export error", "body-plain": plain, "simplified_html": "<p>short preview</p>"})
        result, _ = await self.read(lambda request: httpx.Response(200, text=raw))
        self.assertEqual(result, "Export error\n\n" + plain.rstrip())

    def test_envelope_html_fallback_and_entities(self):
        result = email_body(b'{"subject":"Question","body-html":"<p>MET &amp; EGFR</p>"}')
        self.assertIn("Question", result)
        self.assertIn("MET & EGFR", result)

    async def test_login_html_never_becomes_a_question(self):
        with self.assertRaisesRegex(ValueError, "login/form"):
            await self.read(lambda request: httpx.Response(200, text="<form><input type='password'></form>"))

    async def test_off_cdn_redirect_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Slack's HTTPS"):
            await self.read(lambda request: httpx.Response(302, headers={"location": "https://example.org/login"}))

    async def test_slack_cdn_redirect_keeps_auth(self):
        def response(request):
            if request.url.host == "files.slack.com":
                return httpx.Response(302, headers={"location": "https://files-origin.slack.com/email.html"})
            return httpx.Response(200, text="<p>Question?</p>")
        result, requests = await self.read(response)
        self.assertEqual(result, "Question?")
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(request.headers["authorization"] == "Bearer xoxb-fake" for request in requests))

    async def test_metadata_and_streamed_size_are_bounded(self):
        with self.assertRaisesRegex(ValueError, "size"):
            await self.read(lambda request: self.fail("must not download"), size=MAX_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "size limit"):
            await self.read(lambda request: httpx.Response(200, content=b"x" * (MAX_BYTES + 1)))

    async def test_permission_failure_is_reported(self):
        with self.assertRaises(httpx.HTTPStatusError):
            await self.read(lambda request: httpx.Response(403))

    async def test_unsupported_file_does_not_supply_a_question(self):
        result, requests = await self.read(lambda request: self.fail("must not download"), mimetype="application/pdf")
        self.assertEqual(result, "")
        self.assertEqual(requests, [])
