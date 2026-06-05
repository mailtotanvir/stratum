from enum import StrEnum

from pydantic import BaseModel


class ToolParameterType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    JSON = "json"


class ToolParameterCreate(BaseModel):
    name: str
    type: ToolParameterType
    required: bool = False


class ToolCreate(BaseModel):
    name: str
    description: str
    enabled: bool = True
    parameters: list[ToolParameterCreate] = []


class ToolParameter(BaseModel):
    id: str
    tool_id: str
    name: str
    type: ToolParameterType
    required: bool

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class Tool(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool
    created_at: str
    updated_at: str
    parameters: list[ToolParameter] = []

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")
