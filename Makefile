# PardusInsight geliştirme kısayolları (Linux/Pardus). Windows'ta komutları
# doğrudan çalıştırın (ör. python scripts/build_deb.py).
PYTHON ?= python3
export QT_QPA_PLATFORM ?= offscreen

.PHONY: test kapsam deb tekerlek senaryolar dogrulama temizle

test:        # tüm otomatik testler
	$(PYTHON) -m pytest -q

kapsam:      # testler + satır kapsamı raporu
	$(PYTHON) -m coverage run -m pytest -q
	$(PYTHON) -m coverage report

deb:         # Pardus/Debian paketi: dist/pardusinsight_<sürüm>_all.deb
	$(PYTHON) scripts/build_deb.py

tekerlek:    # pip için tekerlek ve kaynak arşivi (python3 -m pip install build)
	$(PYTHON) -m build

senaryolar:  # scenarios/*.json dosyalarını yeniden üret
	$(PYTHON) scripts/generate_scenarios.py

dogrulama:   # /proc ile psutil karşılaştırması (10 örnek)
	$(PYTHON) scripts/validate_metrics.py --rounds 10

temizle:
	rm -rf build dist *.egg-info .pytest_cache .coverage htmlcov
