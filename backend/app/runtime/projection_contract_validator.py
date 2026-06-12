from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from app.models.projection import Projection, ProjectionSchemaInfo


class ProjectionContractError(ValueError):
    pass


def validate_projection_contract(builder: object) -> ProjectionSchemaInfo:
    try:
        schema_info = getattr(builder, "schema_info")
        if isinstance(schema_info, BaseModel):
            schema_info = schema_info.model_dump()
        schema = ProjectionSchemaInfo.model_validate(schema_info)
    except (AttributeError, TypeError, ValidationError) as exc:
        raise ProjectionContractError(
            "Invalid projection contract"
        ) from exc

    required_values = {
        "projection_type": schema.projection_type,
        "builder_name": schema.builder_name,
        "reconstruction_source": (
            schema.reconstruction.reconstruction_source
        ),
        "authoritative_source": (
            schema.reconstruction.authoritative_source
        ),
    }
    for field_name, value in required_values.items():
        if not value.strip():
            raise ProjectionContractError(
                f"Invalid projection contract: {field_name} is required"
            )

    if schema.reconstruction.rebuildable is not True:
        raise ProjectionContractError(
            "Invalid projection contract: rebuildable must be true"
        )

    return schema.model_copy(deep=True)


def validate_projection_result(
    result: object,
    schema: ProjectionSchemaInfo,
) -> None:
    projections: Sequence[object]
    if isinstance(result, Projection):
        projections = [result]
    elif isinstance(result, Sequence) and not isinstance(
        result,
        (str, bytes, bytearray),
    ):
        projections = result
    else:
        raise ProjectionContractError(
            "Invalid projection rebuild: builder returned an unsupported result"
        )

    for index, projection in enumerate(projections):
        if not isinstance(projection, Projection):
            raise ProjectionContractError(
                "Invalid projection rebuild: "
                f"result item {index} is not a Projection"
            )

        metadata = projection.metadata
        actual_contract = metadata.model_dump(
            exclude={"built_at", "source"},
        )
        if actual_contract != schema.model_dump():
            raise ProjectionContractError(
                "Invalid projection rebuild: "
                f"result item {index} metadata does not match the "
                "registered projection contract"
            )
