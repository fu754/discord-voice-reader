from enum import Enum
from uuid import UUID
from typing import List


class Style:
    name: str
    id: int

    def __init__(self, name: str, id: int) -> None:
        self.name = name
        self.id = id


class PermittedSynthesisMorphing(Enum):
    ALL = "ALL"
    SELF_ONLY = "SELF_ONLY"


class SupportedFeatures:
    permitted_synthesis_morphing: PermittedSynthesisMorphing

    def __init__(self, permitted_synthesis_morphing: PermittedSynthesisMorphing) -> None:
        self.permitted_synthesis_morphing = permitted_synthesis_morphing


class Version(Enum):
    THE_0145 = "0.14.5"


class Speaker:
    supported_features: SupportedFeatures
    name: str
    speaker_uuid: UUID
    styles: List[Style]
    version: Version

    def __init__(self, supported_features: SupportedFeatures, name: str, speaker_uuid: UUID, styles: List[Style], version: Version) -> None:
        self.supported_features = supported_features
        self.name = name
        self.speaker_uuid = speaker_uuid
        self.styles = styles
        self.version = version
