#include <filesystem>

#include <stdio.h>
#include <stdlib.h>
#include <vector>

#include <ert/enkf/enkf_node.hpp>
#include <ert/res_util/file_utils.hpp>
#include <ert/util/util.h>

#include <ert/enkf/enkf_macros.hpp>
#include <ert/enkf/enkf_util.hpp>
#include <ert/enkf/ext_param.hpp>
#include <ert/enkf/ext_param_config.hpp>
#include <ert/python.hpp>

namespace fs = std::filesystem;

GET_DATA_SIZE_HEADER(ext_param);

struct ext_param_struct {
    const ext_param_config_type *config;
    std::vector<std::vector<double>> data;
};

void ext_param_free(ext_param_type *ext_param) { delete ext_param; }

ext_param_type *ext_param_alloc(const ext_param_config_type *config) {
    ext_param_type *ext_param = new ext_param_type();
    ext_param->config = config;
    ext_param->data.resize(ext_param_config_get_data_size(config));
    for (int i = 0; i < ext_param->data.size(); i++) {
        auto const suffix_count =
            ext_param_config_ikey_get_suffix_count(ext_param->config, i);
        ext_param->data[i].resize(std::max(suffix_count, 1));
    }
    return ext_param;
}

bool ext_param_key_set(ext_param_type *param, const char *key, double value) {
    int index = ext_param_config_get_key_index(param->config, key);
    if (index < 0)
        return false;

    param->data[index][0] = value;
    return true;
}

bool ext_param_key_suffix_set(ext_param_type *param, const char *key,
                              const char *suffix, double value) {
    int index = ext_param_config_get_key_index(param->config, key);
    if (index < 0)
        return false;

    int suffix_index =
        ext_param_config_ikey_get_suffix_index(param->config, index, suffix);
    if (suffix_index < 0)
        return false;

    param->data[index][suffix_index] = value;
    return true;
}

double ext_param_key_get(const ext_param_type *param, const char *key) {
    int index = ext_param_config_get_key_index(param->config, key);
    if (index < 0)
        util_abort("%s: invalid key:%s \n", __func__, key);

    return param->data[index].front();
}

double ext_param_key_suffix_get(const ext_param_type *param, const char *key,
                                const char *suffix) {
    int ikey = ext_param_config_get_key_index(param->config, key);
    if (ikey < 0)
        util_abort("%s: invalid key:%s \n", __func__, key);

    int isuffix =
        ext_param_config_ikey_get_suffix_index(param->config, ikey, suffix);
    if (isuffix < 0)
        util_abort("%s: invalid suffix:%s \n", __func__, suffix);

    return param->data[ikey][isuffix];
}

bool ext_param_iset(ext_param_type *param, int index, double value) {
    if (index >= param->data.size())
        return false;

    if (index < 0)
        return false;

    param->data[index].front() = value;
    return true;
}

bool ext_param_iiset(ext_param_type *param, int ikey, int isuffix,
                     double value) {
    if (ikey >= param->data.size())
        return false;

    if (ikey < 0)
        return false;

    if (isuffix >= param->data[ikey].size())
        return false;

    if (isuffix < 0)
        return false;

    param->data[ikey][isuffix] = value;
    return true;
}

double ext_param_iget(const ext_param_type *param, int index) {
    if (index >= param->data.size())
        util_abort("%s: invalid index:%d - range: [0,%d) \n", __func__, index,
                   param->data.size());

    if (index < 0)
        util_abort("%s: invalid index:%d - range: [0,%d) \n", __func__, index,
                   param->data.size());

    return param->data[index].front();
}

double ext_param_iiget(const ext_param_type *param, int ikey, int isuffix) {
    if (ikey >= param->data.size())
        util_abort("%s: invalid key index:%d - range: [0,%d) \n", __func__,
                   ikey, param->data.size());

    if (ikey < 0)
        util_abort("%s: invalid key index:%d - range: [0,%d) \n", __func__,
                   ikey, param->data.size());

    if (isuffix >= param->data[ikey].size())
        util_abort("%s: invalid suffix index:%d - range: [0,%d) \n", __func__,
                   isuffix, param->data[ikey].size());

    if (isuffix < 0)
        util_abort("%s: invalid suffix index:%d - range: [0,%d) \n", __func__,
                   isuffix, param->data[ikey].size());

    return param->data[ikey][isuffix];
}

void ext_param_json_export(const ext_param_type *ext_param,
                           const char *json_file) {
    auto stream = mkdir_fopen(fs::path(json_file), "w");
    fprintf(stream, "{\n");
    for (int ikey = 0; ikey < ext_param->data.size(); ikey++) {
        auto const key = ext_param_config_iget_key(ext_param->config, ikey);
        auto const suffix_count =
            ext_param_config_ikey_get_suffix_count(ext_param->config, ikey);

        fprintf(stream, "\"%s\" : ", key); // print the key
        if (suffix_count == 0) {           // no suffixes, just print the value
            auto const value = ext_param->data[ikey].front();
            fprintf(stream, "%g", value);
        } else { // print suffixes and corresponding values
            fprintf(stream, "{\n");
            for (int isuffix = 0; isuffix < suffix_count; ++isuffix) {
                auto const suffix = ext_param_config_ikey_iget_suffix(
                    ext_param->config, ikey, isuffix);
                auto const value = ext_param->data[ikey][isuffix];
                fprintf(stream, "    \"%s\" : %g", suffix, value);
                fprintf(stream, isuffix == suffix_count - 1 ? "\n" : ",\n");
            }
            fprintf(stream, "}");
        }

        if (ikey < (ext_param->data.size() - 1))
            fprintf(stream, ",\n");
        else
            fprintf(stream, "\n");
    }
    fprintf(stream, "}\n");
    fclose(stream);
}

void ext_param_ecl_write(const ext_param_type *ext_param, const char *run_path,
                         const char *base_file) {
    char *target_file;

    if (run_path)
        target_file = util_alloc_filename(run_path, base_file, NULL);
    else
        target_file = util_alloc_string_copy(base_file);

    ext_param_json_export(ext_param, target_file);
    free(target_file);
}

bool ext_param_write_to_buffer(const ext_param_type *ext_param,
                               buffer_type *buffer, int report_step) {
    buffer_fwrite_int(buffer, EXT_PARAM);
    for (auto const &d : ext_param->data) {
        buffer_fwrite(buffer, d.data(), sizeof *(d.data()), d.size());
    }
    return true;
}

void ext_param_read_from_buffer(ext_param_type *ext_param, buffer_type *buffer,
                                enkf_fs_type *fs, int report_step) {
    enkf_util_assert_buffer_type(buffer, EXT_PARAM);
    for (auto &d : ext_param->data) {
        buffer_fread(buffer, d.data(), sizeof *(d.data()), d.size());
    }
}

ext_param_config_type const *ext_param_get_config(const ext_param_type *param) {
    return param->config;
}

VOID_ALLOC(ext_param)
VOID_FREE(ext_param)
VOID_WRITE_TO_BUFFER(ext_param)
VOID_READ_FROM_BUFFER(ext_param)

ERT_CLIB_SUBMODULE("ext_param", m) {
    m.def("generate_parameter_file",
          [](Cwrap<enkf_node_type> enkf_node, const std::string &run_path,
             const std::optional<std::string> &opt_file) {
              if (enkf_node_get_impl_type(enkf_node) != EXT_PARAM)
                  throw py::value_error{"EnkfNode must be of type EXT_PARAM"};

              auto file = opt_file ? opt_file->c_str() : nullptr;
              ext_param_ecl_write(
                  static_cast<ext_param_type *>(enkf_node_value_ptr(enkf_node)),
                  run_path.c_str(), file);
          });
}
