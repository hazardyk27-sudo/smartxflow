"""The retired standalone retention entrypoint must not scan or delete."""
import ast
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "desktop" / "scraper_standalone" / "standalone_scraper.py"


def test_legacy_cleanup_function_is_network_free():
    tree = ast.parse(PATH.read_text(encoding="utf-8"))
    fns = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "cleanup_old_matches"]
    assert len(fns) == 1
    fn = fns[0]
    code = ast.get_source_segment(PATH.read_text(encoding="utf-8"), fn)
    assert code
    for text in ("requests.get(", "requests.delete(", "writer.delete_before(", "offset=", "select=match_id_hash"):
        assert text not in code
    messages = []
    compiled = compile(ast.Module(body=[fn], type_ignores=[]), str(PATH), "exec")
    namespace = {"SupabaseWriter": object, "log": messages.append}
    exec(compiled, namespace)
    result = namespace["cleanup_old_matches"](object())
    assert result == 0
    assert messages and "retired" in messages[0]
