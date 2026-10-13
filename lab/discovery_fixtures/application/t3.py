@entrypoint
def download_one(actor, row):
    if permitted(actor, row):
        emit_document(row)

@entrypoint
def weekly_package(actor, row):
    transfer(row)

def transfer(row):
    emit_document(row)

@entrypoint
def export_usage(actor, row):
    return "usage"

@entrypoint
def public_sample(actor, row):
    emit_document({"document_id": "public-sample", "tenant": "public"})
