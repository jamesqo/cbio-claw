"""Read bounded Slack email files; never fetch links embedded in their contents."""

from html.parser import HTMLParser
import json
from urllib.parse import urlsplit

MAX_BYTES = 512 * 1024


class EmailHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" or (tag == "input" and attrs.get("type") == "password"):
            raise ValueError("Slack returned a login/form page instead of an email")
        if tag in {"script", "style", "head"}:
            self.hidden += 1
        if not self.hidden:
            if tag in {"br", "p", "div", "tr", "li", "hr"}:
                self.parts.append("\n")
            if tag == "a" and attrs.get("href", "").startswith(("https://", "http://")):
                self.parts.append(" " + attrs["href"] + " ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"} and self.hidden:
            self.hidden -= 1
        if not self.hidden and tag in {"p", "div", "tr", "li"}:
            self.parts.append("\n")

    def handle_data(self, text):
        if not self.hidden:
            self.parts.append(text)


def email_body(raw: bytes, *, html=True) -> str:
    text = raw.decode("utf-8-sig")
    try:
        envelope = json.loads(text)
    except ValueError:
        envelope = None
    subject = ""
    if isinstance(envelope, dict):
        subject = envelope.get("subject", "")
        plain = envelope.get("body-plain")
        if isinstance(plain, str) and plain.strip():
            return f"{subject}\n\n{plain}".strip()
        text = envelope.get("body-html") or envelope.get("simplified_html") or ""
        html = True
    if not html:
        return text.strip()
    parser = EmailHTML()
    parser.feed(text)
    parser.close()
    body = "".join(parser.parts).strip()
    return (subject + "\n\n" + body).strip() if body else ""


def slack_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in {"files.slack.com", "files-origin.slack.com"}
            or parsed.username or parsed.password or parsed.port not in {None, 443}):
        raise ValueError("Email download URL must be on Slack's HTTPS file CDN")
    return url


async def file_text(adapter, event):
    files = event.get("files", [])
    if not files:
        return ""
    import httpx

    if len(files) > 4:
        raise ValueError("Too many email files")
    parts = []
    client = adapter._get_client(event["channel"])
    for stub in files:
        info = await client.files_info(file=stub["id"])
        if not info.get("ok"):
            raise ValueError("Slack files.info did not confirm file access")
        file = info["file"]
        if file.get("mimetype", "").split(";")[0] not in {"text/html", "text/plain", "application/json"}:
            continue
        if not 0 < file.get("size", 0) <= MAX_BYTES:
            raise ValueError("Email file has unknown or excessive size")
        url = slack_url(file.get("url_private_download") or file.get("url_private", ""))
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as downloader:
            for redirect in range(4):
                async with downloader.stream("GET", url, headers={"Authorization": f"Bearer {client.token}"}) as response:
                    if response.is_redirect:
                        url = slack_url(str(response.url.join(response.headers["location"])))
                        continue
                    response.raise_for_status()
                    is_html = file["mimetype"].split(";")[0] == "text/html"
                    if "text/html" in response.headers.get("content-type", "") and not is_html:
                        raise ValueError("Slack returned HTML instead of the declared email file type")
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_BYTES:
                            raise ValueError("Email download exceeds size limit")
                    body = email_body(bytes(raw), html=is_html)
                    if not body:
                        raise ValueError("Email file contains no readable body")
                    parts.append(body)
                    break
            else:
                raise ValueError("Too many Slack file redirects")
    return "\n\n".join(parts)
