# Datasets, Connectors, And Fields

Datasets, connectors, fields, calculated fields, dimensions, measures, and
aggregations are first-class MCP objects. They are not implementation details to
bury inside chart JavaScript.

## Object Schemas

- `schemas/connector-config.schema.json`: connection metadata without secret
  material.
- `schemas/dataset-config.schema.json`: dataset source, fields, calculated
  fields, and joins.
- `schemas/field-config.schema.json`: physical or exposed dataset fields.
- `schemas/calculated-field-config.schema.json`: formula fields with explicit
  dependencies.
- `schemas/measure-dimension-metadata.schema.json`: business semantics for
  measures and dimensions.
- `schemas/aggregation-config.schema.json`: aggregation, grain, denominator, and
  additivity metadata.

## Ordering

Connector work precedes dataset work. Dataset and field validation precedes
chart creation. Dashboard layout and selector relations are handled after the
required widgets and controls have stable object identities.

## Calculated Fields

Calculated fields must include:

- name/title
- role
- expression
- dependencies
- aggregation or unit when applicable

Chart code can reference a calculated field only after that field is represented
in dataset config or an explicit missing-field diagnostic is returned.
