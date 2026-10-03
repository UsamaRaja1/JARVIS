import ast
from pathlib import Path


def _load_method(name):
    source = Path("src/vision_processing/face_recognition_system.py").read_text()
    tree = ast.parse(source)
    method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name)
    method.decorator_list = []
    namespace = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "<scan-test>", "exec"), namespace)
    return namespace[name]


def test_scan_moves_toward_waypoint_without_overshooting():
    move_toward = _load_method("_move_toward")

    assert move_toward(100, 110) == 103
    assert move_toward(100, 90) == 97
    assert move_toward(108, 110) == 110
    assert move_toward(92, 90) == 90


def test_scan_starts_near_last_tracked_position():
    nearest_position_index = _load_method("_nearest_position_index")
    positions = ((127, 127), (75, 127), (180, 127), (127, 160))

    assert nearest_position_index(positions, 70, 125) == 1
    assert nearest_position_index(positions, 130, 165) == 3
