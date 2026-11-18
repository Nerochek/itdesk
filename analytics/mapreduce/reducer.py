"""Hadoop Streaming: суммирование по отсортированному ключу."""
import sys
from itertools import groupby


def reduce_lines(lines):
    pairs = (line.rstrip("\n").split("\t") for line in lines if line.strip())
    for category, group in groupby(pairs, key=lambda pair: pair[0]):
        yield f"{category}\t{sum(int(pair[1]) for pair in group)}\n"


if __name__ == "__main__":
    sys.stdout.writelines(reduce_lines(sys.stdin))
