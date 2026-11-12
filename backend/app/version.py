"""Single source of truth for the version the server reports.

``APP_VERSION`` is the product version (what /server/info advertises to clients);
``API_VERSION`` is the contract version a client can gate on. Bump ``API_VERSION``
only for a breaking change to the HTTP API, not for new endpoints.
"""

from __future__ import annotations

import os

APP_VERSION = "2.1.0"
API_VERSION = 1

#: The variable an image build stamps with the release it was cut from.
#: ``deploy/docker/Dockerfile.api`` turns ``--build-arg PFC_RELEASE_TAG`` into
#: this, and compose fills that argument from ``PFC_IMAGE_TAG``. Reading it here
#: rather than importing a constant is what lets an image describe itself: the
#: ``0.6.3`` image reports ``v0.6.3`` with nobody editing a source file, and a
#: forgotten bump cannot make a release advertise the previous tag.
RELEASE_TAG_ENV = "PFC_RELEASE_TAG"


def release_tag() -> str | None:
    """The release this build was cut from, or None when nothing stamped it.

    A bare ``0.6.3`` gains its ``v`` because the build argument can come from an
    image tag. A source checkout, a test run or a dev container is unstamped and
    reports None rather than claiming to be a release it is not.
    """
    value = os.environ.get(RELEASE_TAG_ENV, "").strip()
    if not value:
        return None
    return value if value.startswith("v") else f"v{value}"


# The oldest client API generation this server still serves.
MIN_CLIENT_API_VERSION = 1
