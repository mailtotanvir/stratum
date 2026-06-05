from fastapi import APIRouter, HTTPException

from app.db.schema import ToolParameterRecord, ToolRecord
from app.models.tool import Tool, ToolCreate, ToolParameter
from app.services.tool_registry_service import (
    ToolAlreadyExistsError,
    ToolNotFoundError,
    tool_registry_service,
)

router = APIRouter()


def to_tool_parameter(record: ToolParameterRecord) -> ToolParameter:
    return ToolParameter(
        id=record.id,
        tool_id=record.tool_id,
        name=record.name,
        type=record.type,
        required=record.required,
    )


def to_tool(record: ToolRecord) -> Tool:
    return Tool(
        id=record.id,
        name=record.name,
        description=record.description,
        enabled=record.enabled,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
        parameters=[
            to_tool_parameter(parameter)
            for parameter in tool_registry_service.list_parameters(record.id)
        ],
    )


@router.post("/tools")
def register_tool(request: ToolCreate) -> Tool:
    try:
        return to_tool(
            tool_registry_service.register_tool(
                name=request.name,
                description=request.description,
                enabled=request.enabled,
                parameters=[
                    parameter.model_dump(mode="json")
                    for parameter in request.parameters
                ],
            )
        )
    except ToolAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/tools")
def list_tools(enabled_only: bool = False) -> list[Tool]:
    return [
        to_tool(tool)
        for tool in tool_registry_service.list_tools(enabled_only=enabled_only)
    ]


@router.get("/tools/{tool_id}")
def get_tool(tool_id: str) -> Tool:
    try:
        return to_tool(tool_registry_service.get_tool(tool_id))
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tools/{tool_id}/enable")
def enable_tool(tool_id: str) -> Tool:
    try:
        return to_tool(tool_registry_service.enable_tool(tool_id))
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tools/{tool_id}/disable")
def disable_tool(tool_id: str) -> Tool:
    try:
        return to_tool(tool_registry_service.disable_tool(tool_id))
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
