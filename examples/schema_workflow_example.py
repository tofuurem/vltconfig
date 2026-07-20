"""Generate and validate a value-free template without contacting Vault."""

from examples.settings import AppConfig
from vltconfig import build_model_schema, build_template, validate_payload


def main() -> None:
    """Exercise the side-effect-free schema APIs without displaying values."""
    schema = build_model_schema(AppConfig)
    template = build_template(schema)
    report = validate_payload(schema, template)

    assert report.valid is False
    print(
        f"Prepared {schema.model_name} with {report.error_count} "
        "required values awaiting population; values were not displayed."
    )


if __name__ == "__main__":
    main()
