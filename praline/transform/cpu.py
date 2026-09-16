"""CPU OpenMP directives; block-local variables remain automatically private."""
from .edits import Edit


def loop_edit(loop):
    shared = loop["shared_variables"]
    clauses = " default(none)" + (f" shared({', '.join(shared)})" if shared else "")
    pragma = f"\n#pragma omp parallel for{clauses}\n"
    start = loop["span"]["start"]
    return Edit(start, start, pragma.encode("utf-8"))
