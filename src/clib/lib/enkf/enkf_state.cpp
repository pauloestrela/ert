#include <stdexcept>
#include <string>
#include <vector>

#include <ert/python.hpp>
#include <ert/res_util/subst_list.hpp>
#include <ert/util/hash.h>

#include <ert/ecl/ecl_kw.h>
#include <ert/ecl/ecl_sum.h>

#include "ert/enkf/ensemble_config.hpp"

#include <ert/enkf/enkf_defaults.hpp>
#include <ert/enkf/enkf_node.hpp>
#include <ert/enkf/enkf_state.hpp>
#include <ert/enkf/gen_data.hpp>
#include <ert/enkf/summary.hpp>
#include <ert/logging.hpp>
#include <ert/res_util/memory.hpp>

static auto logger = ert::get_logger("enkf");

ecl_sum_type *load_ecl_sum(const std::string run_path,
                           const std::string eclbase) {
    ecl_sum_type *summary = NULL;

    char *header_file = ecl_util_alloc_exfilename(
        run_path.c_str(), eclbase.c_str(), ECL_SUMMARY_HEADER_FILE,
        DEFAULT_FORMATTED, -1);
    char *unified_file = ecl_util_alloc_exfilename(
        run_path.c_str(), eclbase.c_str(), ECL_UNIFIED_SUMMARY_FILE,
        DEFAULT_FORMATTED, -1);
    stringlist_type *data_files = stringlist_alloc_new();
    if ((unified_file != NULL) && (header_file != NULL)) {
        stringlist_append_copy(data_files, unified_file);

        bool include_restart = false;

        /*
             * Setting this flag causes summary-data to be loaded by
             * ecl::unsmry_loader which is "horribly slow" according
             * to comments in the code. The motivation for introducing
             * this mode was at some point to use less memory, but
             * computers nowadays should not have a problem with that.
             *
             * For comments, reasoning and discussions, please refer to
             * https://github.com/equinor/ert/issues/2873
             *   and
             * https://github.com/equinor/ert/issues/2972
             */
        bool lazy_load = false;
        if (std::getenv("ERT_LAZY_LOAD_SUMMARYDATA"))
            lazy_load = true;

        {
            ert::utils::scoped_memory_logger memlogger(
                logger, fmt::format("lazy={}", lazy_load));

            int file_options = 0;
            summary = ecl_sum_fread_alloc(
                header_file, data_files, SUMMARY_KEY_JOIN_STRING,
                include_restart, lazy_load, file_options);
        }
    } else {
        stringlist_free(data_files);
        throw std::invalid_argument(
            "Could not find SUMMARY file or using non unified SUMMARY file");
    }
    stringlist_free(data_files);
    free(header_file);
    free(unified_file);
    return summary;
}

/**
 * Check if there are summary keys in the ensemble config that is not found in
 * Eclipse. If this is the case, AND we have observations for this key, we have
 * a problem. Otherwise, just print a message to the log.
 */
static std::pair<fw_load_status, std::string>
enkf_state_check_for_missing_eclipse_summary_data(
    const ensemble_config_type *ens_config,
    const summary_key_matcher_type *matcher, const ecl_smspec_type *smspec,
    const int iens) {
    stringlist_type *keys = summary_key_matcher_get_keys(matcher);
    std::pair<fw_load_status, std::string> result = {LOAD_SUCCESSFUL, ""};
    std::vector<std::string> missing_keys;
    for (int i = 0; i < stringlist_get_size(keys); i++) {

        const char *key = stringlist_iget(keys, i);

        if (ecl_smspec_has_general_var(smspec, key) ||
            !summary_key_matcher_summary_key_is_required(matcher, key))
            continue;

        if (!ensemble_config_has_key(ens_config, key))
            continue;

        const enkf_config_node_type *config_node =
            ensemble_config_get_node(ens_config, key);

        if (stringlist_get_size(config_node->obs_keys) == 0) {
            logger->info(
                "[{:03d}:----] Unable to find Eclipse data for summary key: "
                "{}, but have no observations either, so will continue.",
                iens, key);
        } else {
            missing_keys.push_back(key);
        }
    }
    stringlist_free(keys);
    if (!missing_keys.empty())
        return {
            LOAD_FAILURE,
            fmt::format("Missing Eclipse data for required summary keys: {}",
                        fmt::join(missing_keys, ", "))};
    return result;
}

static std::pair<fw_load_status, std::string>
enkf_state_internalize_dynamic_eclipse_results(
    ensemble_config_type *ens_config, const ecl_sum_type *summary,
    const summary_key_matcher_type *matcher, enkf_fs_type *sim_fs,
    const int iens) {

    auto &time_map = enkf_fs_get_time_map(sim_fs);
    auto status = time_map.summary_update(summary);
    if (!status.empty()) {
        // Something has gone wrong in checking time map, fail
        return {TIME_MAP_FAILURE, status};
    }
    auto time_index = time_map.indices(summary);

    // The actual loading internalizing - from ecl_sum -> enkf_node.
    // step2 is just taken from the number of steps found in the
    // summary file.
    const int step2 = ecl_sum_get_last_report_step(summary);

    time_index[0] = -1; // don't load 0th index
    time_index.resize(step2 + 1, -1);

    const ecl_smspec_type *smspec = ecl_sum_get_smspec(summary);

    for (int i = 0; i < ecl_smspec_num_nodes(smspec); i++) {
        const ecl::smspec_node &smspec_node =
            ecl_smspec_iget_node_w_node_index(smspec, i);
        const char *key = smspec_node.get_gen_key1();

        if (summary_key_matcher_match_summary_key(matcher, key)) {
            summary_key_set_type *key_set = enkf_fs_get_summary_key_set(sim_fs);
            summary_key_set_add_summary_key(key_set, key);

            enkf_config_node_type *config_node =
                ensemble_config_get_or_create_summary_node(ens_config, key);
            enkf_node_type *node = enkf_node_alloc(config_node);

            // Ensure that what is currently on file is loaded
            // before we update.
            enkf_node_try_load_vector(node, sim_fs, iens);

            summary_forward_load_vector(
                static_cast<summary_type *>(enkf_node_value_ptr(node)), summary,
                time_index);
            enkf_node_store_vector(node, sim_fs, iens);
            enkf_node_free(node);
        }
    }

    // Check if some of the specified keys are missing from the Eclipse
    // data, and if there are observations for them. That is a problem.
    return enkf_state_check_for_missing_eclipse_summary_data(
        ens_config, matcher, smspec, iens);
    return {LOAD_SUCCESSFUL, ""};
}

static fw_load_status enkf_state_load_gen_data_node(
    const std::string run_path, enkf_fs_type *sim_fs, int iens,
    const enkf_config_node_type *config_node, size_t start, size_t stop) {
    fw_load_status status = LOAD_SUCCESSFUL;
    for (int report_step = start; report_step <= stop; report_step++) {

        bool should_internalize = false;

        if (config_node->internalize != NULL)
            should_internalize =
                bool_vector_safe_iget(config_node->internalize, report_step);

        if (!should_internalize)
            continue;

        enkf_node_type *node = enkf_node_alloc(config_node);

        if (enkf_node_forward_load(node, report_step, run_path, sim_fs)) {
            node_id_type node_id = {.report_step = report_step, .iens = iens};

            enkf_node_store(node, sim_fs, node_id);
            logger->info("Loaded GEN_DATA: {} instance for step: {} from file: "
                         "{} size: {}",
                         enkf_node_get_key(node), report_step,
                         enkf_config_node_alloc_infile(
                             enkf_node_get_config(node), report_step),
                         gen_data_get_size(
                             (const gen_data_type *)enkf_node_value_ptr(node)));
        } else {
            logger->error(
                "[{:03d}:{:04d}] Failed load data for GEN_DATA node:{}.", iens,
                report_step, enkf_node_get_key(node));
            status = LOAD_FAILURE;
        }
        enkf_node_free(node);
    }
    return status;
}

static fw_load_status enkf_state_internalize_GEN_DATA(
    const ensemble_config_type *ens_config, const int iens,
    enkf_fs_type *sim_fs, const std::string run_path, size_t num_reports) {

    stringlist_type *keylist_GEN_DATA =
        ensemble_config_alloc_keylist_from_impl_type(ens_config, GEN_DATA);

    int numkeys = stringlist_get_size(keylist_GEN_DATA);

    if (numkeys > 0)
        if (num_reports != 0)
            logger->warning(
                "Trying to load GEN_DATA without properly "
                "set num_reports (was {}) - will only look for step 0 data: {}",
                num_reports, stringlist_iget(keylist_GEN_DATA, 0));

    fw_load_status result = LOAD_SUCCESSFUL;
    for (int ikey = 0; ikey < numkeys; ikey++) {
        const enkf_config_node_type *config_node = ensemble_config_get_node(
            ens_config, stringlist_iget(keylist_GEN_DATA, ikey));

        // This for loop should probably be changed to use the report
        // steps configured in the gen_data_config object, instead of
        // spinning through them all.
        size_t start = 0;
        size_t stop = num_reports;
        auto status = enkf_state_load_gen_data_node(run_path, sim_fs, iens,
                                                    config_node, start, stop);
        if (status == LOAD_FAILURE)
            result = LOAD_FAILURE;
    }
    stringlist_free(keylist_GEN_DATA);
    return result;
}

/**
   This function loads the results from a forward simulations from report_step1
   to report_step2. The details of what to load are in model_config and the
   spesific nodes for special cases.

   Will mainly be called at the end of the forward model, but can also
   be called manually from external scope.
*/
static std::pair<fw_load_status, std::string>
enkf_state_internalize_results(ensemble_config_type *ens_config,
                               size_t num_steps, const std::string &job_name,
                               const int iens, const std::string &run_path,
                               enkf_fs_type *sim_fs) {
    const summary_key_matcher_type *matcher = ens_config->summary_key_matcher;

    bool have_summary = false;
    for (const auto &config_pair : ens_config->config_nodes) {
        if (SUMMARY == enkf_config_node_get_impl_type(config_pair.second))
            have_summary = true;
    }

    if (summary_key_matcher_get_size(matcher) > 0 || have_summary) {
        // We are expecting there to be summary data
        // The timing information - i.e. mainly what is the last report step
        // in these results are inferred from the loading of summary results,
        // hence we must load the summary results first.
        try {
            auto summary = load_ecl_sum(run_path, job_name);
            auto status = enkf_state_internalize_dynamic_eclipse_results(
                ens_config, summary, matcher, sim_fs, iens);
            ecl_sum_free(summary);
            if (status.first != LOAD_SUCCESSFUL) {
                return {status.first,
                        status.second + fmt::format(" from: {}/{}.UNSMRY",
                                                    run_path, job_name)};
            }
        } catch (std::invalid_argument const &ex) {
            return {LOAD_FAILURE, ex.what() + fmt::format(" from: {}/{}.UNSMRY",
                                                          run_path, job_name)};
        }
    }

    size_t num_reports = enkf_fs_get_time_map(sim_fs).size();
    if (num_reports == 0)
        num_reports = num_steps;
    auto result = enkf_state_internalize_GEN_DATA(ens_config, iens, sim_fs,
                                                  run_path, num_reports);
    if (result == LOAD_FAILURE)
        return {LOAD_FAILURE, "Failed to internalize GEN_DATA"};
    return {LOAD_SUCCESSFUL, "Results loaded successfully."};
}

std::pair<fw_load_status, std::string> enkf_state_load_from_forward_model(
    ensemble_config_type *ens_config, int last_history_restart, const int iens,
    const std::string &run_path, const std::string &job_name,
    enkf_fs_type *sim_fs) {
    std::pair<fw_load_status, std::string> result;

    bool have_forward_init = false;

    for (auto const &[node_key, enkf_config_node] : ens_config->config_nodes) {
        if (enkf_config_node_use_forward_init(enkf_config_node))
            have_forward_init = true;
    }

    if (have_forward_init)
        result =
            ensemble_config_forward_init(ens_config, iens, run_path, sim_fs);
    if (result.first == LOAD_SUCCESSFUL) {
        result = enkf_state_internalize_results(
            ens_config, last_history_restart, job_name, iens, run_path, sim_fs);
    }
    auto &state_map = enkf_fs_get_state_map(sim_fs);
    if (result.first != LOAD_SUCCESSFUL)
        state_map.set(iens, STATE_LOAD_FAILURE);
    else
        state_map.set(iens, STATE_HAS_DATA);

    return result;
}

ERT_CLIB_SUBMODULE("enkf_state", m) {
    m.def("state_initialize", [](Cwrap<enkf_node_type> param_node,
                                 Cwrap<enkf_fs_type> fs, int iens) {
        node_id_type node_id = {.report_step = 0, .iens = iens};
        if (enkf_node_initialize(param_node, iens))
            enkf_node_store(param_node, fs, node_id);

        return;
    });

    m.def("internalize_results",
          [](Cwrap<ensemble_config_type> ens_config, size_t num_steps,
             const std::string &job_name, const int iens,
             const std::string &run_path, Cwrap<enkf_fs_type> sim_fs) {
              return enkf_state_internalize_results(
                  ens_config, num_steps, job_name, iens, run_path, sim_fs);
          });
}
