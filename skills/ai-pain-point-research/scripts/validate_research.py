#!/usr/bin/env python3
"""Validate a pain-point evidence ledger; no network or third-party packages.

Usage: python validate_research.py LEDGER.json
       python validate_research.py - < LEDGER.json

Validation checks recorded claims, not the truth of a source or the completeness
of a search. Missing measurements remain null; an actually observed zero is valid.
"""

import argparse
import datetime as dt
import json
import math
from pathlib import Path
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SOURCE_SCOPES = {
    "community_post": {"detail", "first_screen_comments", "expanded_thread", "full_thread"},
    "community_comment": {"detail", "first_screen_comments", "expanded_thread", "full_thread"},
    "github_issue": {"detail", "first_screen_comments", "expanded_thread", "full_thread"},
    "search_card": {"card"},
    "search_cache": {"cache"},
    "official_index": {"index_page"},
    "official_doc": {"official_doc"},
}
DIRECT_SOURCES = {"community_post", "community_comment", "github_issue"}
METRIC_KINDS = {"engagement", "search_index", "search_count", "relatedness", "matched_items"}
TRACKING_KEYS = {"xsec_token", "xsec_source", "spm", "vd_source", "share_token", "share_from_user_hidden"}


def canonical_url(url):
    """Discard fragments and known tracking parameters, but keep identity queries."""
    parsed = urlsplit(url)
    params = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
              if not k.lower().startswith("utm_") and k.lower() not in TRACKING_KEYS]
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), host, path, urlencode(sorted(params)), ""))


def validate(data):
    """Return deterministic JSON-compatible results; never mutate the input."""
    errors = []

    def error(code, path, message):
        errors.append({"code": code, "path": path, "message": message})

    def required(obj, names, path):
        for name in names:
            if name not in obj:
                error("REQUIRED_FIELD", path + "." + name, "Required field is missing.")

    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())

    def text_field(obj, key, path):
        if key in obj and not nonempty(obj[key]):
            error("INVALID_TEXT", path + "." + key, "Expected a nonempty string.")

    def date_field(obj, key, path, nullable=False):
        if key not in obj or (nullable and obj[key] is None):
            return
        value = obj[key]
        try:
            if not isinstance(value, str) or len(value) < 10:
                raise ValueError
            dt.date.fromisoformat(value[:10])
            if len(value) > 10:
                dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            error("INVALID_DATE", path + "." + key, "Expected an ISO date or datetime.")

    def enumeration(obj, key, values, path):
        if key in obj and (not isinstance(obj[key], str) or obj[key] not in values):
            error("INVALID_ENUM", path + "." + key, "Value is not in the allowed enumeration.")

    def result():
        return {"result": "FAIL" if errors else "PASS", "error_count": len(errors),
                "errors": errors,
                "summary": {"evidence": len(evidence), "topics": len(topics)}}

    evidence, topics = [], []
    if not isinstance(data, dict):
        error("ROOT_TYPE", "$", "Expected a JSON object.")
        return result()
    required(data, ["schema_version", "observed_at", "evidence", "topics"], "$")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        error("SCHEMA_VERSION", "$.schema_version", "Expected schema_version 1.")
    date_field(data, "observed_at", "$")
    for name in ("evidence", "topics"):
        if name in data and not isinstance(data[name], list):
            error("ARRAY_TYPE", "$." + name, "Expected an array.")
    evidence = data.get("evidence") if isinstance(data.get("evidence"), list) else []
    topics = data.get("topics") if isinstance(data.get("topics"), list) else []
    by_id, metrics_by_id, url_keys = {}, {}, {}

    for i, item in enumerate(evidence):
        path = "$.evidence[%d]" % i
        if not isinstance(item, dict):
            error("OBJECT_TYPE", path, "Expected an evidence object.")
            continue
        required(item, ["id", "platform", "url", "observed_at", "source_type", "read_scope",
                        "independence_key", "demand_basis", "demand_summary", "metrics"], path)
        for name in ("id", "platform", "url", "independence_key"):
            text_field(item, name, path)
        date_field(item, "observed_at", path)
        date_field(item, "published_at", path, nullable=True)
        date_field(item, "question_date", path, nullable=True)
        enumeration(item, "source_type", SOURCE_SCOPES, path)
        enumeration(item, "read_scope", set().union(*SOURCE_SCOPES.values()), path)
        enumeration(item, "demand_basis", {"direct_question", "interest_only", "none"}, path)
        enumeration(item, "issue_state", {"open", "closed", "unknown"}, path)
        source, scope = item.get("source_type"), item.get("read_scope")
        if isinstance(source, str) and source in SOURCE_SCOPES and (not isinstance(scope, str) or scope not in SOURCE_SCOPES[source]):
            error("SCOPE_SOURCE_MISMATCH", path + ".read_scope", "Read scope does not match source type.")
        if item.get("demand_basis") == "direct_question":
            if scope in ("card", "cache"):
                error("DIRECT_REQUIRES_DETAIL", path + ".demand_basis", "Cards and caches are not current direct-question evidence.")
            if not isinstance(source, str) or source not in DIRECT_SOURCES:
                error("DIRECT_QUESTION_SOURCE", path + ".source_type", "Direct questions require community or issue detail evidence.")
            if not nonempty(item.get("demand_summary")):
                error("DIRECT_SUMMARY_REQUIRED", path + ".demand_summary", "A direct question needs a concrete pain-point summary.")
        elif "demand_summary" in item and not isinstance(item["demand_summary"], str):
            error("INVALID_TEXT", path + ".demand_summary", "Expected a string, which may be empty without a direct question.")

        evidence_id = item.get("id")
        if nonempty(evidence_id):
            if evidence_id in by_id:
                error("DUPLICATE_EVIDENCE_ID", path + ".id", "Evidence ids must be unique.")
            else:
                by_id[evidence_id] = item
        if nonempty(item.get("url")):
            try:
                parsed = urlsplit(item["url"])
                if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
                    raise ValueError
                canonical = canonical_url(item["url"])
                key = item.get("independence_key")
                if nonempty(key):
                    if canonical in url_keys and url_keys[canonical] != key:
                        error("CANONICAL_URL_KEY_CONFLICT", path + ".independence_key", "The same canonical URL must use one independence key.")
                    else:
                        url_keys[canonical] = key
            except ValueError:
                error("INVALID_URL", path + ".url", "Expected an absolute HTTP(S) source URL.")

        metrics = item.get("metrics")
        metric_map = {}
        if not isinstance(metrics, list):
            error("ARRAY_TYPE", path + ".metrics", "Expected an array.")
            metrics = []
        for j, metric in enumerate(metrics):
            mpath = path + ".metrics[%d]" % j
            if not isinstance(metric, dict):
                error("OBJECT_TYPE", mpath, "Expected a metric object.")
                continue
            required(metric, ["name", "kind", "status", "value", "display", "scope", "window", "region"], mpath)
            text_field(metric, "name", mpath)
            text_field(metric, "scope", mpath)
            enumeration(metric, "kind", METRIC_KINDS, mpath)
            enumeration(metric, "status", {"observed", "missing"}, mpath)
            for name in ("display", "window", "region"):
                if name in metric and metric[name] is not None and not nonempty(metric[name]):
                    error("INVALID_NULLABLE_TEXT", mpath + "." + name, "Expected null or a nonempty string.")
            value = metric.get("value")
            if metric.get("status") == "missing" and value is not None:
                error("MISSING_VALUE_NOT_NULL", mpath + ".value", "A missing measurement must be null, not zero or another value.")
            if metric.get("status") == "observed":
                if type(value) not in (int, float) or (isinstance(value, float) and not math.isfinite(value)):
                    error("OBSERVED_VALUE_NOT_NUMBER", mpath + ".value", "An observed measurement must be a finite number; true zero is valid.")
                if not nonempty(metric.get("display")):
                    error("OBSERVED_DISPLAY_REQUIRED", mpath + ".display", "Preserve the literal observed display for numeric evidence.")
            if nonempty(metric.get("name")):
                if metric["name"] in metric_map:
                    error("DUPLICATE_METRIC_NAME", mpath + ".name", "Metric names must be unique within an evidence item.")
                else:
                    metric_map[metric["name"]] = metric
        if nonempty(evidence_id) and evidence_id not in metrics_by_id:
            metrics_by_id[evidence_id] = metric_map

    topic_ids = set()
    for i, topic in enumerate(topics):
        path = "$.topics[%d]" % i
        if not isinstance(topic, dict):
            error("OBJECT_TYPE", path, "Expected a topic object.")
            continue
        required(topic, ["id", "title", "format", "evidence_ids", "demand_status", "priority_basis", "solution_status"], path)
        for name in ("id", "title"):
            text_field(topic, name, path)
        enumeration(topic, "format", {"large_tutorial", "small_blocker"}, path)
        enumeration(topic, "demand_status", {"observed", "repeated", "interest_only"}, path)
        enumeration(topic, "priority_basis", {"editorial", "search_volume"}, path)
        enumeration(topic, "solution_status", {"untested", "docs_checked", "tested"}, path)
        topic_id = topic.get("id")
        if nonempty(topic_id):
            if topic_id in topic_ids:
                error("DUPLICATE_TOPIC_ID", path + ".id", "Topic ids must be unique.")
            topic_ids.add(topic_id)
        refs = topic.get("evidence_ids")
        if not isinstance(refs, list) or not refs:
            error("EVIDENCE_REFS_REQUIRED", path + ".evidence_ids", "A topic needs a nonempty evidence-id array.")
            refs = []
        selected, seen_refs = [], set()
        for j, ref in enumerate(refs):
            rpath = path + ".evidence_ids[%d]" % j
            if not nonempty(ref) or ref not in by_id:
                error("UNKNOWN_EVIDENCE_REF", rpath, "Referenced evidence does not exist.")
                continue
            if ref in seen_refs:
                error("DUPLICATE_EVIDENCE_REF", rpath, "A topic must not repeat an evidence id.")
                continue
            seen_refs.add(ref)
            selected.append(by_id[ref])
        direct = [item for item in selected if item.get("demand_basis") == "direct_question"
                  and isinstance(item.get("source_type"), str) and item.get("source_type") in DIRECT_SOURCES
                  and item.get("read_scope") not in ("card", "cache")]
        direct_keys = {item["independence_key"] for item in direct if nonempty(item.get("independence_key"))}
        if topic.get("demand_status") == "observed" and not direct:
            error("OBSERVED_NEEDS_DIRECT", path + ".demand_status", "Observed demand requires at least one direct-question source.")
        if topic.get("demand_status") == "repeated" and len(direct_keys) < 2:
            error("REPEATED_NEEDS_INDEPENDENT", path + ".demand_status", "Repeated demand requires two distinct independent direct-question sources.")
        if topic.get("solution_status") == "tested" and not nonempty(topic.get("solution_test_ref")):
            error("TESTED_NEEDS_TEST_REF", path + ".solution_test_ref", "A tested solution needs a test-record reference.")

        search_refs = topic.get("search_metric_refs", [])
        if not isinstance(search_refs, list):
            error("ARRAY_TYPE", path + ".search_metric_refs", "Expected an array.")
            search_refs = []
        if topic.get("priority_basis") == "search_volume" and not search_refs:
            error("SEARCH_VOLUME_NEEDS_REFS", path + ".search_metric_refs", "Search-volume priority needs exact search-count references.")
        comparison_keys = set()
        seen_search_refs = set()
        for j, ref in enumerate(search_refs):
            rpath = path + ".search_metric_refs[%d]" % j
            if not isinstance(ref, dict):
                error("OBJECT_TYPE", rpath, "Expected a metric reference object.")
                continue
            required(ref, ["evidence_id", "metric_name"], rpath)
            eid, name = ref.get("evidence_id"), ref.get("metric_name")
            if not nonempty(eid) or not nonempty(name) or eid not in metrics_by_id or name not in metrics_by_id[eid]:
                error("UNKNOWN_METRIC_REF", rpath, "Referenced metric does not exist.")
                continue
            if eid not in seen_refs:
                error("METRIC_EVIDENCE_NOT_LINKED", rpath, "Metric evidence must also appear in evidence_ids.")
            pair = (eid, name)
            if pair in seen_search_refs:
                error("DUPLICATE_METRIC_REF", rpath, "A topic must not repeat a metric reference.")
            seen_search_refs.add(pair)
            metric = metrics_by_id[eid][name]
            if topic.get("priority_basis") == "search_volume":
                if metric.get("kind") != "search_count" or metric.get("status") != "observed":
                    error("SEARCH_VOLUME_NOT_COUNT", rpath, "Only observed search counts support search-volume priority; indexes and engagement do not.")
                if not nonempty(metric.get("window")) or not nonempty(metric.get("region")):
                    error("SEARCH_COUNT_SCOPE_REQUIRED", rpath, "Search-count comparisons need a measurement window and region.")
                if nonempty(by_id[eid].get("platform")) and all(nonempty(metric.get(k)) for k in ("window", "region", "scope")):
                    comparison_keys.add((by_id[eid].get("platform"), metric["window"], metric["region"], metric["scope"]))
        if len(comparison_keys) > 1:
            error("SEARCH_COUNT_NOT_COMPARABLE", path + ".search_metric_refs", "Search counts must share platform, window, region, and measurement scope.")

    return result()


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8-sig")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON ledger path, or - for stdin")
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8-sig")
        data = json.loads(raw)
        report = validate(data)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report = {"result": "FAIL", "error_count": 1,
                  "errors": [{"code": "INPUT_ERROR", "path": "$", "message": str(exc)}],
                  "summary": {"evidence": 0, "topics": 0}}
    print(json.dumps(report, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
