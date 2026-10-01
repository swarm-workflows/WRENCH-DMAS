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
};

class CentralizedSchedulingPolicy {
  std::string python_script_name_;

public:
  explicit CentralizedSchedulingPolicy(const std::string& python_script_name) : python_script_name_(python_script_name)
  {
  }

  // Select the best system for a job by running the bidder script once per system in
  // parallel — mirroring exactly what the decentralized agents do — and returning the
  // winner together with the wall-clock duration of the parallel execution (which becomes
  // the simulated DecisionTime for this job).
  CentralizedSchedulingDecision
  select_best_system(const std::shared_ptr<JobDescription>& job_description,
                     const std::vector<HPCSystemInfo>& systems_info)
  {
    if (systems_info.empty())
      return {nullptr, 0.0, ""};

    if (access(python_script_name_.c_str(), F_OK) != 0)
      throw std::runtime_error("Python script not found: " + python_script_name_);

    int N = static_cast<int>(systems_info.size());

    // Per-subprocess file descriptors and pids
    std::vector<int>    read_fds(N, -1);
    std::vector<pid_t>  pids(N, -1);

    auto wall_start = std::chrono::steady_clock::now();

    // Fork one process per system and send each its individual input
    for (int i = 0; i < N; i++) {
      int to_child[2], from_child[2];
      if (pipe(to_child) == -1 || pipe(from_child) == -1)
        throw std::runtime_error("Failed to create pipes");

      pids[i] = fork();
      if (pids[i] == 0) {
        dup2(to_child[0], STDIN_FILENO);
        dup2(from_child[1], STDOUT_FILENO);
        close(to_child[0]); close(to_child[1]);
        close(from_child[0]); close(from_child[1]);
        execlp("python3", "python3", python_script_name_.c_str(), nullptr);
        perror("execlp failed");
        exit(1);
      }
      // Parent: close child-side ends, write input, close write end
      close(to_child[0]);
      close(from_child[1]);

      nlohmann::json j;
      j["job_description"]        = job_description->to_json();
      j["hpc_system_description"] = systems_info[i].description->to_json();
      j["hpc_system_status"]      = systems_info[i].status->to_json();
      j["current_simulated_time"] = wrench::S4U_Simulation::getClock();
      std::string input = j.dump();
      write(to_child[1], input.c_str(), input.size());
      close(to_child[1]); // signal EOF so the child can start computing

      read_fds[i] = from_child[0];
    }

    // Collect all responses (children are running in parallel).
    // Use the Python-reported bid_generation_time_seconds — consistent with the decentralized
    // path which also uses that field — rather than C++ wall-clock time which includes Python
    // interpreter startup overhead (~100 ms) and would distort the simulation clock.
    std::map<std::shared_ptr<wrench::JobSchedulingAgent>, std::pair<double, double>> all_bids;
    constexpr uint64_t SEED  = 42;
    auto job_id_val           = static_cast<uint64_t>(job_description->get_job_id());
    double decision_time      = 0.0; // max(bid_generation_time_seconds) across all systems

    for (int i = 0; i < N; i++) {
      std::string response;
      char buffer[256];
      ssize_t count;
      while ((count = read(read_fds[i], buffer, sizeof(buffer) - 1)) > 0) {
        buffer[count] = '\0';
        response += buffer;
      }
      close(read_fds[i]);
      waitpid(pids[i], nullptr, 0);

      double bid = 0.0;
      try {
        nlohmann::json result = nlohmann::json::parse(response);
        XBT_CVERB(swarm_dmas, "Centralized bid from %s: %s",
                  systems_info[i].description->get_name().c_str(), result.dump().c_str());
        if (result.contains("bid") && result["bid"].is_number())
          bid = result["bid"].get<double>();
        if (result.contains("bid_generation_time_seconds") && result["bid_generation_time_seconds"].is_number())
          decision_time = std::max(decision_time, result["bid_generation_time_seconds"].get<double>());
      } catch (...) { /* treat parse error as bid = 0, no update to decision_time */ }

      const auto& sys_name   = systems_info[i].description->get_name();
      uint64_t mixed         = SEED ^ (job_id_val * 6364136223846793005ULL)
                                    ^ std::hash<std::string>{}(sys_name);
      std::mt19937_64 rng(mixed);
      std::uniform_real_distribution<double> dist(0.0, 100.0);
      double tie_breaker = dist(rng);
      all_bids[systems_info[i].agent] = {bid, tie_breaker};
    }

    (void)wall_start; // kept in case wall-clock measurement is needed in future
    auto bids = get_all_bids_as_string(all_bids);

    // Same comparator as PythonBiddingSchedulingPolicy::determine_bid_winner
    auto max_it = std::max_element(all_bids.begin(), all_bids.end(),
                                   [](const auto& a, const auto& b) { return a.second < b.second; });

    if (max_it->second.first <= 0.0)
      return {nullptr, decision_time, bids};

    return {max_it->first, decision_time, bids};
  }
};

#endif // CENTRALIZED_SCHEDULING_POLICY_H
