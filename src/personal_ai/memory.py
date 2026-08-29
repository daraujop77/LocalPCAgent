"""Small durable memory stores used by the workflow and learning boundaries.

The stores intentionally use JSONL/JSON files rather than a database.  The
record shapes are stable, append-only where possible, and can be moved behind
a database adapter later without changing workflow callers.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from personal_ai.contracts import HealthStatus


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_json(value: object) -> object:
    """Return a JSON-compatible copy without allowing arbitrary objects in stores."""

    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return str(value)


@dataclass(frozen=True, slots=True)
class ExperienceEpisode:
    """A completed or failed execution episode."""

    episode_id: str
    run_id: str
    workflow: str
    task: str
    success: bool
    summary: str
    inputs: Mapping[str, object] = field(default_factory=dict)
    outputs: Mapping[str, object] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    created_at: str = field(default_factory=_now)
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        for name in ("errors", "warnings", "artifacts", "tags"):
            result[name] = list(result[name])
        return result


@dataclass(frozen=True, slots=True)
class SemanticRecord:
    """Stable project or preference knowledge."""

    record_id: str
    key: str
    value: object
    source: str
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SkillVersion:
    """A candidate or promoted procedure with explicit provenance."""

    skill_id: str
    name: str
    version: int
    status: str
    steps: tuple[str, ...]
    source_episode_ids: tuple[str, ...]
    validation_runs: tuple[Mapping[str, object], ...] = ()
    success_rate: float = 0.0
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["steps"] = list(self.steps)
        result["source_episode_ids"] = list(self.source_episode_ids)
        result["validation_runs"] = [dict(item) for item in self.validation_runs]
        return result


class _JsonlStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def read(self) -> list[dict[str, object]]:
        with self._lock:
            if not self.path.exists():
                return []
            records: list[dict[str, object]] = []
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    value = json.loads(line)
                    if isinstance(value, dict):
                        records.append(value)
            return records

    def append(self, value: Mapping[str, object]) -> None:
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


class ExperienceMemory:
    """Append-only episodic memory with simple deterministic search."""

    def __init__(self, root: str | Path = "memory") -> None:
        self.root = Path(root)
        self._store = _JsonlStore(self.root / "episodic" / "episodes.jsonl")

    def record(
        self,
        *,
        run_id: str,
        workflow: str,
        task: str,
        success: bool,
        summary: str,
        inputs: Mapping[str, object] | None = None,
        outputs: Mapping[str, object] | None = None,
        errors: Iterable[str] = (),
        warnings: Iterable[str] = (),
        artifacts: Iterable[str] = (),
        tags: Iterable[str] = (),
        duration_ms: int | None = None,
    ) -> ExperienceEpisode:
        episode = ExperienceEpisode(
            episode_id=uuid4().hex,
            run_id=run_id,
            workflow=workflow,
            task=task,
            success=success,
            summary=summary,
            inputs=_safe_json(dict(inputs or {})),
            outputs=_safe_json(dict(outputs or {})),
            errors=tuple(str(item) for item in errors),
            warnings=tuple(str(item) for item in warnings),
            artifacts=tuple(str(item) for item in artifacts),
            tags=tuple(str(item) for item in tags),
            duration_ms=duration_ms,
        )
        self._store.append(episode.to_dict())
        return episode

    def list(self, *, limit: int = 50) -> list[ExperienceEpisode]:
        return [
            ExperienceEpisode(
                episode_id=str(record.get("episode_id", "")),
                run_id=str(record.get("run_id", "")),
                workflow=str(record.get("workflow", "")),
                task=str(record.get("task", "")),
                success=bool(record.get("success", False)),
                summary=str(record.get("summary", "")),
                inputs=record.get("inputs", {})
                if isinstance(record.get("inputs"), Mapping)
                else {},
                outputs=record.get("outputs", {})
                if isinstance(record.get("outputs"), Mapping)
                else {},
                errors=tuple(str(item) for item in record.get("errors", [])),
                warnings=tuple(str(item) for item in record.get("warnings", [])),
                artifacts=tuple(str(item) for item in record.get("artifacts", [])),
                tags=tuple(str(item) for item in record.get("tags", [])),
                created_at=str(record.get("created_at", "")),
                duration_ms=record.get("duration_ms")
                if isinstance(record.get("duration_ms"), int)
                else None,
            )
            for record in reversed(self._store.read())
        ][: max(0, limit)]

    def search(self, query: str, *, limit: int = 20) -> list[ExperienceEpisode]:
        normalized = query.casefold().strip()
        if not normalized:
            return self.list(limit=limit)
        return [
            episode
            for episode in self.list(limit=max(limit, 1000))
            if normalized in json.dumps(episode.to_dict(), ensure_ascii=False).casefold()
        ][:limit]


class SemanticMemory:
    """Small last-write-wins semantic store keyed by a stable name."""

    def __init__(self, root: str | Path = "memory") -> None:
        self.path = Path(root) / "semantic" / "records.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _read(self) -> dict[str, dict[str, object]]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}

    def remember(self, key: str, value: object, *, source: str) -> SemanticRecord:
        clean_key = key.strip()
        if not clean_key:
            raise ValueError("semantic memory key must not be empty")
        now = _now()
        with self._lock:
            records = self._read()
            previous = records.get(clean_key, {})
            record = SemanticRecord(
                record_id=str(previous.get("record_id", uuid4().hex)),
                key=clean_key,
                value=_safe_json(value),
                source=source,
                created_at=str(previous.get("created_at", now)),
                updated_at=now,
            )
            records[clean_key] = record.to_dict()
            self.path.write_text(
                json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return record

    def get(self, key: str) -> SemanticRecord | None:
        with self._lock:
            record = self._read().get(key)
        if not isinstance(record, Mapping):
            return None
        return SemanticRecord(
            record_id=str(record.get("record_id", "")),
            key=str(record.get("key", key)),
            value=record.get("value"),
            source=str(record.get("source", "")),
            created_at=str(record.get("created_at", "")),
            updated_at=str(record.get("updated_at", "")),
        )

    def list(self) -> list[SemanticRecord]:
        with self._lock:
            records = self._read().values()
        return [
            item
            for key in sorted(record.get("key", "") for record in records)
            if (item := self.get(key)) is not None
        ]


class SkillMemory:
    """Versioned procedural memory; promotion is always explicit."""

    def __init__(self, root: str | Path = "memory") -> None:
        self.path = Path(root) / "procedural" / "skills.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _read(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []

    def _write(self, records: list[dict[str, object]]) -> None:
        self.path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def create_candidate(
        self,
        *,
        name: str,
        steps: Iterable[str],
        source_episode_ids: Iterable[str],
    ) -> SkillVersion:
        clean_name = name.strip()
        clean_steps = tuple(str(step).strip() for step in steps if str(step).strip())
        if not clean_name or not clean_steps:
            raise ValueError("a skill candidate requires a name and at least one step")
        with self._lock:
            records = self._read()
            versions = [
                int(item.get("version", 0)) for item in records if item.get("name") == clean_name
            ]
            skill = SkillVersion(
                skill_id=uuid4().hex,
                name=clean_name,
                version=max(versions, default=0) + 1,
                status="candidate",
                steps=clean_steps,
                source_episode_ids=tuple(str(item) for item in source_episode_ids),
            )
            records.append(skill.to_dict())
            self._write(records)
        return skill

    def list(self, *, name: str | None = None) -> list[SkillVersion]:
        with self._lock:
            records = self._read()
        return [
            self._from_dict(item) for item in records if name is None or item.get("name") == name
        ]

    def get(self, skill_id: str) -> SkillVersion | None:
        return next((item for item in self.list() if item.skill_id == skill_id), None)

    def validate(self, skill_id: str, *, success: bool, notes: str = "") -> SkillVersion:
        with self._lock:
            records = self._read()
            for index, record in enumerate(records):
                if record.get("skill_id") != skill_id:
                    continue
                runs = list(record.get("validation_runs", []))
                runs.append({"success": success, "notes": notes, "timestamp": _now()})
                successes = sum(
                    1 for run in runs if isinstance(run, Mapping) and run.get("success")
                )
                updated = dict(record)
                updated["validation_runs"] = runs
                updated["success_rate"] = successes / len(runs)
                updated["status"] = "validated" if success and successes >= 2 else "candidate"
                updated["updated_at"] = _now()
                records[index] = updated
                self._write(records)
                return self._from_dict(updated)
        raise KeyError(f"unknown skill candidate: {skill_id}")

    def promote(self, skill_id: str) -> SkillVersion:
        with self._lock:
            records = self._read()
            selected: dict[str, object] | None = None
            selected_index = -1
            for index, record in enumerate(records):
                if record.get("skill_id") == skill_id:
                    selected = record
                    selected_index = index
                    break
            if selected is None:
                raise KeyError(f"unknown skill candidate: {skill_id}")
            if selected.get("status") != "validated":
                raise ValueError("only a repeatedly validated candidate can be promoted")
            for index, record in enumerate(records):
                if (
                    record.get("name") == selected.get("name")
                    and record.get("status") == "promoted"
                ):
                    records[index] = {**record, "status": "superseded", "updated_at": _now()}
            promoted = {**selected, "status": "promoted", "updated_at": _now()}
            records[selected_index] = promoted
            self._write(records)
            return self._from_dict(promoted)

    @staticmethod
    def _from_dict(record: Mapping[str, object]) -> SkillVersion:
        return SkillVersion(
            skill_id=str(record.get("skill_id", "")),
            name=str(record.get("name", "")),
            version=int(record.get("version", 0)),
            status=str(record.get("status", "candidate")),
            steps=tuple(str(item) for item in record.get("steps", [])),
            source_episode_ids=tuple(str(item) for item in record.get("source_episode_ids", [])),
            validation_runs=tuple(
                item for item in record.get("validation_runs", []) if isinstance(item, Mapping)
            ),
            success_rate=float(record.get("success_rate", 0.0)),
            created_at=str(record.get("created_at", "")),
            updated_at=str(record.get("updated_at", "")),
        )


@dataclass(slots=True)
class MemoryService:
    """Composition root for semantic, episodic, and procedural memory."""

    root: str = "memory"
    provider_name: str = "memory"
    episodes: ExperienceMemory = field(init=False)
    semantic: SemanticMemory = field(init=False)
    skills: SkillMemory = field(init=False)

    def __post_init__(self) -> None:
        self.episodes = ExperienceMemory(self.root)
        self.semantic = SemanticMemory(self.root)
        self.skills = SkillMemory(self.root)

    def health(self) -> HealthStatus:
        return HealthStatus(
            name=self.provider_name,
            status="ok",
            ready=True,
            details={
                "storage": "jsonl_and_json",
                "root": str(Path(self.root).resolve()),
                "episodic_records": len(self.episodes.list(limit=100000)),
                "semantic_records": len(self.semantic.list()),
                "procedural_versions": len(self.skills.list()),
                "promotion_requires_explicit_validation": True,
            },
        )
