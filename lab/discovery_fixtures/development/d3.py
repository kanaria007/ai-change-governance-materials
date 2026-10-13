@entrypoint
def export_document(actor, row):
    if permitted(actor, row):
        emit_document(row)

@entrypoint
def deliver(actor, row):
    transfer(row)

def transfer(row):
    emit_document(row)

@entrypoint
def csv_description(actor, row):
    return "description"

@entrypoint
def preview(actor, row):
    if False:
        emit_document(row)
    return "not sent"
