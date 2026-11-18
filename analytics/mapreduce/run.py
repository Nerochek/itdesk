"""Реальный Hadoop Streaming без зависимости от политики PowerShell."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from analytics.pipeline import DATA, ROOT, save_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA / "clean.jsonl")
    parser.add_argument("--output", type=Path, default=DATA / "hadoop-output")
    args = parser.parse_args()
    home = Path(os.environ.get("HADOOP_HOME", ROOT / ".tools/hadoop-3.5.0"))
    java = shutil.which("java")
    if not java:
        parser.exit(1, "Java не найдена. Запустите python run_analytics.py hadoop.\n")
    jars = list((home / "share/hadoop/tools/lib").glob("hadoop-streaming-*.jar"))
    if len(jars) != 1:
        parser.exit(1, "Не найден hadoop-streaming JAR. Проверьте HADOOP_HOME.\n")
    if args.output.exists():
        parser.exit(1, "Папка результата существует. Укажите новую --output.\n")
    if not args.input.is_file():
        parser.exit(1, "Не найден входной JSONL. Сначала выполните очистку.\n")
    parts = ["etc/hadoop"] + [f"share/hadoop/{name}{suffix}" for name in
            ("common", "hdfs", "mapreduce", "yarn") for suffix in ("/*", "/lib/*")]
    classpath = os.pathsep.join(str(home / part) for part in parts)
    python = Path(sys.executable).name
    command = [java, "-cp", classpath, "org.apache.hadoop.util.RunJar", str(jars[0]),
        "-D", "mapreduce.framework.name=local", "-D", "fs.defaultFS=file:///",
        "-files", "analytics/mapreduce/mapper.py,analytics/mapreduce/reducer.py",
        "-input", str(args.input.resolve()), "-output", str(args.output.resolve()),
        "-mapper", f"{python} mapper.py", "-reducer", f"{python} reducer.py",
        "-combiner", f"{python} reducer.py", "-numReduceTasks", "1"]
    result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors="replace")
    DATA.mkdir(exist_ok=True)
    (DATA / "hadoop_attempt.log").write_text(result.stdout, encoding="utf-8")
    save_json(DATA / "hadoop_status.json", {"returncode": result.returncode,
        "success_marker": (args.output / "_SUCCESS").exists(),
        "windows_native_missing": os.name == "nt" and not (home / "bin/winutils.exe").exists(),
        "log": "analytics_data/hadoop_attempt.log"})
    print(result.stdout)
    if result.returncode:
        parser.exit(result.returncode, "Hadoop не завершён; подробности в analytics_data/hadoop_attempt.log\n")


if __name__ == "__main__":
    main()
