#ifndef ERT_OBS_VECTOR_H
#define ERT_OBS_VECTOR_H

#include <time.h>
#include <vector>

#include <ert/util/bool_vector.h>
#include <ert/util/int_vector.h>

#include <ert/config/conf.hpp>

#include <ert/ecl/ecl_sum.h>

#include <ert/enkf/enkf_fs.hpp>
#include <ert/enkf/enkf_macros.hpp>
#include <ert/enkf/enkf_node.hpp>
#include <ert/enkf/enkf_types.hpp>
#include <ert/enkf/ensemble_config.hpp>
#include <ert/enkf/obs_data.hpp>
#include <ert/enkf/time_map.hpp>

enum history_source_type {
    REFCASE_SIMULATED = 1, /** ecl_sum_get_well_var( "WWCT" );  */
    REFCASE_HISTORY = 2,   /** ecl_sum_get_well_var( "WWCTH" ); */
};

typedef enum { GEN_OBS = 1, SUMMARY_OBS = 2 } obs_impl_type;

typedef struct obs_vector_struct obs_vector_type;

void obs_vector_measure(const obs_vector_type *, enkf_fs_type *fs,
                        int report_step,
                        const std::vector<int> &ens_active_list,
                        meas_data_type *);

typedef void(obs_free_ftype)(void *);
typedef void(obs_get_ftype)(void *, obs_data_type *, enkf_fs_type *, int);
typedef void(obs_meas_ftype)(const void *, const void *, node_id_type,
                             meas_data_type *);
typedef void(obs_user_get_ftype)(void *, const char *, double *, double *,
                                 bool *);
typedef void(obs_update_std_scale_ftype)(void *, double, const ActiveList *);
typedef double(obs_chi2_ftype)(const void *, const void *, node_id_type);

extern "C" void obs_vector_free(obs_vector_type *);
extern "C" int obs_vector_get_num_active(const obs_vector_type *);
extern "C" bool obs_vector_iget_active(const obs_vector_type *, int);
void obs_vector_iget_observations(const obs_vector_type *, int, obs_data_type *,
                                  enkf_fs_type *fs);
extern "C" bool obs_vector_has_data(const obs_vector_type *obs_vector,
                                    const bool_vector_type *active_mask,
                                    enkf_fs_type *fs);
void obs_vector_measure(const obs_vector_type *, enkf_fs_type *fs,
                        int report_step, const int_vector_type *ens_active_list,
                        meas_data_type *);
extern "C" const char *obs_vector_get_state_kw(const obs_vector_type *);
extern "C" const char *obs_vector_get_key(const obs_vector_type *);
extern "C" obs_impl_type obs_vector_get_impl_type(const obs_vector_type *);
const std::vector<int> &obs_vector_get_step_list(const obs_vector_type *vector);
void obs_vector_user_get(const obs_vector_type *obs_vector,
                         const char *index_key, int report_step, double *value,
                         double *std, bool *valid);
extern "C" int obs_vector_get_next_active_step(const obs_vector_type *, int);
extern "C" void *obs_vector_iget_node(const obs_vector_type *, int);
obs_vector_type *
obs_vector_alloc_from_GENERAL_OBSERVATION(const conf_instance_type *,
                                          const std::vector<time_t> &obs_time,
                                          enkf_config_node_type *);
void obs_vector_load_from_SUMMARY_OBSERVATION(
    obs_vector_type *obs_vector, const conf_instance_type *,
    const std::vector<time_t> &obs_time, ensemble_config_type *);
bool obs_vector_load_from_HISTORY_OBSERVATION(
    obs_vector_type *obs_vector, const conf_instance_type *,
    const std::vector<time_t> &obs_time, const history_source_type history,
    double std_cutoff, const ecl_sum_type *);
extern "C" obs_vector_type *obs_vector_alloc(obs_impl_type obs_type,
                                             const char *obs_key,
                                             enkf_config_node_type *config_node,
                                             size_t num_reports);

extern "C" void obs_vector_install_node(obs_vector_type *obs_vector,
                                        int obs_index, void *node);

void obs_vector_ensemble_chi2(const obs_vector_type *obs_vector,
                              enkf_fs_type *fs, bool_vector_type *valid,
                              int step1, int step2, int iens1, int iens2,
                              double **chi2);

extern "C" double obs_vector_total_chi2(const obs_vector_type *, enkf_fs_type *,
                                        int);
extern "C" enkf_config_node_type *
obs_vector_get_config_node(const obs_vector_type *);
extern "C" const char *
obs_vector_get_obs_key(const obs_vector_type *obs_vector);

VOID_FREE_HEADER(obs_vector);

#endif
