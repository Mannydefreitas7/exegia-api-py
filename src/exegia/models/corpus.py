from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class BookType(str, Enum):
    bible = "bible"
    commentary = "commentary"
    lexicon = "lexicon"
    biography = "biography"
    review = "review"
    manuscript = "manuscript"
    tanakh = "tanakh"
    quran = "quran"
    apocrypha = "apocrypha"


class FormatType(str, Enum):
    xml = "application/xml"
    json = "application/json"
    html = "text/html"
    text = "text/plain"
    pdf = "application/pdf"
    tei = "application/tei+xml"
    tf = "application/tf+xml"
    cfm = "application/cfm+xml"
    epub = "application/epub+xml"


class CategoryType(str, Enum):
    biblical = "biblical"
    religious = "religious"
    literary = "literary"
    historical = "historical"
    paratext = "paratext"


class LanguageType(str, Enum):
    hebrew = "hebrew"
    greek = "greek"
    syriac = "syriac"
    arabic = "arabic"
    aramaic = "aramaic"
    proto_cuneiform = "proto-cuneiform"
    akkadian = "akkadian"
    ugaritic = "ugaritic"
    pali = "pali"
    latin = "latin"
    dutch = "dutch"
    french = "french"
    italian = "italian"
    english = "english"


class BaseBook(BaseModel):
    uuid: UUID
    name: str
    type: BookType
    version: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    format: FormatType
    description: Optional[str] = None
    download_uri: Optional[str] = None
    licence: Optional[str] = None
    date: Optional[datetime] = None
    credits: Optional[str] = None

    class Config:
        populate_by_name = True


class Corpus(BaseBook):
    language: LanguageType
    period: str
    repository: str
    size: Optional[str] = None
    image_url: Optional[str] = None
    category: list[CategoryType]
