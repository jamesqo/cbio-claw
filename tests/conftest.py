import time
import requests
import pytest
from utils import BASE_URL, _installs

@pytest.fixture(scope="session", autouse=True)
def wait_for_gateway():
    """Wait for the Hermes Gateway /health endpoint to become available."""
    print(f"\nWaiting for Gateway at {BASE_URL}...")
    for _ in range(30):
        try:
            r = requests.get(f"{BASE_URL}/health")
            if r.status_code == 200:
                print("Gateway is ready!")
                return
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    pytest.fail("Gateway did not start in time.")


@pytest.fixture(scope="session", autouse=True)
def install_summary():
    """After all tests, print a summary of any packages the agent installed."""
    yield
    print("\n")
    if _installs:
        print("⚠️  Packages installed during the test run (consider pre-installing in the image):")
        for pkg in _installs:
            print(f"  • {pkg}")
    else:
        print("✓ No packages were installed during the test run.")
