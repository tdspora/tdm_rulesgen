from __future__ import annotations


class RulesgenError(Exception):
    """Base domain error."""


class RuleNotFoundError(RulesgenError):
    pass


class JobNotFoundError(RulesgenError):
    pass


class ArtifactNotFoundError(RulesgenError):
    pass


class DatasetUploadNotFoundError(RulesgenError):
    pass


class PromptAuditNotFoundError(RulesgenError):
    pass
