#include "policies/PureLocalSchedulingPolicy.h"
#include "policies/PythonBiddingSchedulingPolicy.h"
#include "policies/RandomBiddingSchedulingPolicy.h"

#include <stdexcept>

std::shared_ptr<SchedulingPolicy> SchedulingPolicy::create_scheduling_policy(const std::string& policy_name,
                                                                             const std::string& python_script_name)
{
  if (policy_name == "PureLocal")
    return std::make_shared<PureLocalSchedulingPolicy>();
  else if (policy_name == "RandomBidding")
    return std::make_shared<RandomBiddingSchedulingPolicy>();
  else if (policy_name == "PythonBidding") {
    if (not python_script_name.empty())
      return std::make_shared<PythonBiddingSchedulingPolicy>(python_script_name);
    else
      throw std::runtime_error("Python script needed");
  } else
    throw std::invalid_argument("Unknown scheduling policy: " + policy_name);
}

void SchedulingPolicy::init_num_received_bids(int job_id)
{
  for (const auto& agent : healthy_job_scheduling_agent_network_)
    num_received_bids_[job_id].try_emplace(agent->getName(), 0);
}

void SchedulingPolicy::mark_agent_as_failed(std::shared_ptr<wrench::JobSchedulingAgent> agent)
{
  healthy_job_scheduling_agent_network_.erase(
      std::remove(healthy_job_scheduling_agent_network_.begin(), healthy_job_scheduling_agent_network_.end(), agent),
      healthy_job_scheduling_agent_network_.end());
  failed_job_scheduling_agent_network_.push_back(agent);
}
