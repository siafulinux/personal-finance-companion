"""Single source of truth for the version the server reports.

``APP_VERSION`` is the product version (what /server/info advertises to clients);
``API_VERSION`` is the contract version a client can gate on. Bump ``API_VERSION``
only for a breaking change to the HTTP API, not for new endpoints.
"""

from __future__ import annotations

APP_VERSION = "2.1.0"
API_VERSION = 1

#: The git release tag this build was cut from, e.g. ``v0.6.0``. Shown in
#: /server/info so an installation can be identified — and its source found —
#: without shell access to the host. Bump it with the tag, not with APP_VERSION:
#: the product version and the release tag move independently.
RELEASE_TAG = "v0.6.0"

# The oldest client API generation this server still serves.
MIN_CLIENT_API_VERSION = 1
