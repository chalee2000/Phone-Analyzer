plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "th.spni.agent"
    compileSdk = 35

    defaultConfig {
        applicationId = "th.spni.agent"
        minSdk = 23
        targetSdk = 35
        versionCode = 4
        versionName = "4.0.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}
