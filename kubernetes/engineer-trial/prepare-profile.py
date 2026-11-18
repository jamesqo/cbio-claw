"""Adjust a copied Engineer profile for the dev cluster; never run on the source."""

from pathlib import Path
import sys

import yaml


root = Path(sys.argv[1]).resolve()
assert root == Path('/migration/data'), 'Run only inside the staging pod'
profile = root / 'profiles/engineering'
config = profile / 'config.yaml'
settings = yaml.safe_load(config.read_text())
assert settings['terminal']['backend'] == 'local'
assert set(settings['mcp_servers']) == {'playwright'}
settings.setdefault('security', {})['tirith_path'] = (
    '/opt/data/profiles/engineering/bin/tirith'
)
config.write_text(yaml.safe_dump(settings, sort_keys=False))

soul = profile / 'SOUL.md'
text = soul.read_text().replace(
    'You are running in Docker on dev-macbook.',
    'You are running in the cbio-engineer-trial namespace of the development '
    'Kubernetes cluster. This is a temporary trial on Spot capacity.',
)
soul.write_text(text)
skill = profile / 'skills/ngrok-preview/SKILL.md'
text = skill.read_text().replace('on dev-macbook', 'in the dev Kubernetes cluster')
text = text.replace('or the Mac loses connectivity', 'or the pod is replaced')
skill.write_text(text)
print('Prepared copied profile for dev Kubernetes')
