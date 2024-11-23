.PHONY: build test clean docker-build docker-run

build:
	python -m build
	pip install -e .

test: build
	python -m pytest

test-setuptools: build
	python setup.py test

clean:
	rm -rf build/ dist/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +

docker-build:
	docker build -t bubble .

docker-run:
	docker run -p 8000:8000 --rm -it bubble
