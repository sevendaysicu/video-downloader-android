[app]
# 基础元数据
title = VideoDownloader
package.name = videodownloader
package.domain = org.rouvideo
source.dir = .
source.include_exts = py,png,jpg,json
version = 1.0

# 核心依赖（已精简，拒绝庞大C++编译开销）
requirements = python3,kivy,requests,urllib3,certifi,charset_normalizer,idna

# 屏幕设置
orientation = portrait
fullscreen = 0

# 安卓系统最高权限声明
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE, MANAGE_EXTERNAL_STORAGE

# 【终极锁定】强制对齐 NDK 最稳历史编译标准，拒绝不稳定的 r28c
android.api = 33
android.minapi = 21
android.ndk_api = 24

# 📢 【核心绝杀行】硬编码锁定最稳的 NDK 版本，不让 Buildozer 乱下最新版
android.ndk = 25c

android.archs = arm64-v8a, armeabi-v7a

# 调试与构建模式限制
android.skip_byte_compile = 0
android.private_storage = 0

[buildozer]
log_level = 2
warn_on_root = 1
