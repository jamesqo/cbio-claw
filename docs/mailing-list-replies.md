# Automatic mailing-list suggestions

The runtime extension hooks the Slack adapter in Hermes `v2026.6.5`. It accepts
new, top-level forwarded emails only from explicitly configured forwarding bot
IDs in configured channels. Human conversations and unconfigured channels use
the normal Hermes path. Do not enable a global bot allow-all flag for this feature.

For an accepted email, the extension preserves complete attachment/block text,
uses the configured channel skills and model through Hermes, and posts the
returned suggested response in the email's Slack thread. It does not send email
to the Google Group. Notifications/spam/reply chains without a new actionable
question are skipped using `NO_REPLY`.

Generation runs in a tracked background task so Socket Mode event handling
returns promptly while the model researches the question.

Only the final suggested response is posted. A per-turn configuration override
disables streaming, progress/interim chatter, and messaging/cron tools during
generation without changing other Slack conversations or the saved config.
The synthetic generation event is authorized after exact forwarding-app and
channel checks, including Hermes's configured allowed channels; human and bot
allowlists are not widened.

## Opt-in configuration

Install the `researcher-support` preset for the target channel. In the selected
local/test Hermes data directory, create `cbio-claw.json`:

```json
{
  "mailing_list": {
    "enabled": false,
    "channels": {
      "CTESTSUPPORT": {
        "forwarder_bot_ids": ["BTESTEMAIL"]
      }
    }
  }
}
```

Replace placeholders with the test channel and forwarding app's `bot_id`, not
its display name or user ID. Include the channel in Hermes's allowed-channel
list if one is configured. The app needs the existing Socket Mode connection,
channel message events/history, and `chat:write`; it must be invited to the
channel. Use separate test app tokens while the existing gateway is active.

Changing `enabled` to `true` deliberately activates posting on the next matching
event. Keep it false until activation is authorized. The file is read each event
and rechecked before posting. Setting `CBIO_MAILING_REPLIES=off` is an additional
off switch. Malformed configuration fails closed. Normal manual replies remain
under Hermes's existing mention/authentication behavior.

## Delivery state and failures

The persistent `cbio-claw-mailing.sqlite3` ledger claims each workspace/channel/
message timestamp once. Duplicate events, concurrent delivery, reconnects, and
process restarts do not produce another suggestion. Other bots, own replies,
message edits, and thread replies do not trigger automatic generation.

States include `drafting`, `generated`, `sending`, `sent`, `skipped`, `failed`,
`disabled`, and `uncertain`. Generation and delivery failures are logged with
the event key. Inspect local state without contacting Slack:

```sh
PYTHONPATH=docker python3 -m cbio_claw.mailing --data-dir /path/to/test-data
```

Only a failed generation can be reset with `--retry-failed EVENT_KEY`; resetting
does not itself replay the event or send anything. If delivery timed out or the
process stopped during sending, reconcile the thread first. The ledger stores
the generated draft and confirmed Slack message timestamp, and sends a stable
`client_msg_id`, but cannot atomically commit both SQLite and Slack. It therefore
does not blindly retry uncertain sends. A crash during generation also requires
operator inspection rather than automatic duplicate processing.

## Offline validation

`make test-unit` uses synthetic email events, a fake generator, and fake Slack
clients. It starts no gateway and needs no tokens. Optional integration tests
exercise the real pinned Slack adapter and skill discovery with network disabled;
see the tests' `HERMES_TEST_SOURCE` and `CBIO_TEST_VAULT` environment variables.
Live model quality and test-workspace permissions still need verification before
enabling this on a real channel.
