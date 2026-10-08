from .models import ArtifactGenerator
from .economic_simulator.generator import EconomicSimulatorGenerator
from .bid_preparation_guide import BidPreparationGuideGenerator
from .technical_summary import TechnicalSummaryGenerator
from .technical_proposal.generator import TechnicalDocumentGenerator

ARTIFACT_GENERATORS: dict[str, ArtifactGenerator] = {
    # Insertion order defines the deterministic default; explicit requests retain caller order.
    "technical-summary": TechnicalSummaryGenerator(), "summary": BidPreparationGuideGenerator(), "technical-document": TechnicalDocumentGenerator(),
    "economic-simulator": EconomicSimulatorGenerator(),
}


def resolve_artifact_generators(artifacts: list[str] | None) -> list[ArtifactGenerator]:
    selected = artifacts or list(ARTIFACT_GENERATORS)
    unknown = [item for item in selected if item not in ARTIFACT_GENERATORS]
    if unknown:
        raise ValueError(f"Artefacto de generación desconocido: {', '.join(unknown)}")
    return [ARTIFACT_GENERATORS[item] for item in selected]
