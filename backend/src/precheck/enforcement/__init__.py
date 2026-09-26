"""Data plane: adapters that enforce the live policy. Never imports `precheck.authoring`;
talks to the control plane only through the contracts in `precheck.schema.lab`, and never
on the request path."""
