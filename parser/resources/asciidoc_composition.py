"""Source-preserving AsciiDoc preprocessing and logical book outlines."""

import ast
import csv
import operator
import posixpath
import re
from urllib.parse import urlparse

from .asciidoc_prepare import load_include
from .asciidoc_selection import include_options, select_lines, line_ranges

ATTRIBUTE = re.compile(r"^:([^:]+):(?:\s+(.*))?$")
INCLUDE = re.compile(r"^include::([^\[]+)\[(.*)\]\s*$")
CONDITION = re.compile(r"^(ifdef|ifndef|ifeval|endif)::([^\[]*)\[(.*)\]\s*$")
HEADING = re.compile(r"^(={1,6})\s+(.+?)\s*$")
FENCE = re.compile(r"^(-{4,}|\.{4,}|\+{4,}|/{4,})\s*$")


def substitute(text, attributes):
    seen = set()
    for _ in range(32):
        if text in seen:
            break
        seen.add(text)
        updated = re.sub(r"\{([\w.-]+)\}", lambda m: attributes.get(m[1], m[0]), text)
        if updated == text:
            break
        text = updated
    return text


def condition_value(kind, names, expression, attributes):
    if kind == "ifeval":
        expanded = substitute(expression, attributes)
        match = re.fullmatch(r"\s*(.*?)\s*(==|!=|>=|<=|>|<)\s*(.*?)\s*", expanded)
        if not match:
            raise ValueError("unsupported ifeval expression")
        left, right = ast.literal_eval(match[1]), ast.literal_eval(match[3])
        return {
            "==": operator.eq,
            "!=": operator.ne,
            ">=": operator.ge,
            "<=": operator.le,
            ">": operator.gt,
            "<": operator.lt,
        }[match[2]](left, right)
    present = (
        all(n in attributes for n in names.split("+"))
        if "+" in names
        else any(n in attributes for n in names.split(","))
    )
    return not present if kind == "ifndef" else present


class Composition:
    def __init__(self, source, path, prepared):
        self.path, self.prepared = path, prepared
        self.attributes = dict((prepared or {}).get("attributes", {}))
        self.locked = set(self.attributes)
        self.attribute_sources = {}
        self.outline, self.includes, self.issues = [], [], []
        self.effective = source.splitlines()
        if self.effective:
            self.effective[0] = self.effective[0].lstrip("\ufeff")
        self.remaining = 50000
        self.walk(source, path, stack=(), level=0, literal=False, anchor=1)

    def issue(self, path, line, message, anchor):
        self.issues.append((line if path == self.path else anchor, f"{path}:{line}: {message}"))

    def walk(self, source, path, *, stack, level, literal, anchor, selected=None):
        if path in stack or len(stack) >= 32:
            self.issue(path, 1, "cyclic include or include depth exceeds 32", anchor)
            return
        lines = (
            selected
            if selected is not None
            else list(enumerate(source.lstrip("\ufeff").splitlines(), 1))
        )
        conditions, fence = [], None
        for number, raw in lines:
            self.remaining -= 1
            if self.remaining < 0:
                self.issue(path, number, "composition exceeds 50000 lines", anchor)
                return
            text = raw
            condition = CONDITION.match(text)
            if condition:
                if condition[1] in {"ifdef", "ifndef"} and condition[3]:
                    text = (
                        condition[3]
                        if all(conditions)
                        and condition_value(condition[1], condition[2], "", self.attributes)
                        else ""
                    )
                else:
                    self._condition(condition, conditions, path, number, anchor)
                    if path == self.path:
                        self.effective[number - 1] = ""
                    continue
            if not all(conditions):
                if path == self.path:
                    self.effective[number - 1] = ""
                continue
            marker = FENCE.match(text)
            if marker:
                token = marker[1][0]
                fence = None if fence == token else (token if fence is None else fence)
                continue
            attribute = ATTRIBUTE.match(text) if not literal and fence is None else None
            if attribute:
                key = attribute[1].strip("!")
                if key not in self.locked:
                    if attribute[1].startswith("!") or attribute[1].endswith("!"):
                        self.attributes.pop(key, None)
                    else:
                        value = substitute(attribute[2] or "", self.attributes)
                        if key == "leveloffset" and value.startswith(("+", "-")):
                            try:
                                value = str(int(self.attributes.get(key, "0")) + int(value))
                            except ValueError:
                                pass
                        self.attributes[key] = value
                        self.attribute_sources[key] = {"file_path": path, "line": number}
                continue
            include = INCLUDE.match(substitute(text, self.attributes))
            if include:
                self._include(
                    include, path, number, stack, level, literal or fence is not None, anchor
                )
            if not literal and fence is None:
                text = substitute(text, self.attributes)
                heading = HEADING.match(text)
                if heading and len(self.outline) < 2000:
                    offset = self.attributes.get("leveloffset", "0")
                    try:
                        offset = int(offset)
                    except ValueError:
                        offset = 0
                    self.outline.append(
                        {
                            "title": heading[2],
                            "level": max(0, len(heading[1]) - 1 + level + offset),
                            "file_path": path,
                            "line": number,
                        }
                    )
            if path == self.path:
                self.effective[number - 1] = text
        if conditions:
            self.issue(path, lines[-1][0] if lines else 1, "unclosed conditional", anchor)

    def _condition(self, match, conditions, path, line, anchor):
        kind, names, expression = match.groups()
        if kind == "endif":
            if conditions:
                conditions.pop()
            else:
                self.issue(path, line, "endif without matching condition", anchor)
            return
        if not all(conditions):
            conditions.append(False)
            return
        try:
            active = condition_value(kind, names, expression, self.attributes)
        except (ValueError, TypeError, SyntaxError):
            active = False
            self.issue(path, line, "conditional could not be evaluated", anchor)
        conditions.append(active)

    def _include(self, match, path, line, stack, level, literal, anchor):
        target, raw_options = match.groups()
        try:
            options = include_options(raw_options)
        except (ValueError, csv.Error) as exc:
            self.issue(path, line, f"include options invalid: {type(exc).__name__}", anchor)
            return
        parsed = urlparse(target)
        target_path = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
        resolution = "external" if parsed.scheme or parsed.netloc else "unresolved"
        if "{" in target or target.startswith("/") or target_path.startswith("../"):
            target_path, resolution = None, "dynamic"
        elif resolution == "external":
            target_path = None
        entry = {
            "line": line,
            "target": target,
            "target_file_path": target_path,
            "resolution": resolution,
            "options": options,
            "selection_ranges": [],
            "literal": literal,
        }
        if path == self.path:
            self.includes.append(entry)
        if target_path is None:
            return
        try:
            included = load_include(self.prepared, target_path)
            if included is None:
                return
            selected = select_lines(included, options)
            entry["selection_ranges"] = line_ranges(selected)
            offset = str(options.get("leveloffset", "0"))
            child_level = (
                level + int(offset)
                if offset.startswith(("+", "-"))
                else int(offset)
                if "leveloffset" in options
                else level
            )
            self.walk(
                included,
                target_path,
                stack=(*stack, path),
                level=child_level,
                literal=literal,
                anchor=line if path == self.path else anchor,
                selected=selected,
            )
        except (OSError, ValueError, UnicodeError) as exc:
            if options.get("opts") != "optional" and "optional" not in options:
                self.issue(
                    path, line, f"include {target!r} unavailable: {type(exc).__name__}", anchor
                )


def compose_asciidoc(source, path, prepared=None):
    return Composition(source, path, prepared)
