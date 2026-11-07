package com.pfc.companion.data

import java.net.URI

/**
 * Parsing and policy for the address of a self-hosted finance server.
 *
 * The user types whatever their installation answers on — `192.168.1.100:5183`,
 * `https://finance.example.com`, or a full `<base>/api/v1/` URL copied out of the
 * web app. This turns all of those into the API base the rest of the app expects
 * (`scheme://host[:port]/api/v1/`), and refuses the addresses that would send
 * financial data somewhere unsafe.
 *
 * The one real policy decision: plain HTTP is accepted only for addresses that
 * cannot leave the local network (loopback, RFC1918, link-local, a ULA, a `.local`
 * mDNS name, or a single-label LAN hostname). A public name must use HTTPS. That is
 * enforced here, in the app, because Android's network-security-config cannot
 * express "cleartext to private ranges only".
 */
object ServerUrl {
    /** A validated address. [apiBaseUrl] always ends with `/api/v1/`. */
    data class Parsed(
        val apiBaseUrl: String,
        val origin: String,
        val insecure: Boolean,
    )

    sealed interface Result {
        data class Valid(val parsed: Parsed) : Result
        data class Invalid(val reason: String) : Result
    }

    fun parse(raw: String): Result {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return Result.Invalid("Enter the address of your finance server.")

        // A bare host is the common case, so default the scheme instead of complaining.
        val withScheme = if (SCHEME_PATTERN.containsMatchIn(trimmed)) trimmed else "https://$trimmed"

        val uri = try {
            URI(withScheme)
        } catch (_: Exception) {
            return Result.Invalid("That does not look like a web address. Example: https://finance.example.com")
        }

        val scheme = uri.scheme?.lowercase()
        if (scheme != "http" && scheme != "https") {
            return Result.Invalid("Use http:// or https:// — that is the only kind of address the app can reach.")
        }
        val host = uri.host?.lowercase()
        if (host.isNullOrBlank()) {
            return Result.Invalid("The address is missing a host. Example: http://192.168.1.100:8088")
        }
        if (uri.userInfo != null) {
            // Credentials in a URL would be stored in clear text and shown on screen.
            return Result.Invalid("Remove the username and password from the address.")
        }
        if (!uri.rawQuery.isNullOrBlank() || !uri.rawFragment.isNullOrBlank()) {
            return Result.Invalid("Remove the query string and #fragment — enter only the server address.")
        }
        val port = uri.port
        if (port != -1 && (port < 1 || port > 65535)) {
            return Result.Invalid("That port number is not valid.")
        }

        val insecure = scheme == "http"
        if (insecure && !isLocalAddress(host)) {
            return Result.Invalid(
                "Use https:// for $host. Plain http:// is only allowed on your local network, " +
                    "because the sign-in token and your financial data travel unencrypted."
            )
        }

        val origin = buildString {
            append(scheme).append("://").append(uri.host.lowercase())
            if (port != -1) append(':').append(port)
        }
        // Accept a pasted `.../api/v1/` (or `/api/v1`) without doubling the path.
        val path = uri.path.orEmpty().trimEnd('/')
        if (path.isNotEmpty() && path != API_PREFIX.trimEnd('/')) {
            return Result.Invalid("Enter the server address only, without a path — the app adds /api/v1 itself.")
        }

        return Result.Valid(Parsed(apiBaseUrl = "$origin$API_PREFIX/", origin = origin, insecure = insecure))
    }

    /**
     * The address as a person would type it: the origin, without the API path.
     * Showing `https://host/api/v1/` in an editable field invites the user to
     * delete the part the app depends on.
     *
     * Built on [apiBaseFromStored] so the field cannot show a stored value that the
     * form would then reject: a stored `/api` or `/api/v1` shows as the origin, which
     * parses, instead of a path the user is told to remove by hand.
     */
    fun displayAddress(apiBaseUrl: String): String {
        val canonical = apiBaseFromStored(apiBaseUrl)
        return if (canonical.isEmpty()) "" else canonical.removeSuffix("$API_PREFIX/")
    }

    /** Convenience for callers that only need the normalized API base. */
    fun apiBaseUrlOrNull(raw: String): String? = (parse(raw) as? Result.Valid)?.parsed?.apiBaseUrl

    /**
     * The API base implied by an address as it is stored on the device.
     *
     * Requests are built by appending to the stored base, so an address saved
     * without the API path (`https://host:8443/`) asked `/auth/me` instead of
     * `/api/v1/auth/me` and answered 404. That value can outlive the build that
     * wrote it: reinstallation keeps app data, so a phone that once stored the
     * display form keeps failing after the code that wrote it is gone.
     *
     * Repairing it here, on the way out, rather than rewriting storage is
     * deliberate — the bearer token is held under the stored address as its key,
     * so rewriting that key would silently sign the user out.
     */
    fun apiBaseFromStored(value: String): String {
        val trimmed = value.trim()
        if (trimmed.isEmpty()) return ""

        // Strip the API path if the stored value carries one — whole (`/api/v1`)
        // or only partly (`/api`, `/v1`), which is what a truncated paste or an
        // older build leaves behind. Appending to a partial prefix such as
        // `/api/` asked `/api/api/v1/auth/me` and answered 404 at a port that was
        // otherwise working, which is exactly the kind of failure that looks like
        // a server problem and is not one.
        var origin = trimmed.trimEnd('/')
        var stripped = true
        while (stripped) {
            stripped = false
            for (suffix in API_PATH_SUFFIXES) {
                if (origin.lowercase().endsWith(suffix)) {
                    origin = origin.dropLast(suffix.length).trimEnd('/')
                    stripped = true
                    break
                }
            }
        }

        if (origin.isEmpty()) return ""
        return "$origin$API_PREFIX/"
    }

    /**
     * True when [host] is something that resolves inside the user's own network.
     *
     * This is deliberately conservative: a public hostname always needs HTTPS, even
     * if it happens to point at the LAN. An address that fails a DNS lookup is not
     * a usability problem here — HTTPS still works on a private name.
     */
    fun isLocalAddress(host: String): Boolean {
        val value = host.trim().lowercase().trim('[', ']')
        if (value == "localhost" || value == "::1") return true
        if (value.endsWith(".local") || value.endsWith(".lan") || value.endsWith(".home.arpa")) return true
        // A single-label name such as "finance" or "nas" is a LAN hostname, not a domain.
        if (!value.contains('.') && !value.contains(':')) return true

        if (value.contains(':')) {
            // IPv6: loopback handled above, unique-local fc00::/7 and link-local fe80::/10.
            val head = value.substringBefore(':')
            if (head.length < 2) return false
            val first = head.take(2)
            if (first == "fc" || first == "fd") return true
            return value.startsWith("fe8") || value.startsWith("fe9") ||
                value.startsWith("fea") || value.startsWith("feb")
        }

        val octets = value.split('.')
        if (octets.size != 4) return false
        val parts = octets.map { it.toIntOrNull() ?: return false }
        if (parts.any { it < 0 || it > 255 }) return false
        val (a, b) = parts
        return a == 127 || a == 10 ||
            (a == 192 && b == 168) ||
            (a == 172 && b in 16..31) ||
            (a == 169 && b == 254)
    }

    private const val API_PREFIX = "/api/v1"
    // Longest first: `/api/v1` must be removed before `/api` can match it.
    private val API_PATH_SUFFIXES = listOf("/api/v1", "/api", "/v1")
    private val SCHEME_PATTERN = Regex("^[a-zA-Z][a-zA-Z0-9+.-]*://")
}
