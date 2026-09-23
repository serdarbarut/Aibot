"""Testler çevrimdışı çalışır: ağ, disk ve canlı servis kullanılmaz."""

import os

# app.config import edilmeden önce ayarlanmalı
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-only-for-unit-tests")
