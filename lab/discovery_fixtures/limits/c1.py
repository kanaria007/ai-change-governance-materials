@entrypoint
def export_csv(actor, row):
    if permitted(actor, row):
        emit_document(row)

@entrypoint
def scheduled_hook(actor, row):
    callback = globals()["emit_document"]
    callback(row)

@entrypoint
def export_help(actor, row):
    return "help"

@entrypoint
def status(actor, row):
    return "ok"
