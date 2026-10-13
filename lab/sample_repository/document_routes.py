# Trusted, synthetic document SaaS. Runtime primitives are supplied by the lab.
@entrypoint
def export_csv(actor, row):
    if permitted(actor, row):
        emit_document(row)

@entrypoint
def batch_export(actor, row):
    if permitted(actor, row):
        emit_document(row)

@entrypoint
def scheduled_delivery(actor, row):
    deliver(row)

def deliver(row):
    emit_document(row)

@entrypoint
def export_help(actor, row):
    return "help"

@entrypoint
def health(actor, row):
    return "ok"
