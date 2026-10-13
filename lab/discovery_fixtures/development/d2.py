@entrypoint
def download_current(actor, row):
    if permitted(actor, row):
        emit_document(row)

@entrypoint
def run_job(actor, row):
    build_csv(row)

def build_csv(row):
    emit_document(row)

@entrypoint
def csv_layout(actor, row):
    return ["title", "tenant"]

@entrypoint
def health(actor, row):
    return "ok"
