#ifndef RANDOM_BIDDING_SCHEDULING_POLICY_H
#define RANDOM_BIDDING_SCHEDULING_POLICY_H

#include <algorithm>

#include "agents/JobSchedulingAgent.h"
#include "messages/ControlMessages.h"
#include "policies/SchedulingPolicy.h"

class RandomBiddingSchedulingPolicy : public SchedulingPolicy {

public:
  void broadcast_job_description(const std::string& agent_name,
                                 const std::shared_ptr<JobDescription>& job_description) override
  {
    // The broadcast is only called upon initial submission, we thus init the number of received bids only once.
    init_num_received_bids(job_description->get_job_id());
    for (const auto& other_agent : get_job_scheduling_agent_network())
      if (agent_name != other_agent->getName())
        other_agent->commport->dputMessage(new wrench::JobRequestMessage(job_description, false));
  }

  std::pair<double, double> compute_bid(const std::shared_ptr<JobDescription>& /*job_description*/,
                                        const std::shared_ptr<HPCSystemDescription>& /*hpc_system_description*/,
                                        const std::shared_ptr<HPCSystemStatus>& /*hpc_system_status*/) override
  {

    std::random_device rd;  // Seed
    std::mt19937 gen(rd()); // Mersenne Twister engine
    std::uniform_real_distribution<double> dis(0.0, std::nextafter(1.0, 2.0));

    return std::make_pair(dis(gen), 0.0);
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
      // All bids contains a pair of double: the bid (first) and a tie_breaker (second)
      if (a.second.first != b.second.first)
        return a.second.first < b.second.first; // higher value wins
      else if (a.second.second != b.second.second)
        return a.second.second < b.second.second; // tie-breaker: higher value wins
      else
        return a.first < b.first; // safety tie-breaker: lower pointer address wins
    });

    return max_it->first;
  }
};
#endif // RANDOM_BIDDING_SCHEDULING_POLICY_H
