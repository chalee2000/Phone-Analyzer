`spni-agent.apk` is built from `android-agent/` by the GitHub Actions workflow
(`.github/workflows/build.yml`) and copied here before PyInstaller runs.
To build it locally: install Android Studio / the Android SDK, then run
`gradle -p android-agent assembleDebug` and copy
`android-agent/app/build/outputs/apk/debug/app-debug.apk` to this folder as
`spni-agent.apk`.
