#ifndef UTILS_H
#define UTILS_H

#include <memory>
#include <nlohmann/json.hpp>
#include <vector>
#include <wrench-dev.h>

#include "info/HPCSystemDescription.h"
#include "info/HPCSystemStatus.h"
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
// Number of systems sharing the highest bid. When it is above 1, the tie-breaker decides the placement.
size_t count_top_bids(
    const std::map<std::shared_ptr<wrench::JobSchedulingAgent>, std::pair<double, double>>& all_bids);
// Content of the prompt file given to the LLM bidders ("" when there is no prompt file)
std::string load_bidder_prompt(const std::string& bidder_prompt_file);
// JSON input sent to a Python bidder for one job and one system, in both decentralized and centralized modes
nlohmann::json build_bidder_input(const std::shared_ptr<JobDescription>& job_description,
                                  const std::shared_ptr<HPCSystemDescription>& hpc_system_description,
                                  const std::shared_ptr<HPCSystemStatus>& hpc_system_status,
                                  double runtime_fraction_lower_bound, const std::string& bidder_prompt);

// Origin of the bids returned by the bidders that report it in a 'bid_source' field (the LLM bidders), counted over
// the whole run: bids produced by the LLM, and bids for which the bidder fell back to the heuristic.
struct BidSourceStats {
  size_t llm_bids      = 0;
  size_t fallback_bids = 0;
};
BidSourceStats& get_bid_source_stats();
void record_bid_source(const nlohmann::json& bidder_response, int job_id, const std::string& system_name);
size_t get_queue_length(const std::shared_ptr<wrench::BatchComputeService>& batch);

#endif // UTILS_H
