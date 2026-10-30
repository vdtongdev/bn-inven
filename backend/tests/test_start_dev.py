"""Exercise the WSL launcher without installing dependencies or starting services."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")


@unittest.skipUnless(os.name == "posix" and BASH, "requires Bash on a POSIX host or WSL")
class StartDevTests(unittest.TestCase):
    def test_launcher_reaches_dependency_preparation(self):
        with tempfile.TemporaryDirectory(prefix="bn-inven-launcher-") as directory:
            command_dir = Path(directory)
            for name in ("uv", "node", "npm"):
                command = command_dir / name
                command.write_text(
                    "#!/usr/bin/env bash\nprintf 'launcher dependency stub reached\\n'\nexit 73\n",
                    encoding="utf-8",
                )
                command.chmod(0o755)

            environment = os.environ.copy()
            environment["PATH"] = f"{command_dir}{os.pathsep}{environment['PATH']}"
            result = subprocess.run(
                [BASH, str(ROOT / "start-dev.sh")],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                timeout=10,
            )

        self.assertEqual(result.returncode, 73, result.stdout + result.stderr)
        self.assertIn("Preparing backend dependencies...", result.stdout)
        self.assertIn("launcher dependency stub reached", result.stdout)


if __name__ == "__main__":
    unittest.main()
