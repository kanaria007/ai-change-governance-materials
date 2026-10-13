@entrypoint
def csv_view(actor, row):
    if permitted(actor, row):
        emit_document(row)

@entrypoint
def scheduled_dispatch(actor, row):
    if permitted(actor, row):
        build_csv(row)

def build_csv(row):
    emit_document(row)

@entrypoint
def export_description(actor, row):
    return "description"

@entrypoint
def status(actor, row):
    return "ok"
