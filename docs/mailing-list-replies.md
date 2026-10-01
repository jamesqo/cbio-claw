# Automatic mailing-list suggestions

The extension accepts new top-level forwarded emails from explicit forwarding
IDs in configured channels. Other conversations use normal Hermes handling.
Slackbot email forwards can have an empty/absent `text` field and an uploaded
HTML file; the extension reads the file before generating a suggestion.

## Opt-in configuration

In a local/test Hermes data directory, create `cbio-claw.json`:

```json
{
  "mailing_list": {
    "enabled": false,
    "channels": {
      "CTESTSUPPORT": {"forwarder_user_ids": ["USLACKBOT"]}
    }
  }
}
```

Use exact user IDs for Slackbot, or `forwarder_bot_ids` for apps supplying a
`bot_id`. IDs are scoped to the configured channel; no global allow-all setting
is needed. Configure the channel's support skills and include it in Hermes's
allowed-channel list. The app needs message events/history, `files:read`, and
`chat:write`, plus membership in the channel. Use separate test app credentials.

Replies remain off until `enabled` is deliberately set to true. The file is
read each event and rechecked before posting; `CBIO_MAILING_REPLIES=off` is an
additional kill switch. Nothing in this PR changes live configuration.

## Files and generation

Downloads use the channel's Slack token and `files.info` metadata, accept only
Slack's HTTPS file CDN (including validated redirects), and cap each file at
512 KiB and each message at four files. Plain text, HTML and JSON email envelopes
are supported. Prefer complete `body-plain`; otherwise extract HTML text and
links without fetching embedded resources. Login/form pages, oversized files,
and permission failures stop generation and are logged. PDF/image interpretation
is outside this reader's scope.

Generation runs in a background task, uses Hermes's model and configured skills,
and treats the email as untrusted content. Only a final `Suggested response`
is posted in the original thread; `NO_REPLY` skips non-actionable mail. Streaming,
progress chatter and messaging/cron tools are disabled for this generation turn.
The extension does not send email to the Google Group.

## Delivery state

A persistent SQLite ledger claims each workspace/channel/message timestamp
once, including across restarts. Bot replies, edits, and true thread replies
are ignored. Confirmed posts are recorded; ambiguous sends are never blindly
retried. SQLite and Slack are not an atomic transaction.

Inspect local state with `PYTHONPATH=docker python3 -m cbio_claw.mailing
--data-dir /path/to/test-data`. Only failed generation can be reset with
`--retry-failed EVENT_KEY`; resetting does not replay or send anything. Reconcile
uncertain delivery or interrupted generation manually before any replay.

## Validation and upstream

`make test-unit` uses synthetic fixtures and mocked HTTP/generation/Slack clients;
install `requirements-dev.txt` first. Optional tests use the actual pinned Hermes
adapter via `HERMES_TEST_SOURCE`. No live replies or model quality are asserted.

Upstream main was inspected at `a3b56cac95488242856b6fb1f121842a38c3e391`.
It has broader document support and a video-only `file_shared` fallback, but
`_download_slack_file_bytes` still rejects all `text/html` responses. The pinned
`v2026.6.5` also excludes HTML from inline text injection. A version upgrade alone
therefore does not establish support for these HTML email forwards.
