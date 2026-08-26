from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


DISCOVERABLE_FACTS = (
    "workbook_id",
    "dashboard_id",
    "chart_id",
    "target_ids",
    "object_type",
    "technology",
    "dataset_schema",
    "field_guids",
    "layout",
    "tabs",
    "saved_revision",
    "published_revision",
    "reference_hash",
    "browser_availability",
    "auth_state",
)
QUESTION_PRIORITY = (
    "business_key",
    "metric_semantics",
    "empty_data_semantics",
    "exact_reference",
    "destructive_scope",
    "unavailable_business_info",
)
QUESTION_TEXT = {
    "business_key": "Какое поле или набор полей является бизнес-ключом для этой задачи?",
    "metric_semantics": "Как именно должна рассчитываться и интерпретироваться целевая метрика?",
    "empty_data_semantics": "Как трактовать пустой результат: как ноль, отсутствие данных или ошибку?",
    "exact_reference": "Какой из найденных reference-объектов нужно воспроизвести точно?",
    "destructive_scope": "Подтвердите точный destructive scope и перечислите объекты, которые разрешено удалить.",
    "unavailable_business_info": "Уточните недоступный из read-only источников бизнес-факт, необходимый для реализации.",
}
QUESTION_WHY = {
    "business_key": "Уникальность нельзя доказать по доступной schema/readback.",
    "metric_semantics": "Технические источники не определяют бизнес-смысл показателя.",
    "empty_data_semantics": "Readback показывает данные, но не задаёт бизнес-трактовку пустого результата.",
    "exact_reference": "Несколько references одинаково подходят, а точный выбор не выводится из текущего запроса.",
    "destructive_scope": "Destructive scope нельзя расширять автоматически.",
    "unavailable_business_info": "Факт отсутствует в доступных read-only источниках.",
}


@dataclass(frozen=True)
class TaskQuestion:
    schema_id: str
    category: str
    question: str
    why_not_discoverable: str
    max_answers: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QuestionDecision:
    question: TaskQuestion | None
    discovery_required: tuple[str, ...]
    ignored_ambiguities: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question.to_dict() if self.question else None,
            "discovery_required": list(self.discovery_required),
            "ignored_ambiguities": list(self.ignored_ambiguities),
        }


def resolve_question_policy(
    *,
    required_discoverable_facts: list[str] | tuple[str, ...] = (),
    discovered_facts: dict[str, Any] | None = None,
    unresolved_facts: dict[str, Any] | None = None,
) -> QuestionDecision:
    discovered = discovered_facts or {}
    discovery_required = tuple(
        fact
        for fact in required_discoverable_facts
        if fact in DISCOVERABLE_FACTS and not _present(discovered.get(fact))
    )
    unresolved = unresolved_facts or {}
    ignored = tuple(sorted(key for key, value in unresolved.items() if _present(value) and key not in QUESTION_PRIORITY))
    for category in QUESTION_PRIORITY:
        if _present(unresolved.get(category)):
            return QuestionDecision(
                question=TaskQuestion(
                    schema_id="datalens_task_question",
                    category=category,
                    question=QUESTION_TEXT[category],
                    why_not_discoverable=QUESTION_WHY[category],
                ),
                discovery_required=discovery_required,
                ignored_ambiguities=ignored,
            )
    return QuestionDecision(question=None, discovery_required=discovery_required, ignored_ambiguities=ignored)


def _present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return value is not None and value is not False
