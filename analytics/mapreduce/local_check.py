"""Локальная проверка алгоритма, не запуск Hadoop."""
from collections import Counter
from pathlib import Path
from analytics.pipeline import DATA, read_jsonl, save_json
from analytics.mapreduce.mapper import map_lines
from analytics.mapreduce.reducer import reduce_lines


def main():
    path = DATA / "clean.jsonl"
    with path.open(encoding="utf-8") as stream:
        result = list(reduce_lines(sorted(map_lines(stream))))
    actual = {line.split("\t")[0]: int(line.split("\t")[1]) for line in result}
    expected = dict(Counter(row["category"] for row in read_jsonl(path)
                            if row["status"] in ("new", "in_progress")))
    if actual != expected:
        raise ValueError("MapReduce не совпал с контрольным подсчётом")
    (DATA / "mapreduce_local.tsv").write_text("".join(result), encoding="utf-8")
    save_json(DATA / "mapreduce_local_check.json", {"equal": True, "counts": actual,
              "execution": "Python local algorithm check, not Hadoop"})
    print("Локальная проверка MapReduce: OK", actual)


if __name__ == "__main__":
    main()
