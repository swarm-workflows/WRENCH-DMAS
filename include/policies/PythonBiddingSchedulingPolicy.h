#ifndef PYTHON_BIDDING_SCHEDULING_POLICY_H
#define PYTHON_BIDDING_SCHEDULING_POLICY_H

#include <algorithm>
#include <iostream>
#include <memory>
#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>
#include <sys/wait.h>
#include <unistd.h>
#include <xbt/log.h>

#include "agents/JobSchedulingAgent.h"
#include "messages/ControlMessages.h"
#include "policies/SchedulingPolicy.h"

XBT_LOG_EXTERNAL_CATEGORY(swarm_dmas);

class PythonBiddingSchedulingPolicy : public SchedulingPolicy {
  std::string python_script_name_;

public:
  PythonBiddingSchedulingPolicy(const std::string& python_script_name)
      : SchedulingPolicy(), python_script_name_(python_script_name)
  {
  }

  void broadcast_job_description(const std::string& agent_name,
                                 const std::shared_ptr<JobDescription>& job_description) override
  {
    // The broadcast is only called upon initial submission, we thus init the number of received bids only once.
    init_num_received_bids(job_description->get_job_id());
    for (const auto& other_agent : get_job_scheduling_agent_network())
      if (agent_name != other_agent->getName())
        other_agent->commport->dputMessage(new wrench::JobRequestMessage(job_description, false));
  }

  std::pair<double, double> compute_bid(const std::shared_ptr<JobDescription>& job_description,
                                        const std::shared_ptr<HPCSystemDescription>& hpc_system_description,
                                        const std::shared_ptr<HPCSystemStatus>& hpc_system_status) override
  {
    int to_python[2];   // C++ writes to python
    int from_python[2]; // C++ reads from python

    if (pipe(to_python) == -1 || pipe(from_python) == -1) {
      throw std::runtime_error("Failed to create pipes");
    }

    if (access(python_script_name_.c_str(), F_OK) != 0)
      throw std::runtime_error("Python script not found");

    pid_t pid = fork();
    if (pid == 0) {
      // External Python process
      dup2(to_python[0], STDIN_FILENO);    // Read from C++
      dup2(from_python[1], STDOUT_FILENO); // Write to C++

      close(to_python[1]);
      close(from_python[0]);
      close(to_python[0]);
      close(from_python[1]);

      execlp("python3", "python3", python_script_name_.c_str(), nullptr);
      perror("execlp failed");
      exit(1);
    } else {
      // C++ process
      close(to_python[0]);
      close(from_python[1]);

      // Serialize input objects to JSON
      nlohmann::json j;
      j["job_description"]        = job_description->to_json();
      j["hpc_system_description"] = hpc_system_description->to_json();
      j["hpc_system_status"]      = hpc_system_status->to_json();
      j["current_simulated_time"] = wrench::S4U_Simulation::getClock();

      std::string jsonStr = j.dump();
      write(to_python[1], jsonStr.c_str(), jsonStr.size());
      close(to_python[1]); // Signal EOF to python

      // Read response from python
      std::string response;
      char buffer[256];
      ssize_t count;
      while ((count = read(from_python[0], buffer, sizeof(buffer) - 1)) > 0) {
        buffer[count] = '\0';
        response += buffer;
      }
      close(from_python[0]);
      waitpid(pid, nullptr, 0);

      try {
        nlohmann::json result = nlohmann::json::parse(response);
        XBT_CVERB(swarm_dmas, "%s", result.dump().c_str());
        if (not result.contains("bid_generation_time_seconds") || not result["bid_generation_time_seconds"].is_number())
          throw std::runtime_error("Invalid response: 'bid_generation_time_seconds' not found or not a number");
        if (result.contains("bid") && result["bid"].is_number()) {
          return std::make_pair(result["bid"].get<double>(), result["bid_generation_time_seconds"].get<double>());
        } else {
          throw std::runtime_error("Invalid response: 'bid' not found or not a number");
        }
      } catch (const std::exception& e) {
        throw std::runtime_error(std::string("Failed to parse response: ") + e.what());
      }
    }
  }

  void broadcast_bid_on_job(const std::shared_ptr<wrench::S4U_Daemon>& bidder,
                            const std::shared_ptr<JobDescription>& job_description, double bid, double tie_breaker)
  {
    // Set the number of needed bids to the size of the network of job scheduling agents
    set_num_needed_bids(get_job_scheduling_agent_network_size());
    for (const auto& other_agent : get_job_scheduling_agent_network())
      other_agent->commport->dputMessage(new wrench::BidOnJobMessage(bidder, job_description, bid, tie_breaker));
  }

  std::shared_ptr<wrench::JobSchedulingAgent> determine_bid_winner(
      const std::map<std::shared_ptr<wrench::JobSchedulingAgent>, std::pair<double, double>>& all_bids) const override
  {
    if (all_bids.empty())
      return nullptr;

    auto max_it = std::max_element(all_bids.begin(), all_bids.end(), [](const auto& a, const auto& b) {
      if (a.second != b.second)
        return a.second < b.second; // higher value wins
      else
        return a.first < b.first; // tie-breaker: lower pointer address wins
    });

    return max_it->first;
  }
};
#endif // PYTHON_BIDDING_SCHEDULING_POLICY_H
