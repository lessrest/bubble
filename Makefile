docker-build:
	docker build -t bubble .

docker-run:
	docker run -p 8000:8000 --rm -it bubble
