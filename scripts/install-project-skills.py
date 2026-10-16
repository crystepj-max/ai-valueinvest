#!/usr/bin/env python3
"""Create project-local Claude Code or Codex skill entry points safely."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


EXCLUDED_PROJECT_SKILLS = {"wechat-article"}


class InstallError(Exception):
    pass


@dataclass(frozen=True)
class LinkPlan:
    source: Path
    target: Path
    is_directory: bool = False


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolved_within(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=False)
    if not is_within(resolved, root):
        raise InstallError(f"拒绝项目外路径：{path} -> {resolved}")
    return resolved


def check_directory_chain(path: Path, root: Path) -> None:
    """Check every existing project-entry ancestor before creating anything."""
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        resolved = resolved_within(current, root)
        if current.exists() or current.is_symlink():
            if not resolved.is_dir():
                raise InstallError(f"目录入口不是目录，保留现状：{current}")


def source_file(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not is_within(resolved, root):
        raise InstallError(f"源文件超出项目目录：{path} -> {resolved}")
    if not resolved.is_file():
        raise InstallError(f"源文件不存在或不是普通文件：{path}")
    return resolved


def source_package(path: Path, root: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not is_within(resolved, root):
        raise InstallError(f"源包超出项目目录：{path} -> {resolved}")
    if not resolved.is_dir() or not (resolved / "SKILL.md").is_file():
        raise InstallError(f"Codex 源包缺少 SKILL.md：{path}")
    return resolved


def make_plan(root: Path, host: str) -> tuple[list[LinkPlan], list[Path]]:
    if host == "codex":
        entry_root = root / ".agents" / "skills"
        packages = sorted(
            package
            for package in (root / "codex-skills").iterdir()
            if package.name not in EXCLUDED_PROJECT_SKILLS
        )
        if not packages:
            raise InstallError("codex-skills/ 下没有可安装的技能包")
        plan = [
            LinkPlan(
                source=source_package(package, root),
                target=entry_root / package.name,
                is_directory=True,
            )
            for package in packages
            if package.is_dir()
        ]
        if not plan:
            raise InstallError("codex-skills/ 下没有含 SKILL.md 的技能包")
        return plan, [root / ".agents", entry_root]

    if host == "claude":
        entry_root = root / ".claude" / "skills"
        command_root = root / ".claude" / "commands"
        sources = sorted(
            source
            for source in (root / "skills").glob("*.md")
            if source.stem not in EXCLUDED_PROJECT_SKILLS
        )
        if not sources:
            raise InstallError("skills/ 下没有可安装的 Markdown 技能")
        plan: list[LinkPlan] = []
        for source in sources:
            resolved = source_file(source, root)
            package_root = entry_root / source.stem
            package = source_package(root / "codex-skills" / source.stem, root)
            plan.append(LinkPlan(package, package_root, is_directory=True))
            plan.append(LinkPlan(resolved, command_root / source.name))
        return plan, [root / ".claude", entry_root, command_root]

    raise InstallError(f"不支持的 host：{host}（可选 codex 或 claude）")


def same_link(target: Path, source: Path) -> bool:
    if not target.is_symlink():
        return False
    try:
        return target.resolve(strict=False) == source.resolve(strict=True)
    except OSError:
        return False


def preflight(plan: list[LinkPlan], directories: list[Path], root: Path) -> set[Path]:
    for directory in directories:
        check_directory_chain(directory, root)

    create: set[Path] = set()
    conflicts: list[str] = []
    for item in plan:
        check_directory_chain(item.target.parent, root)
        # A symlink at an entry target is never followed to create or replace
        # content. Only the exact expected source link is accepted.
        if item.target.is_symlink():
            if not same_link(item.target, item.source):
                conflicts.append(f"{item.target}（未知符号链接）")
            continue
        if item.target.exists():
            conflicts.append(f"{item.target}（已有文件或目录）")
            continue
        create.add(item.target)

    if conflicts:
        listing = "\n  ".join(conflicts)
        raise InstallError("发现现存项目入口；已保留全部内容，未创建任何新入口：\n  " + listing)
    return create


def install(root_arg: str, host: str) -> int:
    root = Path(root_arg).resolve(strict=True)
    if not root.is_dir():
        raise InstallError(f"项目根不是目录：{root}")
    plan, directories = make_plan(root, host)
    create = preflight(plan, directories, root)

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    for item in plan:
        if item.target in create:
            item.target.parent.mkdir(parents=True, exist_ok=True)
            relative_source = os.path.relpath(item.source, item.target.parent)
            try:
                os.symlink(relative_source, item.target, target_is_directory=item.is_directory)
            except OSError as exc:
                if os.name == "nt" and getattr(exc, "winerror", None) in {5, 1314}:
                    raise InstallError(
                        "Windows 当前未允许创建符号链接；请启用开发者模式或配置相应权限后重试。"
                        "本安装器不会复制或覆盖入口。"
                    ) from exc
                raise InstallError(f"创建项目入口失败：{item.target}: {exc}") from exc

    created_count = len(create)
    print(f"项目级 {host} skills：创建 {created_count} 个入口，已存在正确链接 {len(plan) - created_count} 个。")
    if host == "claude":
        print("Claude Code 项目技能位于 .claude/skills/；同时保留 .claude/commands/ 兼容入口。")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("用法：install-project-skills.py <project-root> <codex|claude>", file=sys.stderr)
        return 2
    try:
        return install(argv[1], argv[2])
    except (InstallError, OSError, ValueError) as exc:
        print(f"安装失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
