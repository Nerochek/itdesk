"""Hadoop Streaming: JSONL -> category TAB 1."""
import json
import sys


def map_lines(lines):
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        if row["status"] in ("new", "in_progress"):
            category = row["category"]
            if not isinstance(category, str) or any(c in category for c in "\t\r\n"):
                raise ValueError("Некорректная категория")
            yield f"{category}\t1\n"


if __name__ == "__main__":
    sys.stdout.writelines(map_lines(sys.stdin))
