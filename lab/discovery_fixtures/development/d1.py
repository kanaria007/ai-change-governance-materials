@entrypoint
def export_csv(actor, row):
    if permitted(actor, row):
        emit_document(row)

@entrypoint
def nightly(actor, row):
    package(row)

def package(row):
    emit_document(row)

@entrypoint
def export_help(actor, row):
    return "how to export"

@entrypoint
def health(actor, row):
    return "ok"
