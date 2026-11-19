"""Update the copied profile's location; never edit the source PVC."""

from pathlib import Path

root = Path('/opt/data/profiles/engineering')
soul = root / 'SOUL.md'
text = soul.read_text().replace(
    'You are running in the cbio-engineer-trial namespace of the development '
    'Kubernetes cluster. This is a temporary trial on Spot capacity.',
    'You are running in a Docker container on daikondev, an on-demand MSK '
    'EC2 instance. Your persistent files are stored under '
    '/home/koj2/cbio-engineer on the host.',
)
soul.write_text(text)
skill = root / 'skills/ngrok-preview/SKILL.md'
text = skill.read_text().replace('in the dev Kubernetes cluster', 'on daikondev')
text = text.replace('or the pod is replaced', 'or the container restarts')
skill.write_text(text)
