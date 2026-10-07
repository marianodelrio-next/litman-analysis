from .models import ArtifactGenerator
from .economic_simulator.generator import EconomicSimulatorGenerator
from .summary import SummaryGenerator
from .technical_proposal.generator import TechnicalDocumentGenerator

ARTIFACT_GENERATORS: dict[str, ArtifactGenerator] = {
    "summary": SummaryGenerator(), "technical-document": TechnicalDocumentGenerator(),
    "economic-simulator": EconomicSimulatorGenerator(),
}


def resolve_artifact_generators(artifacts: list[str] | None) -> list[ArtifactGenerator]:
    selected = artifacts or list(ARTIFACT_GENERATORS)
    unknown = [item for item in selected if item not in ARTIFACT_GENERATORS]
    if unknown:
        raise ValueError(f"Artefacto de generación desconocido: {', '.join(unknown)}")
    return [ARTIFACT_GENERATORS[item] for item in selected]
