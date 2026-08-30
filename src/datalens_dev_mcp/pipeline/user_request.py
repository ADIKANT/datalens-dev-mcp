from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse


TaskIntent = Literal[
    "implement",
    "fix",
    "enhance",
    "redesign",
    "update",
    "review",
    "plan",
    "unknown",
]
RouteIntent = Literal[
    "js",
    "advanced_editor",
    "wizard_native",
    "native_table",
    "native_pivot",
    "wizard_map_native",
    "ql_explicit",
    "unspecified",
]
PublishOverride = Literal["none", "plan_only", "dry_run", "draft", "save_only", "no_publish"]
BrowserPreference = Literal["forbidden", "required", "unspecified"]
OperationKind = Literal["inspect", "mutate", "verify_existing_effect"]
EffectKind = Literal[
    "none",
    "saved",
    "published",
    "changed",
    "deleted",
    "moved",
    "data_appeared",
    "restored",
]


@dataclass(frozen=True)
class NormalizedUserRequest:
    raw_text: str
    task_intent: TaskIntent
    route_intent: RouteIntent
    route_explicit: bool = False
    publish_override: PublishOverride = "none"
    destructive_actions: list[str] = field(default_factory=list)
    target_url: str = ""
    reference_url: str = ""
    url_inventory: list[dict[str, str]] = field(default_factory=list)
    target_workbook_id: str = ""
    target_dashboard_id: str = ""
    target_chart_id: str = ""
    target_object_type: str = ""
    approval_sources: list[str] = field(default_factory=lambda: ["current_user_request"])
    evidence: list[str] = field(default_factory=list)
    browser_preference: BrowserPreference = "unspecified"
    explicit_constraints: list[str] = field(default_factory=list)
    operation_kind: OperationKind = "inspect"
    effect_kind: EffectKind = "none"

    @property
    def target_known(self) -> bool:
        return bool(self.target_dashboard_id or self.target_chart_id)

    @property
    def publish_allowed_by_text(self) -> bool:
        return self.publish_override == "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UserRequestNormalizer:
    """Normalize free-form operator text into deterministic delivery signals."""

    IMPLEMENT_TERMS = {
        "implement": (
            "implement",
            "build",
            "create",
            "make",
            "apply",
            "publish",
            "save",
            "реализ",
            "сделай",
            "созд",
            "примени",
            "сохран",
            "опублику",
            "добав",
        ),
        "fix": ("fix", "repair", "исправ", "почин", "устран"),
        "enhance": ("enhance", "improve", "extend", "доработ", "улучш", "расшир"),
        "redesign": ("redesign", "переработ", "редизайн"),
        "update": (
            "update",
            "change",
            "modify",
            "обнов",
            "измени",
            "изменить",
            "замени",
            "поменяй",
            "настрой",
            "передел",
        ),
    }
    REVIEW_TERMS = (
        "review",
        "audit",
        "inspect",
        "diagnose",
        "посмотри",
        "проверь",
        "оцени",
        "аудит",
        "диагност",
        "проанализ",
    )
    VERIFY_EXISTING_EFFECT_PATTERNS = (
        re.compile(
            r"\b(?:i\s+(?:have\s+|already\s+)?|i(?:'ve|\s+have)\s+)"
            r"(?:saved|published|changed|updated|deleted|removed|moved|restored)\b"
            r"(?:(?!\n\n).){0,160}\b(?:check|verify|inspect|confirm)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"\b(?:check|verify|inspect|confirm)\b(?:(?!\n\n).){0,160}"
            r"\b(?:already\s+)?(?:saved|published|changed|updated|deleted|removed|moved|restored|applied)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"(?<!\w)(?:я\s+)?(?:уже\s+)?"
            r"(?:сохранил\w*|опубликовал\w*|изменил\w*|обновил\w*|удалил\w*|перен[её]с\w*|восстановил\w*)"
            r"(?:(?!\n\n).){0,160}(?:проверь\w*|посмотри\w*|вс[её]\s+ли|подтверди\w*)",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"(?:проверь\w*|посмотри\w*|подтверди\w*)(?:(?!\n\n).){0,160}"
            r"(?:применил\w*\s+ли|появил\w*|сохранил\w*|опубликовал\w*|удалил\w*|"
            r"перенес\w*|перенёс\w*|восстановил\w*|на\s+месте)",
            re.IGNORECASE | re.DOTALL,
        ),
    )
    PLAN_TERMS = ("plan", "план", "спланируй", "dry run", "dry_run", "без изменений", "только план")
    NEGATED_MUTATION_PATTERNS = (
        re.compile(
            r"\b(?:do\s+not|don't|never)\s+"
            r"(?:implement\w*|build\w*|create\w*|make|apply\w*|publish\w*|save\w*|fix\w*|repair\w*|"
            r"enhance\w*|improve\w*|extend\w*|redesign\w*|update\w*|change\w*|modify\w*|"
            r"delete\w*|remove\w*)"
            r"(?:\s+(?:or|and)\s+"
            r"(?:implement\w*|build\w*|create\w*|make|apply\w*|publish\w*|save\w*|fix\w*|repair\w*|"
            r"enhance\w*|improve\w*|extend\w*|redesign\w*|update\w*|change\w*|modify\w*|"
            r"delete\w*|remove\w*))*",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:nothing\s+should\s+be|nothing\s+is\s+to\s+be)\s+"
            r"(?:saved|published|changed|created|updated|modified|fixed)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?<!\w)(?:не|никогда\s+не|ничего\s+не)\s+"
            r"(?:созда\w*|сдела\w*|реализ\w*|примен\w*|сохран\w*|опубли\w*|добав\w*|исправ\w*|"
            r"почин\w*|устран\w*|доработ\w*|улучш\w*|расшир\w*|переработ\w*|передел\w*|обнов\w*|измени\w*|"
            r"замен\w*|помен\w*|настро\w*|удал\w*)"
            r"(?:\s+и\s+не\s+"
            r"(?:созда\w*|сдела\w*|реализ\w*|примен\w*|сохран\w*|опубли\w*|добав\w*|исправ\w*|"
            r"почин\w*|устран\w*|доработ\w*|улучш\w*|расшир\w*|переработ\w*|передел\w*|обнов\w*|измени\w*|"
            r"замен\w*|помен\w*|настро\w*|удал\w*))*",
            re.IGNORECASE,
        ),
    )
    ROUTE_TERMS: dict[RouteIntent, tuple[str, ...]] = {
        "ql_explicit": ("ql chart", "ql-чарт", "через ql", "route=ql_explicit", "createqlchart", "updateqlchart"),
        "js": (" js", "javascript", "editor js", "на js", "через js"),
        "advanced_editor": ("advanced editor", "editor chart", "advanced-chart", "адвансед"),
        "wizard_native": ("wizard", "native datalens chart", "обычный график datalens", "через wizard", "визард"),
        "native_table": ("table", "таблиц", "таблич", "detail rows", "registry"),
        "native_pivot": ("pivot", "сводн", "cross-tab", "crosstab"),
        "wizard_map_native": ("map", "geo", "карта", "гео", "latitude", "longitude", "geopoint", "geopolygon"),
    }
    OVERRIDES: dict[PublishOverride, tuple[str, ...]] = {
        "plan_only": (
            "plan only",
            "plan-only",
            "plan_only",
            "только план",
            "составь план",
            "подготовь план",
            "спланируй",
            "без изменений",
            "без записи",
            "не меняй",
            "ничего не меняй",
            "не сохраняй",
            "ничего не сохраняй",
            "do not save",
            "don't save",
            "do not create",
            "don't create",
            "do not change",
            "don't change",
            "make no changes",
            "nothing should be saved",
            "не создавай",
            "ничего не создавай",
            "не исправляй",
            "не обновляй",
            "не изменяй",
        ),
        "dry_run": ("dry run", "dry-run", "dry_run", "пробный"),
        "draft": ("draft", "черновик"),
        "save_only": ("save only", "save-only", "save_only", "only save", "только save", "только сохранить", "только сохрани"),
        "no_publish": (
            "no publish",
            "no-publish",
            "no_publish",
            "do not publish",
            "don't publish",
            "without publishing",
            "without publish",
            "не публикуй",
            "ничего не публикуй",
            "не опубликовывай",
            "без публикации",
            "без publish",
        ),
    }
    DESTRUCTIVE_TERMS = {
        "delete": ("delete", "remove", "удали", "удалить"),
        "move": ("move", "перемести"),
        "permissions_change": ("permission", "access binding", "доступ", "права"),
        "credential_change": ("credential", "token", "password", "iam token", "секрет", "пароль"),
    }
    PARTIAL_CONTENT_TERMS = (
        "legend",
        "column",
        "field",
        "filter",
        "widget",
        "selector",
        "tab",
        "series",
        "label",
        "title",
        "header",
        "axis",
        "measure",
        "metric",
        "dimension",
        "sort",
        "format",
        "color",
        "row",
        "точк",
        "заголов",
        "ось",
        "метрик",
        "измерен",
        "сортиров",
        "формат",
        "цвет",
        "строк",
        "легенд",
        "колон",
        "столб",
        "поле",
        "фильтр",
        "виджет",
        "селектор",
        "вклад",
        "сери",
        "подпис",
    )
    WHOLE_OBJECT_DELETE_TERMS = (
        "delete object",
        "remove object",
        "delete dashboard",
        "delete chart",
        "remove chart",
        "delete dataset",
        "remove dataset",
        "delete connection",
        "remove connection",
        "delete workbook",
        "remove workbook",
        "remove dashboard",
        "удали объект",
        "удалить объект",
        "удали дашборд",
        "удалить дашборд",
        "удали чарт",
        "удалить чарт",
        "удали датасет",
        "удалить датасет",
        "удали подключение",
        "удалить подключение",
        "удали воркбук",
        "удалить воркбук",
    )
    APPROVAL_SOURCES = {
        "goal_objective_file": ("goal objective", "goal-objective", "цель из файла"),
        "codex_tool_approval": ("codex tool approval", "tool approval", "approved tool", "разрешение codex"),
        "project_manifest_operator_approval": ("manifest approved", "operator approval"),
        "explicit_chat_approval": ("i approve", "я подтверждаю", "одобряю"),
    }
    # Markdown links repeat the URL as ``[label](target)``. Treat Markdown
    # delimiters as URL boundaries so a label URL cannot absorb ``](https:``
    # and corrupt the extracted DataLens object ID.
    URL_RE = re.compile(r"https?://[^\s()<>\[\]\"]+", re.I)
    LABELED_ID_RE = re.compile(
        r"\b(?P<label>workbook|workbook_id|workbookId|dashboard|dashboard_id|dashboardId|chart|chart_id|chartId)"
        r"[ \t]*[:=][ \t]*(?P<id>[A-Za-z0-9_-]{5,64})",
        re.I,
    )
    BACKTICK_LABELED_ID_RE = re.compile(
        r"\b(?P<label>workbook|workbook_id|workbookId|dashboard|dashboard_id|dashboardId|chart|chart_id|chartId)"
        r"[ \t]+`(?P<id>[A-Za-z0-9_-]{5,64})`",
        re.I,
    )

    def normalize(
        self,
        text: str,
        *,
        approval_sources: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> NormalizedUserRequest:
        raw = text or ""
        lowered = raw.lower()
        ctx = context or {}
        operation_kind = self._operation_kind(lowered)
        effect_kind = self._effect_kind(lowered) if operation_kind == "verify_existing_effect" else "none"
        task_intent = "review" if operation_kind == "verify_existing_effect" else self._task_intent(lowered)
        publish_override = self._publish_override(lowered)
        route_intent = self._route_intent(lowered)
        url_inventory = self._url_inventory(raw)
        target_url = str(ctx.get("target_url") or self._target_url(url_inventory))
        reference_url = str(ctx.get("reference_url") or self._reference_url(url_inventory))
        extracted = self._extract_targets(raw, target_url=target_url)
        destructive = [] if operation_kind == "verify_existing_effect" else self._destructive_actions(lowered)
        if task_intent == "unknown" and self._is_partial_content_update(lowered) and "delete" not in destructive:
            task_intent = "update"
        sources = ["current_user_request"]
        for source, terms in self.APPROVAL_SOURCES.items():
            if any(term in lowered for term in terms):
                sources.append(source)
        for source in approval_sources or []:
            if source and source not in sources:
                sources.append(source)
        return NormalizedUserRequest(
            raw_text=raw,
            task_intent=task_intent,
            route_intent=route_intent,
            route_explicit=self._route_is_explicit(lowered, route_intent),
            publish_override=publish_override,
            destructive_actions=destructive,
            target_url=target_url,
            reference_url=reference_url,
            url_inventory=url_inventory,
            target_workbook_id=str(ctx.get("target_workbook_id") or extracted.get("workbook_id") or ""),
            target_dashboard_id=str(ctx.get("target_dashboard_id") or extracted.get("dashboard_id") or ""),
            target_chart_id=str(ctx.get("target_chart_id") or extracted.get("chart_id") or ""),
            target_object_type=str(ctx.get("target_object_type") or extracted.get("object_type") or ""),
            approval_sources=sources,
            evidence=extracted.get("evidence", []),
            browser_preference=self._browser_preference(raw),
            explicit_constraints=self._explicit_constraints(raw),
            operation_kind=operation_kind,
            effect_kind=effect_kind,
        )

    def _operation_kind(self, lowered: str) -> OperationKind:
        if any(pattern.search(lowered) for pattern in self.VERIFY_EXISTING_EFFECT_PATTERNS):
            return "verify_existing_effect"
        intent = self._task_intent(lowered)
        return "mutate" if intent in {"implement", "fix", "enhance", "redesign", "update"} else "inspect"

    @staticmethod
    def _effect_kind(lowered: str) -> EffectKind:
        if re.search(r"(?:data\s+(?:appeared|is\s+present)|данн\w*\s+появил\w*)", lowered):
            return "data_appeared"
        if re.search(r"\bpublish(?:ed)?\b|опубликовал\w*|опубликован\w*", lowered):
            return "published"
        if re.search(r"\bsav(?:e|ed)\b|сохранил\w*|сохранен\w*|сохранён\w*", lowered):
            return "saved"
        if re.search(r"\b(?:deleted|removed)\b|удалил\w*|удален\w*|удалён\w*", lowered):
            return "deleted"
        if re.search(r"\bmoved\b|перен[её]с\w*|переместил\w*", lowered):
            return "moved"
        if re.search(r"\brestored\b|восстановил\w*|восстановлен\w*|на\s+месте", lowered):
            return "restored"
        return "changed"

    @staticmethod
    def _browser_preference(raw: str) -> BrowserPreference:
        lowered = raw.lower()
        if re.search(r"\b(?:do not|don't|without|no)\s+(?:use\s+|open\s+)?(?:the\s+)?browser\b", lowered):
            return "forbidden"
        if any(term in lowered for term in ("не надо в браузер", "не используй браузер", "без браузера")):
            return "forbidden"
        if re.search(r"\b(?:use|open|check|verify)\s+(?:(?:in|with)\s+)?(?:the\s+)?browser\b", lowered):
            return "required"
        if any(term in lowered for term in ("используй браузер", "открой браузер", "проверь в браузере")):
            return "required"
        return "unspecified"

    @staticmethod
    def _explicit_constraints(raw: str) -> list[str]:
        return [
            line.strip(" -\t")
            for line in raw.splitlines()
            if line.strip() and any(
                marker in line.lower()
                for marker in ("do not", "don't", "preserve", "keep", "не меня", "не надо", "сохрани", "оставь")
            )
        ]

    def _destructive_actions(self, lowered: str) -> list[str]:
        positive_text = self._positive_mutation_text(lowered)
        destructive = [
            action
            for action, terms in self.DESTRUCTIVE_TERMS.items()
            if (
                self._matches_permissions_change(positive_text)
                if action == "permissions_change"
                else any(self._matches_destructive_term(positive_text, term) for term in terms)
            )
        ]
        if "delete" not in destructive:
            return destructive
        partial_content_update = self._is_partial_content_update(positive_text)
        if partial_content_update:
            destructive.remove("delete")
        return destructive

    @staticmethod
    def _matches_destructive_term(lowered: str, term: str) -> bool:
        # ``move`` must be a standalone word; a substring check also matches
        # the ordinary update verb ``remove``.
        if term == "move":
            return re.search(r"(?<![a-z0-9_])move(?![a-z0-9_])", lowered) is not None
        return term in lowered

    @staticmethod
    def _matches_permissions_change(lowered: str) -> bool:
        """Recognize an actual permission mutation, not ordinary substrings."""

        permission = (
            r"(?:permissions?|access\s+bindings?|access\s+rights?|"
            r"прав(?:а|о|ами|ах)?|доступ(?:а|ом|у)?)"
        )
        action = (
            r"(?:change|modify|update|grant|revoke|remove|add|set|"
            r"измен\w*|помен\w*|обнов\w*|выда\w*|предостав\w*|"
            r"отозв\w*|убер\w*|добав\w*|настро\w*)"
        )
        return bool(
            re.search(rf"(?<![\w]){action}(?:\s+\S+){{0,5}}\s+{permission}(?![\w])", lowered)
            or re.search(rf"(?<![\w]){permission}(?:\s+\S+){{0,5}}\s+{action}(?![\w])", lowered)
        )

    def _is_partial_content_update(self, lowered: str) -> bool:
        has_removal_verb = any(term in lowered for term in self.DESTRUCTIVE_TERMS["delete"])
        return bool(has_removal_verb and any(term in lowered for term in self.PARTIAL_CONTENT_TERMS))

    def _task_intent(self, lowered: str) -> TaskIntent:
        positive_text = self._positive_mutation_text(lowered)
        # Specific change intent must outrank delivery verbs such as save or
        # publish. Otherwise "update ... save and publish" is misclassified
        # as a create task merely because the sentence also contains save.
        for intent in ("redesign", "fix", "enhance", "update", "implement"):
            terms = self.IMPLEMENT_TERMS[intent]
            if any(self._matches_intent_term(positive_text, term) for term in terms):
                return intent  # type: ignore[return-value]
        if any(term in lowered for term in self.REVIEW_TERMS):
            return "review"
        if any(term in lowered for term in self.PLAN_TERMS):
            return "plan"
        return "unknown"

    def _positive_mutation_text(self, lowered: str) -> str:
        positive_text = lowered
        for pattern in self.NEGATED_MUTATION_PATTERNS:
            positive_text = pattern.sub(" ", positive_text)
        return positive_text

    @staticmethod
    def _matches_intent_term(text: str, term: str) -> bool:
        if term.isascii() and re.fullmatch(r"[a-z]+", term):
            return re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", text) is not None
        return term in text

    def _publish_override(self, lowered: str) -> PublishOverride:
        for override, terms in self.OVERRIDES.items():
            if any(term in lowered for term in terms):
                return override
        return "none"

    def _route_intent(self, lowered: str) -> RouteIntent:
        ql_positive_text = re.sub(
            r"(?i)(?:\b(?:no|without|never|forbid(?:den)?|do\s+not\s+use)\s+ql(?:\s+fallback)?\b|"
            r"\bql\s+fallback\s+(?:is\s+)?forbidden\b|"
            r"(?:не\s+использ\w*|без|запрещ\w*)\s+ql\b|"
            r"\bql\s+(?:не\s+использ\w*|не\s+нуж\w*|запрещ\w*|is\s+not\s+used|must\s+not\s+be\s+used)\b)",
            " ",
            lowered,
        )
        if re.search(r"(?<![a-z0-9_])ql(?![a-z0-9_])", ql_positive_text) or any(
            term in ql_positive_text for term in self.ROUTE_TERMS["ql_explicit"]
        ):
            return "ql_explicit"
        route_positive_text = re.sub(
            r"(?i)(?:\b(?:no|without|never|do\s+not\s+use|don't\s+use)\s+"
            r"(?:advanced\s+editor(?:\s+js)?|javascript(?:\s+editor)?|js)\b|"
            r"\b(?:instead\s+of|preferred\s+over)\s+(?:advanced\s+editor(?:\s+js)?|javascript(?:\s+editor)?|js)\b|"
            r"(?:не\s+возвращ\w*\s+к|без\s+возврата\s+к|не\s+использ\w*|вместо)\s+"
            r"(?:advanced\s+editor(?:\s+js)?|javascript(?:\s+editor)?|js))",
            " ",
            lowered,
        )
        wizard_primary = bool(
            re.search(r"в\s+основном\s+использ\w*\s+(?:именно\s+)?wizard|primarily\s+use\s+wizard", lowered)
        )
        if not wizard_primary:
            if re.search(
                r"(?<![a-z0-9_])js(?![a-z0-9_])|javascript|editor js|на js|через js|"
                r"на\s+стороне\s+чарт\w*(?:\s+\S+){0,5}\s+обработчик",
                route_positive_text,
            ):
                return "js"
            if any(term in route_positive_text for term in self.ROUTE_TERMS["advanced_editor"]):
                return "advanced_editor"
        map_terms = self.ROUTE_TERMS["wizard_map_native"]
        if re.search(r"(?<![a-z0-9_])(map|geo)(?![a-z0-9_])", lowered) or any(
            term in lowered for term in map_terms if term not in {"map", "geo"}
        ):
            return "wizard_map_native"
        for route in ("native_pivot", "native_table", "wizard_native"):
            if any(term in lowered for term in self.ROUTE_TERMS[route]):  # type: ignore[index]
                return route  # type: ignore[return-value]
        return "unspecified"

    @staticmethod
    def _route_is_explicit(lowered: str, route: RouteIntent) -> bool:
        if route in {"js", "advanced_editor", "ql_explicit"}:
            return True
        if route == "wizard_native":
            return bool(re.search(r"(?:use|через|использ\w*|route\s*=)\s+(?:the\s+)?(?:wizard|визард)", lowered))
        if route == "native_table":
            return bool(
                re.search(
                    r"native\s+table|wizard\s+table|(?:use|через|использ\w*)\s+(?:the\s+)?(?:wizard|визард)|"
                    r"(?:обычн\w*|нативн\w*)\s+таблиц",
                    lowered,
                )
            )
        if route == "native_pivot":
            return bool(re.search(r"native\s+pivot|wizard\s+pivot|через\s+(?:wizard|визард)", lowered))
        if route == "wizard_map_native":
            return bool(re.search(r"native\s+map|wizard\s+map|через\s+(?:wizard|визард)", lowered))
        return False

    def _url_inventory(self, raw: str) -> list[dict[str, str]]:
        inventory: list[dict[str, str]] = []
        for match in self.URL_RE.finditer(raw):
            url = match.group(0).rstrip(".,;:]}")
            parsed = urlparse(url)
            hostname = (parsed.hostname or "").lower()
            is_datalens = "datalens" in hostname
            line_start = raw.rfind("\n", 0, match.start()) + 1
            line_end = raw.find("\n", match.end())
            if line_end < 0:
                line_end = len(raw)
            before = self.URL_RE.sub(" ", raw[line_start : match.start()]).lower()
            after = self.URL_RE.sub(" ", raw[match.end() : line_end]).lower()
            vicinity = f"{before} {after}"
            reference_marked = any(
                marker in vicinity
                for marker in (
                    "reference",
                    "example",
                    "sample",
                    "style source",
                    "как в",
                    "по аналогии",
                    "эталон",
                    "образец",
                    "референс",
                )
            )
            target_marked = any(
                marker in vicinity
                for marker in (
                    "target",
                    "target dashboard",
                    "target chart",
                    "целевой",
                    "целевая",
                    "целевая ссылка",
                    "изменить дашборд",
                    "обновить дашборд",
                    "доработать дашборд",
                )
            )
            if not is_datalens:
                role = "evidence"
            elif reference_marked and not target_marked:
                role = "reference"
            elif target_marked:
                role = "target"
            else:
                role = "candidate"
            inventory.append(
                {
                    "url": url,
                    "role": role,
                    "kind": "datalens" if is_datalens else "external",
                }
            )
        return inventory

    @staticmethod
    def _target_url(inventory: list[dict[str, str]]) -> str:
        for role in ("target", "candidate"):
            for item in inventory:
                if item.get("kind") == "datalens" and item.get("role") == role:
                    return str(item.get("url") or "")
        return ""

    @staticmethod
    def _reference_url(inventory: list[dict[str, str]]) -> str:
        for item in inventory:
            if item.get("kind") == "datalens" and item.get("role") == "reference":
                return str(item.get("url") or "")
        return ""

    def _extract_targets(self, raw: str, *, target_url: str) -> dict[str, Any]:
        values: dict[str, Any] = {"evidence": []}
        if target_url:
            values.update(_ids_from_url(target_url))
            values["evidence"].append(f"user_url:{target_url}")
        text_without_urls = self.URL_RE.sub(" ", raw)
        matches = [
            *self.LABELED_ID_RE.finditer(text_without_urls),
            *self.BACKTICK_LABELED_ID_RE.finditer(text_without_urls),
        ]
        for match in sorted(matches, key=lambda item: item.start()):
            label = match.group("label").lower()
            value = match.group("id")
            if "workbook" in label:
                values["workbook_id"] = value
                values["evidence"].append(f"text_workbook_id:{value}")
            elif "dashboard" in label:
                values["dashboard_id"] = value
                values["object_type"] = "dashboard"
                values["evidence"].append(f"text_dashboard_id:{value}")
            elif "chart" in label:
                values["chart_id"] = value
                values["object_type"] = "chart"
                values["evidence"].append(f"text_chart_id:{value}")
        return values


def normalize_user_request(
    text: str,
    *,
    approval_sources: list[str] | None = None,
    context: dict[str, Any] | None = None,
) -> NormalizedUserRequest:
    return UserRequestNormalizer().normalize(text, approval_sources=approval_sources, context=context)


def _ids_from_url(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    is_datalens_host = "datalens" in (parsed.hostname or "").lower()
    query = parse_qs(parsed.query)
    result: dict[str, str] = {}
    for key, target_key in (
        ("workbookId", "workbook_id"),
        ("workbook_id", "workbook_id"),
        ("dashboardId", "dashboard_id"),
        ("dashboard_id", "dashboard_id"),
        ("chartId", "chart_id"),
        ("chart_id", "chart_id"),
        ("id", "dashboard_id"),
    ):
        if is_datalens_host and query.get(key):
            result[target_key] = query[key][0]
    parts = [part for part in parsed.path.split("/") if part]
    if is_datalens_host and parts:
        seo_dashboard = re.match(r"^(?P<id>[A-Za-z0-9]{13})(?:-|$)", parts[0])
        if seo_dashboard:
            result.setdefault("dashboard_id", seo_dashboard.group("id"))
            result.setdefault("object_type", "dashboard")
    for index, part in enumerate(parts if is_datalens_host else []):
        lowered = part.lower()
        next_part = parts[index + 1] if index + 1 < len(parts) else ""
        if lowered in {"workbook", "workbooks"} and next_part:
            result.setdefault("workbook_id", next_part)
        elif lowered in {"dashboard", "dashboards"} and next_part:
            result.setdefault("dashboard_id", next_part)
            result.setdefault("object_type", "dashboard")
        elif lowered in {"chart", "charts"} and next_part:
            result.setdefault("chart_id", next_part)
            result.setdefault("object_type", "chart")
    return result
