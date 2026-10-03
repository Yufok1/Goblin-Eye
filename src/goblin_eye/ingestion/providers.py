from __future__ import annotations

from pathlib import Path

from goblin_eye.repository import Database

from .base import AdapterCapability, AdapterNotReadyError, ImportResult


class SchemaGatedAdapter:
    capability: AdapterCapability

    def import_file(self, database: Database, path: Path) -> ImportResult:
        missing = "; ".join(self.capability.needs)
        raise AdapterNotReadyError(
            f"{self.capability.display_name} integration is intentionally disabled: {missing}. "
            "Use the normalized JSON/CSV adapters only with sourced real data until the schema is verified."
        )


class BootyBayBrokerAdapter(SchemaGatedAdapter):
    capability = AdapterCapability(
        key="booty_bay_broker",
        display_name="Booty Bay Broker",
        status="documentation_review_required",
        input_types=("documented community API or export",),
        supplies=("community auction snapshots", "market coverage"),
        needs=("documented permitted access method", "verified schema", "sample response"),
        documentation_url="https://bootybaybroker.com/forever",
    )


class TheWowDbAdapter(SchemaGatedAdapter):
    capability = AdapterCapability(
        key="thewowdb",
        display_name="TheWoWDB",
        status="documentation_review_required",
        input_types=("documented dataset or API",),
        supplies=("Forever item research", "community auction prices"),
        needs=("documented permitted access method", "verified schema and provenance rules"),
        documentation_url="https://thewowdb.com/wow-forever/",
    )


PROVIDER_ADAPTERS = (
    BootyBayBrokerAdapter(),
    TheWowDbAdapter(),
)
