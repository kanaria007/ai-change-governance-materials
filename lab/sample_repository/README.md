# Source Fixtures for E2

[日本語 / Japanese](README.ja.md)

`document_routes.py` is a trusted example containing five module-level entry points. At runtime, `route_discovery.probe()` supplies `@entrypoint`, `permitted`, and `emit_document`. This is not a standalone web application or a configured production job.

Name-based and output-based discovery both **parse this actual source file**. The missing tenant check in `scheduled_delivery` is an intentional defect. The fixture does not transmit data to an external destination.
