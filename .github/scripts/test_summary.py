import json
import sys


def main() -> int:
    try:
        with open("test-results.json", "r") as f:
            data = json.load(f)

        summary = data.get("summary", {})
        total = summary.get("total", 0)
        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0)
        skipped = summary.get("skipped", 0)
        error = summary.get("error", 0)
        duration = summary.get("duration", 0)

        print(f"- **Total:** {total}")
        print(f"- **Passed:** {passed} :white_check_mark:")
        print(f"- **Failed:** {failed} :x:")
        print(f"- **Skipped:** {skipped}")
        print(f"- **Error:** {error} :warning:")
        print(f"- **Duration:** {duration:.2f}s")

        if failed > 0 or error > 0:
            return 1
        return 0
    except Exception as e:
        print(f"Error generating summary: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
