#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>

#include "agents/JobSchedulingAgent.h"
#include "info/HPCSystemDescription.h"
#include "info/JobDescription.h"
#include "info/JobLifecycle.h"
#include "utils/utils.h"

using json = nlohmann::json;

template <typename T>
std::shared_ptr<std::vector<std::shared_ptr<T>>>
load_objects_from_json(const std::string& filename,
                       const std::function<std::shared_ptr<T>(const nlohmann::json&)>& constructor)
{
  auto result = std::make_shared<std::vector<std::shared_ptr<T>>>();
  std::ifstream file(filename);

  if (!file.is_open()) {
    std::cerr << "Failed to open file: " << filename << std::endl;
    return result;
  }

  nlohmann::json j;
  file >> j;

  for (const auto& item : j)
    result->push_back(constructor(item));

  return result;
}

std::shared_ptr<std::vector<std::shared_ptr<JobDescription>>> extract_job_descriptions(const std::string& filename)
{
  return load_objects_from_json<JobDescription>(filename, [](const nlohmann::json& item) {
    return std::make_shared<JobDescription>(
        item.at("JobID").get<int>(), item.at("UserID").get<int>(), item.at("GroupID").get<int>(),
        JobDescription::string_to_job_type(item.at("JobType").get<std::string>()),
        item.at("SubmissionTime").get<double>(), item.at("Walltime").get<sg_size_t>(), item.at("Nodes").get<size_t>(),
        item.at("RequestedGPU").get<bool>(), item.at("MemoryGB").get<double>(),
        item.at("RequestedStorageGB").get<double>(), item.at("HPCSite").get<std::string>(),
        item.at("HPCSystem").get<std::string>());
  });
}

std::shared_ptr<std::vector<std::shared_ptr<JobLifecycle>>> create_job_lifecycles(const std::string& filename)
{
  return load_objects_from_json<JobLifecycle>(filename, [](const nlohmann::json& item) {
    return std::make_shared<JobLifecycle>(item.at("JobID").get<int>(), item.at("HPCSystem").get<std::string>(),
                                          item.at("SubmissionTime").get<double>());
  });
}

size_t get_number_of_available_nodes_on(const std::shared_ptr<wrench::BatchComputeService>& batch)
{
  size_t total_number_of_available_nodes = 0;
  auto num_idle_core_map                 = batch->getPerHostNumIdleCores(false);
  // all nodes/hosts are declare as having only 1 core. Simple sum will do
  for (auto const& [host, idle_cores] : num_idle_core_map)
    total_number_of_available_nodes += idle_cores;
  return total_number_of_available_nodes;
}

double get_job_start_time_estimate_on(const std::shared_ptr<JobDescription>& job_description,
                                      const std::shared_ptr<wrench::BatchComputeService>& batch)
{
  // Fake a Wrench job to get an estimate of the job starting time on that batch compute service
  std::tuple<std::string, unsigned long, unsigned long, sg_size_t> wrench_job_description = {
      std::to_string(job_description->get_job_id()), job_description->get_num_nodes(), 1 /*num_cores*/,
      job_description->get_walltime()};
  auto current_job_start_time_estimate = batch->getStartTimeEstimates({wrench_job_description});
  return current_job_start_time_estimate.begin()->second;
}

size_t get_queue_length(const std::shared_ptr<wrench::BatchComputeService>& batch)
{
  return batch->getQueue().size();
}

int do_not_pass_acceptance_tests(const std::shared_ptr<JobDescription>& job_description,
                                 const std::shared_ptr<HPCSystemDescription>& hpc_system_description)
{
  int do_pass = 0;
  if (job_description->needs_gpu() && not hpc_system_description->has_gpu())
    do_pass = 1;

  if (job_description->get_num_nodes() > hpc_system_description->get_num_nodes())
    do_pass = 2;

  if (job_description->get_requested_memory_gb() >
      (hpc_system_description->get_num_nodes() * hpc_system_description->get_memory_amount_in_gb()))
    do_pass = 3;

  // TODO add test for storage

  return do_pass;
}

std::string get_failure_cause_as_string(int failure_code)
{
  switch (failure_code) {
    case 1:
      return "Job requires GPU while System has none";
      break;
    case 2:
      return "Job requires more nodes than the System has";
      break;
    case 3:
      return "Job requires more nodes than the System has";
      break;
    default:
      return "Unknown failure code";
  }
}

std::string
get_all_bids_as_string(const std::map<std::shared_ptr<wrench::JobSchedulingAgent>, std::pair<double, double>>& all_bids)
{
  std::ostringstream oss;
  oss << std::fixed << std::setprecision(2) << "\"";
  for (auto it = all_bids.begin(); it != all_bids.end(); ++it) {
    oss << it->second.first;
    if (std::next(it) != all_bids.end())
      oss << ":";
  }
  oss << "\"";
  return oss.str();
}
