plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
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
        // 0.6.0.1: a patch on the 0.6.0 maintenance line -- the sync/fixture date
        // fixes only, not a new feature. versionCode still increases so an install
        // upgrades in place instead of being refused as a downgrade, and it skips
        // past 0.6.2's 9: a maintenance build that shares a versionCode with a
        // newer release is refused as a downgrade on a device carrying that
        // release, which is exactly the device this patch is meant to rescue.
        // 11 is free because 0.6.6 on master holds 10.
        versionCode = 11
        versionName = "0.6.0.1"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // 10.0.2.2 is the host machine as seen from the Android emulator. Traffic
        // goes through the Caddy TLS front (port 8443). Change it in Settings for
        // a physical device, using the host's LAN address and the same port.
        buildConfigField("String", "API_BASE_URL", "\"https://10.0.2.2:8443/api/v1/\"")
        // The API generation this build speaks. A server reporting a lower
        // /server/info api_version is too old to connect to.
        buildConfigField("int", "CLIENT_API_VERSION", "1")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
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
