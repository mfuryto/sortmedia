from contextlib import redirect_stdout
from io import StringIO
import json
import unittest

from sortmedia.reporting import JsonReporter, QuietReporter


class ReportingTests(unittest.TestCase):
    def test_json_reporter_emits_machine_readable_json_lines(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            reporter = JsonReporter()
            reporter.progress(1, 2)
            reporter.event("summary", processed=3, skipped=1)

        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(events[0], {"event": "progress", "current": 1, "total": 2})
        self.assertEqual(events[1], {"event": "summary", "processed": 3, "skipped": 1})

    def test_quiet_reporter_emits_nothing(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            reporter = QuietReporter()
            reporter.progress(1, 1)
            reporter.event("file", source="a", destination="b")
            reporter.finish()
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
