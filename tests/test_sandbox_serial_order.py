import ast
from pathlib import Path


def allocate(rows, model_order, max_seq=0):
    # Execute the route's allocation block without importing DB/auth services.
    source = Path(__file__).resolve().parents[1] / "api/routes/sandbox.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    function = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)
                    and n.name == "sync_batch_to_plan")
    start = next(i for i, n in enumerate(function.body)
                 if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                 and n.targets[0].id == "records")
    end = next(i for i, n in enumerate(function.body[start:], start)
               if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
               and n.targets[0].id == "df")
    block = ast.Module(body=function.body[start:end], type_ignores=[])
    context = dict(filtered=list(rows), model_order=model_order, max_seq=max_seq,
                   target_prefix="96-10-", batch_code="10-01", inbound_date_str="2026-10-17")
    exec(compile(block, str(source), "exec"), context)
    return context["serial_pairs"]


def unit(identifier, model, serial=""):
    return (identifier, model, "", "", "", None, "", serial)


def test_dictionary_order_wins_over_display_slots():
    rows = ([unit(f"fh-{i}", "FH-300C") for i in range(5)]
            + [unit(f"600-{i}", "FR-600G") for i in range(6)]
            + [unit(f"400-{i}", "FR-400G") for i in range(19)])
    pairs = allocate(rows, {"FH-300C": 0, "FR-400G": 1, "FR-600G": 7})
    assert pairs[:5] == [(f"fh-{i}", f"96-10-{i + 1:02d}") for i in range(5)]
    assert pairs[5:24] == [(f"400-{i}", f"96-10-{i + 6:02d}") for i in range(19)]
    assert pairs[24:] == [(f"600-{i}", f"96-10-{i + 25:02d}") for i in range(6)]


def test_existing_identity_is_preserved_on_retry():
    rows = [unit("600", "FR-600G", "96-10-01"), unit("400", "FR-400G")]
    pairs = allocate(rows, {"FR-400G": 1, "FR-600G": 7}, max_seq=1)
    assert dict(pairs) == {"600": "96-10-01", "400": "96-10-02"}


def test_dictionary_rank_not_model_name_controls_order():
    rows = [unit("a", "FR-400G"), unit("b", "FR-600G"), unit("c", "FR-600G")]
    assert allocate(rows, {"FR-400G": 9, "FR-600G": 2}) == [
        ("b", "96-10-01"), ("c", "96-10-02"), ("a", "96-10-03")]
