PY ?= .venv/bin/python
.PHONY: site setup clean-data stops load routeinfo fares expand levels crowding backtest sanity gpscheck export web serve test crowding-all query
setup:
	python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
clean-data:
	$(PY) -m bharosa.clean
stops: clean-data
	$(PY) -m bharosa.stops
load: stops
	$(PY) -m bharosa.load
routeinfo: load
	$(PY) -m bharosa.routeinfo
fares: load
	$(PY) -m bharosa.fares
expand: routeinfo
	$(PY) -m bharosa.expand
levels: expand
	$(PY) -m bharosa.levels
crowding: levels
backtest: levels
	$(PY) -m bharosa.backtest
sanity: levels
	$(PY) -m bharosa.sanity
gpscheck:
	$(PY) -m bharosa.gps_check
export: levels
	$(PY) -m bharosa.export
web:
	cd web && ../$(PY) -m http.server 8000
serve:
	$(PY) -m bharosa.serve 8000
test:
	$(PY) -m pytest -q
query:
	$(PY) -m bharosa.query --route $(ROUTE) --day weekday
crowding-all: crowding fares backtest sanity export

site: export
	rm -rf dist && mkdir -p dist && cp -R web/* dist/ && echo "static site in dist/ (upload the folder to any static host)"
