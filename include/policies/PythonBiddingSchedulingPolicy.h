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
#include "utils/PythonRunner.h"
#include "utils/utils.h"

XBT_LOG_EXTERNAL_CATEGORY(swarm_dmas);

class PythonBiddingSchedulingPolicy : public SchedulingPolicy {
  std::string python_script_name_;
  // This policy belongs to one machine agent, so its Python worker is reused across that agent's bids.
  PersistentPythonWorker python_worker_;
  std::string bidder_prompt_;
  double runtime_fraction_lower_bound_;

public:
  PythonBiddingSchedulingPolicy(const std::string& python_script_name, const std::string& bidder_prompt_file,
                                double runtime_fraction_lower_bound)
      : SchedulingPolicy()
      , python_script_name_(python_script_name)
      , python_worker_(python_script_name_)
      , bidder_prompt_(load_bidder_prompt(bidder_prompt_file))
      , runtime_fraction_lower_bound_(runtime_fraction_lower_bound)
  {
  }

  void broadcast_job_description(const std::string& agent_name,
                                 const std::shared_ptr<JobDescription>& job_description) override
  {
    // The broadcast is only called upon initial submission, we thus init the number of received bids only once.
    init_num_received_bids(job_description->get_job_id());
    for (const auto& other_agent : get_job_scheduling_agent_network())
      if (agent_name != other_agent->getName())
        other_agent->getCommPort()->dputMessage(new wrench::JobRequestMessage(job_description, false));
  }

  std::pair<double, double> compute_bid(const std::shared_ptr<JobDescription>& job_description,
                                        const std::shared_ptr<HPCSystemDescription>& hpc_system_description,
                                        const std::shared_ptr<HPCSystemStatus>& hpc_system_status) override
  {
    auto input = build_bidder_input(job_description, hpc_system_description, hpc_system_status,
                                    runtime_fraction_lower_bound_, bidder_prompt_);

    try {
      nlohmann::json result = python_worker_.request(input);
      XBT_CVERB(swarm_dmas, "%s", result.dump().c_str());
      record_bid_source(result, job_description->get_job_id(), hpc_system_description->get_name());
      if (not result.contains("bid_generation_time_seconds") || not result["bid_generation_time_seconds"].is_number())
        throw std::runtime_error("Invalid response: 'bid_generation_time_seconds' not found or not a number");
      if (result.contains("bid") && result["bid"].is_number()) {
        return std::make_pair(result["bid"].get<double>(), result["bid_generation_time_seconds"].get<double>());
      }
      throw std::runtime_error("Invalid response: 'bid' not found or not a number");
    } catch (const std::exception& e) {
      throw std::runtime_error(std::string("Python bidder failed: ") + e.what());
    }
  }

  void broadcast_bid_on_job(const std::shared_ptr<wrench::S4U_Daemon>& bidder,
                            const std::shared_ptr<JobDescription>& job_description, double bid, double tie_breaker)
  {
    // Set the number of needed bids to the size of the network of job scheduling agents
    set_num_needed_bids(get_job_scheduling_agent_network_size());
    for (const auto& other_agent : get_job_scheduling_agent_network())
      other_agent->getCommPort()->dputMessage(new wrench::BidOnJobMessage(bidder, job_description, bid, tie_breaker));
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
        return a.first < b.first; // tie-breaker: higher pointer address wins
    });

    return max_it->first;
  }
};
#endif // PYTHON_BIDDING_SCHEDULING_POLICY_H
