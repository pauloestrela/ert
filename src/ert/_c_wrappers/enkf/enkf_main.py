import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Mapping, Sequence, Union

import numpy as np

from ert import _clib
from ert._c_wrappers.analysis.configuration import UpdateConfiguration
from ert._c_wrappers.enkf import EnkfFs
from ert._c_wrappers.enkf.analysis_config import AnalysisConfig
from ert._c_wrappers.enkf.data import EnkfNode
from ert._c_wrappers.enkf.enkf_fs_manager import FileSystemManager
from ert._c_wrappers.enkf.enkf_obs import EnkfObs
from ert._c_wrappers.enkf.ensemble_config import EnsembleConfig
from ert._c_wrappers.enkf.enums import RealizationStateEnum
from ert._c_wrappers.enkf.enums.enkf_var_type_enum import EnkfVarType
from ert._c_wrappers.enkf.enums.ert_impl_type_enum import ErtImplType
from ert._c_wrappers.enkf.ert_run_context import RunContext
from ert._c_wrappers.enkf.ert_workflow_list import ErtWorkflowList
from ert._c_wrappers.enkf.model_config import ModelConfig
from ert._c_wrappers.enkf.node_id import NodeId
from ert._c_wrappers.enkf.queue_config import QueueConfig
from ert._c_wrappers.enkf.runpaths import Runpaths
from ert._c_wrappers.util.substitution_list import SubstitutionList
from ert._clib.state_map import STATE_LOAD_FAILURE, STATE_UNDEFINED

if TYPE_CHECKING:
    from ert._c_wrappers.enkf.res_config import ResConfig


logger = logging.getLogger(__name__)


def _backup_if_existing(path: Path) -> None:
    if not path.exists():
        return
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%SZ")
    new_path = path.parent / f"{path.name}_backup_{timestamp}"
    path.rename(new_path)


def _value_export_txt(
    run_path: str, export_base_name: str, values: Mapping[str, Mapping[str, float]]
) -> None:
    path = Path(run_path) / f"{export_base_name}.txt"
    _backup_if_existing(path)

    if len(values) == 0:
        return

    with path.open("w") as f:
        for key, param_map in values.items():
            for param, value in param_map.items():
                print(f"{key}:{param} {value:g}", file=f)


def _value_export_json(
    run_path: str, export_base_name: str, values: Mapping[str, Mapping[str, float]]
) -> None:
    path = Path(run_path) / f"{export_base_name}.json"
    _backup_if_existing(path)

    if len(values) == 0:
        return

    # Hierarchical
    json_out = {key: dict(param_map.items()) for key, param_map in values.items()}

    # Composite
    json_out.update(
        {
            f"{key}:{param}": value
            for key, param_map in values.items()
            for param, value in param_map.items()
        }
    )

    # Disallow NaN from being written: ERT produces the parameters and the only
    # way for the output to be NaN is if the input is invalid or if the sampling
    # function is buggy. Either way, that would be a bug and we can report it by
    # having json throw an error.
    json.dump(
        json_out, path.open("w"), allow_nan=False, indent=0, separators=(", ", " : ")
    )


def _generate_parameter_files(
    ens_config: "EnsembleConfig",
    export_base_name: str,
    run_path: str,
    iens: int,
    fs: "EnkfFs",
) -> None:
    """
    Generate parameter files that are placed in each runtime directory for
    forward-model jobs to consume.

    Args:
        ens_config: Configuration which contains the parameter nodes for this
            ensemble run.
        export_base_name: Base name for the GEN_KW parameters file. Ie. the
            `parameters` in `parameters.json`.
        run_path: Path to the runtime directory
        iens: Realisation index
        fs: EnkfFs from which to load parameter data
    """
    exports = {}
    for key in ens_config.getKeylistFromVarType(
        EnkfVarType.PARAMETER + EnkfVarType.EXT_PARAMETER
    ):
        node = ens_config[key]
        enkf_node = EnkfNode(node)
        node_id = NodeId(report_step=0, iens=iens)

        if node.getUseForwardInit() and not enkf_node.has_data(fs, node_id):
            continue
        enkf_node.load(fs, node_id)

        node_eclfile = node.get_enkf_outfile()

        type_ = enkf_node.getImplType()
        if type_ == ErtImplType.FIELD:
            _clib.field.generate_parameter_file(enkf_node, run_path, node_eclfile)
        elif type_ == ErtImplType.SURFACE:
            _clib.surface.generate_parameter_file(enkf_node, run_path, node_eclfile)
        elif type_ == ErtImplType.EXT_PARAM:
            _clib.ext_param.generate_parameter_file(enkf_node, run_path, node_eclfile)
        elif type_ == ErtImplType.GEN_KW:
            _clib.gen_kw.generate_parameter_file(
                enkf_node, run_path, node_eclfile, exports
            )
        else:
            raise NotImplementedError

    _value_export_txt(run_path, export_base_name, exports)
    _value_export_json(run_path, export_base_name, exports)


class EnKFMain:
    def __init__(self, config: "ResConfig", read_only: bool = False):
        self.res_config = config
        self.update_snapshots = {}
        self._update_configuration = None
        if config is None:
            raise TypeError(
                "Failed to construct EnKFMain instance due to invalid res_config."
            )

        self._observations = EnkfObs(
            config.model_config.history_source,
            config.model_config.time_map,
            config.ensemble_config.grid,
            config.ensemble_config.refcase,
            config.ensemble_config,
        )
        if config.model_config.obs_config_file:
            if self._observations.error:
                raise ValueError(
                    f"Incorrect observations file: "
                    f"{config.model_config.obs_config_file}"
                    f": {self._observations.error}"
                )
            self._observations.load(
                config.model_config.obs_config_file,
                config.analysis_config.get_std_cutoff(),
            )
        self._ensemble_size = self.res_config.model_config.num_realizations
        self._runpaths = Runpaths(
            self.resConfig().preferred_job_fmt(),
            self.getModelConfig().runpath_format_string,
            Path(config.runpath_file),
            self.get_context().substitute_real_iter,
        )
        run_path = self.runpaths.format_runpath()
        jobname = self.runpaths.format_job_name()
        self.addDataKW("<RUNPATH>", run_path)
        self.addDataKW("<ECL_BASE>", jobname)
        self.addDataKW("<ECLBASE>", jobname)

        # Initialize storage
        ens_path = Path(config.model_config.ens_path)
        self.storage_manager = FileSystemManager(
            5,
            ens_path,
            config.ensemble_config,
            self.getEnsembleSize(),
            read_only=read_only,
        )
        self.switchFileSystem(self.storage_manager.active_case)

        # Set up RNG
        config_seed = self.resConfig().random_seed
        if config_seed is None:
            seed_seq = np.random.SeedSequence()
            logger.info(
                "To repeat this experiment, "
                "add the following random seed to your config file:"
            )
            logger.info(f"RANDOM_SEED {seed_seq.entropy}")
        else:
            seed: Union[int, Sequence[int]]
            try:
                seed = int(config_seed)
            except ValueError:
                seed = [ord(x) for x in config_seed]
            seed_seq = np.random.SeedSequence(seed)
        self._global_seed = seed_seq
        self._shared_rng = np.random.default_rng(seed_seq)

    @property
    def update_configuration(self) -> UpdateConfiguration:
        if not self._update_configuration:
            global_update_step = [
                {
                    "name": "ALL_ACTIVE",
                    "observations": self._observation_keys,
                    "parameters": self._parameter_keys,
                }
            ]
            self._update_configuration = UpdateConfiguration(
                update_steps=global_update_step
            )
        return self._update_configuration

    @update_configuration.setter
    def update_configuration(self, user_config: Any):
        config = UpdateConfiguration(update_steps=user_config)
        config.context_validate(self._observation_keys, self._parameter_keys)
        self._update_configuration = config

    @property
    def _observation_keys(self):
        return list(self._observations.getMatchingKeys("*"))

    @property
    def _parameter_keys(self):
        return self.ensembleConfig().parameters

    @property
    def runpaths(self):
        return self._runpaths

    @property
    def runpath_list_filename(self):
        return self._runpaths.runpath_list_filename

    def getEnkfFsManager(self) -> "EnKFMain":
        return self

    def getLocalConfig(self) -> "UpdateConfiguration":
        return self.update_configuration

    def loadFromForwardModel(
        self, realization: List[bool], iteration: int, fs: "EnkfFs"
    ) -> int:
        """Returns the number of loaded realizations"""
        run_context = self.create_ensemble_experiment_run_context(
            active_mask=realization, iteration=iteration, source_filesystem=fs
        )
        nr_loaded = fs.load_from_run_path(
            self.getEnsembleSize(),
            self.ensembleConfig(),
            self.getHistoryLength(),
            run_context.run_args,
            run_context.mask,
        )
        fs.sync()
        return nr_loaded

    def create_ensemble_experiment_run_context(
        self, iteration: int, active_mask: List[bool] = None, source_filesystem=None
    ) -> RunContext:
        """Creates an ensemble experiment run context
        :param fs: The source filesystem, defaults to
            getEnkfFsManager().getCurrentFileSystem().
        :param active_mask: Whether a realization is active or not,
            defaults to all active.
        """
        return self._create_run_context(
            iteration=iteration,
            active_mask=active_mask,
            source_filesystem=source_filesystem,
            target_fs=None,
        )

    def create_ensemble_smoother_run_context(
        self,
        iteration: int,
        target_filesystem,
        active_mask: List[bool] = None,
        source_filesystem=None,
    ) -> RunContext:
        """Creates an ensemble smoother run context
        :param fs: The source filesystem, defaults to
            getEnkfFsManager().getCurrentFileSystem().
        """
        return self._create_run_context(
            iteration=iteration,
            active_mask=active_mask,
            source_filesystem=source_filesystem,
            target_fs=target_filesystem,
        )

    def _create_run_context(
        self,
        iteration: int = 0,
        active_mask: List[bool] = None,
        source_filesystem=None,
        target_fs=None,
    ) -> RunContext:
        if active_mask is None:
            active_mask = [True] * self.getEnsembleSize()
        if source_filesystem is None:
            source_filesystem = self.getCurrentFileSystem()

        realizations = list(range(len(active_mask)))
        paths = self.runpaths.get_paths(realizations, iteration)
        jobnames = self.runpaths.get_jobnames(realizations, iteration)

        return RunContext(
            sim_fs=source_filesystem,
            target_fs=target_fs,
            mask=active_mask,
            iteration=iteration,
            paths=paths,
            jobnames=jobnames,
        )

    def write_runpath_list(self, iterations: List[int], realizations: List[int]):
        self.runpaths.write_runpath_list(iterations, realizations)

    def get_queue_config(self) -> QueueConfig:
        return self.resConfig().queue_config

    def get_num_cpu(self) -> int:
        return self.res_config.preferred_num_cpu()

    def set_geo_id(self, geo_id: str, realization: int, iteration: int):
        self.addDataKW(f"<GEO_ID_{realization}_{iteration}>", str(geo_id))

    def __repr__(self):
        return f"EnKFMain(size: {self.getEnsembleSize()}, config: {self.res_config})"

    def getEnsembleSize(self) -> int:
        return self._ensemble_size

    def ensembleConfig(self) -> EnsembleConfig:
        return self.resConfig().ensemble_config

    def analysisConfig(self) -> AnalysisConfig:
        return self.resConfig().analysis_config

    def getModelConfig(self) -> ModelConfig:
        return self.res_config.model_config

    def resConfig(self) -> "ResConfig":
        return self.res_config

    def get_context(self) -> SubstitutionList:
        return self.res_config.substitution_list

    def addDataKW(self, key: str, value: str) -> None:
        self.get_context().addItem(key, value)

    def getObservations(self) -> EnkfObs:
        return self._observations

    def have_observations(self) -> bool:
        return len(self._observations) > 0

    def getHistoryLength(self) -> int:
        return self.resConfig().model_config.get_history_num_steps()

    def getWorkflowList(self) -> ErtWorkflowList:
        return self.resConfig().ert_workflow_list

    def sample_prior(
        self,
        storage: "EnkfFs",
        active_realizations: List[int],
        parameters: List[str] = None,
    ) -> None:
        """This function is responsible for getting the prior into storage,
        in the case of GEN_KW we sample the data and store it, and if INIT_FILES
        are used without FORWARD_INIT we load files and store them. If FORWARD_INIT
        is set the state is set to INITIALIZED, but no parameters are saved to storage
        until after the forward model has completed.
        """
        # pylint: disable=too-many-nested-blocks
        # (this is a real code smell that we mute for now)
        if parameters is None:
            parameters = self._parameter_keys
        state_map = storage.getStateMap()

        for parameter in parameters:
            config_node = self.ensembleConfig().getNode(parameter)
            enkf_node = EnkfNode(config_node)
            if config_node.getUseForwardInit():
                continue
            impl_type = enkf_node.getImplType()
            if impl_type == ErtImplType.GEN_KW:
                gen_kw_node = enkf_node.asGenKw()
                keys = [val[0] for val in gen_kw_node.items()]
                if config_node.get_init_file_fmt():
                    parameter_values = gen_kw_node.values_from_files(
                        active_realizations,
                        config_node.get_init_file_fmt(),
                        keys,
                    )
                else:
                    parameter_values = gen_kw_node.sample_values(
                        parameter,
                        keys,
                        str(self._global_seed.entropy),
                        active_realizations,
                        self.getEnsembleSize(),
                    )
                storage.save_parameters(
                    config_node,
                    active_realizations,
                    _clib.update.Parameter(parameter),
                    parameter_values,
                )
            else:
                for realization_nr in active_realizations:
                    _clib.enkf_state.state_initialize(
                        enkf_node,
                        storage,
                        realization_nr,
                    )
        for realization_nr in active_realizations:
            if state_map[realization_nr] in [STATE_UNDEFINED, STATE_LOAD_FAILURE]:
                state_map[realization_nr] = RealizationStateEnum.STATE_INITIALIZED
        storage.sync()

    def rng(self) -> np.random.Generator:
        "Will return the random number generator used for updates."
        return self._shared_rng

    def getFileSystem(self, case_name: str) -> "EnkfFs":
        try:
            case = self.storage_manager[case_name]
        except KeyError:
            case = self.storage_manager.add_case(case_name)
        if self.res_config.ensemble_config.refcase:
            time_map = case.getTimeMap()
            time_map.attach_refcase(self.res_config.ensemble_config.refcase)
        return case

    def getCurrentFileSystem(self) -> "EnkfFs":
        """Returns the currently selected file system"""
        return self.getFileSystem(self.storage_manager.active_case)

    def switchFileSystem(self, case_name: str) -> None:
        if isinstance(case_name, EnkfFs):
            case_name = case_name.case_name
        if case_name not in self.storage_manager.cases:
            raise KeyError(
                f"Unknown case: {case_name}, valid: {self.storage_manager.cases}"
            )
        self.addDataKW("<ERT-CASE>", case_name)
        self.addDataKW("<ERTCASE>", case_name)
        self.storage_manager.active_case = case_name
        (Path(self.getModelConfig().ens_path) / "current_case").write_text(case_name)

    def createRunPath(self, run_context: RunContext) -> None:
        for iens, run_arg in enumerate(run_context):
            if run_context.is_active(iens):
                os.makedirs(
                    run_arg.runpath,
                    exist_ok=True,
                )

                for source_file, target_file in self.res_config.ert_templates:
                    target_file = self.get_context().substitute_real_iter(
                        target_file, run_arg.iens, run_context.iteration
                    )
                    result = self.get_context().substitute_real_iter(
                        Path(source_file).read_text("utf-8"),
                        run_arg.iens,
                        run_context.iteration,
                    )
                    target = Path(run_arg.runpath) / target_file
                    if not target.parent.exists():
                        os.makedirs(
                            target.parent,
                            exist_ok=True,
                        )
                    target.write_text(result)

                res_config = self.resConfig()
                model_config = res_config.model_config
                _generate_parameter_files(
                    res_config.ensemble_config,
                    model_config.gen_kw_export_name,
                    run_arg.runpath,
                    run_arg.iens,
                    run_arg.sim_fs,
                )
                res_config.forward_model.formatted_fprintf(
                    run_arg.get_run_id(),
                    run_arg.runpath,
                    model_config.data_root,
                    iens,
                    run_context.iteration,
                    self.get_context(),
                    res_config.env_vars,
                )

        active_list = [
            run_context[i] for i in range(len(run_context)) if run_context.is_active(i)
        ]
        iterations = sorted({runarg.iter_id for runarg in active_list})
        realizations = sorted({runarg.iens for runarg in active_list})

        self.runpaths.write_runpath_list(iterations, realizations)

    def runWorkflows(self, runtime: int) -> None:
        workflow_list = self.getWorkflowList()
        for workflow in workflow_list.get_workflows_hooked_at(runtime):
            workflow.run(self, context=self.res_config.substitution_list)
