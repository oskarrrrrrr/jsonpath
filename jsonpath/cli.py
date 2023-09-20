import argparse
import json
import sys

from . import jsp


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="jsp",
        description="description",
    )
    parser.add_argument("JSONPath")
    args = parser.parse_args()
    path = args.JSONPath

    data = sys.stdin.read()
    data = json.loads(data)

    try:
        result = jsp.query(data, path)
    except jsp.ParseError as e:
        print("ERROR:", e)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
