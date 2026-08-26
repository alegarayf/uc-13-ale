"""On-cluster driver for ``verify_legal_register`` (eval-signal-foldback M8 T2).

Invoked by ``legal_register_verify_submit.py`` via a serverless SparkPythonTask.
Delegates to ``verify_legal_register`` and ``s2_writer.make_sdk_sql_executor()``.
Does not construct a warehouse client of its own.
"""
from __future__ import annotations


def main(company: str, run_id: str, catalog: str) -> None:
    from eval.content.legal_register_verifier import verify_legal_register
    from eval.content.s2_writer import make_sdk_sql_executor

    n_claims = verify_legal_register(
        company,
        run_id,
        catalog=catalog,
        sql_executor=make_sdk_sql_executor(),
    )
    print(
        f"legal_register_verify_driver company={company!r} run_id={run_id} "
        f"catalog={catalog} n_claims={n_claims}"
    )


if __name__ == "__main__":
    import argparse
    import os
    import sys
    from pathlib import Path

    here = Path(__file__).resolve()
    if here.parent.name == "program" and here.parent.parent.name == "eval":
        repo = here.parents[2]
        os.chdir(repo)
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        os.environ.setdefault("PYTHONPATH", str(repo))

    parser = argparse.ArgumentParser(description="On-cluster legal_register verify driver")
    parser.add_argument("company")
    parser.add_argument("run_id")
    parser.add_argument("catalog")
    args = parser.parse_args()
    main(args.company, args.run_id, args.catalog)
