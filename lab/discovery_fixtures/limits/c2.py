@entrypoint
def download_one(actor, row):
    if permitted(actor, row):
        emit_document(row)

@entrypoint
def legacy_writer(actor, row):
    archive_document(row)

@entrypoint
def csv_schema(actor, row):
    return {"title": "string"}

@entrypoint
def status(actor, row):
    return "ok"
