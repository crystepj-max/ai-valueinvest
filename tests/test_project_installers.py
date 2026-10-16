from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def project_fixture(temp: tempfile.TemporaryDirectory[str]) -> Path:
    root = Path(temp) / "checkout"
    for item in ("scripts", "skills", "codex-skills"):
        shutil.copytree(PROJECT_ROOT / item, root / item, symlinks=True)
    return root


def run_installer(root: Path, host: str) -> subprocess.CompletedProcess[str]:
    script = "install-codex-skills.sh" if host == "codex" else "install-claude-commands.sh"
    return subprocess.run(
        ["bash", str(root / "scripts" / script)],
        cwd=Path(tempfile.gettempdir()),
        text=True,
        capture_output=True,
        check=False,
    )


class ProjectInstallerTests(unittest.TestCase):
    def test_wechat_source_is_retained_without_project_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = project_fixture(temp)
            flat_source = root / "skills/wechat-article.md"
            generated_source = root / "codex-skills/wechat-article/SKILL.md"
            flat_before = flat_source.read_bytes()
            generated_before = generated_source.read_bytes()

            codex = run_installer(root, "codex")
            self.assertEqual(codex.returncode, 0, codex.stderr)
            claude = run_installer(root, "claude")
            self.assertEqual(claude.returncode, 0, claude.stderr)

            canonical_names = {path.stem for path in (root / "skills").glob("*.md")} - {"wechat-article"}
            package_names = {path.name for path in (root / "codex-skills").iterdir() if path.is_dir()} - {"wechat-article"}
            self.assertEqual(len(canonical_names), 20)
            self.assertEqual(package_names, canonical_names)
            self.assertEqual({path.name for path in (root / ".agents/skills").iterdir()}, package_names)
            self.assertEqual({path.name for path in (root / ".claude/skills").iterdir()}, canonical_names)
            self.assertEqual({path.stem for path in (root / ".claude/commands").glob("*.md")}, canonical_names)

            for alias in (
                root / ".agents/skills/wechat-article",
                root / ".claude/skills/wechat-article",
                root / ".claude/commands/wechat-article.md",
            ):
                self.assertFalse(alias.exists() or alias.is_symlink(), alias)
            self.assertEqual(flat_source.read_bytes(), flat_before)
            self.assertEqual(generated_source.read_bytes(), generated_before)

    def test_codex_installs_complete_package_links_and_repeat_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = project_fixture(temp)
            first = run_installer(root, "codex")
            self.assertEqual(first.returncode, 0, first.stderr)
            aliases = sorted((root / ".agents/skills").iterdir())
            sources = sorted(
                path
                for path in (root / "codex-skills").iterdir()
                if path.is_dir() and path.name != "wechat-article"
            )
            self.assertEqual([p.name for p in aliases], [p.name for p in sources])
            for alias, source in zip(aliases, sources, strict=True):
                self.assertTrue(alias.is_symlink(), alias)
                self.assertEqual(alias.resolve(strict=True), source.resolve(strict=True))
                self.assertTrue((alias / "SKILL.md").is_file())
                self.assertEqual((alias / "SKILL.md").read_bytes(), (source / "SKILL.md").read_bytes())
                if (source / "agents/openai.yaml").exists():
                    self.assertTrue((alias / "agents/openai.yaml").is_file())
            before = [(p.name, p.readlink()) for p in aliases]
            second = run_installer(root, "codex")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("创建 0 个入口", second.stdout)
            self.assertEqual(before, [(p.name, p.readlink()) for p in sorted((root / ".agents/skills").iterdir())])
            checked = subprocess.run(
                ["python3", str(root / "scripts/sync-codex-skills.py"), "--check"],
                cwd=Path(tempfile.gettempdir()),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_claude_installs_project_skills_and_compat_commands_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = project_fixture(temp)
            first = run_installer(root, "claude")
            self.assertEqual(first.returncode, 0, first.stderr)
            sources = sorted(
                path for path in (root / "skills").glob("*.md") if path.stem != "wechat-article"
            )
            aliases = sorted((root / ".claude/skills").iterdir())
            self.assertEqual([p.name for p in aliases], [p.stem for p in sources])
            for source in sources:
                skill_link = root / ".claude/skills" / source.stem
                command_link = root / ".claude/commands" / source.name
                package = root / "codex-skills" / source.stem
                self.assertTrue(skill_link.is_symlink(), skill_link)
                self.assertTrue(skill_link.is_dir())
                self.assertEqual(skill_link.resolve(strict=True), package.resolve(strict=True))
                self.assertEqual(
                    sorted(p.name for p in skill_link.iterdir()),
                    sorted(p.name for p in package.iterdir()),
                )
                self.assertTrue((skill_link / "SKILL.md").is_file())
                self.assertTrue(command_link.is_symlink(), command_link)
                self.assertEqual(command_link.resolve(strict=True), source.resolve(strict=True))
                self.assertEqual(command_link.read_bytes(), source.read_bytes())
            memo_source = root / "skills/investment-memo-craft.md"
            if memo_source.exists():
                memo_alias = root / ".claude/skills/investment-memo-craft"
                memo_metadata = root / "codex-skills/investment-memo-craft/agents/openai.yaml"
                self.assertTrue(memo_alias.is_symlink(), memo_alias)
                self.assertEqual(
                    memo_alias.resolve(strict=True),
                    (root / "codex-skills/investment-memo-craft").resolve(strict=True),
                )
                self.assertTrue((memo_alias / "agents/openai.yaml").is_file())
                self.assertEqual(
                    (memo_alias / "agents/openai.yaml").read_bytes(),
                    memo_metadata.read_bytes(),
                )
            second = run_installer(root, "claude")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("创建 0 个入口", second.stdout)

    def test_unknown_entry_conflict_preserves_marker_and_creates_no_other_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = project_fixture(temp)
            existing = root / ".agents/skills/investment-research"
            existing.mkdir(parents=True)
            marker = existing / "local-note.txt"
            marker.write_text("user-owned", encoding="utf-8")
            result = run_installer(root, "codex")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("保留全部内容", result.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "user-owned")
            self.assertEqual(list((root / ".agents/skills").iterdir()), [existing])

    def test_unknown_symlink_conflict_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = project_fixture(temp)
            outside_dir = Path(outside) / "custom-skill"
            outside_dir.mkdir()
            link = root / ".agents/skills/investment-research"
            link.parent.mkdir(parents=True)
            link.symlink_to(outside_dir, target_is_directory=True)
            result = run_installer(root, "codex")
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(strict=True), outside_dir.resolve(strict=True))
            self.assertEqual(list(link.parent.iterdir()), [link])

    def test_codex_parent_symlink_cannot_escape_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = project_fixture(temp)
            escape = root / ".agents"
            escape.symlink_to(outside, target_is_directory=True)
            result = run_installer(root, "codex")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("拒绝项目外路径", result.stderr)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_claude_parent_symlink_cannot_escape_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = project_fixture(temp)
            escape = root / ".claude"
            escape.symlink_to(outside, target_is_directory=True)
            result = run_installer(root, "claude")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("拒绝项目外路径", result.stderr)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_shell_syntax_and_batch_scope_are_bounded(self) -> None:
        scripts = PROJECT_ROOT / "scripts"
        for name in (
            "install-codex-skills.sh",
            "install-claude-commands.sh",
            "install-project-skills.py",
        ):
            path = scripts / name
            if name.endswith(".sh"):
                subprocess.run(["bash", "-n", str(path)], check=True)
                body = path.read_text(encoding="utf-8")
                self.assertNotIn("$HOME", body)
                self.assertNotIn("CODEX_HOME", body)
                self.assertNotIn("CLAUDE_COMMANDS_DIR", body)
            else:
                subprocess.run(["python3", "-m", "py_compile", str(path)], check=True)
        for name in ("install-codex-skills.bat", "install-claude-commands.bat"):
            body = (scripts / name).read_text(encoding="utf-8").lower()
            self.assertNotIn("codex_home", body)
            self.assertNotIn("userprofile", body)
            self.assertNotIn("claude_commands_dir", body)
            self.assertNotIn("rmdir /s /q", body)
            self.assertNotIn("xcopy", body)
            self.assertNotIn("copy /y", body)
            self.assertIn("install-project-skills.py", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
