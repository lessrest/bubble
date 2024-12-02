.PHONY: test clean docker-build docker-run

test:; uv run invoke test
clean:; uv run invoke clean
