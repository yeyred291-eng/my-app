[app]
title = Meine Kivy App
package.name = myapp
package.domain = org.test
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1

requirements = python3,kivy

orientation = portrait
fullscreen = 1

# Android Einstellungen (Festgenagelt auf stabile Versionen)
android.api = 33
android.minapi = 21
android.ndk = 25c
android.archs = armeabi-v7a, arm64-v8a
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
