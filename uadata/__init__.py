"""Ingestion package for the user agent dataset."""

from .model import CATEGORIES, Record, SourceError, SourceResult, merge_records

__all__ = ["CATEGORIES", "Record", "SourceError", "SourceResult", "merge_records"]
