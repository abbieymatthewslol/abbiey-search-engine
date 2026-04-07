from engine.engine import ZeroClickEngine


def test_calculator():
    engine = ZeroClickEngine()
    answer = engine.answer("2 * 300")
    assert answer is not None
    assert answer.answer_type == "calculator"
    assert answer.summary == "600"


def test_domain():
    engine = ZeroClickEngine()
    answer = engine.answer("abbieysearch.com")
    assert answer is not None
    assert answer.answer_type == "domain"


def test_ipv4():
    engine = ZeroClickEngine()
    answer = engine.answer("192.168.0.1")
    assert answer is not None
    assert answer.answer_type == "ip"


def test_coordinates():
    engine = ZeroClickEngine()
    answer = engine.answer("-37.8136, 144.9631")
    assert answer is not None
    assert answer.answer_type == "coordinates"
