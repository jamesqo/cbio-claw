# Skill presets

The private [cBio Claw configuration vault](https://github.com/cBioPortal/cbio-claw-configuration)
owns skill content and `presets.json`. Runtime code in this repository composes
its reusable modules and installs the selected skills into
`<HERMES_DATA>/skills/cbio-claw`. Nothing is installed until explicitly selected.

- `researcher-support` includes the existing support/product/diagnosis skills.
- `engineering` reuses the product context and adds stack/development/import/
  operations recipes. It does not preload the mailing-list reply workflow.

The installer preserves unrelated installed skills. It reuses a byte-identical
existing skill rather than installing a duplicate name. A differing name
collision stops installation so the operator can reconcile it. Preset switching
only replaces the installer-owned directory, identified by `.managed.json`.
Reference files and scripts are copied with their owning skill.

## Local preparation

Clone the private vault with your own GitHub access, then use an empty local
data directory to inspect a preset:

```sh
python3 -m pip install -r requirements-dev.txt
PYTHONPATH=docker python3 -m cbio_claw.vault \
  --vault /path/to/cbio-claw-configuration \
  --data-dir /path/to/test-data --preset engineering
```

No model, Slack connection, SSH session, or database is used. The installer
does not copy the vault's private `config.yaml`, pairing state, sync scripts,
or credentials. For a deployment, install its private runtime configuration
separately. Pin/review the vault revision alongside the runtime image.

## Deployment and channel selection

Install the deployment's chosen preset and optionally bind Slack channel IDs:

```sh
PYTHONPATH=docker python3 -m cbio_claw.vault \
  --vault /path/to/cbio-claw-configuration \
  --data-dir /path/to/test-data --preset engineering \
  --channel CTESTSUPPORT=researcher-support \
  --channel CTESTENGINEERING=engineering
```

Channel selection installs the union of the deployment and channel presets.
Hermes discovers that union; each channel automatically preloads its preset's
entrypoint skills. This provides focused guidance, not a permission boundary or
per-channel isolation of tools. Related skills are loaded on demand.

Bindings are written to top-level `slack.channel_skill_bindings`, where the
pinned Hermes configuration loader reads them. Other channel bindings and
settings are retained. The first rewrite saves `config.yaml.before-presets`;
YAML comments/formatting are not preserved. Stop the gateway before updating
the selected skill tree/configuration, then restart it after reviewing the result.

For a future container deployment, the optional Compose override mounts a
reviewed vault checkout read-only:

```sh
export CBIO_SKILL_VAULT=/absolute/host/path/to/cbio-claw-configuration
export CBIO_SKILL_PRESET=engineering
export CBIO_SKILL_CHANNELS='{"CTESTSUPPORT":"researcher-support"}'
docker compose --env-file docker-compose.env \
  -f docker-compose.yml -f docker-compose.skills.yml config
```

Use the same override when starting the gateway only after deployment is
authorized. Without the override or `CBIO_SKILL_PRESET`, startup leaves the
existing vault/config alone. Installing the skills does not enable auto-replies.

## Extending the vault

Add a named skill folder and its references in the private vault, register its
relative path in `presets.json.skills`, add it to a reusable module, and select
that module in a preset. `auto_skills` must reference skills in that preset.
Use entrypoints to route work, rather than preloading every detailed recipe.
The runtime installer validates paths, frontmatter, and preset membership before
changing the installed tree.
