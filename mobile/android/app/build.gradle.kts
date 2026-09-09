plugins { id("com.android.application") }

android {
    namespace = "com.aura.notes"
    compileSdk = 37
    defaultConfig {
        applicationId = "com.aura.notes"
        minSdk = 29
        targetSdk = 37
        versionCode = 2
        versionName = "0.2.0-a04"
        testInstrumentationRunner = "com.aura.notes.SmokeInstrumentation"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
}
dependencies { implementation(project(":core")) }
