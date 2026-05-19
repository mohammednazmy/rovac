plugins {
    id("com.android.application")
}

android {
    namespace = "com.rovac.phonesensors"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.rovac.phonesensors"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.2.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
        debug {
            isDebuggable = true
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

configurations.all {
    resolutionStrategy {
        force("org.jetbrains.kotlin:kotlin-stdlib:1.8.22")
        force("org.jetbrains.kotlin:kotlin-stdlib-jdk7:1.8.22")
        force("org.jetbrains.kotlin:kotlin-stdlib-jdk8:1.8.22")
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.core:core:1.15.0")

    // OkHttp WebSocket client (rosbridge transport)
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    // CameraX
    val cameraxVersion = "1.4.1"
    implementation("androidx.camera:camera-core:$cameraxVersion")
    implementation("androidx.camera:camera-camera2:$cameraxVersion")
    implementation("androidx.camera:camera-lifecycle:$cameraxVersion")
    implementation("androidx.camera:camera-view:$cameraxVersion")

    // Lifecycle service (for CameraX binding)
    implementation("androidx.lifecycle:lifecycle-service:2.8.7")

    // Guava (for ListenableFuture)
    implementation("com.google.guava:guava:33.0.0-android")
}
