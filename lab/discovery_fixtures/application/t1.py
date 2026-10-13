@entrypoint
def export_csv(actor, row):
    if permitted(actor, row):
        emit_document(row)

@entrypoint
def customer_digest(actor, row):
    if permitted(actor, row):
        assemble(row)

def assemble(row):
    wrap(row)

def wrap(row):
    emit_document(row)

@entrypoint
def download_help(actor, row):
    return "help"

@entrypoint
def status(actor, row):
    return "ok"
