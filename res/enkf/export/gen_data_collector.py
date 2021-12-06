import numpy
from ecl.util.util import IntVector
from pandas import DataFrame

from res.enkf import EnKFMain
from res.enkf.enums import RealizationStateEnum
from res.enkf.plot_data import EnsemblePlotGenData


class GenDataCollector(object):
    @staticmethod
    def loadGenData(ert: EnKFMain, case_name, key, report_step, realization_index=None):
        """@type ert: EnKFMain
        @type case_name: str
        @type key: str
        @type report_step: int
        @rtype: DataFrame

        In the returned dataframe the realisation index runs along the
        rows, and the gen_data element index runs vertically along the
        columns.
        """
        fs = ert.getEnkfFsManager().getFileSystem(case_name)
        realizations = fs.realizationList(RealizationStateEnum.STATE_HAS_DATA)
        if realization_index:
            if realization_index not in realizations:
                raise IndexError(f"No such realization {realization_index}")
            realizations = IntVector.active_list(str(realization_index))

        config_node = ert.ensembleConfig().getNode(key)
        gen_data_config = config_node.getModelConfig()

        ensemble_data = EnsemblePlotGenData(config_node, fs, report_step)
        # The data size and active can only be inferred *after* the EnsembleLoad.
        data_size = gen_data_config.getDataSize(report_step)
        active_mask = gen_data_config.getActiveMask()

        data_array = numpy.empty(
            shape=(data_size, len(realizations)), dtype=numpy.float64
        )
        data_array.fill(numpy.nan)
        for realization_index, realization_number in enumerate(realizations):
            realization_vector = ensemble_data[realization_number]
            if (
                len(realization_vector) > 0
            ):  # Must check because of a bug changing between different case with different states
                for data_index in range(data_size):
                    if active_mask[data_index]:
                        value = realization_vector[data_index]
                        data_array[data_index][realization_index] = value

        realizations = numpy.array(realizations)
        return DataFrame(data=data_array, columns=realizations)
