from bubble.n3 import N3Processor

if __name__ == "__main__":
    processor = N3Processor()
    processor.process_file("tests/test_n3.py")
