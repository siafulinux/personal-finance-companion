import java.io.File
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

/**
 * The server address an APK starts with, supplied at build time.
 *
 * Precedence: the `pfcApiBaseUrl` Gradle property, then the `PFC_API_BASE_URL`
 * environment variable, then the emulator default. Whatever the user later enters in
 * Settings → Server address is stored and wins over this, so this is only the first-run
 * default.
 *
 *   ./gradlew assembleDebug -PpfcApiBaseUrl=https://finance.example.com
 *   PFC_API_BASE_URL=https://finance.example.com ./gradlew assembleRelease
 *
 * The value is normalised rather than pasted in verbatim: a bare host gets https://, and
 * the `/api/v1/` path the app talks to is appended when it is missing, so a build can be
 * pointed at `finance.example.com:8443` and still produce a working client. A value that
 * is not a usable address fails the build instead of shipping an APK that cannot connect.
 */
val defaultApiBaseUrl: String = run {
    val raw = (project.findProperty("pfcApiBaseUrl") as String?)
        ?: System.getenv("PFC_API_BASE_URL")
        ?: "https://10.0.2.2:8443/api/v1/"
    val cleaned = raw.trim().trimEnd('/')

    fun rejected(why: String): Nothing = throw GradleException(
        "pfcApiBaseUrl/PFC_API_BASE_URL is not a usable server address ($why): '$raw'\n" +
            "Use an origin such as https://finance.example.com, or the full API root " +
            "https://finance.example.com/api/v1/."
    )

    if (cleaned.isEmpty()) rejected("empty")
    if (cleaned.contains(' ')) rejected("it contains a space")

    val hasScheme = cleaned.startsWith("https://", ignoreCase = true) ||
        cleaned.startsWith("http://", ignoreCase = true)
    val scheme = when {
        cleaned.startsWith("https://", ignoreCase = true) -> "https://"
        cleaned.startsWith("http://", ignoreCase = true) -> "http://"
        cleaned.contains("://") -> rejected("only http:// and https:// are supported")
        // The common case: somebody types the host they use in a browser.
        else -> "https://"
    }
    val rest = if (hasScheme) cleaned.substring(scheme.length) else cleaned
    if (rest.isEmpty()) rejected("it has no host")
    if (rest.contains('?') || rest.contains('#')) rejected("remove the query string and #fragment")
    if (rest.contains('@')) rejected("remove the username and password from the address")

    val authority = rest.substringBefore('/')
    if (authority.isEmpty()) rejected("it has no host")

    val path = rest.substringAfter('/', "").trimEnd('/')
    if (path.isNotEmpty() && path != "api/v1") {
        rejected("the path must be empty or /api/v1, not '/$path'")
    }

    // ServerUrl always stores the API root, so the baked-in default matches it.
    "$scheme$authority/api/v1/"
}

/**
 * Release signing material, which deliberately lives outside this repository.
 *
 * The path and passwords come from a properties file — by default
 * `~/.pfc/release.properties`, or wherever `PFC_KEYSTORE_PROPERTIES` points —
 * holding `storeFile`, `storePassword`, `keyAlias` and `keyPassword`. The same
 * four values are also accepted from the environment as `PFC_KEYSTORE_FILE`,
 * `PFC_KEYSTORE_PASSWORD`, `PFC_KEY_ALIAS` and `PFC_KEY_PASSWORD`, so a CI job
 * can sign from masked secrets without a file on disk.
 *
 * No key means an unsigned release build rather than a failed one: a contributor
 * or a debug loop must not need the release key to compile. A published artifact
 * is checked with `apksigner verify` before it is uploaded, so an unsigned build
 * cannot reach a release by accident.
 */
val releaseSigning: Map<String, String> = run {
    // `java` is the Java plugin extension inside this script, so the package is
    // imported by name above rather than reached through it.
    val properties = Properties()
    val path = System.getenv("PFC_KEYSTORE_PROPERTIES")
        ?: (System.getProperty("user.home") + "/.pfc/release.properties")
    val file = File(path)
    if (file.isFile) file.inputStream().use { properties.load(it) }

    fun value(env: String, key: String): String? =
        System.getenv(env) ?: properties.getProperty(key)

    val storeFile = value("PFC_KEYSTORE_FILE", "storeFile")
    if (storeFile == null) {
        emptyMap()
    } else {
        mapOf(
            "storeFile" to storeFile,
            "storePassword" to (value("PFC_KEYSTORE_PASSWORD", "storePassword") ?: ""),
            "keyAlias" to (value("PFC_KEY_ALIAS", "keyAlias") ?: ""),
            "keyPassword" to (value("PFC_KEY_PASSWORD", "keyPassword") ?: ""),
        )
    }
}

android {
    namespace = "com.pfc.companion"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.pfc.companion"
        minSdk = 26
        targetSdk = 36
        // 0.3.0: the app now points at any self-hosted server the user chooses,
        // with per-server sessions, instead of one hardcoded address.
        // 0.3.1: a stored server address without /api/v1 is repaired before each
        // request, so a value carried over from an earlier install cannot 404.
        // 0.3.2: so is an address holding only part of that path (`/api`, `/v1`),
        // and the address field shows the origin instead of a value the same form
        // would reject.
        // 0.4.0: Settings can change the account password after confirming the
        // current one; the change signs out every other device.
        // 0.5.0: everything first-run setup collected is editable in the app —
        // paydays and income sources, bills, the month's budget — plus profile,
        // categories, merchant aliases, notification rules and export.
        // 0.6.0: Phase 4 — loans and advances, savings goals, unified obligations,
        // the Safe-to-Spend breakdown, merchant insights and location-aware
        // Shopping Intelligence.
        // 0.6.2: no new feature. The manifest still said 0.6.0 while the server had
        // moved on, so an installed APK could not be told apart from the first
        // 0.6.0 build. The version is the change.
        // 0.6.6: aligned with the release tag, which is what the tag gate checks.
        // The manifest had been left at 0.6.2 / 9 while 0.6.3-0.6.5 shipped, so no
        // tag since could be verified. versionCode 10 is the next one after the
        // published 0.6.2 build (9); no release ever used 10.
        // 0.6.7: the tag gate allows a manifest ahead of the tag, so this names the
        // build rather than waiting for the next release. 12 is the next free code:
        // 11 belongs to the 0.6.0.1 maintenance build, and reusing it would put two
        // different APKs at one number.
        // 0.6.8: 0.6.7 was merged but never tagged, so the number moved on rather
        // than leaving a build claiming a release that does not exist. 13 is next
        // free; below it sit 12 (0.6.7), 11 (0.6.0.1) and 9 (0.6.2).
        versionCode = 13
        versionName = "0.6.8"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // First-run default only; Settings → Server address overrides it per install.
        // Defaults to 10.0.2.2:8443 (the emulator's view of this machine through the
        // Caddy TLS front) and is replaced at build time by pfcApiBaseUrl or
        // PFC_API_BASE_URL — see defaultApiBaseUrl above.
        buildConfigField("String", "API_BASE_URL", "\"$defaultApiBaseUrl\"")
        // The API generation this build speaks. A server reporting a lower
        // /server/info api_version is too old to connect to.
        buildConfigField("int", "CLIENT_API_VERSION", "1")
    }

    signingConfigs {
        if (releaseSigning.isNotEmpty()) {
            create("release") {
                storeFile = File(releaseSigning.getValue("storeFile"))
                storePassword = releaseSigning.getValue("storePassword")
                keyAlias = releaseSigning.getValue("keyAlias")
                keyPassword = releaseSigning.getValue("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            // Present only when a key was found; see releaseSigning above.
            signingConfigs.findByName("release")?.let { signingConfig = it }
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.05.00")
    implementation(composeBom)

    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.0")
    implementation("androidx.navigation:navigation-compose:2.9.0")
    implementation("androidx.datastore:datastore-preferences:1.1.7")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.8.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    // Shopping Intelligence: geofences for saved places and Activity Recognition
    // for low-power discovery. Battery-conscious APIs only; no continuous GPS.
    implementation("com.google.android.gms:play-services-location:21.3.0")
    // .await() on the Play services Task returned by the geofence and location APIs.
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-play-services:1.10.2")

    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")

    androidTestImplementation(composeBom)
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
}
