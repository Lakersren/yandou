import os
import subprocess
import tempfile
from pathlib import Path

from django.test import SimpleTestCase


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "deploy" / "manage.sh"


class DeployManageScriptTests(SimpleTestCase):
    def run_script(self, command, *args, with_env_file=True):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            bin_dir = temp_path / "bin"
            bin_dir.mkdir()
            docker_log = temp_path / "docker.log"
            fake_docker = bin_dir / "docker"
            fake_docker.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$DOCKER_LOG\"\n",
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)

            env_file = temp_path / ".env"
            if with_env_file:
                env_file.write_text("POSTGRES_PASSWORD=test-password\n", encoding="utf-8")

            env = os.environ.copy()
            env.update({
                "PATH": f"{bin_dir}:{env['PATH']}",
                "DOCKER_LOG": str(docker_log),
                "ENV_FILE": str(env_file),
            })
            result = subprocess.run(
                ["/bin/sh", str(SCRIPT), command, *args],
                cwd=temp_path,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            calls = docker_log.read_text(encoding="utf-8").splitlines() if docker_log.exists() else []
            return result, calls, env_file

    def test_start_runs_compose_in_background_with_build(self):
        result, calls, env_file = self.run_script("start")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [
            f"compose --project-directory {PROJECT_ROOT} --env-file "
            f"{env_file} up -d --build --remove-orphans"
        ])

    def test_start_refuses_to_run_without_environment_file(self):
        result, calls, _env_file = self.run_script("start", with_env_file=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("配置文件不存在", result.stderr)
        self.assertEqual(calls, [])

    def test_management_commands_delegate_to_compose(self):
        cases = {
            "stop": "down",
            "restart": "restart",
            "status": "ps",
            "logs": "logs -f --tail 200 web worker worker_bright_data beat",
        }

        for command, expected_action in cases.items():
            with self.subTest(command=command):
                result, calls, env_file = self.run_script(command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [
                    f"compose --project-directory {PROJECT_ROOT} --env-file "
                    f"{env_file} {expected_action}"
                ])

    def test_unknown_command_prints_complete_usage(self):
        result, calls, _env_file = self.run_script("unknown")

        self.assertEqual(result.returncode, 2)
        self.assertIn("export-db", result.stderr)
        self.assertIn("import-db", result.stderr)
        self.assertEqual(calls, [])

    def test_export_database_uses_custom_postgres_dump(self):
        with tempfile.TemporaryDirectory() as backup_dir:
            backup_file = Path(backup_dir) / "current.dump"
            result, calls, env_file = self.run_script("export-db", str(backup_file))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(backup_file.exists())
            self.assertEqual(calls, [
                f"compose --project-directory {PROJECT_ROOT} --env-file {env_file} "
                "exec -T db sh -c pg_dump --format=custom --no-owner --no-acl "
                '-U "$POSTGRES_USER" -d "$POSTGRES_DB"'
            ])

    def test_import_database_restores_then_starts_services(self):
        with tempfile.NamedTemporaryFile() as backup_file:
            backup_file.write(b"database-backup")
            backup_file.flush()
            result, calls, env_file = self.run_script("import-db", backup_file.name)

            prefix = f"compose --project-directory {PROJECT_ROOT} --env-file {env_file} "
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls, [
                prefix + "stop web worker worker_bright_data beat",
                prefix + "up -d db redis",
                prefix + "exec -T db sh -c until pg_isready -U \"$POSTGRES_USER\" "
                "-d \"$POSTGRES_DB\"; do sleep 1; done",
                prefix + "exec -T db sh -c until pg_isready -U \"$POSTGRES_USER\" "
                "-d \"$POSTGRES_DB\"; do sleep 1; done",
                prefix + "exec -T db sh -c pg_restore --clean --if-exists --no-owner "
                '--no-acl --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
                prefix + "up -d --build --remove-orphans",
            ])
