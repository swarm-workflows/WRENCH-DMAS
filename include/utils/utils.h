#ifndef UTILS_H
#define UTILS_H

#include <memory>
#include <vector>
#include <wrench-dev.h>

#include "info/HPCSystemDescription.h"
#include "info/JobDescription.h"
#include "info/JobLifecycle.h"

std::shared_ptr<std::vector<std::shared_ptr<JobDescription>>> extract_job_descriptions(const std::string& filename);
std::shared_ptr<std::vector<std::shared_ptr<JobLifecycle>>> create_job_lifecycles(const std::string& filename);

size_t get_number_of_available_nodes_on(const std::shared_ptr<wrench::BatchComputeService>& batch);
double get_job_start_time_estimate_on(const std::shared_ptr<JobDescription>& job_description,
                                      const std::shared_ptr<wrench::BatchComputeService>& batch);
int do_not_pass_acceptance_tests(const std::shared_ptr<JobDescription>& job_description,
                                 const std::shared_ptr<HPCSystemDescription>& hpc_system_description);
std::string get_failure_cause_as_string(int failure_code);
std::string get_all_bids_as_string(
    const std::map<std::shared_ptr<wrench::JobSchedulingAgent>, std::pair<double, double>>& all_bids);
size_t get_queue_length(const std::shared_ptr<wrench::BatchComputeService>& batch);

#endif // UTILS_H
