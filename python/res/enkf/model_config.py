#  Copyright (C) 2012  Equinor ASA, Norway.
#
#  The file 'model_config.py' is part of ERT - Ensemble based Reservoir Tool.
#
#  ERT is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  ERT is distributed in the hope that it will be useful, but WITHOUT ANY
#  WARRANTY; without even the implied warranty of MERCHANTABILITY or
#  FITNESS FOR A PARTICULAR PURPOSE.
#
#  See the GNU General Public License at <http://www.gnu.org/licenses/gpl.html>
#  for more details.
from cwrap import BaseCClass

from ecl.summary import EclSum

from res import ResPrototype
from res.job_queue import ForwardModel
from res.sched import HistorySourceEnum
from res.util import PathFormat


class ModelConfig(BaseCClass):
    TYPE_NAME = "model_config"

    _alloc                       = ResPrototype("void*  model_config_alloc( config_content, char*, ext_joblist, int, ecl_sum)", bind=False)
    _free                        = ResPrototype("void  model_config_free( model_config )")
    _get_forward_model           = ResPrototype("forward_model_ref model_config_get_forward_model(model_config)")
    _get_max_internal_submit     = ResPrototype("int   model_config_get_max_internal_submit(model_config)")
    _set_max_internal_submit     = ResPrototype("void  model_config_set_max_internal_submit(model_config, int)")
    _get_runpath_as_char         = ResPrototype("char* model_config_get_runpath_as_char(model_config)")
    _select_runpath              = ResPrototype("bool  model_config_select_runpath(model_config, char*)")
    _set_runpath                 = ResPrototype("void  model_config_set_runpath(model_config, char*)")
    _get_enspath                 = ResPrototype("char* model_config_get_enspath(model_config)")
    _get_fs_type                 = ResPrototype("enkf_fs_type_enum model_config_get_dbase_type(model_config)")
    _get_history                 = ResPrototype("history_ref model_config_get_history(model_config)")
    _get_history_source          = ResPrototype("history_source_enum model_config_get_history_source(model_config)")
    _select_history              = ResPrototype("bool  model_config_select_history(model_config, history_source_enum, ecl_sum)")
    _has_history                 = ResPrototype("bool  model_config_has_history(model_config)")
    _gen_kw_export_name          = ResPrototype("char* model_config_get_gen_kw_export_name(model_config)")
    _runpath_requires_iterations = ResPrototype("bool  model_config_runpath_requires_iter(model_config)")
    _get_jobname_fmt             = ResPrototype("char* model_config_get_jobname_fmt(model_config)")
    _get_runpath_fmt             = ResPrototype("path_fmt_ref model_config_get_runpath_fmt(model_config)")
    _get_num_realizations        = ResPrototype("int model_config_get_num_realizations(model_config)")
    _get_obs_config_file         = ResPrototype("char* model_config_get_obs_config_file(model_config)")
    _get_data_root               = ResPrototype("char* model_config_get_data_root(model_config)")
    _set_data_root               = ResPrototype("void model_config_get_data_root(model_config, char*)")

    def __init__(self, config_content, data_root, joblist, last_history_restart, refcase, is_reference=False):
        c_ptr = self._alloc(config_content, data_root, joblist, last_history_restart, refcase)

        if c_ptr is None:
            raise ValueError('Failed to construct SiteConfig instance.')

        super(ModelConfig, self).__init__(c_ptr, is_reference=is_reference)

    def hasHistory(self):
        return self._has_history()

    def get_history_source(self):
        """ @rtype: HistorySourceEnum """
        return self._get_history_source()

    def set_history_source(self, history_source, sched_file, refcase):
        """
         @type history_source: HistorySourceEnum
         @type sched_file: SchedFile
         @type refcase: EclSum
         @rtype: bool
        """
        assert isinstance(history_source, HistorySourceEnum)
        assert isinstance(sched_file, SchedFile)
        assert isinstance(refcase, EclSum)
        return self._select_history(history_source, sched_file, refcase)


    def get_max_internal_submit(self):
        """ @rtype: int """
        return self._get_max_internal_submit()

    def set_max_internal_submit(self, max_value):
        self._get_max_internal_submit(max_value)

    def getForwardModel(self):
        """ @rtype: ForwardModel """
        return self._get_forward_model().setParent(self)


    def getRunpathAsString(self):
        """ @rtype: str """
        return self._get_runpath_as_char()

    def selectRunpath(self, path_key):
        """ @rtype: bool """
        return self._select_runpath(path_key)

    def setRunpath(self, path_format):
        self._set_runpath(path_format)

    def free(self):
        self._free()

    def getFSType(self):
        return self._get_fs_type()

    def getGenKWExportName(self):
        """ @rtype: str """
        return self._gen_kw_export_name( )

    def runpathRequiresIterations(self):
        """ @rtype: bool """
        return self._runpath_requires_iterations()

    def getJobnameFormat(self):
        """ @rtype: str """
        return self._get_jobname_fmt()

    @property
    def obs_config_file(self):
        return self._get_obs_config_file()

    def getEnspath(self):
        """ @rtype: str """
        return self._get_enspath()

    def getRunpathFormat(self):
        """ @rtype: PathFormat """
        return self._get_runpath_fmt()

    @property
    def num_realizations(self):
        return self._get_num_realizations()

    def data_root(self):
        return self._get_data_root( )

    def set_data_root(self, data_root):
         self._set_data_root( data_root )
