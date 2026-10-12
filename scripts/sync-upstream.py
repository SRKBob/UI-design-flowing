# -*- coding: utf-8 -*-
"""
UI-design-flowing 上游同步与校验。

三层结构（这是关键，别混）：
  snapshots/   精简后的上游源码快照（**入 git**，供离线重抽；由 build 命令生成）
  payload/     抽取出来的技能目录（**入 git**，各 AI 工具真正加载的就是它）
  vendor/      完整上游浅克隆（**不入 git**，只在升级上游时用；可随时丢弃重建）

命令：
  python scripts/sync-upstream.py build            # 从 vendor 生成/刷新 snapshots（离线，不动 payload）
  python scripts/sync-upstream.py extract          # 从 snapshots 重抽 payload（**离线**，日常用这个）
  python scripts/sync-upstream.py check            # 只读：报 snapshots / payload / vendor 三层现状
  python scripts/sync-upstream.py fetch            # 只读：查上游最新 tag / commit（要联网）
  python scripts/sync-upstream.py update           # 联网拉上游 → 刷新 snapshots + payload（会改文件）
  python scripts/sync-upstream.py validate         # 校验 payload 结构与 frontmatter

退出码：0 正常；1 有错误；2 有警告。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "snapshots"
PAYLOAD = ROOT / "payload" / "skills"
VENDOR = ROOT / "vendor"
MANIFEST = ROOT / "upstream.json"

PAYLOAD_SKILLS = ["ui-design-workflow", "ui-ux-pro-max", "taste", "interface-design", "impeccable"]
# 快照里不该带进去的东西：版本库元数据、纯展示素材、测试与构建产物
SNAPSHOT_DROP_DIRS = {".git", "docs", "evals", "tests", "test", "node_modules", "target", "dist", ".github"}
SNAPSHOT_DROP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4"}
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def load_manifest() -> dict:
    if not MANIFEST.exists():
        sys.exit(f"[FAIL] 找不到 {MANIFEST}")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def save_manifest(data: dict) -> None:
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _force_rmtree(path: Path) -> None:
    """删目录，并先清掉只读位。
    踩过的坑：从 git 工作树复制出来的 .git/objects 里的包文件常带只读属性，
    在 Windows 上 shutil.rmtree 会报 [WinError 5] 拒绝访问。"""
    if not path.exists():
        return
    for p in list(path.rglob("*")):
        try:
            if p.is_file():
                p.chmod(0o666)
        except OSError:
            pass
    for p in [path, *path.rglob("*")]:
        try:
            if p.is_dir():
                p.chmod(0o777)
        except OSError:
            pass
    shutil.rmtree(path, ignore_errors=True)


def dir_size(path: Path) -> tuple[int, float]:
    n, total = 0, 0
    if path.exists():
        for f in path.rglob("*"):
            if f.is_file():
                n += 1
                total += f.stat().st_size
    return n, total / 1024 / 1024


def head_commit(repo: Path) -> str:
    code, out = run(["git", "rev-parse", "--short", "HEAD"], cwd=repo)
    return out.strip() if code == 0 else ""


def _emit(lines: list[str]) -> None:
    """既打控制台，也写一份 UTF-8 报告文件。
    Windows 控制台默认 GBK，中文会变问号；报告文件保证任何环境都能读准。"""
    text = "\n".join(lines)
    print(text)
    try:
        (ROOT / "sync-report.txt").write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass


# ---------------- 快照 ----------------

def snapshot_skill_dir(comp: dict) -> Path:
    return ROOT / comp["snapshotSkill"]


def build_snapshots(comps: list[dict]) -> int:
    out = ["生成上游快照（从 vendor 精简，不入 .git / 展示素材 / 测试）："]
    errors = 0
    for comp in comps:
        name = Path(comp["vendorPath"]).name
        vendor_dir = VENDOR / name
        if not vendor_dir.exists():
            out.append(f"  [FAIL] {comp['skill']}: 缺少 vendor/{name}，先跑 update（需联网）")
            errors += 1
            continue
        src = vendor_dir / comp["vendorSkillPath"]
        if not src.exists():
            out.append(f"  [FAIL] {comp['skill']}: vendor 里找不到 {comp['vendorSkillPath']}")
            errors += 1
            continue
        dst = snapshot_skill_dir(comp)
        _force_rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        # 剔除不该入库的东西（.git / 展示素材 / 测试 / 构建产物）。
        # 踩过的坑：先 rglob 出列表再删——若某目录（如 taste 的 .git）整体被删，
        #   它底下的路径仍在列表里，unlink 会失败。所以先按排除目录过滤掉这些路径。
        drop_dirs = SNAPSHOT_DROP_DIRS | set(comp.get("exclude") or [])
        to_del = [p for p in list(dst.rglob("*"))
                  if p.is_dir() and p.name in drop_dirs
                  and not any(part in drop_dirs for part in p.relative_to(dst).parts[:-1])]
        for d in to_del:
            _force_rmtree(d)
        for p in list(dst.rglob("*")):
            if not p.exists():
                continue
            if p.is_file() and p.suffix.lower() in SNAPSHOT_DROP_SUFFIX:
                p.unlink(missing_ok=True)
        # 许可证与来源说明
        for lic in ("LICENSE", "NOTICE.md", "COPYING"):
            cand = vendor_dir / lic
            if cand.exists():
                shutil.copy2(cand, dst.parent / lic)
        (dst.parent / "SOURCE.txt").write_text(
            f"repo: {comp['repo']}\n"
            f"pin: {json.dumps(comp['pin'], ensure_ascii=False)}\n"
            f"vendorSkillPath: {comp['vendorSkillPath']}\n"
            f"snapshottedAt: {datetime.now().astimezone().isoformat(timespec='seconds')}\n"
            f"说明: 本目录是从完整上游精简单出的快照，只保留重抽 payload 所需内容；\n"
            f"      .git / docs / evals / tests 与图片素材已剔除。原仓 URL 见 repo 行。\n",
            encoding="utf-8")
        n, mb = dir_size(dst.parent)
        comp["snapshotSkill"] = str(dst.relative_to(ROOT)).replace("\\", "/")
        out.append(f"  {comp['skill']:<18} {n:>4} files {mb:>6.2f} MB -> {comp['snapshotSkill']}")
    if not errors:
        save_manifest_called = True  # manifest 由调用方保存
        out.append(f"[OK] snapshots 合计 {dir_size(SNAPSHOTS)[0]} 文件 / {dir_size(SNAPSHOTS)[1]:.2f} MB")
    _emit(out)
    return 1 if errors else 0


# ---------------- 抽取 ----------------

def extract_one(comp: dict) -> str:
    skill = comp["skill"]
    src = snapshot_skill_dir(comp)
    if not src.exists():
        return f"  [FAIL] {skill}: 快照不存在 {src}，先跑 build 或 update"
    dst = ROOT / comp["payloadPath"]
    _force_rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    for lic in ("LICENSE", "NOTICE.md", "COPYING"):
        cand = src.parent / lic
        if cand.exists() and not (dst / lic).exists():
            shutil.copy2(cand, dst / lic)
    n, mb = dir_size(dst)
    return f"  {skill:<18} {n:>4} files {mb:>6.2f} MB -> {comp['payloadPath']}"


def cmd_extract(args) -> int:
    man = load_manifest()
    only = set(args.only.split(",")) if args.only else None
    out = ["从快照重抽 payload（离线）："]
    for comp in man["components"]:
        if only and comp["skill"] not in only:
            continue
        out.append(extract_one(comp))
    _emit(out)
    return cmd_validate(args)


def cmd_build(args) -> int:
    man = load_manifest()
    only = set(args.only.split(",")) if args.only else None
    comps = [c for c in man["components"] if not only or c["skill"] in only]
    rc = build_snapshots(comps)
    if rc == 0:
        man["generatedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
        save_manifest(man)
    return rc


# ---------------- 上游 ----------------

def remote_latest_tag(url: str) -> str:
    code, out = run(["git", "ls-remote", "--tags", "--refs", url])
    if code != 0:
        return ""
    tags = [ln.split("\t")[-1].replace("refs/tags/", "").strip() for ln in out.splitlines() if "\t" in ln]
    tags = [t for t in tags if t]
    return max(tags, key=lambda t: ([int(x) for x in re.findall(r"\d+", t)], t)) if tags else ""


def remote_default_head(url: str) -> str:
    code, out = run(["git", "ls-remote", url, "HEAD"])
    return out.split()[0][:7] if code == 0 and out.strip() else ""


def clone_or_update(comp: dict, want_tag: str | None) -> Path:
    name = Path(comp["vendorPath"]).name
    dst = VENDOR / name
    url = comp["repo"]
    if not dst.exists():
        VENDOR.mkdir(parents=True, exist_ok=True)
        cmd = ["git", "clone", "--depth", "1"] + (["--branch", want_tag] if want_tag else []) + [url, str(dst)]
        code, out = run(cmd)
        print(f"  {'cloned' if code == 0 else '[FAIL] clone'} {name}" + (f" @ {want_tag}" if want_tag else " @ HEAD"))
        if code != 0:
            print("     " + out.strip()[-300:])
    else:
        if want_tag:
            run(["git", "fetch", "--depth", "1", "origin", f"refs/tags/{want_tag}:refs/tags/{want_tag}"], cwd=dst)
            run(["git", "checkout", "--detach", want_tag], cwd=dst)
        else:
            run(["git", "fetch", "--depth", "1", "origin", "HEAD"], cwd=dst)
            run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=dst)
        print(f"  updated {name} -> {head_commit(dst)}")
    return dst


def cmd_fetch(_args) -> int:
    man = load_manifest()
    out = ["查上游最新版本（只读，要联网）："]
    for comp in man["components"]:
        if comp["pin"].get("tag"):
            latest = remote_latest_tag(comp["repo"])
            flag = "已是最新" if latest == comp["pin"]["tag"] else f"**可升级 -> {latest}**"
            out.append(f"  {comp['skill']:<18} pin={comp['pin']['tag']:<10} 最新 tag={latest or '?':<10} {flag}")
        else:
            latest = remote_default_head(comp["repo"])
            flag = "已是最新" if latest and latest.startswith(comp["pin"]["commit"][:7]) else f"**HEAD 已前进 -> {latest}**"
            out.append(f"  {comp['skill']:<18} pin={comp['pin']['commit']:<10} 最新 HEAD={latest or '?':<10} {flag}")
    _emit(out)
    return 0


def cmd_update(args) -> int:
    man = load_manifest()
    only = set(args.only.split(",")) if args.only else None
    tag_override = {}
    for pair in (args.tag or "").split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            tag_override[k.strip()] = v.strip()

    comps = [c for c in man["components"] if not only or c["skill"] in only]
    print("拉上游（联网）：")
    for comp in comps:
        want = tag_override.get(comp["skill"]) or comp["pin"].get("tag")
        clone_or_update(comp, want)
        hc = head_commit(VENDOR / Path(comp["vendorPath"]).name)
        if hc:
            comp["pin"]["commit"] = hc
        if want:
            comp["pin"]["tag"] = want
    rc = build_snapshots(comps)
    if rc == 0:
        man["generatedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
        save_manifest(man)
        return cmd_extract(args)
    return rc


# ---------------- 校验 ----------------

def _parse_frontmatter_fallback(block: str) -> dict:
    """不依赖 PyYAML 的降级解析：支持 `key: value` 与 `key: >-` / `key: |` 块标量。
    踩过的坑：只认单行 `key: value` 会把块标量读成 2 个字符，于是误报 description 过短。"""
    fm: dict[str, str] = {}
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.startswith("#") or line.startswith((" ", "\t")) or ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key, rest = key.strip(), rest.strip()
        if rest in (">", ">-", "|", "|-", ">+", "|+"):
            chunk = []
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith((" ", "\t"))):
                chunk.append(lines[i].strip())
                i += 1
            fm[key] = " ".join(x for x in chunk if x).strip()
        else:
            fm[key] = rest.strip().strip('"').strip("'")
    return fm


def parse_frontmatter(path: Path) -> dict | None:
    m = FM_RE.match(path.read_text(encoding="utf-8", errors="replace"))
    if not m:
        return None
    try:  # 有 PyYAML 就用，没有就降级——不把 PyYAML 变成硬依赖
        import yaml  # type: ignore
        data = yaml.safe_load(m.group(1))
        if isinstance(data, dict):
            return {str(k): ("" if v is None else str(v)) for k, v in data.items()}
    except Exception:
        pass
    return _parse_frontmatter_fallback(m.group(1))


def cmd_validate(_args) -> int:
    out = ["校验 payload："]
    errors, warns = [], []
    wf = PAYLOAD / "ui-design-workflow"
    for ref in ("references/capabilities.md", "references/spec-template.md", "references/routing-matrix.md"):
        if not (wf / ref).exists():
            errors.append(f"ui-design-workflow 缺少 {ref}")
    for name in PAYLOAD_SKILLS:
        d = PAYLOAD / name
        smd = d / "SKILL.md"
        if not smd.exists():
            errors.append(f"{name}: 没有 SKILL.md")
            continue
        fm = parse_frontmatter(smd)
        if fm is None:
            errors.append(f"{name}: SKILL.md 缺 frontmatter")
            continue
        if not fm.get("name"):
            errors.append(f"{name}: frontmatter 缺 name")
        desc = fm.get("description", "")
        if len(desc) < 40:
            errors.append(f"{name}: description 过短（{len(desc)} 字符），触发会不稳")
        if (d / ".git").exists():
            errors.append(f"{name}: 混进了 .git")
        n, mb = dir_size(d)
        out.append(f"  {name:<18} {n:>4} files {mb:>6.2f} MB  name={fm.get('name','-')}  desc={len(desc)}字符")
    for e in errors:
        out.append(f"  [FAIL] {e}")
    for w in warns:
        out.append(f"  [WARN] {w}")
    if errors:
        out.append(f"[FAIL] 校验未通过：{len(errors)} 个错误")
        _emit(out)
        return 1
    out.append("[OK] 校验通过")
    _emit(out)
    return 2 if warns else 0


def cmd_check(_args) -> int:
    man = load_manifest()
    out = ["三层现状（快照 / payload / 完整克隆）：",
           f"  {'技能':<18} {'pin':<12} {'snapshot':>16} {'payload':>14} {'vendor':>12}"]
    warn = 0
    for comp in man["components"]:
        skill = comp["skill"]
        sn, sm = dir_size(snapshot_skill_dir(comp))
        pn, pm = dir_size(ROOT / comp["payloadPath"])
        vdir = VENDOR / Path(comp["vendorPath"]).name
        vn, vm = dir_size(vdir)
        pin = comp["pin"].get("tag") or comp["pin"].get("commit", "-")
        bad = "" if (sn and pn) else "   <-- 缺失"
        if bad:
            warn += 1
        out.append(f"  {skill:<18} {pin:<12} {sn:>5}f{sm:>9.2f}M {pn:>4}f{pm:>8.2f}M {vn:>5}f{vm:>6.1f}M{bad}")
    sn, sm = dir_size(SNAPSHOTS)
    _, vm = dir_size(VENDOR)
    out.append(f"  合计 snapshot {sn} 文件 {sm:.2f} MB / vendor {vm:.1f} MB（vendor 不入 git，可丢弃）")
    _emit(out)
    return 2 if warn else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="UI-design-flowing 上游同步与校验")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("build", cmd_build), ("extract", cmd_extract), ("check", cmd_check),
                     ("fetch", cmd_fetch), ("update", cmd_update), ("validate", cmd_validate)):
        p = sub.add_parser(name)
        p.add_argument("--only", help="逗号分隔，只处理这些技能")
        p.add_argument("--tag", help="技能=tag 覆盖，如 ui-ux-pro-max=v2.15.0")
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
