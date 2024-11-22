.PHONY: inbox.out.2.n3 inbox.out.1.n3

inbox.out.2.n3: inbox.out.1.n3
	uv run ../n3.py < inbox.out.1.n3

inbox.out.1.n3: inbox.n3
	eye --quiet --nope --pass inbox.n3 > inbox.out.1.n3
