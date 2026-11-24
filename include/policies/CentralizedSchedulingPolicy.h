#ifndef CENTRALIZED_SCHEDULING_POLICY_H
#define CENTRALIZED_SCHEDULING_POLICY_H

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <nlohmann/json.hpp>
#include <random>
#include <stdexcept>
#include <string>
#include <sys/wait.h>
#include <unistd.h>
#include <utility>
#include <vector>
#include <wrench.h>
#include <xbt/log.h>

#include "agents/JobSchedulingAgent.h"
#include "info/HPCSystemDescription.h"
#include "info/HPCSystemStatus.h"
#include "info/JobDescription.h"
#include "utils/PythonRunner.h"
#include "utils/utils.h"

XBT_LOG_EXTERNAL_CATEGORY(swarm_dmas);

// Structure to hold system info for centralized decision making
struct HPCSystemInfo {
  std::shared_ptr<wrench::JobSchedulingAgent> agent;
  std::shared_ptr<HPCSystemDescription> description;
  std::shared_ptr<HPCSystemStatus> status;
};

struct CentralizedSchedulingDecision {
  std::shared_ptr<wrench::JobSchedulingAgent> target_agent;
  double decision_time;
  std::string bids;
  size_t num_top_bids; // number of systems sharing the highest bid
};

class CentralizedSchedulingPolicy {
  std::string python_script_name_;
  std::string bidder_prompt_;
  double runtime_fraction_lower_bound_;
  // CEN keeps one persistent worker per system, so that each system reuses its own bidder process (and LLM client).
  std::map<std::string, std::unique_ptr<PersistentPythonWorker>> python_workers_;
  // Bids requested from the bidders, and those that failed (no response or no valid bid, counted as 0)
  size_t num_requested_bids_ = 0;
  size_t num_failed_bids_    = 0;

  PersistentPythonWorker& worker_for_system(const std::string& system_name)
  {
    auto& worker = python_workers_[system_name];
    if (!worker)
      worker = std::make_unique<PersistentPythonWorker>(python_script_name_);
    return *worker;
  }

public:
  CentralizedSchedulingPolicy(const std::string& python_script_name, const std::string& bidder_prompt_file,
                              double runtime_fraction_lower_bound)
      : python_script_name_(python_script_name)
      , bidder_prompt_(load_bidder_prompt(bidder_prompt_file))
      , runtime_fraction_lower_bound_(runtime_fraction_lower_bound)
  {
  }

  size_t get_num_requested_bids() const { return num_requested_bids_; }
  size_t get_num_failed_bids() const { return num_failed_bids_; }

  // Select the best system for a job by collecting one bid from each system.
  CentralizedSchedulingDecision
  select_best_system(const std::shared_ptr<JobDescription>& job_description,
                     const std::vector<HPCSystemInfo>& systems_info)
  {
    if (systems_info.empty())
      return {nullptr, 0.0, ""};

    if (access(python_script_name_.c_str(), F_OK) != 0)
      throw std::runtime_error("Python script not found: " + python_script_name_);

    const int N = static_cast<int>(systems_info.size());
    std::vector<std::string> responses(N);
    std::vector<std::string> failures(N); // why no response was obtained from a system's worker, if so

    std::vector<PersistentPythonWorker*> workers(N, nullptr);

    // One persistent worker per system. Send to every system before waiting, so that bids are computed in parallel.
    for (int i = 0; i < N; i++) {
      auto input = build_bidder_input(job_description, systems_info[i].description, systems_info[i].status,
                                      runtime_fraction_lower_bound_, bidder_prompt_);
      try {
        workers[i] = &worker_for_system(systems_info[i].description->get_name());
        workers[i]->send_request(input);
      } catch (const std::exception& e) {
        workers[i]  = nullptr;
        failures[i] = e.what();
      }
    }

    for (int i = 0; i < N; i++) {
      if (workers[i] == nullptr)
        continue;
      try {
        responses[i] = workers[i]->read_response().dump();
      } catch (const std::exception& e) {
        responses[i].clear();
        failures[i] = e.what();
      }
    }

    // Use the Python-reported bid time, excluding interpreter startup from simulated decision time.
    std::map<std::shared_ptr<wrench::JobSchedulingAgent>, std::pair<double, double>> all_bids;
    constexpr uint64_t SEED  = 42;
    auto job_id_val           = static_cast<uint64_t>(job_description->get_job_id());
    double decision_time      = 0.0; // max(bid_generation_time_seconds) across all systems

    for (int i = 0; i < N; i++) {
      const auto& sys_name = systems_info[i].description->get_name();
      // A system without a valid bid bids 0 (and does not update decision_time), but the failure is reported.
      double bid = 0.0;
      num_requested_bids_++;
      if (!failures[i].empty()) {
        num_failed_bids_++;
        XBT_CWARN(swarm_dmas, "Job #%d: no bid from the '%s' bidder (bid = 0): %s", job_description->get_job_id(),
                  sys_name.c_str(), failures[i].c_str());
      } else {
        try {
          nlohmann::json result = nlohmann::json::parse(responses[i]);
          XBT_CVERB(swarm_dmas, "Centralized bid from %s: %s", sys_name.c_str(), result.dump().c_str());
          record_bid_source(result, job_description->get_job_id(), sys_name);
          if (result.contains("bid") && result["bid"].is_number())
            bid = result["bid"].get<double>();
          else {
            num_failed_bids_++;
            XBT_CWARN(swarm_dmas, "Job #%d: invalid response from the '%s' bidder (bid = 0): %s",
                      job_description->get_job_id(), sys_name.c_str(), result.dump().c_str());
          }
          if (result.contains("bid_generation_time_seconds") && result["bid_generation_time_seconds"].is_number())
            decision_time = std::max(decision_time, result["bid_generation_time_seconds"].get<double>());
        } catch (const std::exception& e) {
          num_failed_bids_++;
          XBT_CWARN(swarm_dmas, "Job #%d: unparsable response from the '%s' bidder (bid = 0): %s",
                    job_description->get_job_id(), sys_name.c_str(), e.what());
        }
      }


      uint64_t mixed         = SEED ^ (job_id_val * 6364136223846793005ULL)
                                    ^ std::hash<std::string>{}(sys_name);
      std::mt19937_64 rng(mixed);
      std::uniform_real_distribution<double> dist(0.0, 100.0);
      double tie_breaker = dist(rng);
      all_bids[systems_info[i].agent] = {bid, tie_breaker};
    }

    auto bids         = get_all_bids_as_string(all_bids);
    auto num_top_bids = count_top_bids(all_bids);

    // Same comparator as PythonBiddingSchedulingPolicy::determine_bid_winner
    auto max_it = std::max_element(all_bids.begin(), all_bids.end(),
                                   [](const auto& a, const auto& b) { return a.second < b.second; });

    if (max_it->second.first <= 0.0)
      return {nullptr, decision_time, bids, num_top_bids};

    if (num_top_bids > 1)
      XBT_CINFO(swarm_dmas, "Job #%d: %zu systems share the highest bid, the tie-breaker placed it on '%s'",
                job_description->get_job_id(), num_top_bids, max_it->first->get_hpc_system_name().c_str());
    return {max_it->first, decision_time, bids, num_top_bids};
  }
};

#endif // CENTRALIZED_SCHEDULING_POLICY_H
