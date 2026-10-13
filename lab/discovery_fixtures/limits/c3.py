@entrypoint
def export_csv(actor, row):
    if permitted(actor, row):
        emit_document(row)

@entrypoint
def indirect_job(actor, row):
    callback = emit_document
    callback(row)

@entrypoint
def csv_hint(actor, row):
    return "hint"

@entrypoint
def unreachable(actor, row):
    if False:
        emit_document(row)
