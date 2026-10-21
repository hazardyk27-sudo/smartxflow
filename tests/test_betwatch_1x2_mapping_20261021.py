"""Provider runner permutations must NEVER swap 1/X/2 money selections."""
from importlib import util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _mapper(path, suffix):
    spec=util.spec_from_file_location("betwatch_market_mapping_"+suffix,str(path))
    mod=util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.map_market


def _r(name,amount):
    return {"name":name,"odd":1.80,"volume":amount}


def test_all_common_1x2_runner_orders_map_same_fixture_side():
    for idx,path in enumerate((ROOT/"betwatch_client.py",
                               ROOT/"desktop/scraper_standalone/betwatch_client.py")):
        mapping=_mapper(path,str(idx))
        input_=[_r("Real Madrid",1200),_r("Draw",300),_r("Barcelona",800)]
        for order in ((0,1,2),(0,2,1),(1,0,2),(2,1,0),(2,0,1),(1,2,0)):
            market, selections=mapping("Match Odds",[input_[i] for i in order],
                home="Real Madrid",away="Barcelona")
            assert market=="1X2"
            assert {side:runner["name"] for side,runner in selections}=={
                "1":"Real Madrid","X":"Draw","2":"Barcelona"}
            assert {side:runner["volume"] for side,runner in selections}=={
                "1":1200,"X":300,"2":800}


def test_duplicate_or_ambiguous_runners_never_generate_dubious_1x2():
    for idx,path in enumerate((ROOT/"betwatch_client.py",
                               ROOT/"desktop/scraper_standalone/betwatch_client.py")):
        mapping=_mapper(path,str(idx))
        cases=(
            [_r("Home",100),_r("Home",200),_r("Draw",30)],
            [_r("Mystery One",100),_r("Draw",200),_r("Mystery Two",30)],
            [_r("Draw",100),_r("Draw",200),_r("Away",30)],
        )
        for runners in cases:
            assert mapping("Match Odds",runners,home="Real Madrid",
                           away="Barcelona")== (None,[])


def test_partial_but_identifiable_runner_keeps_only_actual_sides():
    for idx,path in enumerate((ROOT/"betwatch_client.py",
                               ROOT/"desktop/scraper_standalone/betwatch_client.py")):
        mapping=_mapper(path,str(idx))
        key,sels=mapping("Match Odds",[_r("Draw",120),_r("Away",400)],
            home="Home",away="Away")
        assert key=="1X2"
        assert {k:r["name"] for k,r in sels}=={"X":"Draw","2":"Away"}
        assert mapping("Match Odds",[_r("Home",100),_r("Away",200)],
            home="Home",away="Away")[0]=="1X2"


def test_ou25_and_btts_mapping_not_modified():
    mapping=_mapper(ROOT/"betwatch_client.py","other")
    assert [s for s,r in mapping("Over/Under 2.5 Goals",
           [_r("Over 2.5",800),_r("Under 2.5",200)])[1]]==["O","U"]
    assert [s for s,r in mapping("Both teams to Score?",
           [_r("Yes",800),_r("No",200)])[1]]==["Y","N"]
