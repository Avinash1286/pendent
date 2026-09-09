plugins {
    kotlin("jvm")
}

kotlin {
    jvmToolchain(17)
}

tasks.test {
    // The dependency-free CoreChecks main is run by verifyCore, not JUnit.
    // Gradle 9 otherwise treats the intentionally empty JUnit discovery as a
    // configuration failure. check still requires the actual executable below.
    failOnNoDiscoveredTests = false
}

// No JUnit/network dependency: this real JVM executable consumes an independent
// Python-generated index of existing C archive fixtures and writes exact results.
tasks.register<JavaExec>("verifyCore") {
    dependsOn(tasks.named("testClasses"))
    classpath = sourceSets["test"].runtimeClasspath
    mainClass.set("com.aura.capture.CoreChecksKt")
    val fixtureIndex = providers.gradleProperty("auraFixtureIndex")
    val resultDirectory = providers.gradleProperty("auraResultDirectory")
    doFirst {
        check(fixtureIndex.isPresent && resultDirectory.isPresent) {
            "Use scripts/verify_core.py or supply -PauraFixtureIndex and -PauraResultDirectory"
        }
        args(fixtureIndex.get(), resultDirectory.get())
    }
}

tasks.named("check") {
    dependsOn("verifyCore")
}
