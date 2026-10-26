"""AsciiDoc include options and physical line/tag selections."""

import csv
import re

TAG = re.compile(r"\b(?P<end>end::|tag::)(?P<name>[^\[\s]+)\[\]")


def include_options(text):
    result = {}
    for item in next(csv.reader([text], skipinitialspace=True)):
        key, separator, value = item.partition("=")
        result[key.strip()] = value.strip().strip('"') if separator else True
    return result


def select_lines(source, options):
    selected, tags = [], []
    wanted = str(options.get("tags", options.get("tag", ""))).split(";")
    positives = {t for t in wanted if t and not t.startswith("!")}
    negatives = {t[1:] for t in wanted if t.startswith("!")}
    ranges = []
    for entry in str(options.get("lines", "")).split(";"):
        if not entry:
            continue
        start, separator, end = entry.partition("..")
        ranges.append(
            (
                int(start),
                int(end) if separator and end != "-1" else (10**9 if separator else int(start)),
            )
        )
    for number, text in enumerate(source.splitlines(), 1):
        marker = TAG.search(text)
        if marker:
            if marker["end"] == "tag::":
                tags.append(marker["name"])
            elif marker["name"] in tags:
                tags.remove(marker["name"])
            continue
        active = (
            not positives
            or "**" in positives
            or ("*" in positives and bool(tags))
            or bool(positives & set(tags))
        )
        if (
            active
            and not (negatives & set(tags))
            and (not ranges or any(start <= number <= end for start, end in ranges))
        ):
            selected.append((number, text))
    return selected


def line_ranges(lines):
    ranges = []
    for number, _ in lines:
        if ranges and ranges[-1][1] + 1 == number:
            ranges[-1][1] = number
        else:
            ranges.append([number, number])
    return ranges
