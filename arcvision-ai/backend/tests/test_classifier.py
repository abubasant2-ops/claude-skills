from app.services.classifier import classify_discipline, classify_filetype


def test_filetype_by_extension():
    assert classify_filetype("plan.PDF") == "pdf"
    assert classify_filetype("model.ifc") == "ifc"
    assert classify_filetype("model.rvt") == "rvt"
    assert classify_filetype("layout.dwg") == "dwg"
    assert classify_filetype("layout.DXF") == "dwg"
    assert classify_filetype("boq.xlsx") == "boq"
    assert classify_filetype("notes.txt") == "unknown"


def test_arabic_discipline_detection():
    assert classify_discipline("معماري_فيلا.pdf") == "arch"
    assert classify_discipline("إنشائي.ifc") == "struct"
    assert classify_discipline("كهرباء_بلوك1.pdf") == "elec"
    assert classify_discipline("ميكانيكا.pdf") == "mech"
    assert classify_discipline("سباكة.pdf") == "plumb"


def test_english_discipline_detection():
    assert classify_discipline("Architectural-Plans.pdf") == "arch"
    assert classify_discipline("structural_rebar.pdf") == "struct"
