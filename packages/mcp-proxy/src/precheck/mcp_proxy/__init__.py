"""Data plane: adapters that enforce the live policy. Never imports `precheck.server.authoring`;
talks to the control plane only through the contracts in `precheck.core.schema.lab`, and never
on the request path."""
