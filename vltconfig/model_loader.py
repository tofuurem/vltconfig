"""Safe loading of importable Pydantic model references."""

import importlib

from pydantic import BaseModel

from vltconfig.errors import ModelReferenceError


def load_model(reference: str) -> type[BaseModel]:
    """Load ``<module>:<class>`` without instantiating the resolved model."""
    module_name, separator, attribute_path = reference.partition(":")
    if not separator or not module_name or not attribute_path or ":" in attribute_path:
        raise ModelReferenceError(
            "Model reference must use the form '<module>:<class>'"
        )

    try:
        target: object = importlib.import_module(module_name)
    except Exception as cause:
        raise ModelReferenceError(
            f"Could not import model module {module_name!r}",
            cause_type=type(cause).__name__,
        ) from None

    for attribute in attribute_path.split("."):
        if not attribute:
            raise ModelReferenceError("Model class path contains an empty attribute")
        try:
            target = getattr(target, attribute)
        except AttributeError as cause:
            raise ModelReferenceError(
                f"Model class {attribute_path!r} was not found in {module_name!r}",
                cause_type=type(cause).__name__,
            ) from None

    if not isinstance(target, type) or not issubclass(target, BaseModel):
        raise ModelReferenceError(
            f"Imported object {attribute_path!r} is not a Pydantic model class"
        )
    return target
