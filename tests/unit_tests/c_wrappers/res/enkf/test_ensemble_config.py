import os
from datetime import datetime

import pytest
from ecl.grid.ecl_grid import EclGrid
from ecl.summary import EclSum

from ert._c_wrappers.enkf import ConfigKeys, EnsembleConfig
from ert._c_wrappers.enkf.enums import EnkfVarType, ErtImplType, GenDataFileType


def test_create():
    empty_ens_conf = EnsembleConfig()
    conf_from_dict = EnsembleConfig.from_dict({})

    assert empty_ens_conf == conf_from_dict
    assert conf_from_dict.get_refcase_file == None
    assert conf_from_dict.grid_file == None
    assert conf_from_dict.parameters == []

    assert "XYZ" not in conf_from_dict

    with pytest.raises(KeyError):
        _ = conf_from_dict["KEY"]


def test_ensemble_config_constructor(setup_case):
    res_config = setup_case("configuration_tests", "ensemble_config.ert")
    assert res_config.ensemble_config == EnsembleConfig.from_dict(
        config_dict={
            ConfigKeys.GEN_KW_TAG_FORMAT: "<%s>",
            ConfigKeys.GEN_DATA: [
                {
                    ConfigKeys.NAME: "SNAKE_OIL_OPR_DIFF",
                    ConfigKeys.INPUT_FORMAT: GenDataFileType.ASCII,
                    ConfigKeys.RESULT_FILE: "snake_oil_opr_diff_%d.txt",
                    ConfigKeys.REPORT_STEPS: [0, 1, 2, 199],
                },
                {
                    ConfigKeys.NAME: "SNAKE_OIL_GPR_DIFF",
                    ConfigKeys.INPUT_FORMAT: GenDataFileType.ASCII,
                    ConfigKeys.RESULT_FILE: "snake_oil_gpr_diff_%d.txt",
                    ConfigKeys.REPORT_STEPS: [199],
                },
            ],
            ConfigKeys.GEN_KW: [
                {
                    ConfigKeys.NAME: "MULTFLT",
                    ConfigKeys.TEMPLATE: "FAULT_TEMPLATE",
                    ConfigKeys.OUT_FILE: "MULTFLT.INC",
                    ConfigKeys.PARAMETER_FILE: "MULTFLT.TXT",
                    ConfigKeys.INIT_FILES: None,
                    ConfigKeys.FORWARD_INIT: False,
                }
            ],
            ConfigKeys.SURFACE_KEY: [
                {
                    ConfigKeys.NAME: "TOP",
                    ConfigKeys.INIT_FILES: "surface/small.irap",
                    ConfigKeys.OUT_FILE: "surface/small_out.irap",
                    ConfigKeys.BASE_SURFACE_KEY: ("surface/small.irap"),
                    ConfigKeys.FORWARD_INIT: False,
                }
            ],
            ConfigKeys.SUMMARY: [
                "WOPR:OP_1",
                "WOPR:PROD",
                "WOPT:PROD",
                "WWPR:PROD",
                "WWCT:PROD",
                "WWPT:PROD",
                "WBHP:PROD",
                "WWIR:INJ",
                "WWIT:INJ",
                "WBHP:INJ",
                "ROE:1",
            ],
            ConfigKeys.FIELD_KEY: [
                {
                    ConfigKeys.NAME: "PERMX",
                    ConfigKeys.VAR_TYPE: "PARAMETER",
                    ConfigKeys.INIT_FILES: "fields/permx%d.grdecl",
                    ConfigKeys.OUT_FILE: "permx.grdcel",
                    ConfigKeys.ENKF_INFILE: None,
                    ConfigKeys.INIT_TRANSFORM: None,
                    ConfigKeys.OUTPUT_TRANSFORM: None,
                    ConfigKeys.INPUT_TRANSFORM: None,
                    ConfigKeys.MIN_KEY: None,
                    ConfigKeys.MAX_KEY: None,
                    ConfigKeys.FORWARD_INIT: False,
                }
            ],
            ConfigKeys.SCHEDULE_PREDICTION_FILE: {
                ConfigKeys.TEMPLATE: "input/schedule.sch",
                ConfigKeys.INIT_FILES: "fields/permx%d.grdecl",
                ConfigKeys.PARAMETER_KEY: "MULTFLT.TXT",
            },
            ConfigKeys.GRID: "grid/CASE.EGRID",
            # ConfigKeys.REFCASE: "input/refcase/SNAKE_OIL_FIELD",
        },
    )


@pytest.mark.usefixtures("use_tmpdir")
def test_ensemble_config_fails_on_non_sensical_refcase_file():
    refcase_file = "CEST_PAS_UNE_REFCASE"
    refcase_file_content = """
_________________________________________     _____    ____________________
\\______   \\_   _____/\\_   _____/\\_   ___ \\   /  _  \\  /   _____/\\_   _____/
 |       _/|    __)_  |    __)  /    \\  \\/  /  /_\\  \\ \\_____  \\  |    __)_
 |    |   \\|        \\ |     \\   \\     \\____/    |    \\/        \\ |        \\
 |____|_  /_______  / \\___  /    \\______  /\\____|__  /_______  //_______  /
        \\/        \\/      \\/            \\/         \\/        \\/         \\/
"""
    with open(refcase_file, "w+", encoding="utf-8") as refcase_file_handler:
        refcase_file_handler.write(refcase_file_content)
    with pytest.raises(expected_exception=IOError, match=refcase_file):
        config_dict = {ConfigKeys.REFCASE: refcase_file}
        EnsembleConfig.from_dict(config_dict=config_dict)


@pytest.mark.usefixtures("use_tmpdir")
def test_ensemble_config_fails_on_non_sensical_grid_file():
    grid_file = "BRICKWALL"
    # NB: this is just silly ASCII content, not even close to a correct GRID file
    grid_file_content = """
_|___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|
___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|__
_|___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|
___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|__
_|___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|___|
"""
    with open(grid_file, "w+", encoding="utf-8") as grid_file_handler:
        grid_file_handler.write(grid_file_content)
    with pytest.raises(expected_exception=ValueError, match=grid_file):
        config_dict = {ConfigKeys.GRID: grid_file}
        EnsembleConfig.from_dict(config_dict=config_dict)


def test_ensemble_config_construct_refcase_and_grid(setup_case):
    setup_case("configuration_tests", "ensemble_config.ert")
    grid_file = "grid/CASE.EGRID"
    refcase_file = "input/refcase/SNAKE_OIL_FIELD"

    ec = EnsembleConfig.from_dict(
        config_dict={
            ConfigKeys.GRID: grid_file,
            ConfigKeys.REFCASE: refcase_file,
        },
    )

    assert isinstance(ec, EnsembleConfig)
    assert isinstance(ec.grid, EclGrid)
    assert isinstance(ec.refcase, EclSum)

    assert ec._grid_file == os.path.realpath(grid_file)
    assert ec._refcase_file == os.path.realpath(refcase_file)


def test_that_refcase_gets_correct_name(tmpdir):
    refcase_name = "MY_REFCASE"
    config_dict = {
        ConfigKeys.REFCASE: refcase_name,
    }

    with tmpdir.as_cwd():
        ecl_sum = EclSum.writer(refcase_name, datetime(2014, 9, 10), 10, 10, 10)
        ecl_sum.addVariable("FOPR", unit="SM3/DAY")
        t_step = ecl_sum.addTStep(2, sim_days=1)
        t_step["FOPR"] = 1
        ecl_sum.fwrite()

        ec = EnsembleConfig.from_dict(config_dict=config_dict)
        assert os.path.realpath(refcase_name) == ec.refcase.case


@pytest.mark.parametrize(
    "gen_data_str, expected",
    [
        pytest.param(
            "GDK RESULT_FILE:Results INPUT_FORMAT:ASCII REPORT_STEPS:10",
            None,
            id="RESULT_FILE missing %d in file name",
        ),
        pytest.param(
            "GDK RESULT_FILE:Results%d INPUT_FORMAT:ASCII",
            None,
            id="REPORT_STEPS missing",
        ),
        pytest.param(
            "GDK RESULT_FILE:Results%d INPUT_FORMAT:ASCIIX REPORT_STEPS:10",
            None,
            id="Unsupported INPUT_FORMAT",
        ),
        pytest.param(
            "GDK RESULT_FILE:Results%d REPORT_STEPS:10", None, id="Missing INPUT_FORMAT"
        ),
        pytest.param(
            "GDK RESULT_FILE:Results%d INPUT_FORMAT:ASCII REPORT_STEPS:10,20,30",
            "Valid",
            id="Valid case",
        ),
    ],
)
def test_gen_data_node(gen_data_str, expected):
    node = EnsembleConfig.gen_data_node(gen_data_str.split(" "))
    if expected is None:
        assert node == expected
    else:
        assert node is not None
        assert node.getVariableType() == EnkfVarType.DYNAMIC_RESULT
        assert node.getImplementationType() == ErtImplType.GEN_DATA
        assert node.getDataModelConfig().getNumReportStep() == 3
        assert node.getDataModelConfig().hasReportStep(10)
        assert node.getDataModelConfig().hasReportStep(20)
        assert node.getDataModelConfig().hasReportStep(30)
        assert not node.getDataModelConfig().hasReportStep(32)
        assert node.get_init_file_fmt() is None
        assert node.get_enkf_outfile() is None
        assert node.getDataModelConfig().getInputFormat() == GenDataFileType.ASCII


def test_get_surface_node(setup_case, caplog):
    _ = setup_case("configuration_tests", "ensemble_config.ert")
    surface_str = "TOP"
    with pytest.raises(ValueError):
        EnsembleConfig.get_surface_node(surface_str.split(" "))

    surface_in = "surface/small.irap"
    surface_out = "surface/small_out.irap"
    # add init file
    surface_str += f" INIT_FILES:{surface_in}"

    with pytest.raises(ValueError):
        EnsembleConfig.get_surface_node(surface_str.split(" "))

    # add output file
    surface_str += f" OUTPUT_FILE:{surface_out}"
    with pytest.raises(ValueError):
        EnsembleConfig.get_surface_node(surface_str.split(" "))

    # add base surface
    surface_str += f" BASE_SURFACE:{surface_in}"

    surface_node = EnsembleConfig.get_surface_node(surface_str.split(" "))

    assert surface_node is not None

    assert surface_node.get_init_file_fmt() == surface_in
    assert surface_node.get_enkf_outfile() == surface_out
    assert not surface_node.getUseForwardInit()

    surface_str += " FORWARD_INIT:TRUE"
    surface_node = EnsembleConfig.get_surface_node(surface_str.split(" "))
    assert surface_node.getUseForwardInit()
