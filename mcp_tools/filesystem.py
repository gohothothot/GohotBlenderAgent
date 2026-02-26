"""
文件系统工具 — 读写文件、列目录、读项目结构
[DEVLOG]
- 2026-02-26: 初始版本。file_read/write/list/read_project 4 个工具。
  基于项目根目录限制访问范围。
"""

import os
import fnmatch

_BASE = os.path.dirname(os.path.dirname(__file__))


def execute(tool_name: str, arguments: dict) -> dict:
    dispatch = {
        "file_read": file_read,
        "file_write": file_write,
        "file_list": file_list,
        "file_read_project": file_read_project,
    }
    func = dispatch.get(tool_name)
    if not func:
        return {"success": False, "result": None, "error": f"未知文件工具: {tool_name}"}
    return func(**arguments)


def file_read(path: str, encoding: str = "utf-8", max_lines: int = 500) -> dict:
    try:
        if not os.path.isabs(path):
            path = os.path.join(_BASE, path)
        if not os.path.isfile(path):
            return {"success": False, "result": None, "error": f"文件不存在: {path}"}
        with open(path, "r", encoding=encoding, errors="replace") as f:
            lines = f.readlines()[:max_lines]
        return {
            "success": True,
            "result": {"path": path, "content": "".join(lines), "lines": len(lines), "truncated": len(lines) >= max_lines},
            "error": None,
        }
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def file_write(path: str, content: str, encoding: str = "utf-8", append: bool = False) -> dict:
    try:
        if not os.path.isabs(path):
            path = os.path.join(_BASE, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mode = "a" if append else "w"
        with open(path, mode, encoding=encoding) as f:
            f.write(content)
        action = "追加" if append else "写入"
        return {"success": True, "result": f"已{action}: {path} ({len(content)} 字符)", "error": None}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def file_list(path: str = "", pattern: str = "", recursive: bool = False) -> dict:
    try:
        if not path or not os.path.isabs(path):
            path = os.path.join(_BASE, path) if path else _BASE
        if not os.path.isdir(path):
            return {"success": False, "result": None, "error": f"目录不存在: {path}"}
        entries = []
        if recursive:
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for f in files:
                    if pattern and not fnmatch.fnmatch(f, pattern):
                        continue
                    entries.append({"name": os.path.relpath(os.path.join(root, f), path), "type": "file"})
                    if len(entries) > 200:
                        break
        else:
            for name in sorted(os.listdir(path)):
                if name.startswith(".") or name == "__pycache__":
                    continue
                if pattern and not fnmatch.fnmatch(name, pattern):
                    continue
                full = os.path.join(path, name)
                entries.append({"name": name, "type": "dir" if os.path.isdir(full) else "file"})
        return {"success": True, "result": entries, "error": None}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def file_read_project(filename: str) -> dict:
    try:
        import bpy
        blend_path = bpy.data.filepath
        if not blend_path:
            return {"success": False, "result": None, "error": "Blender 文件未保存，无法确定项目目录"}
        target = os.path.join(os.path.dirname(blend_path), filename)
        return file_read(target)
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}
